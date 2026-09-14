from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from src.models.enums import (
    ArtifactType,
    CandidateRecommendation,
    CodeLanguage,
    InterviewStage,
    InterviewStatus,
    QuestionDifficulty,
    TechnicalProblemType,
    TranscriptSpeaker,
)
from src.models.interview import CodeFile, QuestionScore, RubricScore


class TechnicalProblemCreate(BaseModel):
    session_id: Optional[UUID] = None
    interview_id: Optional[UUID] = None
    problem_type: TechnicalProblemType
    title: str
    prompt_question: str
    context: Optional[str] = None
    code_files: List[CodeFile] = Field(default_factory=list)
    key_discussion_points: List[str] = Field(default_factory=list)
    expected_solution_summary: Optional[str] = None


class TechnicalProblemResponse(BaseModel):
    id: UUID
    session_id: Optional[UUID] = None
    interview_id: Optional[UUID] = None
    problem_type: TechnicalProblemType
    title: str
    prompt_question: str
    context: Optional[str] = None
    code_files: List[CodeFile] = Field(default_factory=list)
    key_discussion_points: List[str] = Field(default_factory=list)
    expected_solution_summary: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InterviewArtifactCreate(BaseModel):
    session_id: Optional[UUID] = None
    problem_id: Optional[UUID] = None
    artifact_type: ArtifactType
    title: str
    content: Dict[str, Any] = Field(default_factory=dict)


class InterviewArtifactResponse(BaseModel):
    id: UUID
    session_id: Optional[UUID] = None
    problem_id: Optional[UUID] = None
    artifact_type: ArtifactType
    title: str
    content: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)



class InterviewCreate(BaseModel):
    job_title: str
    job_id: Optional[UUID] = None
    seniority: Optional[QuestionDifficulty] = None
    years_of_experience: int = Field(default=0, ge=0)
    questions_count: int = Field(default=10, ge=1, le=20)
    duration_minutes: int = Field(default=30, ge=10, le=120)
    technical_focus: list[str] = Field(default_factory=list)
    behavioral_focus: list[str] = Field(default_factory=list)
    instructions: Optional[str] = None
    description: Optional[str] = None
    evaluation_criteria: Optional[str] = None

    @field_validator("seniority", mode="before")
    @classmethod
    def normalize_seniority(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().upper()
            for d in QuestionDifficulty:
                if d.value == clean or d.name == clean:
                    return d
        return v


class CandidateResponseCreate(BaseModel):
    session_id: UUID
    problem_id: Optional[UUID] = None
    stage: InterviewStage = InterviewStage.TECHNICAL_EXERCISE
    question_text: str
    candidate_answer: str


class CandidateResponseScore(BaseModel):
    score: float = Field(..., ge=1.0, le=5.0, description="Evaluation score between 1.0 and 5.0")
    evaluation_notes: Optional[str] = Field(default=None, description="Detailed feedback or scoring justification")


class CandidateResponseResponse(BaseModel):
    id: UUID
    session_id: UUID
    problem_id: Optional[UUID] = None
    stage: InterviewStage
    question_text: str
    candidate_answer: str
    evaluation_notes: Optional[str] = None
    score: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InterviewJoin(BaseModel):
    room_code: str = Field(..., min_length=6, max_length=8, pattern=r"^\d{6,8}$", description="6 to 8 digit numeric room entry code")
    candidate_name: str
    email: Optional[EmailStr] = None
    candidate_email: Optional[EmailStr] = None
    redo: Optional[bool] = Field(default=False, description="Whether to start a fresh attempt / redo the interview")

    @model_validator(mode="after")
    def validate_email_required(self):
        if not self.email and not self.candidate_email:
            raise ValueError("Candidate email address is required to join an interview.")
        return self


class InterviewJoinResponse(BaseModel):
    session: dict
    interview: dict
    candidate_profile: Optional[dict] = None
    message: str


class InterviewUpdate(BaseModel):
    job_title: Optional[str] = None
    seniority: Optional[QuestionDifficulty] = None
    duration_minutes: Optional[int] = Field(default=None, ge=10, le=120)
    questions_count: Optional[int] = Field(default=None, ge=1, le=20)
    technical_focus: Optional[list[str]] = None
    behavioral_focus: Optional[list[str]] = None
    instructions: Optional[str] = None
    description: Optional[str] = None
    evaluation_criteria: Optional[str] = None

    @field_validator("seniority", mode="before")
    @classmethod
    def normalize_seniority(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().upper()
            for d in QuestionDifficulty:
                if d.value == clean or d.name == clean:
                    return d
        return v


class InterviewResponse(BaseModel):
    id: UUID
    recruiter_id: UUID
    job_id: Optional[UUID] = None
    job_title: str
    seniority: Optional[QuestionDifficulty] = None
    years_of_experience: int
    room_code: str  # 6-digit generated access code
    status: InterviewStatus
    current_stage: InterviewStage
    duration_minutes: int
    questions_count: int
    technical_focus: list[str]
    behavioral_focus: list[str]
    instructions: Optional[str] = None
    description: Optional[str] = None
    evaluation_criteria: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class InterviewSessionCreate(BaseModel):
    interview_id: UUID
    candidate_id: Optional[UUID] = None
    candidate_name: str
    candidate_email: EmailStr


class InterviewSessionResponse(BaseModel):
    id: UUID
    interview_id: UUID
    candidate_id: Optional[UUID] = None
    candidate_name: str
    candidate_email: str
    room_code: str
    current_stage: InterviewStage
    status: InterviewStatus
    resumption_handle: Optional[str] = None
    resumption_updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionStageUpdate(BaseModel):
    current_stage: InterviewStage


class SessionStatusUpdate(BaseModel):
    status: InterviewStatus


class TranscriptTurnCreate(BaseModel):
    session_id: UUID
    speaker: TranscriptSpeaker
    stage: InterviewStage
    content: str
    audio_url: Optional[str] = None


class TranscriptTurnResponse(BaseModel):
    id: UUID
    session_id: UUID
    speaker: TranscriptSpeaker
    stage: InterviewStage
    content: str
    audio_url: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InterviewEvaluationCreate(BaseModel):
    session_id: UUID
    interview_id: UUID
    candidate_id: Optional[UUID] = None
    candidate_name: str
    overall_score: float = Field(..., ge=0.0, le=10.0)
    recommendation: CandidateRecommendation
    summary: str
    key_strengths: List[str] = Field(default_factory=list)
    key_weaknesses: List[str] = Field(default_factory=list)
    rubric_scores: List[RubricScore] = Field(default_factory=list)
    question_scores: List[QuestionScore] = Field(default_factory=list)
    snapshot_id: Optional[UUID] = None
    audit_trail: Optional[List[Dict[str, Any]]] = None
    score_breakdown: Optional[Dict[str, Any]] = None


class InterviewEvaluationResponse(BaseModel):
    id: UUID
    session_id: UUID
    interview_id: UUID
    candidate_id: Optional[UUID] = None
    candidate_name: str
    overall_score: float = Field(..., ge=0.0, le=10.0)
    recommendation: CandidateRecommendation
    summary: str
    key_strengths: List[str]
    key_weaknesses: List[str]
    rubric_scores: List[RubricScore]
    question_scores: List[QuestionScore]
    snapshot_id: Optional[UUID] = None
    audit_trail: Optional[List[Dict[str, Any]]] = None
    score_breakdown: Optional[Dict[str, Any]] = None
    completed_at: datetime

    model_config = ConfigDict(from_attributes=True)

