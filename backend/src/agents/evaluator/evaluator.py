import asyncio
from datetime import datetime, timezone
import json
import logging
import threading
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from openai import OpenAI
from google import genai
from google.genai import types

from config import settings
from src.schemas.evaluator import (
    CompetencyAssessment,
    CompetencyObservation,
    EvaluatorBatchInput,
    EvaluatorBatchOutput,
    StrategicProbeObjective,
)
from src.utils.json_utils import safe_json_loads

logger = logging.getLogger("vetra.agents.evaluator")


class AsyncEvaluatorAgent:
    """Asynchronous LLM Judge agent for evaluating candidate dialogue slices and code changes.
    
    Uses Kimi (kimi-k2.6) as primary deep-reasoning judge with Gemini Flash fallback.
    Enforces non-aggressive competency modeling (observations vs assessments) and
    produces structured strategic probing objectives with explicit turn lifecycles.
    """

    def __init__(
        self,
        moonshot_api_key: Optional[str] = None,
        moonshot_base_url: Optional[str] = None,
        kimi_model: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
    ):
        self.moonshot_api_key = moonshot_api_key or settings.MOONSHOT_API_KEY
        self.moonshot_base_url = moonshot_base_url or settings.MOONSHOT_BASE_URL
        self.kimi_model = kimi_model or settings.KIMI_EXERCISE_MODEL
        self.kimi_timeout_seconds = getattr(settings, "KIMI_TIMEOUT_SECONDS", 60.0)

        self.gemini_api_key = gemini_api_key or settings.GOOGLE_API_KEY
        self.gemini_model = gemini_model or getattr(settings, "EVALUATION_MODEL", "gemini-2.5-flash-lite")

        # Moonshot 1-concurrency thread safety lock
        self._kimi_lock = threading.Lock()

        # Moonshot / Kimi client (OpenAI SDK compatible)
        self.kimi_client: Optional[OpenAI] = None
        if self.moonshot_api_key and self.moonshot_api_key not in ("EMPTY_MOONSHOT_KEY", ""):
            try:
                self.kimi_client = OpenAI(
                    api_key=self.moonshot_api_key,
                    base_url=self.moonshot_base_url,
                    timeout=self.kimi_timeout_seconds,
                )
            except Exception as err:
                logger.warning(f"Failed to initialize Kimi client for Evaluator: {err}")

        # Google Gemini Client
        self.gemini_client: Optional[genai.Client] = None
        if self.gemini_api_key and self.gemini_api_key not in ("EMPTY_GEMINI_KEY", ""):
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_api_key)
            except Exception as err:
                logger.warning(f"Failed to initialize Gemini client for Evaluator: {err}")

    async def evaluate_batch(self, batch_input: EvaluatorBatchInput) -> EvaluatorBatchOutput:
        """Evaluate an asynchronous dialogue slice and code diff without blocking event loop."""
        # 1. Try Kimi primary evaluation in threadpool to prevent blocking asyncio loop
        if self.kimi_client:
            try:
                return await asyncio.to_thread(self._evaluate_with_kimi, batch_input)
            except Exception as err:
                logger.warning(f"Kimi evaluation failed: {err}. Falling back to Gemini Flash...")

        # 2. Try Gemini Flash fallback in threadpool
        if self.gemini_client:
            try:
                return await asyncio.to_thread(self._evaluate_with_gemini, batch_input)
            except Exception as err:
                logger.warning(f"Gemini Flash evaluation failed: {err}. Using rule-based fallback...")

        # 3. Resilient heuristic fallback
        return self._heuristic_fallback_evaluation(batch_input)

    def _build_evaluation_prompt(self, batch_input: EvaluatorBatchInput) -> str:
        """Constructs prompt for asynchronous evaluation."""
        turns_repr = "\n".join(
            f"[{t.get('turn_id', 'turn_???')}] {t.get('speaker', 'UNKNOWN')}: {t.get('content', '').strip()}"
            for t in batch_input.recent_turns
        )

        existing_assess_repr = json.dumps(
            {k: v.model_dump() for k, v in batch_input.existing_assessments.items()},
            indent=2,
            default=str,
        )

        active_probes_repr = json.dumps(
            [p.model_dump() for p in batch_input.active_probes],
            indent=2,
            default=str,
        )

        problem_summary = "None active"
        if batch_input.active_problem:
            p = batch_input.active_problem
            problem_summary = f"Title: {p.get('title')}\nPrompt: {p.get('prompt_question')}"

        code_summary = batch_input.code_diff_summary or "No recent code changes"

        prompt = f"""You are the Lead Technical Evaluator for Vetra AI Technical Interviewer.
You are evaluating a 3-5 turn slice of an ongoing software engineering interview.

### CORE PRINCIPLES: QUESTION-CONDITIONED MECHANISM EVALUATION
1. OBJECTIVE & QUESTION-CONDITIONED DEPTH CALIBRATION:
   Evaluate the candidate strictly against the reasoning dimensions required by the specific question asked:
   - Claim: Did the candidate state a concrete technical approach or solution?
   - Mechanism Explanation: Did they explain how it works internally?
   - Causal Reasoning (Cause -> Effect): Did they explain WHY it works or behaves that way?
   - Question-Conditioned Dimensions: Did they demonstrate the dimensions demanded by this question (e.g. failure modes, tradeoffs, invariants, boundary cases)?
   Do NOT penalize the candidate for omitting out-of-scope concepts that were never asked (e.g. do not demand distributed scaling tradeoffs for a simple language syntax or data structure question).

2. ANSWER QUALITY TIERS (DERIVED FROM QUESTION-CONDITIONED REASONING DEPTH):
   - "SURFACE_MENTION": Candidate named a technology, library, or approach without explaining its internal mechanism or causal logic.
   - "PARTIAL_UNDERSTANDING": Candidate explained the core mechanism correctly, but overlooked key practical details, edge cases, or reasoning dimensions required by this specific question.
   - "DEMONSTRATED_MASTERY": Candidate clearly articulated the core mechanism, causal chain, and addressed the reasoning dimensions expected for this question.

3. CONFIDENCE CONTRACT (EVALUATOR EVIDENCE CERTAINTY, NOT SKILL SCORE):
   - "confidence" (0.00 to 1.00) strictly reflects how clear and unambiguous the transcript excerpt is as evidence for your observation.
   - High confidence (0.80 - 1.00) can accompany "SURFACE_MENTION" if the candidate's answer is blatantly brief (e.g. "We used Redis.") where there is zero ambiguity that only a surface mention was provided.
   - Lower confidence may accompany verbose answers if the candidate's actual mastery or understanding remains ambiguous.

4. OBSERVATION BUDGET & NON-AGGRESSIVE GRADING:
   - Emit strictly 1–3 high-signal observations per batch, only for competencies with genuine new evidence in this slice.
   - Slices of 3-5 turns are insufficient for conclusive global grades. Do NOT assign provisional scores unless there is sufficient evidence across multiple turns.
5. CITATIONS MUST BE EMPIRICAL: All 'evidence_turn_ids' must strictly match the turn IDs provided below.
6. ROLE-ALIGNED STRATEGIC PROBES: Formulate unscripted high-level objectives targeting unverified technical gaps grounded in the JOB DESCRIPTION and the candidate's actual answers.
7. MARK RESOLVED PROBES: If the candidate answered or covered an existing active probe in this slice, add its ID to 'satisfied_probe_ids'.
8. ZERO-HALLUCINATION & ANTI-BIAS PROBES:
   - NEVER invent imaginary sub-components, named pipelines, arbitrary SLA targets (like P99 latency, unless in the problem prompt), or out-of-context metrics.
   - Probes must be fair, unbiased, and explore what a normal engineering interviewer would ask for this job description.
   - Do NOT penalize the candidate for omitting out-of-scope concepts that were never asked.
9. ANTI-REPETITION & SINGLE-PROBE CEILING (CRITICAL):
   - NEVER generate probes for topics, competencies, or questions that have already been asked or discussed in this dialogue slice or previous turns.
   - Do NOT ask the candidate to rephrase, repeat, or answer the same concept again.
   - If the candidate provided an explanation (even if brief or partial), record an observation and evaluate what they gave.
   - Each probe MUST have a strict turn expiration. Set 'expires_after_turn' to at most current turn + 2.
10. CONNECTIVITY, INTERRUPTION & REPETITION EXCLUSION (CRITICAL):
   - Interrupted speech, audio checks ('can you hear me'), repetition requests ('can you repeat that', 'you cut out'), and clarification requests ('what do you mean by...') are non-substantive operational dialogue turns.
   - NEVER evaluate them as candidate technical answers or score them as technical weaknesses/penalties.
   - If a question was interrupted or could not be delivered due to network disruptions, do NOT evaluate it as 'NO_ANSWER' or candidate failure.

### CONTEXT
Current Stage: {batch_input.current_stage.value if hasattr(batch_input.current_stage, 'value') else batch_input.current_stage}
Active Problem:
{problem_summary}

Recent Code Diff / State:
{code_summary}

Active Competencies to Target:
{json.dumps(batch_input.active_competencies)}
{f"Recruiter Evaluation Criteria & Benchmarks:\n{batch_input.evaluation_criteria}\n" if batch_input.evaluation_criteria else ""}
Existing Running Assessments:
{existing_assess_repr}

Currently Active Probing Directives:
{active_probes_repr}

### RECENT DIALOGUE SLICE
{turns_repr}

### REQUIRED OUTPUT FORMAT
Respond ONLY with valid JSON matching this structure:
{{
  "observations": [
    {{
      "competency": "<Target Competency>",
      "polarity": "POSITIVE", // Allowed: "POSITIVE", "NEGATIVE", "NEUTRAL"
      "confidence": 0.85, // Evaluator certainty in evidence (0.0 to 1.0)
      "answer_quality": "PARTIAL_UNDERSTANDING", // Allowed: "SURFACE_MENTION", "PARTIAL_UNDERSTANDING", "DEMONSTRATED_MASTERY"
      "missing_concepts": ["<specific technical gap or omitted reasoning dimension>"],
      "recommended_probe": "<Targeted probe to explore depth on the missing concept>",
      "evidence_turn_ids": ["turn_003"],
      "rationale": "<Concise explanation connecting transcript evidence to the observed reasoning depth>"
    }}
  ],
  "updated_assessments": {{
    "<Target Competency>": {{
      "competency": "<Target Competency>",
      "provisional_score": null,
      "confidence": 0.70,
      "evidence_count": 1,
      "coverage_status": "PARTIAL", // Allowed: "INSUFFICIENT", "PARTIAL", "SUFFICIENT" (use "INSUFFICIENT" when coverage is none or low)
      "key_findings": ["Understands basic caching approach but has not addressed cache invalidation."]
    }}
  }},
  "new_probes": [
    {{
      "topic": "Cache Invalidation",
      "priority": "HIGH", // Allowed: "HIGH", "MEDIUM", "LOW"
      "objective": "Probe candidate on cache invalidation and data freshness under concurrent updates.",
      "gap_reason": "Candidate proposed adding a cache layer but did not discuss how stale data is prevented.",
      "suggested_direction": "Ask what strategy they would use to keep the cache consistent when writes occur.",
      "competency_target": "System Design",
      "created_from_turn_id": "turn_003",
      "expires_after_turn": 15
    }}
  ],
  "satisfied_probe_ids": [],
  "evaluator_reasoning_summary": "Brief 1-2 sentence evaluation summary."
}}
"""
        return prompt

    def _evaluate_with_kimi(self, batch_input: EvaluatorBatchInput) -> EvaluatorBatchOutput:
        """Call Moonshot Kimi API with structured JSON output."""
        prompt = self._build_evaluation_prompt(batch_input)

        with self._kimi_lock:
            completion = self.kimi_client.chat.completions.create(
                model=self.kimi_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are Vetra's Asynchronous Technical Evaluation Judge. Output strictly valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
                timeout=self.kimi_timeout_seconds,
            )

        content = completion.choices[0].message.content
        if not content:
            raise ValueError("Kimi returned empty response content.")

        data = safe_json_loads(content)
        return self._parse_evaluation_dict(data)

    def _evaluate_with_gemini(self, batch_input: EvaluatorBatchInput) -> EvaluatorBatchOutput:
        """Call Google Gemini Flash with JSON response mode."""
        prompt = self._build_evaluation_prompt(batch_input)

        response = self.gemini_client.models.generate_content(
            model=self.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        content = response.text
        if not content:
            raise ValueError("Gemini Flash returned empty response text.")

        data = safe_json_loads(content)
        return self._parse_evaluation_dict(data)

    def _parse_evaluation_dict(self, data: Dict[str, Any]) -> EvaluatorBatchOutput:
        """Parse and validate evaluator output dictionary into Pydantic models."""
        observations: List[CompetencyObservation] = []
        for obs in data.get("observations", []):
            try:
                observations.append(CompetencyObservation(**obs))
            except Exception as e:
                logger.warning(f"Error parsing CompetencyObservation: {e} -> {obs}")

        updated_assessments: Dict[str, CompetencyAssessment] = {}
        for comp_name, assess_data in data.get("updated_assessments", {}).items():
            try:
                if isinstance(assess_data, dict):
                    if "competency" not in assess_data:
                        assess_data["competency"] = comp_name
                    updated_assessments[comp_name] = CompetencyAssessment(**assess_data)
            except Exception as e:
                logger.warning(f"Error parsing CompetencyAssessment: {e} -> {assess_data}")

        new_probes: List[StrategicProbeObjective] = []
        for probe in data.get("new_probes", []):
            try:
                raw_id = probe.get("id")
                try:
                    if raw_id:
                        probe["id"] = UUID(str(raw_id).strip())
                    else:
                        probe["id"] = uuid4()
                except (ValueError, TypeError, AttributeError):
                    probe["id"] = uuid4()

                new_probes.append(StrategicProbeObjective(**probe))
            except Exception as e:
                logger.warning(f"Error parsing StrategicProbeObjective: {e} -> {probe}")

        satisfied_probe_ids = [str(pid) for pid in data.get("satisfied_probe_ids", [])]
        reasoning = data.get("evaluator_reasoning_summary")

        return EvaluatorBatchOutput(
            observations=observations,
            updated_assessments=updated_assessments,
            new_probes=new_probes,
            satisfied_probe_ids=satisfied_probe_ids,
            evaluator_reasoning_summary=reasoning,
        )

    def _heuristic_fallback_evaluation(self, batch_input: EvaluatorBatchInput) -> EvaluatorBatchOutput:
        """Deterministic fallback when external AI models are inaccessible."""
        observations: List[CompetencyObservation] = []
        assessments: Dict[str, CompetencyAssessment] = dict(batch_input.existing_assessments)
        new_probes: List[StrategicProbeObjective] = []

        last_turn_id = "turn_001"
        for turn in batch_input.recent_turns:
            t_id = turn.get("turn_id", "turn_001")
            last_turn_id = t_id
            speaker = str(turn.get("speaker", "")).upper()
            content = turn.get("content", "")

            if speaker == "CANDIDATE" and len(content.split()) >= 15:
                # Identify observed competencies
                matched_comp = "General Problem Solving"
                for comp in batch_input.active_competencies:
                    if comp.lower() in content.lower():
                        matched_comp = comp
                        break

                obs = CompetencyObservation(
                    competency=matched_comp,
                    polarity="POSITIVE",
                    confidence=0.75,
                    answer_quality="PARTIAL_UNDERSTANDING",
                    missing_concepts=[f"{matched_comp} practical implementation details and edge case considerations"],
                    recommended_probe=f"Ask candidate to explain how they handle edge cases or practical tradeoffs in {matched_comp}.",
                    evidence_turn_ids=[t_id],
                    rationale=f"Candidate addressed {matched_comp} constructively.",
                )
                observations.append(obs)

                # Update running assessment
                prev = assessments.get(matched_comp)
                prev_count = prev.evidence_count if prev else 0
                new_count = prev_count + 1
                coverage = "SUFFICIENT" if new_count >= 3 else ("PARTIAL" if new_count >= 1 else "INSUFFICIENT")
                prov_score = 3.5 if coverage != "INSUFFICIENT" else None

                assessments[matched_comp] = CompetencyAssessment(
                    competency=matched_comp,
                    provisional_score=prov_score,
                    confidence=0.70,
                    evidence_count=new_count,
                    coverage_status=coverage,
                    key_findings=[f"Observed in {t_id}."],
                )

        # Propose follow-up probe ONLY for competencies that have not been discussed yet
        turn_num = 1
        try:
            turn_num = int(str(last_turn_id).split("_")[-1])
        except Exception:
            pass

        existing_probe_targets = {
            p.competency_target.lower() for p in batch_input.active_probes if p.status == "ACTIVE"
        }
        for comp, assess in assessments.items():
            # Only probe if zero evidence has been recorded and no active probe exists for this competency
            if assess.evidence_count == 0 and comp.lower() not in existing_probe_targets:
                new_probes.append(
                    StrategicProbeObjective(
                        topic=f"{comp} Overview",
                        priority="MEDIUM",
                        objective=f"Probe candidate for practical experience with {comp}.",
                        gap_reason=f"Candidate has not yet discussed {comp}.",
                        suggested_direction=f"Ask candidate about their experience with {comp}.",
                        competency_target=comp,
                        created_from_turn_id=last_turn_id,
                        status="ACTIVE",
                        expires_after_turn=turn_num + 2,
                    )
                )
                break

        return EvaluatorBatchOutput(
            observations=observations,
            updated_assessments=assessments,
            new_probes=new_probes,
            satisfied_probe_ids=[],
            evaluator_reasoning_summary="Heuristic evaluation completed.",
        )
