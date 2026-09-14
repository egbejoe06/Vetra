import json
import logging
import time
from typing import Any, Dict, List, Optional

from google.genai import types
from openai import APIConnectionError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from src.agents.planner.client import PlannerLLMClient
from src.agents.planner.prompts.system_design_prompts import (
    SYSTEM_DESIGN_INSTRUCTION,
    build_system_design_prompt,
)
from src.schemas.planner import (
    CandidateProfile,
    InterviewBlueprint,
    InterviewPlanCreate,
    SystemDesignExercise,
)

logger = logging.getLogger(__name__)


class SystemDesignGenerator:
    """Generates scenario-driven System Design interview exercises tailored to candidate domain,
    real-world scale targets, and architectural dilemmas.
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
    ) -> Optional[SystemDesignExercise]:
        """Generates system design exercise using Gemini Flash (Primary) with retries,
        optionally falling back to Kimi AI if enabled.
        """
        if diagnostic_list is None:
            diagnostic_list = []

        exercise: Optional[SystemDesignExercise] = None
        gemini_retries = 2
        logger.info("Generating system design exercise using Gemini Flash (Primary)...")

        for g_attempt in range(1, gemini_retries + 1):
            try:
                hint = f"Attempt #{g_attempt}" if g_attempt > 1 else ""
                exercise = self.generate_gemini(
                    profile,
                    job_spec,
                    blueprint,
                    retry_hint=hint,
                    diagnostic_list=diagnostic_list,
                    previous_exercises=previous_exercises,
                )
                if exercise:
                    break
            except Exception as fb_err:
                diagnostic_list.append({
                    "provider": "gemini",
                    "operation": "system_design",
                    "error_type": type(fb_err).__name__,
                    "message": f"Gemini attempt {g_attempt} error: {str(fb_err)}",
                })
                logger.error(f"Gemini system design exercise failed on attempt {g_attempt}: {fb_err}")
            if g_attempt < gemini_retries:
                time.sleep(1.0)

        if not exercise:
            if (
                self.client.enable_kimi_coding_fallback
                and self.client.kimi_client
                and self.client.moonshot_api_key
                and self.client.moonshot_api_key != "EMPTY_MOONSHOT_KEY"
            ):
                logger.info("Gemini Flash system design exercise failed. Falling back to Kimi AI (explicitly enabled)...")
                max_retries = self.client.kimi_max_retries
                for attempt in range(1, max_retries + 1):
                    try:
                        exercise = self.generate_kimi(
                            profile,
                            job_spec,
                            blueprint,
                            diagnostic_list=diagnostic_list,
                            previous_exercises=previous_exercises,
                        )
                        if exercise:
                            break
                    except Exception as e:
                        diagnostic_list.append({
                            "provider": "kimi",
                            "operation": "system_design_fallback",
                            "error_type": type(e).__name__,
                            "message": f"Kimi attempt {attempt} error: {str(e)}",
                        })
                        logger.warning(f"Kimi AI system design exercise fallback failed on attempt {attempt}: {e}")
                    if attempt < max_retries:
                        time.sleep(1.0)
            else:
                diagnostic_list.append({
                    "provider": "planner_policy",
                    "operation": "system_design",
                    "error_type": "ControlledFallbackNotice",
                    "message": "Kimi fallback for system design is disabled to prevent unnecessary high costs.",
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
    ) -> SystemDesignExercise:
        user_prompt = build_system_design_prompt(
            profile,
            job_spec,
            blueprint,
            retry_hint=retry_hint,
            previous_exercises=previous_exercises,
        )

        def _call():
            return self.client.gemini_client.models.generate_content(
                model=self.client.gemini_flash_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_DESIGN_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=SystemDesignExercise,
                    temperature=0.3,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=self.client.thinking_budget
                    ),
                ),
            )

        try:
            resp = self.client.call_gemini_with_retry(_call, operation_name="Generate System Design Exercise (Gemini Flash)")
            if resp.parsed and isinstance(resp.parsed, SystemDesignExercise):
                return resp.parsed
            if resp.text:
                return SystemDesignExercise(**json.loads(resp.text))
            raise RuntimeError("Gemini Flash returned empty system design exercise.")
        except Exception as e:
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "gemini",
                    "operation": "system_design_fallback",
                    "error_type": type(e).__name__,
                    "message": str(e),
                })
            raise

    def generate_kimi(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
        previous_exercises: Optional[List[str]] = None,
    ) -> Optional[SystemDesignExercise]:
        if not self.client.moonshot_api_key or self.client.moonshot_api_key == "EMPTY_MOONSHOT_KEY" or not self.client.kimi_client:
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "kimi",
                    "operation": "system_design",
                    "error_type": "ConfigurationNotice",
                    "message": "Moonshot API key is unconfigured or empty; directly using Gemini Flash fallback.",
                })
            return None

        user_prompt = build_system_design_prompt(
            profile,
            job_spec,
            blueprint,
            previous_exercises=previous_exercises,
        )

        try:
            logger.info(f"Calling Kimi AI ({self.client.kimi_model}) for system design exercise generation...")
            with self.client._kimi_lock:
                completion = self.client.kimi_client.chat.completions.create(
                    model=self.client.kimi_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_DESIGN_INSTRUCTION},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    extra_body={"thinking": {"type": "disabled"}},
                    timeout=self.client.kimi_timeout_seconds,
                )

            response_content = completion.choices[0].message.content
            if response_content:
                data = json.loads(response_content)
                if isinstance(data, dict):
                    for key in ("system_design_exercise", "SystemDesignExercise", "exercise", "data"):
                        if key in data and isinstance(data[key], dict):
                            data = data[key]
                            break
                try:
                    return SystemDesignExercise(**data)
                except ValidationError as val_err:
                    logger.error(
                        f"Kimi AI system design schema validation error (Schema Drift Detected): {val_err.errors()}",
                        extra={"schema_errors": str(val_err.errors()), "raw_payload": response_content[:500]},
                    )
                    if diagnostic_list is not None:
                        diagnostic_list.append({
                            "provider": "kimi",
                            "operation": "system_design",
                            "error_type": "ValidationError",
                            "message": f"Schema mismatch: {val_err.errors()}",
                        })
                    return None
        except (RateLimitError, APIConnectionError, APITimeoutError) as net_err:
            logger.error(f"Network/Quota error calling Kimi AI ({self.client.kimi_model}) for system design exercise: {net_err}")
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "kimi",
                    "operation": "system_design",
                    "error_type": type(net_err).__name__,
                    "status_code": getattr(net_err, "status_code", None),
                    "message": str(net_err),
                })
            return None
        except Exception as e:
            logger.error(f"Error generating system design exercise with Kimi AI: {e}")
            if diagnostic_list is not None:
                diagnostic_list.append({
                    "provider": "kimi",
                    "operation": "system_design",
                    "error_type": type(e).__name__,
                    "message": str(e),
                })
            return None

        return None
