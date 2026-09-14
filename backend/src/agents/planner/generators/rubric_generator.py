import json
import logging
from typing import List, Optional, Tuple

from google.genai import types

from src.agents.planner.client import PlannerLLMClient
from src.agents.planner.exceptions import RubricsAndGuidanceContainer
from src.agents.planner.prompts.rubric_prompts import (
    RUBRIC_SYSTEM_INSTRUCTION,
    build_rubrics_prompt,
)
from src.schemas.planner import (
    InterviewBlueprint,
    InterviewPlanCreate,
    InterviewerGuidance,
    RubricCriterion,
)

logger = logging.getLogger(__name__)


class RubricGenerator:
    """Generates measurable 1/3/5 scoring rubrics and live interviewer guidance
    tied to Blueprint competencies and risk hypotheses.
    """

    def __init__(self, client: PlannerLLMClient):
        self.client = client

    def generate(
        self, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Tuple[List[RubricCriterion], InterviewerGuidance]:
        """Generates scoring rubrics & guidance using Gemini Flash-Lite with immediate retry.
        Does NOT fall back to Kimi to prevent expensive token consumption.
        """
        try:
            return self.generate_gemini(job_spec, blueprint)
        except Exception as e:
            logger.warning(f"Initial Gemini Flash-Lite rubrics generation failed ({e}). Retrying with fresh call...")
            return self.generate_gemini(job_spec, blueprint)

    def generate_gemini(
        self, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Tuple[List[RubricCriterion], InterviewerGuidance]:
        prompt = build_rubrics_prompt(job_spec, blueprint)

        def _call():
            return self.client.gemini_client.models.generate_content(
                model=self.client.gemini_flash_lite_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=RUBRIC_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=RubricsAndGuidanceContainer,
                    temperature=0.3,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=self.client.thinking_budget
                    ),
                ),
            )

        try:
            resp = self.client.call_gemini_with_retry(_call, operation_name="Generate Rubrics (Gemini Flash-Lite)")
            if resp.parsed and isinstance(resp.parsed, RubricsAndGuidanceContainer):
                return resp.parsed.rubrics, resp.parsed.interviewer_guidance
            if resp.text:
                data = json.loads(resp.text)
                container = RubricsAndGuidanceContainer(**data)
                return container.rubrics, container.interviewer_guidance
        except Exception as e:
            logger.error(f"Error generating rubrics via Gemini Flash-Lite: {e}")
            raise RuntimeError(f"Failed to generate rubrics via Gemini Flash-Lite: {e}") from e

        raise RuntimeError("Failed to generate rubrics: Gemini returned an empty response.")

    def generate_kimi(
        self, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Optional[Tuple[List[RubricCriterion], InterviewerGuidance]]:
        if not self.client.moonshot_api_key or self.client.moonshot_api_key == "EMPTY_MOONSHOT_KEY" or not self.client.kimi_client:
            return None

        prompt = build_rubrics_prompt(job_spec, blueprint)

        try:
            logger.info(f"Calling Kimi AI ({self.client.kimi_model}) for Scoring Rubrics & Guidance generation (Primary)...")
            with self.client._kimi_lock:
                completion = self.client.kimi_client.chat.completions.create(
                    model=self.client.kimi_model,
                    messages=[
                        {"role": "system", "content": RUBRIC_SYSTEM_INSTRUCTION},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    extra_body={"thinking": {"type": "disabled"}},
                    timeout=self.client.kimi_timeout_seconds,
                )
            content = completion.choices[0].message.content
            if content:
                data = json.loads(content)
                container = RubricsAndGuidanceContainer(**data)
                return container.rubrics, container.interviewer_guidance
        except Exception as e:
            logger.warning(f"Kimi AI rubrics generation failed: {e}")
            return None
        return None
