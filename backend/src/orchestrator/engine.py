import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver

from src.db.supabase import supabase
from src.orchestrator.events import EventActor, OrchestratorEvent
from src.orchestrator.graph import build_interview_graph
from src.orchestrator.guards import STAGE_RULES, validate_transition_guard
from src.orchestrator.state import (
    GuidancePayload,
    InterviewerContext,
    InterviewState,
    TransitionDecision,
)

logger = logging.getLogger("vetra.orchestrator")


class InterviewOrchestrator:
    """Authoritative Orchestrator managing interview stage progression, guard enforcement,
    dynamic guidance injection, and serialized event dispatch via LangGraph.
    """

    def __init__(self, checkpointer: Optional[BaseCheckpointSaver] = None):
        self.graph = build_interview_graph(checkpointer=checkpointer)
        self._session_locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """Retrieve or create an asyncio.Lock per session to serialize concurrent events."""
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    async def dispatch_event(
        self, session_id: str, event: OrchestratorEvent
    ) -> Dict[str, Any]:
        """Dispatch an event to the LangGraph FSM with per-session async serialization."""
        lock = self._get_lock(session_id)
        async with lock:
            config = {"configurable": {"thread_id": str(session_id)}}
            result = await self.graph.ainvoke(
                {"incoming_event": event.model_dump()},
                config=config,
            )
            return result

    async def initialize_session(
        self,
        session_id: str,
        interview_id: str,
        candidate_name: str,
        initial_stage: str = "INTRO",
    ) -> Dict[str, Any]:
        """Initialize an active interview session in LangGraph."""
        lock = self._get_lock(session_id)
        now = datetime.now(timezone.utc).isoformat()
        initial_state: InterviewState = {
            "session_id": str(session_id),
            "interview_id": str(interview_id),
            "candidate_name": candidate_name,
            "current_stage": initial_stage,
            "incoming_event": None,
            "speech_state": "NORMAL",
            "recovery_required": False,
            "recovery_reason": None,
            "max_recovery_attempts": 2,
            "pending_question_id": None,
            "pending_question_text": None,
            "active_questions": {},
            "stage_question_slots": {s: 0 for s in STAGE_RULES.keys()},
            "delivered_question_counts": {s: 0 for s in STAGE_RULES.keys()},
            "answered_question_counts": {s: 0 for s in STAGE_RULES.keys()},
            "stage_question_counts": {s: 0 for s in STAGE_RULES.keys()},
            "stage_substantive_turn_counts": {s: 0 for s in STAGE_RULES.keys()},
            "total_questions_asked": 0,
            "delivered_question_ids": [],
            "answered_question_ids": [],
            "active_problem_id": None,
            "problem_presented": False,
            "problem_discussed": False,
            "latest_guidance": None,
            "guidance_version": 0,
            "guidance_history": [],
            "competency_coverage": {},
            "pending_objectives": [],
            "completed_objectives": [],
            "stage_history": [
                {
                    "stage": initial_stage,
                    "entered_at": now,
                    "requested_by": "SYSTEM",
                    "reason": "Session initialized",
                }
            ],
            "event_history": [],
            "processed_event_ids": [],
            "last_transition_error": None,
            "last_decision": None,
            "is_completed": False,
        }

        async with lock:
            config = {"configurable": {"thread_id": str(session_id)}}
            result = await self.graph.ainvoke(initial_state, config=config)
            return result

    async def process_transcript_turn(
        self,
        session_id: str,
        speaker: str,
        content: str,
        stage: Optional[str] = None,
        completion_status: str = "complete",
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Authoritative entrypoint for transcript turns into the LangGraph orchestrator."""
        actor: EventActor = "CANDIDATE" if speaker == "CANDIDATE" else "GEMINI"
        event = OrchestratorEvent(
            event_id=event_id or OrchestratorEvent.__fields__["event_id"].default_factory(),
            type="TRANSCRIPT_TURN_COMMITTED",
            actor=actor,
            stage=stage,
            question_text=content,
            completion_status=completion_status,
        )
        return await self.dispatch_event(session_id, event)

    async def record_question_asked(
        self,
        session_id: str,
        question_text: str,
        stage: Optional[str] = None,
        actor: EventActor = "GEMINI",
        event_id: Optional[str] = None,
        completion_status: str = "complete",
    ) -> Dict[str, Any]:
        """Record that an interview question was asked to the candidate."""
        event = OrchestratorEvent(
            event_id=event_id or OrchestratorEvent.__fields__["event_id"].default_factory(),
            type="QUESTION_ASKED",
            actor=actor,
            stage=stage,
            question_text=question_text,
            completion_status=completion_status,
        )
        return await self.dispatch_event(session_id, event)

    async def inject_guidance(
        self,
        session_id: str,
        guidance: GuidancePayload,
        actor: EventActor = "KIMI",
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Inject strategic topic focus, competency targets, or probing objectives."""
        event = OrchestratorEvent(
            event_id=event_id or OrchestratorEvent.__fields__["event_id"].default_factory(),
            type="GUIDANCE_RECEIVED",
            actor=actor,
            payload=guidance.model_dump(),
        )
        return await self.dispatch_event(session_id, event)

    async def present_problem(
        self,
        session_id: str,
        problem_id: str,
        actor: EventActor = "GEMINI",
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mark a technical coding challenge or architecture problem as presented."""
        event = OrchestratorEvent(
            event_id=event_id or OrchestratorEvent.__fields__["event_id"].default_factory(),
            type="PROBLEM_PRESENTED",
            actor=actor,
            problem_id=problem_id,
        )
        return await self.dispatch_event(session_id, event)

    async def mark_problem_discussed(
        self,
        session_id: str,
        problem_id: Optional[str] = None,
        actor: EventActor = "GEMINI",
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Flag that the active technical problem has been sufficiently discussed."""
        event = OrchestratorEvent(
            event_id=event_id or OrchestratorEvent.__fields__["event_id"].default_factory(),
            type="PROBLEM_DISCUSSED",
            actor=actor,
            problem_id=problem_id,
        )
        return await self.dispatch_event(session_id, event)

    async def request_stage_transition(
        self,
        session_id: str,
        target_stage: str,
        requested_by: EventActor = "GEMINI",
        reason: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> TransitionDecision:
        """Validate guard rails and execute a stage transition if permitted."""
        event = OrchestratorEvent(
            event_id=event_id or OrchestratorEvent.__fields__["event_id"].default_factory(),
            type="TRANSITION_REQUESTED",
            actor=requested_by,
            target_stage=target_stage,
            requested_by=requested_by,
            transition_reason=reason,
        )
        result = await self.dispatch_event(session_id, event)
        decision_data = result.get("last_decision") or {}
        decision = TransitionDecision(**decision_data)

        # Best-effort projected update to Supabase session table if allowed
        if decision.allowed:
            self._project_stage_to_supabase(session_id, target_stage)

        return decision

    async def complete_interview(
        self,
        session_id: str,
        requested_by: EventActor = "SYSTEM",
        reason: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Complete the interview session."""
        event = OrchestratorEvent(
            event_id=event_id or OrchestratorEvent.__fields__["event_id"].default_factory(),
            type="INTERVIEW_COMPLETED",
            actor=requested_by,
            requested_by=requested_by,
            transition_reason=reason,
        )
        result = await self.dispatch_event(session_id, event)
        self._project_stage_to_supabase(session_id, "COMPLETED", mark_completed=True)
        return result

    async def get_state(self, session_id: str) -> Optional[InterviewState]:
        """Fetch the latest state snapshot from the checkpointer for a session."""
        config = {"configurable": {"thread_id": str(session_id)}}
        snapshot = self.graph.get_state(config)
        if not snapshot or not snapshot.values:
            return None
        return snapshot.values  # type: ignore

    async def get_state_history(self, session_id: str) -> List[Any]:
        """Fetch chronological checkpoint history for a session."""
        config = {"configurable": {"thread_id": str(session_id)}}
        return list(self.graph.get_state_history(config))

    async def get_interviewer_state(self, session_id: str) -> InterviewerContext:
        """Generate a compact context projection for Gemini Live tool calls."""
        state = await self.get_state(session_id)
        if not state:
            return InterviewerContext(
                stage="INTRO",
                questions_asked_in_stage=0,
                minimum_questions=1,
                transition_eligible=False,
                transition_allowed=False,
            )

        current_stage = state.get("current_stage", "INTRO")
        rule = STAGE_RULES.get(current_stage)
        min_q = rule.min_questions if rule else 0
        max_q = rule.max_questions if rule else 3
        q_count = state.get("stage_question_counts", {}).get(current_stage, 0)

        # Check if currently eligible to advance
        is_eligible = False
        if rule and rule.next_stage:
            decision = validate_transition_guard(state, rule.next_stage)
            is_eligible = decision.allowed

        # Hard ceiling override: If stage question count reached maximum, check eligibility
        # But NEVER override if recovery is pending or question is unanswered!
        if max_q > 0 and q_count >= max_q and not state.get("recovery_required", False) and state.get("pending_question_id") is None:
            is_eligible = True

        guidance_dict = state.get("latest_guidance") or {}
        cov_dict = state.get("competency_coverage") or guidance_dict.get("competency_coverage", {})

        # Compute covered (score/ratio >= 0.8) and missing (< 0.8)
        covered_topics = [
            comp for comp, val in cov_dict.items()
            if (isinstance(val, (int, float)) and val >= 0.8)
        ]
        missing_topics = [
            comp for comp, val in cov_dict.items()
            if (not isinstance(val, (int, float)) or val < 0.8)
        ]
        if not covered_topics and guidance_dict.get("competencies_covered"):
            covered_topics = guidance_dict["competencies_covered"]
        if not missing_topics and guidance_dict.get("competencies_missing"):
            missing_topics = guidance_dict["competencies_missing"]

        rec_probe = guidance_dict.get("recommended_probe")
        instructions = guidance_dict.get("instructions", [])

        pending_qid = state.get("pending_question_id")
        pending_qtext = state.get("pending_question_text")
        active_q = state.get("active_questions", {})
        attempts = 0
        if pending_qid and pending_qid in active_q:
            attempts = active_q[pending_qid].get("recovery_attempts", 0)

        return InterviewerContext(
            stage=current_stage,
            questions_asked_in_stage=q_count,
            minimum_questions=min_q,
            maximum_questions=max_q,
            transition_eligible=is_eligible,
            transition_allowed=is_eligible,
            speech_state=state.get("speech_state", "NORMAL"),
            recovery_required=state.get("recovery_required", False),
            recovery_reason=state.get("recovery_reason"),
            recovery_attempts=attempts,
            max_recovery_attempts=state.get("max_recovery_attempts", 2),
            pending_question_id=pending_qid,
            pending_question_text=pending_qtext,
            active_problem_id=state.get("active_problem_id"),
            problem_presented=state.get("problem_presented", False),
            problem_discussed=state.get("problem_discussed", False),
            guidance=guidance_dict or None,
            competency_coverage=cov_dict,
            competencies_covered=covered_topics,
            competencies_missing=missing_topics,
            pending_objectives=state.get("pending_objectives", []),
            completed_objectives=state.get("completed_objectives", []),
            recommended_probe=rec_probe,
            instructions=instructions,
        )

    def _project_stage_to_supabase(
        self, session_id: str, stage: str, mark_completed: bool = False
    ) -> None:
        """Project authoritative stage transition to Supabase (best-effort projection)."""
        try:
            payload: Dict[str, Any] = {"current_stage": stage}
            if mark_completed:
                payload["status"] = "COMPLETED"
                payload["completed_at"] = datetime.now(timezone.utc).isoformat()

            supabase.table("interview_sessions").update(payload).eq(
                "id", str(session_id)
            ).execute()
        except Exception as err:
            logger.warning(
                f"Failed to project stage update to Supabase for session {session_id}: {err}"
            )


# Default singleton orchestrator instance
interview_orchestrator = InterviewOrchestrator()
