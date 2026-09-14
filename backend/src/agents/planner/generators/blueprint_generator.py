import json
import logging
from typing import Optional

from google.genai import types

from src.agents.planner.client import PlannerLLMClient
from src.agents.planner.prompts.blueprint_prompts import (
    BLUEPRINT_GEMINI_SYSTEM_INSTRUCTION,
    BLUEPRINT_KIMI_SYSTEM_INSTRUCTION,
    build_blueprint_prompt,
)
from src.schemas.planner import (
    CandidateProfile,
    InterviewBlueprint,
    InterviewPlanCreate,
)

logger = logging.getLogger(__name__)


class BlueprintGenerator:
    """Generates the Interview Blueprint (definitive source of truth for competencies,
    capabilities, and evidence claims) using Gemini Flash-Lite or Kimi AI.
    """

    def __init__(self, client: PlannerLLMClient):
        self.client = client

    def generate(self, profile: CandidateProfile, job_spec: InterviewPlanCreate) -> InterviewBlueprint:
        """Generates interview blueprint using Gemini Flash-Lite with immediate retry on failure.
        Does NOT fall back to Kimi to prevent expensive token consumption for simple blueprints.
        """
        try:
            return self.generate_gemini(profile, job_spec)
        except Exception as e:
            logger.warning(f"Initial Gemini Flash-Lite blueprint generation failed ({e}). Retrying with fresh call...")
            return self.generate_gemini(profile, job_spec)

    def generate_gemini(self, profile: CandidateProfile, job_spec: InterviewPlanCreate) -> InterviewBlueprint:
        prompt = build_blueprint_prompt(profile, job_spec)

        def _call():
            return self.client.gemini_client.models.generate_content(
                model=self.client.gemini_flash_lite_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=BLUEPRINT_GEMINI_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=InterviewBlueprint,
                    temperature=0.3,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=self.client.thinking_budget
                    ),
                ),
            )

        try:
            resp = self.client.call_gemini_with_retry(_call, operation_name="Generate Blueprint (Gemini Flash-Lite)")
            if resp.parsed and isinstance(resp.parsed, InterviewBlueprint):
                return resp.parsed
            if resp.text:
                return InterviewBlueprint(**json.loads(resp.text))
        except Exception as e:
            logger.error(f"Error generating interview blueprint via Gemini Flash-Lite: {e}")
            raise RuntimeError(f"Failed to generate interview blueprint via Gemini Flash-Lite: {e}") from e

        raise RuntimeError("Failed to generate interview blueprint: Gemini returned an empty response.")

    def generate_kimi(
        self, profile: CandidateProfile, job_spec: InterviewPlanCreate
    ) -> Optional[InterviewBlueprint]:
        if not self.client.moonshot_api_key or self.client.moonshot_api_key == "EMPTY_MOONSHOT_KEY" or not self.client.kimi_client:
            return None

        prompt = build_blueprint_prompt(profile, job_spec)

        try:
            logger.info(f"Calling Kimi AI ({self.client.kimi_model}) for Interview Blueprint generation (Primary)...")
            with self.client._kimi_lock:
                completion = self.client.kimi_client.chat.completions.create(
                    model=self.client.kimi_model,
                    messages=[
                        {"role": "system", "content": BLUEPRINT_KIMI_SYSTEM_INSTRUCTION},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    extra_body={"thinking": {"type": "disabled"}},
                    timeout=self.client.kimi_timeout_seconds,
                )
            content = completion.choices[0].message.content
            if content:
                data = json.loads(content)
                if isinstance(data, dict):
                    for key in ("interview_blueprint", "blueprint", "data", "InterviewBlueprint"):
                        if key in data and isinstance(data[key], dict):
                            data = data[key]
                            break
                return InterviewBlueprint(**data)
        except Exception as e:
            logger.warning(f"Kimi AI blueprint generation failed: {e}")
            return None
        return None
