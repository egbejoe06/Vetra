from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
import uuid
from pydantic import BaseModel, Field

EventType = Literal[
    "SESSION_INITIALIZED",
    "QUESTION_ASKED",
    "TRANSCRIPT_TURN_COMMITTED",
    "QUESTION_STARTED",
    "QUESTION_DELIVERED",
    "QUESTION_INTERRUPTED",
    "CANDIDATE_TURN_EVALUATED",
    "RECOVERY_TRIGGERED",
    "RECOVERY_RESOLVED",
    "RECOVERY_EXHAUSTED",
    "GUIDANCE_RECEIVED",
    "PROBLEM_PRESENTED",
    "PROBLEM_DISCUSSED",
    "TRANSITION_REQUESTED",
    "INTERVIEW_COMPLETED",
]

EventActor = Literal[
    "GEMINI",
    "KIMI",
    "SYSTEM",
    "RECRUITER",
    "CANDIDATE",
]


class OrchestratorEvent(BaseModel):
    """Authoritative event driving LangGraph state machine mutations."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType
    actor: EventActor = "GEMINI"
    stage: Optional[str] = None
    question_text: Optional[str] = None
    question_id: Optional[str] = None
    completion_status: Optional[str] = None
    candidate_intent: Optional[str] = None
    recovery_reason: Optional[str] = None
    is_substantive: Optional[bool] = None
    target_stage: Optional[str] = None
    requested_by: Optional[EventActor] = None
    transition_reason: Optional[str] = None
    problem_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
