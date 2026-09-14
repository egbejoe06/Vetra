from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import CandidateRecommendation


class InterviewSynthesisSnapshot(BaseModel):
    """Immutable snapshot of all transcript turns, code states, and evaluation signals
    frozen at the exact moment of session completion.
    """
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    transcript_version: int = 1
    transcript_turn_ids: List[str] = Field(default_factory=list, description="List of turn UUIDs")
    turn_labels: List[str] = Field(default_factory=list, description="List of sequential labels: turn_001, turn_002...")
    code_snapshot_ids: List[UUID] = Field(default_factory=list)
    evaluation_signal_ids: List[UUID] = Field(default_factory=list)
    stages_reached: List[str] = Field(default_factory=list, description="Stages that occurred in the session transcript")
    stages_not_reached: List[str] = Field(default_factory=list, description="Stages that were never reached before the session concluded")
    blueprint_version: str = "v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)


class AuditTrailItem(BaseModel):
    """Internal model telemetry record capturing verification or rejection of claims and turn citations."""
    claim: str
    original_citation: str = Field(..., description="e.g. turn_045 or quoted text")
    resolution: Literal["VERIFIED", "REJECTED", "MODIFIED"]
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)


class GroundedRubricScore(BaseModel):
    """Category assessment with deterministic weight and empirically verified turn citations."""
    category: str
    score: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    weight: float = Field(default=0.0, ge=0.0, le=1.0)
    status: str = Field(default="ASSESSED", description="'ASSESSED' or 'NOT_ASSESSED'")
    feedback: str
    verified_turn_ids: List[str] = Field(default_factory=list)
    evidence_quotes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class GroundedQuestionScore(BaseModel):
    """Question or exercise score backed by verified dialogue evidence."""
    question_text: str
    score: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    status: str = Field(default="ASSESSED", description="'ASSESSED' or 'NOT_ASSESSED'")
    feedback: str
    verified_turn_ids: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ScoreBreakdown(BaseModel):
    """Deterministic mathematical audit breakdown of the overall score."""
    weights: Dict[str, float]
    raw_category_scores: Dict[str, float]
    weighted_composite: float
    calibrated_overall_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    assessed_categories: List[str] = Field(default_factory=list)
    unassessed_categories: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ComprehensiveRecruiterScorecard(BaseModel):
    """Complete post-interview recruiter evaluation report with calibrated deterministic scoring,
    evidence-grounded strengths/weaknesses, and an audit trail for citations.
    """
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    interview_id: UUID
    candidate_id: Optional[UUID] = None
    candidate_name: str
    overall_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    score_breakdown: ScoreBreakdown
    recommendation: CandidateRecommendation
    summary: str
    key_strengths: List[str] = Field(default_factory=list)
    key_weaknesses: List[str] = Field(default_factory=list)
    rubric_scores: List[GroundedRubricScore] = Field(default_factory=list)
    question_scores: List[GroundedQuestionScore] = Field(default_factory=list)
    completion_status: str = Field(default="COMPLETED", description="'COMPLETED' or 'INCOMPLETE'")
    stages_completed: List[str] = Field(default_factory=list)
    stages_not_reached: List[str] = Field(default_factory=list)
    audit_trail: List[AuditTrailItem] = Field(default_factory=list)
    snapshot_id: Optional[UUID] = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)
