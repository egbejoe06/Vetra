from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr
from src.models.enums import UserRole


class User(BaseModel):
    """Base User Entity Model mapping to Supabase public.users"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole = UserRole.CANDIDATE
    created_at: datetime = datetime.utcnow()
    updated_at: Optional[datetime] = None


class RecruiterProfile(BaseModel):
    """Recruiter Profile entity object"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    company_name: str
    created_at: datetime = datetime.utcnow()


class CandidateUserProfile(BaseModel):
    """Candidate User Profile entity object mapping to public.candidate_profiles"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: Optional[UUID] = None
    email: EmailStr
    full_name: Optional[str] = None
    resume_url: Optional[str] = None
    resume_filename: Optional[str] = None
    resume_hash: Optional[str] = None
    parsed_resume: Optional[dict] = None
    experience_years: Optional[int] = None
    created_at: datetime = datetime.utcnow()
    updated_at: Optional[datetime] = None

