import json
import logging
import time
from typing import Any, Dict, List, Optional

from google.genai import types
from openai import APIConnectionError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from src.agents.planner.client import PlannerLLMClient
from src.agents.planner.ecosystem import detect_technology_ecosystem
from src.agents.planner.prompts.coding_prompts import (
    build_coding_exercise_system_instruction,
    build_coding_exercise_user_prompt,
)
from src.agents.planner_validators import validate_codebase
from src.schemas.planner import (
    CandidateProfile,
    CodingExerciseAsset,
    InterviewBlueprint,
    InterviewPlanCreate,
)

logger = logging.getLogger(__name__)


class CodingExerciseGenerator:
    """Generates realistic multi-file engineering exercises adhering to the Monaco editor contract,
    strict anti-technology-soup rules, and scenario-first candidate prompts.
    """

    def __init__(self, client: PlannerLLMClient):
        self.client = client

    def generate(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
        previous_exercises: Optional[List[str]] = None,
    ) -> Optional[CodingExerciseAsset]:
        """Generates a coding exercise using Gemini Flash (Primary) with AST validation.
        Optionally falls back to Kimi AI if enabled.
        """
        if diagnostic_list is None:
            diagnostic_list = []

        exercise: Optional[CodingExerciseAsset] = None
        gemini_retries = 2
        logger.info("Generating coding exercise using Gemini Flash (Primary)...")

        last_gemini_errors: List[str] = []
        for g_attempt in range(1, gemini_retries + 1):
            try:
                hint = (
                    f"PREVIOUS ATTEMPT VALIDATION WARNINGS (Must resolve): {'; '.join(last_gemini_errors)}"
                    if last_gemini_errors
                    else (f"Attempt #{g_attempt}" if g_attempt > 1 else "")
                )
                ex = self.generate_gemini(
                    profile,
                    job_spec,
                    blueprint,
                    retry_hint=hint,
                    diagnostic_list=diagnostic_list,
                    previous_exercises=previous_exercises,
                )
                if ex:
                    is_valid, errors = validate_codebase(ex)
                    if is_valid:
                        exercise = ex
                        break
                    last_gemini_errors = errors
                    diagnostic_list.append({
                        "provider": "ast_validator",
                        "operation": "validate_codebase",
                        "error_type": "SyntaxWarning",
                        "message": f"Gemini attempt {g_attempt} AST warnings: {'; '.join(errors)}",
                    })
                    logger.warning(f"Gemini coding exercise validation warnings on attempt {g_attempt}: {errors}")
            except Exception as fb_err:
                diagnostic_list.append({
                    "provider": "gemini",
                    "operation": "coding_exercise",
                    "error_type": type(fb_err).__name__,
                    "message": f"Gemini attempt {g_attempt} error: {str(fb_err)}",
                })
                logger.error(f"Gemini coding exercise failed on attempt {g_attempt}: {fb_err}")
            if g_attempt < gemini_retries:
                time.sleep(1.0)

        if not exercise:
            if (
                self.client.enable_kimi_coding_fallback
                and self.client.kimi_client
                and self.client.moonshot_api_key
                and self.client.moonshot_api_key != "EMPTY_MOONSHOT_KEY"
            ):
                logger.info("Gemini Flash coding exercise failed or invalid. Falling back to Kimi AI (explicitly enabled)...")
                max_retries = self.client.kimi_max_retries
                last_kimi_errors: List[str] = []
                for attempt in range(1, max_retries + 1):
                    try:
                        hint = (
                            f"PREVIOUS ATTEMPT VALIDATION WARNINGS (Must resolve): {'; '.join(last_kimi_errors)}"
                            if last_kimi_errors
                            else f"Attempt #{attempt}"
                        )
                        ex = self.generate_kimi(
                            profile, job_spec, blueprint, retry_hint=hint, diagnostic_list=diagnostic_list
                        )
                        if ex:
                            is_valid, errors = validate_codebase(ex)
                            if is_valid:
                                exercise = ex
                                break
                            last_kimi_errors = errors
                            diagnostic_list.append({
                                "provider": "ast_validator",
                                "operation": "validate_codebase",
                                "error_type": "SyntaxWarning",
                                "message": f"Kimi fallback attempt {attempt} AST validation failed: {'; '.join(errors)}",
                            })
                            logger.warning(f"Kimi coding exercise fallback AST validation failed on attempt {attempt}: {errors}")
                    except Exception as e:
                        diagnostic_list.append({
                            "provider": "kimi",
                            "operation": "coding_exercise_fallback",
                            "error_type": type(e).__name__,
                            "message": f"Kimi fallback attempt {attempt} error: {str(e)}",
                        })
                        logger.warning(f"Kimi coding exercise fallback generation failed on attempt {attempt}: {e}")
                    if attempt < max_retries:
                        time.sleep(1.0)
            else:
                diagnostic_list.append({
                    "provider": "planner_policy",
                    "operation": "coding_exercise",
                    "error_type": "ControlledFallbackNotice",
                    "message": "Kimi fallback for coding exercise is disabled or unconfigured to prevent silent high costs.",
                })

        return exercise

    def generate_gemini(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        retry_hint: str = "",
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
        previous_exercises: Optional[List[str]] = None,
    ) -> CodingExerciseAsset:
        target_lang, target_ext, ecosystem = detect_technology_ecosystem(job_spec, profile)
        system_instruction = build_coding_exercise_system_instruction(target_lang, target_ext, ecosystem, include_json_schema=False)
        user_prompt = build_coding_exercise_user_prompt(
            profile,
            job_spec,
            blueprint,
            target_lang,
            target_ext,
            ecosystem,
            retry_hint=retry_hint,
            schema_target="CodingExerciseAsset",
            previous_exercises=previous_exercises,
        )

        gen_temp = 0.7 if previous_exercises else 0.4

        def _call():
            return self.client.gemini_client.models.generate_content(
                model=self.client.gemini_flash_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=CodingExerciseAsset,
                    temperature=gen_temp,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=self.client.thinking_budget
                    ),
                ),
            )

        try:
            resp = self.client.call_gemini_with_retry(_call, operation_name="Generate Coding Exercise (Gemini Flash)")
            if resp.parsed and isinstance(resp.parsed, CodingExerciseAsset):
                resp.parsed.technology_environment = ecosystem
                return resp.parsed
            if resp.text:
                ex = CodingExerciseAsset(**json.loads(resp.text))
                ex.technology_environment = ecosystem
                return ex
            raise RuntimeError("Gemini Flash returned empty coding exercise.")
        except Exception as e:
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "gemini",
                    "operation": "coding_exercise_fallback",
                    "error_type": type(e).__name__,
                    "message": str(e),
                })
            raise

    def generate_kimi(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        retry_hint: str = "",
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[CodingExerciseAsset]:
        if not self.client.moonshot_api_key or self.client.moonshot_api_key == "EMPTY_MOONSHOT_KEY" or not self.client.kimi_client:
            logger.warning("Moonshot API Key is missing or client not initialized.")
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "kimi",
                    "operation": "coding_exercise",
                    "error_type": "ConfigurationNotice",
                    "message": "Moonshot API key is unconfigured or empty in environment",
                })
            return None

        target_lang, target_ext, ecosystem = detect_technology_ecosystem(job_spec, profile)
        system_instruction = build_coding_exercise_system_instruction(target_lang, target_ext, ecosystem, include_json_schema=True)
        user_prompt = build_coding_exercise_user_prompt(
            profile, job_spec, blueprint, target_lang, target_ext, ecosystem, retry_hint=retry_hint, schema_target="JSON schema"
        )

        try:
            logger.info(f"Calling Kimi AI ({self.client.kimi_model}) for multi-file coding exercise generation...")
            with self.client._kimi_lock:
                completion = self.client.kimi_client.chat.completions.create(
                    model=self.client.kimi_model,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    extra_body={"thinking": {"type": "disabled"}},
                    timeout=self.client.kimi_timeout_seconds,
                )

            response_content = completion.choices[0].message.content
            if not response_content:
                raise ValueError("Kimi AI returned an empty response content.")

            data = json.loads(response_content)
            if isinstance(data, dict):
                for key in ("coding_exercise", "coding_exercise_asset", "CodingExerciseAsset", "exercise", "data"):
                    if key in data and isinstance(data[key], dict):
                        data = data[key]
                        break

            try:
                ex = CodingExerciseAsset(**data)
                ex.technology_environment = ecosystem
                return ex
            except ValidationError as val_err:
                logger.error(
                    f"Kimi AI schema validation error (Schema Drift Detected): {val_err.errors()}",
                    extra={"schema_errors": str(val_err.errors()), "raw_payload": response_content[:500]},
                )
                if diagnostic_list is not None:
                    diagnostic_list.append({
                        "provider": "kimi",
                        "operation": "coding_exercise",
                        "error_type": "ValidationError",
                        "message": f"Schema mismatch: {val_err.errors()}",
                    })
                return None

        except (RateLimitError, APIConnectionError, APITimeoutError) as net_err:
            logger.error(f"Network/Quota error calling Kimi AI ({self.client.kimi_model}) for coding exercise: {net_err}")
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "kimi",
                    "operation": "coding_exercise",
                    "error_type": type(net_err).__name__,
                    "status_code": getattr(net_err, "status_code", None),
                    "message": str(net_err),
                })
            return None
        except json.JSONDecodeError as json_err:
            logger.error(f"Kimi AI returned malformed JSON: {json_err}. Raw snippet: {response_content[:300] if 'response_content' in locals() else 'None'}")
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "kimi",
                    "operation": "coding_exercise",
                    "error_type": "JSONDecodeError",
                    "message": str(json_err),
                })
            return None
        except Exception as e:
            logger.error(f"Error calling Kimi AI ({self.client.kimi_model}) for coding exercise: {e}")
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "kimi",
                    "operation": "coding_exercise",
                    "error_type": type(e).__name__,
                    "message": str(e),
                })
            return None
