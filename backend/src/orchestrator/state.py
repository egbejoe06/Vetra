from typing import Annotated, Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict
import operator
from pydantic import BaseModel, Field

from src.orchestrator.events import EventActor

InterviewStage = Literal[
    "INTRO",
    "RESUME_DEEP_DIVE",
    "TECHNICAL_QA",
    "TECHNICAL_EXERCISE",
    "BEHAVIORAL",
    "WRAP_UP",
    "COMPLETED",
]


class GuidancePayload(BaseModel):
    """Dynamic topic focus and probing directives injected by Kimi / Interview Planner."""

    topic: str
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    goal: str
    transition_hint: Optional[str] = None
    suggested_direction: Optional[str] = None
    competency_target: Optional[str] = None
    pending_objectives: List[str] = Field(default_factory=list)
    completed_objectives: List[str] = Field(default_factory=list)
    competency_coverage: Dict[str, float] = Field(default_factory=dict)
    competencies_covered: List[str] = Field(default_factory=list)
    competencies_missing: List[str] = Field(default_factory=list)
    candidate_strengths: List[str] = Field(default_factory=list)
    candidate_gaps: List[str] = Field(default_factory=list)
    recommended_probe: Optional[str] = None
    instructions: List[str] = Field(default_factory=list)
    version: int = 1


class TransitionDecision(BaseModel):
    """Structured decision returned for stage transition guard evaluation."""

    allowed: bool
    current_stage: str
    requested_stage: str
    requested_by: EventActor = "GEMINI"
    reason: Optional[str] = None
    remaining_questions: int = 0
    next_allowed_stage: Optional[str] = None


class InterviewerContext(BaseModel):
    """Compact state projection consumed by Gemini Live tool calls (get_interviewer_state)."""

    stage: str
    questions_asked_in_stage: int
    minimum_questions: int
    maximum_questions: int = 3
    transition_eligible: bool
    transition_allowed: bool = False
    active_problem_id: Optional[str] = None
    problem_presented: bool = False
    problem_discussed: bool = False
    guidance: Optional[Dict[str, Any]] = None
    competency_coverage: Dict[str, float] = Field(default_factory=dict)
    competencies_covered: List[str] = Field(default_factory=list)
    competencies_missing: List[str] = Field(default_factory=list)
    pending_objectives: List[str] = Field(default_factory=list)
    completed_objectives: List[str] = Field(default_factory=list)
    recommended_probe: Optional[str] = None
    instructions: List[str] = Field(default_factory=list)


class InterviewState(TypedDict):
    """Authoritative LangGraph state schema for an active interview session."""

    session_id: str
    interview_id: str
    candidate_name: str
    current_stage: str
    incoming_event: Optional[Dict[str, Any]]

    # Stage tracking
    stage_question_counts: Dict[str, int]
    stage_substantive_turn_counts: Dict[str, int]
    total_questions_asked: int

    # Technical exercise
    active_problem_id: Optional[str]
    problem_presented: bool
    problem_discussed: bool

    # Planner / Kimi guidance
    latest_guidance: Optional[Dict[str, Any]]
    guidance_version: int
    guidance_history: Annotated[List[Dict[str, Any]], operator.add]

    # Evaluation coverage & objectives
    competency_coverage: Dict[str, float]
    pending_objectives: List[str]  # Overwrite semantics (not operator.add)
    completed_objectives: Annotated[List[str], operator.add]

    # Audit trail & idempotency
    stage_history: Annotated[List[Dict[str, Any]], operator.add]
    event_history: Annotated[List[Dict[str, Any]], operator.add]
    processed_event_ids: Annotated[List[str], operator.add]

    # Transition state & lifecycle
    last_transition_error: Optional[str]
    last_decision: Optional[Dict[str, Any]]
    is_completed: bool
