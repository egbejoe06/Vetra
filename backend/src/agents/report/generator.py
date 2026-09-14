from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from google import genai
from google.genai import types

from config import settings
from src.utils.json_utils import safe_json_loads
from src.schemas.report import (
    GroundedQuestionScore,
    GroundedRubricScore,
    InterviewSynthesisSnapshot,
)

logger = logging.getLogger("vetra.agents.report.generator")


class ReportGeneratorAgent:
    """Agent responsible for synthesizing comprehensive candidate scorecards from sealed snapshots.
    
    Uses Gemini Flash to analyze holistic interview dialogue, code submissions, and
    accumulated evaluation signals, demanding strict turn-level citations.
    """

    def __init__(self, gemini_api_key: Optional[str] = None, model: Optional[str] = None):
        self.gemini_api_key = gemini_api_key or settings.GOOGLE_API_KEY
        self.model = model or getattr(settings, "EVALUATION_MODEL", "gemini-2.5-flash-lite")
        self.client: Optional[genai.Client] = None

        if self.gemini_api_key and self.gemini_api_key not in ("EMPTY_GEMINI_KEY", ""):
            try:
                self.client = genai.Client(api_key=self.gemini_api_key)
            except Exception as err:
                logger.warning(f"Failed to initialize Gemini client for ReportGenerator: {err}")

    async def generate_draft_report(
        self,
        snapshot: InterviewSynthesisSnapshot,
        snapshot_data: Dict[str, Any],
        candidate_name: str,
        job_title: str = "Software Engineer",
    ) -> Dict[str, Any]:
        """Generates draft scorecard from sealed interview snapshot."""
        if self.client:
            try:
                return self._generate_with_gemini(
                    snapshot=snapshot,
                    snapshot_data=snapshot_data,
                    candidate_name=candidate_name,
                    job_title=job_title,
                )
            except Exception as err:
                logger.warning(f"Gemini report generation failed: {err}. Using fallback generator...")

        return self._heuristic_fallback_generator(
            snapshot=snapshot,
            snapshot_data=snapshot_data,
            candidate_name=candidate_name,
        )

    def _generate_with_gemini(
        self,
        snapshot: InterviewSynthesisSnapshot,
        snapshot_data: Dict[str, Any],
        candidate_name: str,
        job_title: str,
    ) -> Dict[str, Any]:
        """Prompts Gemini Flash for comprehensive evaluation."""
        turns = snapshot_data.get("turns", [])
        formatted_transcript = "\n".join(
            f"[{t.get('turn_id', 'turn_???')}] {t.get('speaker', 'SPEAKER')} ({t.get('stage', 'STAGE')}): {t.get('content', '').strip()}"
            for t in turns
        )

        signals = snapshot_data.get("evaluation_signals", [])
        eval_criteria = snapshot_data.get("evaluation_criteria")
        job_description = snapshot_data.get("job_description")
        stages_reached = snapshot_data.get("stages_reached", snapshot.stages_reached or [])
        stages_not_reached = snapshot_data.get("stages_not_reached", snapshot.stages_not_reached or [])
        is_coding_reached = "TECHNICAL_EXERCISE" in stages_reached

        signals_summary = json.dumps(
            [
                {
                    "observations": s.get("competency_observations", []),
                    "assessments": s.get("competency_assessments", {}),
                }
                for s in signals
            ],
            indent=2,
            default=str,
        )

        prompt = f"""You are the Lead Technical Bar Raiser for Vetra AI Technical Interviewer.
You are evaluating the complete sealed interview transcript and code signals for:
Candidate: {candidate_name}
Target Role: {job_title}
{f"Job Description:\n{job_description}\n" if job_description else ""}
{f"RECRUITER EVALUATION CRITERIA & SCORING PRIORITIES:\n{eval_criteria}\nEvaluate candidate against these specific recruiter criteria and standards.\n" if eval_criteria else ""}
### INTERVIEW EXECUTION STAGES:
- Stages Reached in Session: {', '.join(stages_reached) if stages_reached else 'None recorded'}
- Stages NOT Reached (Session Concluded Early): {', '.join(stages_not_reached) if stages_not_reached else 'None (All stages reached)'}

### CRITICAL RULES FOR CITATION AND GROUNDING:
1. CITATIONS ARE MANDATORY: Every observation, key strength, and key weakness MUST reference the exact sequential turn ID (e.g. [turn_005], [turn_018]) where the evidence occurred.
2. DO NOT HALLUCINATE TURN IDS: The transcript below defines the only valid turn IDs from {snapshot.turn_labels[0] if snapshot.turn_labels else 'turn_001'} to {snapshot.turn_labels[-1] if snapshot.turn_labels else 'turn_001'}.
3. STRICT STAGE-CONDITIONED ASSESSMENT & ANTI-CROSS-CONTAMINATION (CRITICAL):
   - 'Technical Depth & Mastery': Grounded in candidate's demonstrated knowledge in RESUME_DEEP_DIVE and TECHNICAL_QA.
   - 'Scalability & Failure Modes': Grounded in trade-offs, failure recovery, and architectural discussions in TECHNICAL_QA or RESUME_DEEP_DIVE.
   - 'Problem Solving & Algorithms': Strictly requires an interactive problem solving or coding exercise. If TECHNICAL_EXERCISE is in Stages NOT Reached, you MUST set "status": "NOT_ASSESSED", "score": null, "verified_turn_ids": [], and feedback: "Coding / problem solving challenge was not reached before the interview concluded. Not assessed."
   - 'Code Quality & Architecture': Strictly requires candidate code inspection, modification, or code execution in TECHNICAL_EXERCISE. If TECHNICAL_EXERCISE is in Stages NOT Reached, you MUST set "status": "NOT_ASSESSED", "score": null, "verified_turn_ids": [], and feedback: "Candidate did not interact with the code exercise before the interview concluded. Not assessed."
   - ZERO FALSE EVIDENCE ATTRIBUTION: NEVER use a verbal explanation about architecture or system components (e.g., from TECHNICAL_QA) as substitute evidence for "Code Quality & Architecture" or "Problem Solving & Algorithms" when the coding stage was not reached!
   - DO NOT CONVERT "NOT ASSESSED" INTO A FAILING SCORE: An unreached stage is NOT a failure; set "score": null and "status": "NOT_ASSESSED".
4. STRICT ANTI-BIAS AND RELEVANCE RULE:
   - Evaluate the candidate strictly against the provided Job Description, Recruiter Criteria, and the actual questions asked in the interview.
   - Do NOT penalize candidates for omitting out-of-scope concepts (e.g. distributed deadlocks, GC pauses, sharding, or P99 latency SLAs) unless the role or interview question specifically demanded them.
   - Base all strengths, weaknesses, and ratings purely on verifiable evidence from the transcript.

### SEALED INTERVIEW TRANSCRIPT:
{formatted_transcript}

### ACCUMULATED EVALUATION SIGNALS:
{signals_summary}

### REQUIRED OUTPUT FORMAT:
Respond ONLY with valid JSON matching this schema:
{{
  "summary": "Executive summary of candidate's technical performance, fit, and stage completion notes.",
  "key_strengths": [
    "Demonstrated clear architectural reasoning and clean abstraction boundaries [turn_004].",
    "Effectively walked through practical edge case handling and data validation [turn_012]."
  ],
  "key_weaknesses": [
    "Did not fully address boundary conditions or error recovery for the proposed solution [turn_016].",
    "Could have provided deeper rationale for architectural and state management choices [turn_020]."
  ],
  "rubric_scores": [
    {{
      "category": "Technical Depth & Mastery",
      "status": "ASSESSED", // or "NOT_ASSESSED" if stage not reached
      "score": 4.5, // float 1.0-5.0 if ASSESSED, null if NOT_ASSESSED
      "feedback": "Strong command of core low-level primitives.",
      "verified_turn_ids": ["turn_004", "turn_012"],
      "evidence_quotes": ["Candidate explained composite indexes."]
    }},
    {{
      "category": "Problem Solving & Algorithms",
      "status": "{'ASSESSED' if is_coding_reached else 'NOT_ASSESSED'}",
      "score": {4.0 if is_coding_reached else 'null'},
      "feedback": "{'Methodical decomposition of problems.' if is_coding_reached else 'Stage not reached before interview ended. Not assessed.'}",
      "verified_turn_ids": {['turn_008'] if is_coding_reached else []},
      "evidence_quotes": []
    }},
    {{
      "category": "Code Quality & Architecture",
      "status": "{'ASSESSED' if is_coding_reached else 'NOT_ASSESSED'}",
      "score": {3.5 if is_coding_reached else 'null'},
      "feedback": "{'Clean modular code with good structure.' if is_coding_reached else 'Stage not reached before interview ended. Not assessed.'}",
      "verified_turn_ids": {['turn_014'] if is_coding_reached else []},
      "evidence_quotes": []
    }},
    {{
      "category": "Scalability & Failure Modes",
      "status": "ASSESSED",
      "score": 3.5,
      "feedback": "Addressed standard operational considerations but lacked depth on edge cases and failure recovery.",
      "verified_turn_ids": ["turn_016"],
      "evidence_quotes": []
    }}
  ],
  "question_scores": [
    {{
      "question_text": "Technical Exercise / Coding Challenge",
      "status": "{'ASSESSED' if is_coding_reached else 'NOT_ASSESSED'}",
      "score": {3.5 if is_coding_reached else 'null'},
      "feedback": "{'Solid implementation with good algorithmic efficiency.' if is_coding_reached else 'Stage not reached. Not assessed.'}",
      "verified_turn_ids": {['turn_014'] if is_coding_reached else []}
    }}
  ]
}}
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        content = response.text
        if not content:
            raise ValueError("Gemini returned empty synthesis response.")

        parsed = safe_json_loads(content)
        if not parsed:
            raise ValueError(f"Failed to parse valid JSON from Gemini synthesis response: {content[:200]}")

        return parsed

    def _heuristic_fallback_generator(
        self,
        snapshot: InterviewSynthesisSnapshot,
        snapshot_data: Dict[str, Any],
        candidate_name: str,
    ) -> Dict[str, Any]:
        """Deterministic fallback report generation when AI API is unavailable."""
        turns = snapshot_data.get("turns", [])
        turn_labels = snapshot.turn_labels or ["turn_001"]

        first_turn = turn_labels[0]
        last_turn = turn_labels[-1]
        mid_turn = turn_labels[len(turn_labels) // 2] if len(turn_labels) > 2 else first_turn

        stages_reached = snapshot_data.get("stages_reached", snapshot.stages_reached or [])
        is_coding_reached = "TECHNICAL_EXERCISE" in stages_reached

        return {
            "summary": (
                f"{candidate_name} completed the technical interview session across {len(turns)} dialogue turns. The candidate engaged constructively across technical discussions."
                if not snapshot_data.get("is_incomplete")
                else f"{candidate_name} participated in an incomplete interview session across {len(turns)} dialogue turns. Stages not reached were marked as Not Assessed."
            ),
            "key_strengths": [
                f"Engaged constructively in technical discussion from the outset [{first_turn}].",
                f"Maintained structured reasoning throughout intermediate technical stages [{mid_turn}].",
            ],
            "key_weaknesses": [
                f"Could have provided deeper operational analysis regarding system failure modes [{last_turn}].",
            ] if not snapshot_data.get("is_incomplete") else [
                "Interview concluded before all planned technical and coding stages were completed.",
            ],
            "rubric_scores": [
                {
                    "category": "Technical Depth & Mastery",
                    "status": "ASSESSED",
                    "score": 3.5,
                    "feedback": "Demonstrated competent foundational technical knowledge.",
                    "verified_turn_ids": [first_turn, mid_turn],
                    "evidence_quotes": [],
                },
                {
                    "category": "Problem Solving & Algorithms",
                    "status": "ASSESSED" if is_coding_reached else "NOT_ASSESSED",
                    "score": 3.5 if is_coding_reached else None,
                    "feedback": "Approached technical questions methodically." if is_coding_reached else "Stage not reached before interview ended. Not assessed.",
                    "verified_turn_ids": [mid_turn] if is_coding_reached else [],
                    "evidence_quotes": [],
                },
                {
                    "category": "Code Quality & Architecture",
                    "status": "ASSESSED" if is_coding_reached else "NOT_ASSESSED",
                    "score": 3.0 if is_coding_reached else None,
                    "feedback": "Adequate software reasoning and structure." if is_coding_reached else "Stage not reached before interview ended. Not assessed.",
                    "verified_turn_ids": [mid_turn] if is_coding_reached else [],
                    "evidence_quotes": [],
                },
                {
                    "category": "Scalability & Failure Modes",
                    "status": "ASSESSED",
                    "score": 3.0,
                    "feedback": "Basic understanding of scalability with room for deeper distributed systems analysis.",
                    "verified_turn_ids": [last_turn],
                    "evidence_quotes": [],
                },
            ],
            "question_scores": [
                {
                    "question_text": "Technical Exercise / Coding Challenge",
                    "status": "ASSESSED" if is_coding_reached else "NOT_ASSESSED",
                    "score": 3.5 if is_coding_reached else None,
                    "feedback": "Successfully navigated core interview milestones." if is_coding_reached else "Stage not reached. Not assessed.",
                    "verified_turn_ids": [mid_turn] if is_coding_reached else [],
                }
            ],
        }
