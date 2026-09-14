import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from src.schemas.candidate import (
    CandidateProfileRecord,
    CandidateResumeUploadResponse,
)
from src.service.candidate import candidate_service

logger = logging.getLogger("vetra.routes.candidate")

router = APIRouter(prefix="/candidate", tags=["Candidate Profile"])


def _parse_optional_uuid(val: Optional[str], field_name: str = "id") -> Optional[UUID]:
    if not val or not val.strip():
        return None
    try:
        return UUID(val.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name} format. Must be a valid UUID.",
        )


@router.get(
    "/profile",
    response_model=CandidateProfileRecord,
    status_code=status.HTTP_200_OK,
    summary="Get candidate profile and stored resume",
)
async def get_candidate_profile(
    candidate_id: Optional[str] = Query(None, description="Candidate or User UUID"),
    email: Optional[str] = Query(None, description="Candidate email address"),
):
    """Retrieve stored Candidate Profile including parsed resume data and skills taxonomy."""
    parsed_uuid = _parse_optional_uuid(candidate_id, "candidate_id")
    return await run_in_threadpool(
        candidate_service.get_candidate_profile,
        candidate_id=parsed_uuid,
        email=email,
    )


@router.post(
    "/profile/resume-file",
    response_model=CandidateResumeUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload PDF resume with automatic parsing and permanent profile storage",
)
async def upload_candidate_resume_file(
    file: UploadFile = File(..., description="Resume PDF file (strictly PDF format)"),
    candidate_id: Optional[str] = Form(None, description="Candidate or User UUID"),
    email: Optional[str] = Form(None, description="Candidate email"),
    full_name: Optional[str] = Form(None, description="Candidate full name"),
    force_refresh: bool = Form(default=False, description="Bypass change-detection cache"),
):
    """Upload a candidate PDF resume file. The resume is automatically parsed via Gemini AI
    multimodal understanding and stored permanently in the candidate's profile.
    
    If the candidate re-uploads the identical resume, it is recognized instantly via content hash
    and re-uses the existing parsed profile without re-invoking the LLM.
    NOTE: Resume text pasting is strictly disallowed; only PDF files are accepted.
    """
    if not file.filename.lower().endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF resume files (.pdf) are supported. Resume text pasting is not allowed.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded resume PDF file is empty.",
        )

    parsed_uuid = _parse_optional_uuid(candidate_id, "candidate_id")

    return await run_in_threadpool(
        candidate_service.upload_candidate_resume_file,
        file_bytes=content,
        filename=file.filename,
        candidate_id=parsed_uuid,
        email=email,
        full_name=full_name,
        force_refresh=force_refresh,
    )


@router.delete(
    "/profile/resume",
    status_code=status.HTTP_200_OK,
    summary="Clear candidate's stored resume from profile",
)
async def delete_candidate_resume(
    candidate_id: Optional[str] = Query(None, description="Candidate or User UUID"),
    email: Optional[str] = Query(None, description="Candidate email"),
):
    """Delete candidate's stored resume and purge from freeze cache."""
    parsed_uuid = _parse_optional_uuid(candidate_id, "candidate_id")
    return await run_in_threadpool(
        candidate_service.delete_candidate_resume,
        candidate_id=parsed_uuid,
        email=email,
    )
