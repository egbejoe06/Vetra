import asyncio
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status

from src.models.enums import InterviewStatus
from src.schemas.interview import (
    CandidateResponseCreate,
    CandidateResponseResponse,
    CandidateResponseScore,
    InterviewArtifactCreate,
    InterviewArtifactResponse,
    InterviewCreate,
    InterviewEvaluationCreate,
    InterviewEvaluationResponse,
    InterviewJoin,
    InterviewJoinResponse,
    InterviewResponse,
    InterviewSessionResponse,
    InterviewUpdate,
    SessionStageUpdate,
    SessionStatusUpdate,
    TechnicalProblemCreate,
    TechnicalProblemResponse,
    TranscriptTurnCreate,
    TranscriptTurnResponse,
)
from src.schemas.report import ComprehensiveRecruiterScorecard
from src.service.interview import interview_service
from src.service.report_synthesizer import report_synthesizer

router = APIRouter(prefix="/interviews", tags=["Interviews"])


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


# ==============================================================================
# 1. Recruiter Interview Template Management
# ==============================================================================

@router.post("", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def create_interview(
    data: InterviewCreate,
    recruiter_id: UUID = Query(..., description="UUID of the recruiter creating the interview"),
):
    """
    Create a new interview configuration template with an auto-generated 6-digit access code.
    """
    return interview_service.create_interview(recruiter_id=recruiter_id, data=data)


@router.get("", response_model=List[InterviewResponse], status_code=status.HTTP_200_OK)
async def list_interviews(
    recruiter_id: Optional[str] = Query(None, description="Filter by recruiter UUID"),
    status_filter: Optional[InterviewStatus] = Query(None, alias="status", description="Filter by interview status"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List all interview configurations with optional filters by recruiter, status, and pagination.
    """
    parsed_recruiter_id = _parse_optional_uuid(recruiter_id, "recruiter_id")
    return interview_service.list_interviews(
        recruiter_id=parsed_recruiter_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/code/{room_code}", response_model=InterviewResponse, status_code=status.HTTP_200_OK)
async def get_interview_by_room_code(room_code: str):
    """
    Retrieve interview configuration by its 6-digit access room code.
    """
    return interview_service.get_interview_by_room_code(room_code=room_code)


@router.get("/{interview_id}", response_model=InterviewResponse, status_code=status.HTTP_200_OK)
async def get_interview(interview_id: UUID):
    """
    Retrieve interview configuration by its unique ID.
    """
    return interview_service.get_interview(interview_id=interview_id)


@router.patch("/{interview_id}", response_model=InterviewResponse, status_code=status.HTTP_200_OK)
async def update_interview(
    interview_id: UUID,
    data: InterviewUpdate,
    recruiter_id: Optional[str] = Query(None, description="Optional recruiter UUID for authorization"),
):
    """
    Update interview configuration parameters (e.g. title, duration, question count, focuses).
    """
    parsed_recruiter_id = _parse_optional_uuid(recruiter_id, "recruiter_id")
    return interview_service.update_interview(
        interview_id=interview_id,
        data=data,
        recruiter_id=parsed_recruiter_id,
    )


@router.delete("/{interview_id}", status_code=status.HTTP_200_OK)
async def delete_interview(
    interview_id: UUID,
    recruiter_id: Optional[str] = Query(None, description="Optional recruiter UUID for authorization"),
):
    """
    Delete an interview template and its associated sessions.
    """
    parsed_recruiter_id = _parse_optional_uuid(recruiter_id, "recruiter_id")
    return interview_service.delete_interview(
        interview_id=interview_id,
        recruiter_id=parsed_recruiter_id,
    )


# ==============================================================================
# 2. Candidate Session Joining & Session Lifecycle
# ==============================================================================

@router.post("/join", response_model=InterviewJoinResponse, status_code=status.HTTP_200_OK)
async def join_interview(
    data: InterviewJoin,
    candidate_id: Optional[str] = Query(None, description="Optional registered candidate UUID"),
):
    """
    Validate 6-digit room code, join or resume a candidate session, and transition interview to ACTIVE.
    """
    parsed_candidate_id = _parse_optional_uuid(candidate_id, "candidate_id")
    return interview_service.join_interview_by_code(
        join_data=data,
        candidate_id=parsed_candidate_id,
    )


@router.get("/sessions/{session_id}", response_model=InterviewSessionResponse, status_code=status.HTTP_200_OK)
async def get_session(session_id: UUID):
    """
    Retrieve candidate interview session details by session ID.
    """
    return interview_service.get_session(session_id=session_id)


@router.patch("/sessions/{session_id}/stage", response_model=InterviewSessionResponse, status_code=status.HTTP_200_OK)
async def update_session_stage(session_id: UUID, data: SessionStageUpdate):
    """
    Advance or update the current stage of an ongoing interview session.
    """
    return interview_service.update_session_stage(
        session_id=session_id,
        stage=data.current_stage,
    )


@router.patch("/sessions/{session_id}/status", response_model=InterviewSessionResponse, status_code=status.HTTP_200_OK)
async def update_session_status(session_id: UUID, data: SessionStatusUpdate):
    """
    Update the status of an interview session (e.g. ACTIVE, CANCELLED, COMPLETED).
    """
    return interview_service.update_session_status(
        session_id=session_id,
        status_val=data.status,
    )


@router.post("/sessions/{session_id}/complete", response_model=InterviewSessionResponse, status_code=status.HTTP_200_OK)
async def complete_session(session_id: UUID):
    """
    Mark an active interview session as COMPLETED and trigger Phase 6 report synthesis in the background.
    """
    session_resp = interview_service.complete_session(session_id=session_id)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(report_synthesizer.synthesize_session_report(session_id=session_id))
    except RuntimeError:
        pass
    return session_resp


@router.post("/sessions/{session_id}/synthesize-report", response_model=ComprehensiveRecruiterScorecard, status_code=status.HTTP_200_OK)
async def synthesize_report_endpoint(session_id: UUID):
    """
    Trigger immediate synthesis or re-synthesis of the comprehensive Phase 6 evaluation scorecard with audit trail.
    """
    return await report_synthesizer.synthesize_session_report(session_id=session_id)


# ==============================================================================
# 3. Technical Problems & Coding Exercises
# ==============================================================================

@router.post("/technical-problems", response_model=TechnicalProblemResponse, status_code=status.HTTP_201_CREATED)
async def create_technical_problem(data: TechnicalProblemCreate):
    """
    Create and associate a technical coding challenge or review exercise with an interview session.
    """
    return interview_service.create_technical_problem(data=data)


@router.get("/sessions/{session_id}/technical-problems", response_model=List[TechnicalProblemResponse], status_code=status.HTTP_200_OK)
async def get_technical_problems(session_id: UUID):
    """
    Retrieve all technical problems and code exercises generated for an interview session.
    """
    return interview_service.get_technical_problems(session_id=session_id)


# ==============================================================================
# 4. Interview Artifacts (Codebases, System Architecture Diagrams)
# ==============================================================================

@router.post("/artifacts", response_model=InterviewArtifactResponse, status_code=status.HTTP_201_CREATED)
async def create_artifact(data: InterviewArtifactCreate):
    """
    Save multi-file sample codebase or architecture diagram artifacts for an interview session.
    """
    return interview_service.create_artifact(data=data)


@router.get("/sessions/{session_id}/artifacts", response_model=List[InterviewArtifactResponse], status_code=status.HTTP_200_OK)
async def get_artifacts(session_id: UUID):
    """
    Retrieve all codebase and architectural artifacts created for an interview session.
    """
    return interview_service.get_artifacts_by_session(session_id=session_id)


# ==============================================================================
# 5. Candidate Responses & Scoring
# ==============================================================================

@router.post("/responses", response_model=CandidateResponseResponse, status_code=status.HTTP_201_CREATED)
async def record_candidate_response(data: CandidateResponseCreate):
    """
    Record a candidate's answer or code solution for an interview question / exercise.
    """
    return interview_service.record_candidate_response(data=data)


@router.patch("/responses/{response_id}/score", response_model=CandidateResponseResponse, status_code=status.HTTP_200_OK)
async def score_candidate_response(response_id: UUID, data: CandidateResponseScore):
    """
    Assign a rubric evaluation score (1.0 - 5.0) and optional feedback notes to a recorded answer.
    """
    return interview_service.score_candidate_response(
        response_id=response_id,
        score=data.score,
        evaluation_notes=data.evaluation_notes,
    )


@router.get("/sessions/{session_id}/responses", response_model=List[CandidateResponseResponse], status_code=status.HTTP_200_OK)
async def get_candidate_responses(session_id: UUID):
    """
    Retrieve all recorded candidate answers and scores for an interview session.
    """
    return interview_service.get_candidate_responses(session_id=session_id)


# ==============================================================================
# 6. Dialogue Transcripts
# ==============================================================================

@router.post("/transcripts", response_model=TranscriptTurnResponse, status_code=status.HTTP_201_CREATED)
async def add_transcript_turn(data: TranscriptTurnCreate):
    """
    Log an individual dialogue turn (Interviewer, Candidate, or System) to the session transcript.
    """
    return interview_service.add_transcript_turn(data=data)


@router.get("/sessions/{session_id}/transcript", response_model=List[TranscriptTurnResponse], status_code=status.HTTP_200_OK)
async def get_transcript(session_id: UUID):
    """
    Retrieve full chronological dialogue transcript for an interview session.
    """
    return interview_service.get_transcript(session_id=session_id)


# ==============================================================================
# 7. Post-Interview Evaluations & Recruiter Reports
# ==============================================================================

@router.post("/evaluations", response_model=InterviewEvaluationResponse, status_code=status.HTTP_201_CREATED)
async def save_evaluation(data: InterviewEvaluationCreate):
    """
    Save or update comprehensive scorecard evaluation for a candidate's interview session.
    """
    return interview_service.save_evaluation(data=data)


@router.get("/sessions/{session_id}/evaluation", response_model=InterviewEvaluationResponse, status_code=status.HTTP_200_OK)
async def get_session_evaluation(session_id: UUID):
    """
    Retrieve the evaluation scorecard report for a specific interview session.
    If not yet persisted, triggers on-demand synthesis to generate the scorecard.
    """
    evaluation = interview_service.get_evaluation_by_session(session_id=session_id)
    if not evaluation:
        try:
            # Attempt on-demand synthesis
            scorecard = await report_synthesizer.synthesize_session_report(session_id=session_id)
            if scorecard:
                evaluation = interview_service.get_evaluation_by_session(session_id=session_id)
        except Exception as e:
            pass

    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation report for session '{session_id}' was not found.",
        )
    return evaluation


@router.get("/{interview_id}/evaluations", response_model=List[InterviewEvaluationResponse], status_code=status.HTTP_200_OK)
async def list_interview_evaluations(interview_id: UUID):
    """
    List all candidate evaluation reports associated with an interview template.
    """
    return interview_service.list_evaluations_for_interview(interview_id=interview_id)
