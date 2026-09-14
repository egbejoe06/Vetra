from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.enums import InterviewStage, TranscriptSpeaker


class TurnEvidenceRef(BaseModel):
    """Reference to a specific dialogue turn as empirical evidence."""
    turn_id: str = Field(..., description="Sequential turn label (e.g. turn_012) or UUID")
    speaker: TranscriptSpeaker
    stage: InterviewStage
    quote_snippet: str = Field(..., description="Verbatim or near-verbatim quote from candidate")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)


AnswerQuality = Literal["SURFACE_MENTION", "PARTIAL_UNDERSTANDING", "DEMONSTRATED_MASTERY"]


class CompetencyObservation(BaseModel):
    """Granular observation of a candidate's response in a 3-5 turn slice.
    Avoids premature global grading of competencies.
    """
    competency: str = Field(..., description="Target competency (e.g. Concurrency, System Design)")
    polarity: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] = Field(..., description="Directional signal")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this observation")
    answer_quality: AnswerQuality = Field(
        default="PARTIAL_UNDERSTANDING",
        description="Depth of response: SURFACE_MENTION (names technology/approach without explaining mechanism), "
                    "PARTIAL_UNDERSTANDING (explains core mechanism but omits key practical details or edge cases), "
                    "DEMONSTRATED_MASTERY (clearly articulates core mechanisms, causal chains, and practical considerations)",
    )
    missing_concepts: List[str] = Field(
        default_factory=list,
        description="List of specific technical concepts, mechanisms, or invariants omitted or unverified in the candidate's answer",
    )
    recommended_probe: Optional[str] = Field(
        default=None,
        description="Targeted follow-up probe to expose depth on missing or unverified concepts",
    )
    evidence_turn_ids: List[str] = Field(default_factory=list, description="List of turn IDs (e.g. turn_023)")
    rationale: str = Field(..., description="Specific explanation of the observation")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("polarity", mode="before")
    @classmethod
    def normalize_polarity(cls, v: Any) -> str:
        if isinstance(v, str):
            val = v.strip().upper()
            if val in ("POSITIVE", "POS", "+"):
                return "POSITIVE"
            if val in ("NEGATIVE", "NEG", "-"):
                return "NEGATIVE"
            if val in ("NEUTRAL", "NEUT", "MIXED"):
                return "NEUTRAL"
        return "NEUTRAL"

    @field_validator("answer_quality", mode="before")
    @classmethod
    def normalize_answer_quality(cls, v: Any) -> str:
        if isinstance(v, str):
            val = v.strip().upper()
            if "MASTERY" in val or "EXCELLENT" in val or "STRONG" in val:
                return "DEMONSTRATED_MASTERY"
            if "SURFACE" in val or "BUZZWORD" in val or "SUPERFICIAL" in val:
                return "SURFACE_MENTION"
            if "PARTIAL" in val or "BASIC" in val or "MODERATE" in val:
                return "PARTIAL_UNDERSTANDING"
        return "PARTIAL_UNDERSTANDING"

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_obs_confidence(cls, v: Any) -> float:
        if v is None:
            return 0.5
        try:
            val = float(v)
            if 1.0 < val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.5


class InterviewerGuidance(BaseModel):
    """Authoritative guidance compiled from evaluator state and LangGraph guards for Gemini Live."""
    current_stage: str
    objective: str
    competencies_covered: List[str] = Field(
        default_factory=list,
        description="Competencies verified to have sufficient depth (DO NOT REVISIT)",
    )
    competencies_missing: List[str] = Field(
        default_factory=list,
        description="Competencies with partial or zero coverage (PRIORITIZE)",
    )
    candidate_strengths: List[str] = Field(default_factory=list)
    candidate_gaps: List[str] = Field(default_factory=list)
    recommended_probe: Optional[str] = Field(
        default=None,
        description="High-priority concrete follow-up question suggested by the evaluator",
    )
    transition_allowed: bool = False
    transition_reason: Optional[str] = None
    instructions: List[str] = Field(
        default_factory=list,
        description="Actionable directives (e.g. 'Do NOT ask another Redis question; probe concurrent updates')",
    )
    version: int = 1

    model_config = ConfigDict(from_attributes=True)


