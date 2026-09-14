from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from src.agents.planner_checkpoint import planner_checkpoint_manager
from src.schemas.planner import (
    CandidateProfile,
    GenerateExercisesRequest,
    GeneratePlanRequest,
    GeneratePlanResponse,
    ParseResumeTextRequest,
)
from src.service.planner import planner_service

router = APIRouter(prefix="", tags=["Pre-Interview Generator"])


@router.post(
    "/resume/parse-text",
    response_model=CandidateProfile,
    status_code=status.HTTP_200_OK,
    summary="Parse plain text resume with freeze caching",
)
async def parse_resume_text(data: ParseResumeTextRequest):
    """Parse plain text candidate resume into structured CandidateProfile using Gemini 2.5 Flash,
    with automatic content-based freeze caching.
    """
    return await run_in_threadpool(
        planner_service.parse_resume_text,
        resume_text=data.resume_text,
        force_refresh=data.force_refresh,
    )


@router.post(
    "/resume/parse-file",
    response_model=CandidateProfile,
    status_code=status.HTTP_200_OK,
    summary="Parse PDF resume file with freeze caching",
)
async def parse_resume_file(
    file: UploadFile = File(...),
    force_refresh: bool = Query(default=False, description="Bypass resume freeze cache"),
):
    """Upload PDF resume file to extract structured CandidateProfile via Gemini 2.5 Flash native multimodal parsing,
    with automatic content-based freeze caching.
    """
    if not file.filename.endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF resume files (.pdf) are supported for file parsing.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded PDF file is empty.",
        )

    return await run_in_threadpool(
        planner_service.parse_resume_file,
        file_bytes=content,
        filename=file.filename,
        force_refresh=force_refresh,
    )


@router.post(
    "/interviews/generate-plan",
    response_model=GeneratePlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate candidate-tailored InterviewPlan and coding exercise",
)
async def generate_interview_plan(request: GeneratePlanRequest):
    """Generate structured Candidate-tailored InterviewPlan (questions, dynamic multi-file coding challenge, rubrics)
    from CandidateProfile and Job Specification, using 3-stage checkpointing and asset persistence.
    """
    return await run_in_threadpool(planner_service.generate_interview_plan, request=request)


@router.get(
    "/interviews/planner/checkpoints/{checkpoint_id}",
    status_code=status.HTTP_200_OK,
    summary="Get interview planner checkpoint status and stored assets",
)
async def get_planner_checkpoint(checkpoint_id: str):
    """Retrieve the status, stored exercises, and diagnostic error telemetry of a planner checkpoint."""
    cp = planner_checkpoint_manager.get(checkpoint_id)
    if not cp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint '{checkpoint_id}' not found or has expired.",
        )
    return cp


@router.post(
    "/interviews/generate-exercises",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger in-interview background coding exercise generation",
)
async def trigger_generate_exercises(
    request: GenerateExercisesRequest,
    background_tasks: BackgroundTasks,
):
    """Asynchronously generate and persist technical coding problem and system design challenge
    into Supabase while candidate is participating in live conversational stages.
    """
    background_tasks.add_task(
        planner_service.generate_and_persist_exercises,
        interview_id=request.interview_id,
        session_id=request.session_id,
        checkpoint_id=request.checkpoint_id,
        problem_type=request.problem_type,
        force_refresh=request.force_refresh,
    )
    return {
        "status": "QUEUED",
        "interview_id": str(request.interview_id),
        "session_id": str(request.session_id) if request.session_id else None,
        "message": "Exercise generation dispatched to background worker.",
    }



