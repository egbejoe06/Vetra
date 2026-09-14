from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.schemas.planner import CandidateProfile


class CandidateResumeMetadata(BaseModel):
    """Metadata regarding candidate's uploaded resume document."""
    filename: str
    uploaded_at: datetime
    file_size_bytes: Optional[int] = None
    resume_hash: str
    experience_years: Optional[int] = None


class CandidateProfileRecord(BaseModel):
    """Full Candidate Profile with stored parsed resume."""
    id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    email: EmailStr
    full_name: Optional[str] = None
    experience_years: Optional[int] = 0
    resume_url: Optional[str] = None
    resume_filename: Optional[str] = None
    resume_hash: Optional[str] = None
    has_resume: bool = False
    parsed_profile: Optional[CandidateProfile] = None
    metadata: Optional[CandidateResumeMetadata] = None
    updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CandidateResumeUploadResponse(BaseModel):
    """Response returned after successful candidate resume upload and parse."""
    status: str = "success"
    message: str
    reused_cache: bool = False
    candidate_profile: CandidateProfileRecord
