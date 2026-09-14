import json
import logging
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import APIError

from config import settings
from src.schemas.planner import CandidateProfile

logger = logging.getLogger(__name__)


class ResumeParserAgent:
    """Callable agent service for parsing candidate resumes (text or PDF) into structured CandidateProfile
    using fast, cost-efficient Gemini 2.5 Flash-Lite structured capabilities.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.GOOGLE_API_KEY
        self.model_name = model_name or getattr(settings, "GEMINI_FLASH_LITE_MODEL", "gemini-2.5-flash-lite")
        self.client: Optional[genai.Client] = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client for ResumeParser: {e}")


    def parse_text(self, resume_text: str) -> CandidateProfile:
        """Parse raw resume plain text into structured CandidateProfile."""
        system_instruction = (
            "You are an expert technical recruiter and software engineering resume analyst. Extract accurate, structured candidate details "
            "from the provided resume text into the requested CandidateProfile schema.\n"
            "CRITICAL INSTRUCTIONS FOR WORK EXPERIENCE & PROJECTS:\n"
            "- For each project in 'projects', extract a comprehensive 'description' covering the project's architecture, problem solved, technical challenges, scale, and exact role. Do NOT compress or drop technical details.\n"
            "- For each position in 'work_experience', preserve specific engineering 'responsibilities' including architectural decisions, concurrency/scaling solutions, system design trade-offs, and claimed impact.\n"
            "- Extract skills taxonomy, frameworks, education, and detect timeline gaps or unverified skill depth claims."
        )

        prompt = f"Extract structured candidate profile from the following resume text:\n\n{resume_text}"

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=CandidateProfile,
                    temperature=0.2,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )

            if response.parsed and isinstance(response.parsed, CandidateProfile):
                profile: CandidateProfile = response.parsed
                profile.raw_resume_text = resume_text
                return profile

            if response.text:
                data = json.loads(response.text)
                profile = CandidateProfile(**data)
                profile.raw_resume_text = resume_text
                return profile

            raise ValueError("Empty or unparsable response received from Gemini model.")
        except APIError as e:
            logger.error(f"Gemini API error during resume text parsing: {e}")
            raise RuntimeError(f"Failed to parse resume via Gemini API: {str(e)}") from e
        except Exception as e:
            logger.error(f"Error parsing resume text: {e}")
            raise

    def parse_pdf_bytes(self, pdf_bytes: bytes, filename: str = "resume.pdf") -> CandidateProfile:
        """Parse raw PDF file bytes using native Gemini 2.5 Flash multimodal file input."""
        system_instruction = (
            "You are an expert technical recruiter and software engineering resume analyst. Extract accurate, structured candidate details "
            "from the attached PDF resume into the requested CandidateProfile schema.\n"
            "CRITICAL INSTRUCTIONS FOR WORK EXPERIENCE & PROJECTS:\n"
            "- For each project in 'projects', extract a comprehensive 'description' covering the project's architecture, problem solved, technical challenges, scale, and exact role. Do NOT compress or drop technical details.\n"
            "- For each position in 'work_experience', preserve specific engineering 'responsibilities' including architectural decisions, concurrency/scaling solutions, system design trade-offs, and claimed impact.\n"
            "- Extract candidate contact details, skills taxonomy, frameworks, education, and detect timeline gaps or unverified tech claims."
        )

        pdf_part = types.Part.from_bytes(
            data=pdf_bytes,
            mime_type="application/pdf",
        )

        prompt = f"Extract structured candidate profile from the attached PDF resume '{filename}'."

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, pdf_part],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=CandidateProfile,
                    temperature=0.2,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )

            if response.parsed and isinstance(response.parsed, CandidateProfile):
                return response.parsed

            if response.text:
                data = json.loads(response.text)
                return CandidateProfile(**data)

            raise ValueError("Empty or unparsable response received from Gemini model for PDF parsing.")
        except APIError as e:
            logger.error(f"Gemini API error during PDF resume parsing: {e}")
            raise RuntimeError(f"Failed to parse PDF resume via Gemini API: {str(e)}") from e
        except Exception as e:
            logger.error(f"Error parsing PDF resume: {e}")
            raise


# Default singleton instance
resume_parser_agent = ResumeParserAgent()