class CompetencyAssessment(BaseModel):
    """Running aggregate assessment of a competency across the interview."""
    competency: str
    provisional_score: Optional[float] = Field(
        default=None,
        ge=1.0,
        le=5.0,
        description="Provisional score if coverage is sufficient/partial; None if insufficient",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_count: int = Field(default=0, ge=0)
    coverage_status: Literal["INSUFFICIENT", "PARTIAL", "SUFFICIENT"] = "INSUFFICIENT"
    key_findings: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("coverage_status", mode="before")
    @classmethod
    def normalize_coverage_status(cls, v: Any) -> str:
        if isinstance(v, str):
            val = v.strip().upper()
            if val in ("SUFFICIENT", "FULL", "COMPLETE", "HIGH", "SATISFIED"):
                return "SUFFICIENT"
            if val in ("PARTIAL", "MEDIUM", "MODERATE", "SOME"):
                return "PARTIAL"
            if val in ("INSUFFICIENT", "NONE", "ZERO", "LOW", "NOT_COVERED", "NO_COVERAGE", "UNCOVERED", "INCOMPLETE", "N/A"):
                return "INSUFFICIENT"
        return "INSUFFICIENT"

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v: Any) -> float:
        if v is None:
            return 0.5
        try:
            val = float(v)
            if 1.0 < val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.5

    @field_validator("provisional_score", mode="before")
    @classmethod
    def normalize_provisional_score(cls, v: Any) -> Optional[float]:
        if v is None or v == "" or str(v).strip().lower() in ("none", "null", "n/a"):
            return None
        try:
            val = float(v)
            if 1.0 <= val <= 5.0:
                return val
            return None
        except (ValueError, TypeError):
            return None

    @field_validator("evidence_count", mode="before")
    @classmethod
    def normalize_evidence_count(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return max(0, int(v))
        except (ValueError, TypeError):
            return 0


class StrategicProbeObjective(BaseModel):
    """Dynamic high-level probing directive injected into LangGraph orchestrator."""
    id: UUID = Field(default_factory=uuid4)
    topic: str
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    objective: str = Field(..., description="Strategic probing instruction for the interviewer")
    gap_reason: str = Field(..., description="Reason why this probe is necessary")
    suggested_direction: str = Field(..., description="Suggested follow-up angle or scenario")
    competency_target: str
    created_from_turn_id: str = Field(..., description="Turn ID where gap or signal was observed")
    status: Literal["ACTIVE", "SATISFIED", "EXPIRED", "SUPERSEDED"] = "ACTIVE"
    expires_after_turn: Optional[int] = Field(
        default=None,
        description="Absolute turn number after which this probe becomes stale",
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v: Any) -> str:
        if isinstance(v, str):
            val = v.strip().upper()
            if val in ("HIGH", "URGENT", "CRITICAL"):
                return "HIGH"
            if val in ("LOW", "OPTIONAL"):
                return "LOW"
            if val in ("MEDIUM", "MED", "NORMAL"):
                return "MEDIUM"
        return "MEDIUM"

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> str:
        if isinstance(v, str):
            val = v.strip().upper()
            if val in ("ACTIVE", "OPEN", "PENDING"):
                return "ACTIVE"
            if val in ("SATISFIED", "RESOLVED", "ANSWERED", "DONE"):
                return "SATISFIED"
            if val in ("EXPIRED", "STALE"):
                return "EXPIRED"
            if val in ("SUPERSEDED", "REPLACED"):
                return "SUPERSEDED"
        return "ACTIVE"

    @field_validator("id", mode="before")
    @classmethod
    def validate_or_generate_uuid(cls, v: Any) -> UUID:
        if isinstance(v, UUID):
            return v
        if isinstance(v, str) and v.strip():
            try:
                return UUID(v.strip())
            except (ValueError, AttributeError):
                return uuid4()
        return uuid4()


class EvaluatorBatchInput(BaseModel):
    """Input payload provided to the asynchronous evaluator LLM."""
    session_id: UUID
    batch_index: int
    current_stage: InterviewStage
    recent_turns: List[Dict[str, Any]] = Field(
        ...,
        description="Chronological dialogue slice formatted as [{'turn_id': 'turn_001', 'speaker': '...', 'content': '...'}]"
    )
    active_problem: Optional[Dict[str, Any]] = None
    code_diff_summary: Optional[str] = None
    active_competencies: List[str] = Field(default_factory=list)
    existing_assessments: Dict[str, CompetencyAssessment] = Field(default_factory=dict)
    active_probes: List[StrategicProbeObjective] = Field(default_factory=list)
    evaluation_criteria: Optional[str] = None


class EvaluatorBatchOutput(BaseModel):
    """Structured output returned by Kimi or Gemini Evaluator agent."""
    observations: List[CompetencyObservation] = Field(default_factory=list)
    updated_assessments: Dict[str, CompetencyAssessment] = Field(default_factory=dict)
    new_probes: List[StrategicProbeObjective] = Field(default_factory=list)
    satisfied_probe_ids: List[str] = Field(default_factory=list)
    evaluator_reasoning_summary: Optional[str] = None
