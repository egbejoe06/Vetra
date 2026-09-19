import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
import uuid

from src.agents.report.evidence_resolver import EvidenceResolver
from src.agents.report.generator import ReportGeneratorAgent
from src.agents.report.scorer import DeterministicScorer
from src.agents.report.snapshot_manager import snapshot_manager
from src.db.supabase import supabase
from src.models.enums import CandidateRecommendation
from src.schemas.report import (
    ComprehensiveRecruiterScorecard,
    GroundedQuestionScore,
    GroundedRubricScore,
    ScoreBreakdown,
)

logger = logging.getLogger("vetra.service.report_synthesizer")


class ReportSynthesizerService:
    """Phase 6 Final Synthesis Service.
    
    Coordinates:
    1. Creation of immutable InterviewSynthesisSnapshot.
    2. Synthesis of draft scorecard via ReportGeneratorAgent (Gemini Flash).
    3. Deterministic evidence resolution & audit trail logging.
    4. Deterministic weighted score computation & recommendation derivation.
    5. Persistence of final scorecard & audit trail to public.interview_evaluations.
    """

    def __init__(self, generator_agent: Optional[ReportGeneratorAgent] = None):
        self.generator = generator_agent or ReportGeneratorAgent()
        self.supabase = supabase
        self._scorecard_cache: Dict[str, ComprehensiveRecruiterScorecard] = {}
        self._in_flight_tasks: Dict[str, asyncio.Task] = {}

    def _reconstruct_scorecard_from_row(
        self, row: Dict[str, Any], session_id: uuid.UUID
    ) -> Optional[ComprehensiveRecruiterScorecard]:
        try:
            rubrics = [
                GroundedRubricScore(
                    category=r.get("category", "General"),
                    score=float(r.get("score")) if r.get("score") is not None else None,
                    weight=float(r.get("weight", 0.25)),
                    status=r.get("status", "ASSESSED" if r.get("score") is not None else "NOT_ASSESSED"),
                    feedback=r.get("feedback", ""),
                    verified_turn_ids=r.get("verified_turn_ids", []),
                    evidence_quotes=r.get("evidence_quotes", []),
                )
                for r in row.get("rubric_scores", [])
            ]
            questions = [
                GroundedQuestionScore(
                    question_text=q.get("question_text", "Interview Problem"),
                    score=float(q.get("score")) if q.get("score") is not None else None,
                    status=q.get("status", "ASSESSED" if q.get("score") is not None else "NOT_ASSESSED"),
                    feedback=q.get("feedback", ""),
                    verified_turn_ids=q.get("verified_turn_ids", []),
                )
                for q in row.get("question_scores", [])
            ]
            breakdown_dict = row.get("score_breakdown") or {}
            raw_overall = row.get("overall_score")
            calibrated = float(raw_overall) if raw_overall is not None else None
            breakdown = ScoreBreakdown(
                weights=breakdown_dict.get("weights", {}),
                raw_category_scores=breakdown_dict.get("raw_category_scores", {}),
                weighted_composite=float(breakdown_dict.get("weighted_composite", 0.0)),
                calibrated_overall_score=calibrated,
                assessed_categories=breakdown_dict.get("assessed_categories", []),
                unassessed_categories=breakdown_dict.get("unassessed_categories", []),
            )
            rec_val = row.get("recommendation", "INCONCLUSIVE")
            try:
                rec_enum = CandidateRecommendation(rec_val)
            except ValueError:
                rec_enum = CandidateRecommendation.INCONCLUSIVE

            return ComprehensiveRecruiterScorecard(
                id=uuid.UUID(row.get("id")) if row.get("id") else uuid.uuid4(),
                session_id=session_id,
                interview_id=uuid.UUID(row.get("interview_id")) if row.get("interview_id") else uuid.uuid4(),
                candidate_id=uuid.UUID(row.get("candidate_id")) if row.get("candidate_id") else None,
                candidate_name=row.get("candidate_name", "Candidate"),
                overall_score=calibrated,
                score_breakdown=breakdown,
                recommendation=rec_enum,
                summary=row.get("summary", ""),
                key_strengths=row.get("key_strengths", []),
                key_weaknesses=row.get("key_weaknesses", []),
                rubric_scores=rubrics,
                question_scores=questions,
                completion_status=row.get("completion_status", "COMPLETED"),
                stages_completed=row.get("stages_completed", []),
                stages_not_reached=row.get("stages_not_reached", []),
                audit_trail=[],
                snapshot_id=uuid.UUID(row.get("snapshot_id")) if row.get("snapshot_id") else None,
                completed_at=datetime.fromisoformat(row.get("completed_at")) if row.get("completed_at") else datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.warning(f"Failed to reconstruct scorecard from DB row: {e}")
            return None

    async def synthesize_session_report(
        self,
        session_id: uuid.UUID,
        candidate_name: Optional[str] = None,
        job_title: Optional[str] = None,
        force_regenerate: bool = False,
    ) -> ComprehensiveRecruiterScorecard:
        """Synthesizes an immutable, audit-trailed scorecard for a completed session."""
        s_id = str(session_id)

        # 1. Deduplicate in-flight synthesis tasks to prevent parallel race conditions and score divergence
        if s_id in self._in_flight_tasks:
            logger.info(f"Report synthesis already in flight for session {s_id}, awaiting existing task...")
            return await self._in_flight_tasks[s_id]

        # 2. Check local memory cache if not forcing regeneration
        if not force_regenerate and s_id in self._scorecard_cache:
            logger.info(f"Returning cached scorecard for session {s_id}")
            return self._scorecard_cache[s_id]

        # 3. Check Supabase for existing persisted evaluation if not forcing regeneration
        if not force_regenerate and self.supabase:
            try:
                res = self.supabase.table("interview_evaluations").select("*").eq("session_id", s_id).execute()
                if res.data and len(res.data) > 0:
                    existing = self._reconstruct_scorecard_from_row(res.data[0], session_id)
                    if existing:
                        logger.info(f"Found existing evaluation in Supabase for session {s_id} (Score: {existing.overall_score})")
                        self._scorecard_cache[s_id] = existing
                        return existing
            except Exception as check_err:
                logger.warning(f"Could not check existing evaluation in Supabase: {check_err}")

        # Register current task in-flight
        curr_task = asyncio.current_task()
        if curr_task:
            self._in_flight_tasks[s_id] = curr_task

        try:
            return await self._execute_synthesis(
                session_id=session_id,
                candidate_name=candidate_name,
                job_title=job_title,
            )
        finally:
            self._in_flight_tasks.pop(s_id, None)

    async def _execute_synthesis(
        self,
        session_id: uuid.UUID,
        candidate_name: Optional[str] = None,
        job_title: Optional[str] = None,
    ) -> ComprehensiveRecruiterScorecard:
        s_id = str(session_id)
        logger.info(f"Starting Phase 6 report synthesis for session {s_id}...")

        # 1. Fetch session metadata if name/job not provided
        interview_id = uuid.uuid4()
        c_name = candidate_name or "Candidate"
        j_title = job_title or "Software Engineer"
        candidate_id = None
        eval_criteria = None
        job_desc = None

        if supabase:
            try:
                res = (
                    supabase.table("interview_sessions")
                    .select("*")
                    .eq("id", s_id)
                    .execute()
                )
                if res.data and len(res.data) > 0:
                    sess_data = res.data[0]
                    c_name = candidate_name or sess_data.get("candidate_name") or "Candidate"
                    if sess_data.get("interview_id"):
                        try:
                            interview_id = uuid.UUID(str(sess_data.get("interview_id")))
                        except Exception:
                            pass
                    if sess_data.get("candidate_id"):
                        try:
                            candidate_id = uuid.UUID(str(sess_data.get("candidate_id")))
                        except Exception:
                            pass

                    # Query parent interview for job title and criteria
                    if sess_data.get("interview_id"):
                        try:
                            intv_res = (
                                supabase.table("interviews")
                                .select("*")
                                .eq("id", str(sess_data.get("interview_id")))
                                .execute()
                            )
                            if intv_res.data and len(intv_res.data) > 0:
                                intv_data = intv_res.data[0]
                                j_title = job_title or intv_data.get("job_title") or j_title
                                eval_criteria = intv_data.get("evaluation_criteria")
                                job_desc = intv_data.get("description")
                        except Exception as intv_err:
                            logger.warning(f"Could not load parent interview details: {intv_err}")
            except Exception as err:
                logger.warning(f"Could not load session details from Supabase: {err}")

        # 2. Create immutable snapshot
        snapshot, snapshot_data = snapshot_manager.create_snapshot(session_id=s_id)
        if eval_criteria:
            snapshot_data["evaluation_criteria"] = eval_criteria
        if job_desc:
            snapshot_data["job_description"] = job_desc

        # 3. Generate draft scorecard
        draft = await self.generator.generate_draft_report(
            snapshot=snapshot,
            snapshot_data=snapshot_data,
            candidate_name=c_name,
            job_title=j_title,
        )

        # 4. Resolve citations & compile internal audit trail
        resolved_draft, audit_trail = EvidenceResolver.resolve_report_evidence(
            raw_report=draft,
            snapshot_turns=snapshot_data["turns"],
        )

        # 5. Parse grounded rubric scores with backend-calibrated weights
        rubric_scores: list[GroundedRubricScore] = []
        for r in resolved_draft.get("rubric_scores", []):
            try:
                cat_name = r.get("category", "General")
                canonical_cat = DeterministicScorer.CATEGORY_ALIASES.get(cat_name.lower().strip(), cat_name)
                backend_weight = DeterministicScorer.DEFAULT_RUBRIC_WEIGHTS.get(canonical_cat, 0.25)
                raw_score = r.get("score")
                score_val = float(raw_score) if raw_score is not None else None
                status_val = r.get("status", "ASSESSED" if score_val is not None else "NOT_ASSESSED")

                rubric_scores.append(
                    GroundedRubricScore(
                        category=cat_name,
                        score=score_val,
                        weight=backend_weight,
                        status=status_val,
                        feedback=r.get("feedback", ""),
                        verified_turn_ids=r.get("verified_turn_ids", []),
                        evidence_quotes=r.get("evidence_quotes", []),
                    )
                )
            except Exception as e:
                logger.warning(f"Error constructing GroundedRubricScore: {e} -> {r}")

        # 6. Parse question scores
        question_scores: list[GroundedQuestionScore] = []
        for q in resolved_draft.get("question_scores", []):
            try:
                q_score = float(q.get("score")) if q.get("score") is not None else None
                q_status = q.get("status", "ASSESSED" if q_score is not None else "NOT_ASSESSED")
                question_scores.append(
                    GroundedQuestionScore(
                        question_text=q.get("question_text", "Interview Problem"),
                        score=q_score,
                        status=q_status,
                        feedback=q.get("feedback", ""),
                        verified_turn_ids=q.get("verified_turn_ids", []),
                    )
                )
            except Exception as e:
                logger.warning(f"Error constructing GroundedQuestionScore: {e} -> {q}")

        # 7. Compute deterministic score and recommendation with Incomplete Guard
        is_incomplete = bool(snapshot_data.get("is_incomplete", False))
        overall_score, breakdown, recommendation = DeterministicScorer.compute_scorecard(
            rubric_scores=rubric_scores,
            is_incomplete=is_incomplete,
        )

        now = datetime.now(timezone.utc)
        scorecard = ComprehensiveRecruiterScorecard(
            id=uuid.uuid4(),
            session_id=session_id,
            interview_id=interview_id,
            candidate_id=candidate_id,
            candidate_name=c_name,
            overall_score=overall_score,
            score_breakdown=breakdown,
            recommendation=recommendation,
            summary=resolved_draft.get("summary", "Technical interview evaluation completed."),
            key_strengths=resolved_draft.get("key_strengths", []),
            key_weaknesses=resolved_draft.get("key_weaknesses", []),
            rubric_scores=rubric_scores,
            question_scores=question_scores,
            completion_status="INCOMPLETE" if is_incomplete else "COMPLETED",
            stages_completed=snapshot_data.get("stages_reached", []),
            stages_not_reached=snapshot_data.get("stages_not_reached", []),
            audit_trail=audit_trail,
            snapshot_id=snapshot.id,
            completed_at=now,
        )

        # 8. Persist to Supabase public.interview_evaluations
        evaluation_record = {
            "id": str(scorecard.id),
            "session_id": s_id,
            "interview_id": str(interview_id),
            "candidate_id": str(candidate_id) if candidate_id else None,
            "candidate_name": c_name,
            "overall_score": overall_score,
            "recommendation": recommendation.value,
            "summary": scorecard.summary,
            "key_strengths": scorecard.key_strengths,
            "key_weaknesses": scorecard.key_weaknesses,
            "rubric_scores": [r.model_dump() for r in scorecard.rubric_scores],
            "question_scores": [q.model_dump() for q in scorecard.question_scores],
            "score_breakdown": scorecard.score_breakdown.model_dump(),
            "audit_trail": [a.model_dump() for a in scorecard.audit_trail],
            "snapshot_id": str(snapshot.id),
            "completion_status": scorecard.completion_status,
            "stages_completed": scorecard.stages_completed,
            "stages_not_reached": scorecard.stages_not_reached,
            "completed_at": now.isoformat(),
        }

        if self.supabase:
            try:
                self.supabase.table("interview_evaluations").upsert(
                    evaluation_record, on_conflict="session_id"
                ).execute()
                logger.info(f"Persisted evaluation scorecard {scorecard.id} to Supabase.")
            except Exception as err:
                logger.warning(f"Full evaluation upsert failed ({err}), attempting fallback...")
                try:
                    fallback_record = dict(evaluation_record)
                    err_str = str(err)
                    # Guard: INCONCLUSIVE recommendation enum not yet in DB
                    if "candidate_recommendation" in err_str and "INCONCLUSIVE" in err_str:
                        fallback_record["recommendation"] = "LEAN_REJECT"
                    # Guard: overall_score NOT NULL violation (premature/incomplete interview)
                    # Substitute 0.0 sentinel until migration 010 makes the column nullable.
                    if "overall_score" in err_str and "not-null" in err_str.lower():
                        if fallback_record.get("overall_score") is None:
                            fallback_record["overall_score"] = 0.0
                            logger.warning(
                                f"Substituting overall_score=0.0 for INCONCLUSIVE session {s_id} "
                                f"due to NOT NULL constraint. Apply migration 010 to allow NULL scores."
                            )
                    self.supabase.table("interview_evaluations").upsert(
                        fallback_record, on_conflict="session_id"
                    ).execute()
                    logger.info(f"Persisted fallback evaluation scorecard {scorecard.id} to Supabase.")
                except Exception as fallback_err:
                    logger.error(f"Failed to persist fallback interview_evaluation to Supabase: {fallback_err}")

        # Cache locally
        self._scorecard_cache[s_id] = scorecard
        return scorecard

    def get_cached_scorecard(self, session_id: uuid.UUID) -> Optional[ComprehensiveRecruiterScorecard]:
        """Returns scorecard from cache if available."""
        return self._scorecard_cache.get(str(session_id))


# Default singleton instance
report_synthesizer = ReportSynthesizerService()
