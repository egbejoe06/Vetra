from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from uuid import UUID
from datetime import datetime

class UserCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50, description="User's first name")
    last_name: str = Field(..., min_length=1, max_length=50, description="User's last name")
    email: EmailStr = Field(..., description="User's valid email address")
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    role: Literal["candidate", "recruiter"] = "candidate"

class UserLogin(BaseModel):
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=1, description="User's password")

class UserResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    user: Optional[UserResponse] = None


class RecruiterCreate(BaseModel):
    user_id: UUID
    company_name: str


class CandidateCreate(BaseModel):
    user_id: UUID
    resume_url: Optional[str] = None
    experience_years: Optional[int] = None


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[Literal["candidate", "recruiter"]] = None


class CandidateResponse(BaseModel):
    id: UUID
    user_id: UUID
    resume_url: Optional[str] = None
    experience_years: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecruiterResponse(BaseModel):
    id: UUID
    user_id: UUID
    company_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)