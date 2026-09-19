import json
import logging
import time
from typing import Any, Dict, List, Optional

from google.genai import types

from src.agents.planner.client import PlannerLLMClient
from src.agents.planner.ecosystem import detect_technology_ecosystem
from src.agents.planner.prompts.contract_prompts import (
    build_contract_system_instruction,
    build_contract_user_prompt,
)
from src.agents.planner_validators import validate_contract
from src.schemas.planner import (
    CandidateProfile,
    CodingExerciseContract,
    InterviewBlueprint,
    InterviewPlanCreate,
)

logger = logging.getLogger(__name__)


class ExerciseContractGenerator:
    """Generates rigorous, candidate-grounded CodingExerciseContracts adhering to the two-phase
    exercise generation architecture. Uses Gemini Flash with a dedicated thinking budget (reasoning-only).
    """

    def __init__(self, client: PlannerLLMClient):
        self.client = client

    def generate(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
        previous_contracts: Optional[List[str]] = None,
    ) -> Optional[CodingExerciseContract]:
        """Generates a CodingExerciseContract using Gemini Flash with dedicated thinking budget.
        Validates the contract against strict design rules (failure mechanism depth, architecture count).
        """
        if diagnostic_list is None:
            diagnostic_list = []

        contract: Optional[CodingExerciseContract] = None
        gemini_retries = 2
        logger.info("Generating coding exercise contract using Gemini Flash (Thinking Budget = %d)...", self.client.contract_thinking_budget)

        last_errors: List[str] = []
        for attempt in range(1, gemini_retries + 1):
            try:
                hint = (
                    f"PREVIOUS ATTEMPT VALIDATION WARNINGS (Must resolve): {'; '.join(last_errors)}"
                    if last_errors
                    else (f"Attempt #{attempt}" if attempt > 1 else "")
                )
                c = self.generate_gemini(
                    profile=profile,
                    job_spec=job_spec,
                    blueprint=blueprint,
                    retry_hint=hint,
                    diagnostic_list=diagnostic_list,
                    previous_contracts=previous_contracts,
                )
                if c:
                    is_valid, errors = validate_contract(c)
                    if is_valid:
                        contract = c
                        logger.info(
                            "[Contract Generator] Contract validated successfully: ID=%s, Domain='%s', Failure='%s'",
                            c.contract_id,
                            c.scenario.domain,
                            c.failure_mechanism.observable_symptom,
                        )
                        break
                    last_errors = errors
                    diagnostic_list.append({
                        "provider": "contract_validator",
                        "operation": "validate_contract",
                        "error_type": "DesignWarning",
                        "message": f"Contract attempt {attempt} validation warnings: {'; '.join(errors)}",
                    })
                    logger.warning("[Contract Generator] Attempt %d validation warnings: %s", attempt, errors)
            except Exception as fb_err:
                diagnostic_list.append({
                    "provider": "gemini",
                    "operation": "exercise_contract",
                    "error_type": type(fb_err).__name__,
                    "message": f"Contract generation attempt {attempt} error: {str(fb_err)}",
                })
                logger.error("[Contract Generator] Attempt %d failed: %s", attempt, fb_err)
            if attempt < gemini_retries:
                time.sleep(1.0)

        return contract

    def generate_gemini(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        retry_hint: str = "",
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
        previous_contracts: Optional[List[str]] = None,
    ) -> CodingExerciseContract:
        target_lang, target_ext, ecosystem = detect_technology_ecosystem(job_spec, profile)
        system_instruction = build_contract_system_instruction(target_lang, target_ext, ecosystem, include_json_schema=False)
        user_prompt = build_contract_user_prompt(
            profile=profile,
            job_spec=job_spec,
            blueprint=blueprint,
            target_lang=target_lang,
            target_ext=target_ext,
            ecosystem=ecosystem,
            retry_hint=retry_hint,
            schema_target="CodingExerciseContract",
            previous_contracts=previous_contracts,
        )

        gen_temp = 0.6 if previous_contracts else 0.4

        def _call():
            return self.client.gemini_client.models.generate_content(
                model=self.client.gemini_flash_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=CodingExerciseContract,
                    temperature=gen_temp,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=self.client.contract_thinking_budget
                    ),
                ),
            )

        try:
            resp = self.client.call_gemini_with_retry(_call, operation_name="Generate Exercise Contract (Gemini Flash)")
            if resp.parsed and isinstance(resp.parsed, CodingExerciseContract):
                return resp.parsed
            if resp.text:
                return CodingExerciseContract(**json.loads(resp.text))
            raise RuntimeError("Gemini Flash returned empty exercise contract.")
        except Exception as e:
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "gemini",
                    "operation": "exercise_contract",
                    "error_type": type(e).__name__,
                    "message": str(e),
                })
            raise
