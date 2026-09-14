import json
import logging
import time
from typing import List, Optional, Tuple

from google.genai import types

from src.agents.planner.client import PlannerLLMClient
from src.agents.planner.exceptions import QuestionsContainer
from src.agents.planner.prompts.question_prompts import (
    QUESTION_SYSTEM_INSTRUCTION,
    build_questions_prompt,
)
from src.schemas.planner import (
    CandidateProfile,
    InterviewBlueprint,
    InterviewPlanCreate,
    InterviewQuestion,
)

logger = logging.getLogger(__name__)


class QuestionGenerator:
    """Generates introductory, technical probing, and behavioral interview questions
    grounded directly in the candidate's claims, capabilities, and risks.
    """

    def __init__(self, client: PlannerLLMClient):
        self.client = client

    def generate(
        self, profile: CandidateProfile, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Tuple[List[InterviewQuestion], List[InterviewQuestion], List[InterviewQuestion]]:
        """Generates interview questions using Gemini Flash with internal retry.
        Does NOT fall back to Kimi to prevent silently generating thousands of expensive tokens
        from massive candidate resume and project payloads.
        """
        for attempt in range(1, 3):
            try:
                intro, tech, beh = self.generate_gemini(profile, job_spec, blueprint)
                if intro and tech and beh:
                    return intro, tech, beh
                logger.warning(f"Incomplete question generation on attempt {attempt}. Retrying with Gemini Flash...")
            except Exception as e:
                if attempt == 2:
                    logger.error(f"Failed to generate questions via Gemini Flash after retries: {e}")
                    raise
                logger.warning(f"Gemini Flash question generation failed on attempt 1 ({e}). Retrying with fresh call...")
                time.sleep(1.0)
        raise RuntimeError("Failed to generate complete questions via Gemini Flash after retries.")

    def generate_gemini(
        self, profile: CandidateProfile, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Tuple[List[InterviewQuestion], List[InterviewQuestion], List[InterviewQuestion]]:
        prompt = build_questions_prompt(profile, job_spec, blueprint)

        def _call():
            return self.client.gemini_client.models.generate_content(
                model=self.client.gemini_flash_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=QUESTION_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=QuestionsContainer,
                    temperature=0.4,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=self.client.thinking_budget
                    ),
                ),
            )

        try:
            resp = self.client.call_gemini_with_retry(_call, operation_name="Generate Questions (Gemini Flash)")
            if resp.parsed and isinstance(resp.parsed, QuestionsContainer):
                return resp.parsed.intro_questions, resp.parsed.questions, resp.parsed.behavioral_questions
            if resp.text:
                data = json.loads(resp.text)
                container = QuestionsContainer(**data)
                return container.intro_questions, container.questions, container.behavioral_questions
        except Exception as e:
            logger.error(f"Error generating interview questions via Gemini Flash: {e}")
            raise RuntimeError(f"Failed to generate interview questions via Gemini Flash: {e}") from e

        raise RuntimeError("Failed to generate interview questions: Gemini returned an empty response.")

    def generate_kimi(
        self, profile: CandidateProfile, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Optional[Tuple[List[InterviewQuestion], List[InterviewQuestion], List[InterviewQuestion]]]:
        if not self.client.moonshot_api_key or self.client.moonshot_api_key == "EMPTY_MOONSHOT_KEY" or not self.client.kimi_client:
            return None

        prompt = build_questions_prompt(profile, job_spec, blueprint)

        try:
            logger.info(f"Calling Kimi AI ({self.client.kimi_model}) for Interview Questions generation (Primary)...")
            with self.client._kimi_lock:
                completion = self.client.kimi_client.chat.completions.create(
                    model=self.client.kimi_model,
                    messages=[
                        {"role": "system", "content": QUESTION_SYSTEM_INSTRUCTION},
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
                    for key in ("questions_container", "QuestionsContainer", "data", "payload", "interview_questions"):
                        if key in data and isinstance(data[key], dict):
                            data = data[key]
                            break
                container = QuestionsContainer(**data)
                return container.intro_questions, container.questions, container.behavioral_questions
        except Exception as e:
            logger.warning(f"Kimi AI questions generation failed: {e}")
            return None
        return None
