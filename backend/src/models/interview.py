from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import (
    CandidateRecommendation,
    CodeLanguage,
    InterviewStage,
    InterviewStatus,
    TranscriptSpeaker,
)


class RubricScore(BaseModel):
    """Evaluation score for a specific rubric category"""
    category: str
    score: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    weight: Optional[float] = None
    feedback: str
    verified_turn_ids: List[str] = Field(default_factory=list)
    evidence_quotes: List[str] = Field(default_factory=list)


class QuestionScore(BaseModel):
    """Evaluation score for a specific interview question"""
    question_id: Optional[UUID] = None
    question_text: str
    score: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    feedback: str
    verified_turn_ids: List[str] = Field(default_factory=list)


class CodeFile(BaseModel):
    """File entry in a code editor snapshot or artifact"""
    path: str
    content: str
    language: CodeLanguage = CodeLanguage.PYTHON
    readonly: bool = False


class CodeSnapshot(BaseModel):
    """Code editor state snapshot"""
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    files: List[CodeFile] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TechnicalProblem(BaseModel):
    """Technical challenge entity mapping to Supabase public.technical_problems"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: Optional[UUID] = None
    interview_id: Optional[UUID] = None
    problem_type: str
    title: str
    prompt_question: str
    context: Optional[str] = None
    code_files: List[CodeFile] = Field(default_factory=list)
    key_discussion_points: List[str] = Field(default_factory=list)
    expected_solution_summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InterviewArtifact(BaseModel):
    """Interview artifact entity mapping to Supabase public.interview_artifacts"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: Optional[UUID] = None
    problem_id: Optional[UUID] = None
    artifact_type: str
    title: str
    content: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Interview(BaseModel):
    """Interview Configuration Entity mapping to Supabase public.interviews"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    recruiter_id: UUID
    job_id: Optional[UUID] = None
    job_title: str
    seniority: Optional[str] = None
    years_of_experience: int = Field(default=0, ge=0)
    room_code: str = Field(..., min_length=6, max_length=8, pattern=r"^\d{6,8}$", description="6-8 digit numeric access code")
    status: InterviewStatus = InterviewStatus.SCHEDULED
    current_stage: InterviewStage = InterviewStage.INTRO
    duration_minutes: int = Field(default=30, ge=10, le=120)
    questions_count: int = Field(default=10, ge=1, le=20)
    technical_focus: List[str] = Field(default_factory=list)
    behavioral_focus: List[str] = Field(default_factory=list)
    instructions: Optional[str] = None
    description: Optional[str] = None
    evaluation_criteria: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None


class InterviewSession(BaseModel):
    """Active Candidate Interview Session mapping to Supabase public.interview_sessions"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    interview_id: UUID
    candidate_id: Optional[UUID] = None
    candidate_name: str
    candidate_email: str
    room_code: str
    current_stage: InterviewStage = InterviewStage.INTRO
    status: InterviewStatus = InterviewStatus.SCHEDULED
    resumption_handle: Optional[str] = None
    resumption_updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CandidateResponse(BaseModel):
    """Candidate's response to a specific technical problem or question"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    problem_id: Optional[UUID] = None
    stage: InterviewStage = InterviewStage.TECHNICAL_EXERCISE
    question_text: str
    candidate_answer: str
    evaluation_notes: Optional[str] = None
    score: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TranscriptTurn(BaseModel):
    """Individual dialogue turn mapping to Supabase public.transcript_turns"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    speaker: TranscriptSpeaker
    stage: InterviewStage
    content: str
    audio_url: Optional[str] = None
    turn_index: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InterviewEvaluation(BaseModel):
    """Post-interview evaluation report mapping to Supabase public.interview_evaluations"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    interview_id: UUID
    candidate_id: Optional[UUID] = None
    candidate_name: str
    overall_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    recommendation: CandidateRecommendation
    summary: str
    key_strengths: List[str] = Field(default_factory=list)
    key_weaknesses: List[str] = Field(default_factory=list)
    rubric_scores: List[RubricScore] = Field(default_factory=list)
    question_scores: List[QuestionScore] = Field(default_factory=list)
    snapshot_id: Optional[UUID] = None
    audit_trail: List[dict] = Field(default_factory=list)
    score_breakdown: dict = Field(default_factory=dict)
    completed_at: datetime = Field(default_factory=datetime.utcnow)
