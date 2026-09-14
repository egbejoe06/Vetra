import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from supabase import Client

logger = logging.getLogger(__name__)

from src.db.supabase import supabase
from src.models.enums import (
    CandidateRecommendation,
    InterviewStage,
    InterviewStatus,
    TranscriptSpeaker,
)
from src.schemas.interview import (
    CandidateResponseCreate,
    InterviewArtifactCreate,
    InterviewCreate,
    InterviewEvaluationCreate,
    InterviewJoin,
    InterviewUpdate,
    SessionStageUpdate,
    SessionStatusUpdate,
    TechnicalProblemCreate,
    TranscriptTurnCreate,
)


class InterviewService:
    """Comprehensive Interview Service managing interview lifecycles, access codes,
    candidate sessions, technical problems, transcript turns, and evaluations.
    """

    def __init__(self, client: Client = supabase):
        self.supabase = client

    # --------------------------------------------------------------------------
    # 1. Room Code Generation
    # --------------------------------------------------------------------------

    def generate_unique_room_code(self, max_attempts: int = 10) -> str:
        """Generate a cryptographically secure, unique 6-digit numeric room code."""
        for _ in range(max_attempts):
            code = str(secrets.randbelow(900000) + 100000)  # 100000 to 999999
            # Check if code already exists in active or scheduled interviews
            res = (
                self.supabase.table("interviews")
                .select("id")
                .eq("room_code", code)
                .neq("status", InterviewStatus.COMPLETED.value)
                .neq("status", InterviewStatus.CANCELLED.value)
                .execute()
            )
            if not res.data:
                return code

        # Fallback to 8-digit numeric code if 6-digit namespace has high collisions
        return str(secrets.randbelow(90000000) + 10000000)

    # --------------------------------------------------------------------------
    # 2. Interview Template Management (Recruiter actions)
    # --------------------------------------------------------------------------

    def create_interview(
        self, recruiter_id: UUID, data: InterviewCreate
    ) -> Dict[str, Any]:
        """Create a new interview configuration with an auto-generated 6-digit access code."""
        try:
            room_code = self.generate_unique_room_code()
            payload = {
                "recruiter_id": str(recruiter_id),
                "job_id": str(data.job_id) if data.job_id else None,
                "job_title": data.job_title,
                "years_of_experience": data.years_of_experience,
                "room_code": room_code,
                "status": InterviewStatus.SCHEDULED.value,
                "current_stage": InterviewStage.INTRO.value,
                "duration_minutes": data.duration_minutes,
                "questions_count": data.questions_count,
                "technical_focus": data.technical_focus,
                "behavioral_focus": data.behavioral_focus,
                "instructions": data.instructions,
                "description": data.description,
                "evaluation_criteria": data.evaluation_criteria,
            }
            if data.seniority is not None:
                payload["seniority"] = data.seniority.value if hasattr(data.seniority, "value") else str(data.seniority)

            try:
                res = self.supabase.table("interviews").insert(payload).execute()
            except Exception as insert_err:
                err_msg = str(insert_err)
                retry_needed = False
                if "evaluation_criteria" in err_msg and "evaluation_criteria" in payload:
                    logger.warning("Remote 'interviews' table does not have 'evaluation_criteria' column yet. Falling back to insert without it.")
                    payload.pop("evaluation_criteria", None)
                    retry_needed = True
                if "seniority" in err_msg and "seniority" in payload:
                    logger.warning("Remote 'interviews' table does not have 'seniority' column yet. Falling back to insert without it.")
                    payload.pop("seniority", None)
                    retry_needed = True

                if retry_needed:
                    res = self.supabase.table("interviews").insert(payload).execute()
                else:
                    raise insert_err

            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to create interview configuration.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Failed to create interview")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred while creating the interview: {str(e)}",
            )

    def get_interview(self, interview_id: UUID) -> Dict[str, Any]:
        """Retrieve interview details by ID."""
        try:
            res = (
                self.supabase.table("interviews")
                .select("*")
                .eq("id", str(interview_id))
                .execute()
            )
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Interview with ID '{interview_id}' was not found.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving interview: {str(e)}",
            )

    def get_interview_by_room_code(self, room_code: str) -> Dict[str, Any]:
        """Retrieve interview configuration by its 6-digit room code."""
        try:
            res = (
                self.supabase.table("interviews")
                .select("*")
                .eq("room_code", room_code)
                .execute()
            )
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No interview found for room code '{room_code}'.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving interview by room code: {str(e)}",
            )

    def list_interviews(
        self,
        recruiter_id: Optional[UUID] = None,
        status_filter: Optional[InterviewStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List all interviews with optional recruiter filter, status filter, and pagination."""
        try:
            query = self.supabase.table("interviews").select("*")
            if recruiter_id:
                query = query.eq("recruiter_id", str(recruiter_id))
            if status_filter:
                query = query.eq("status", status_filter.value)

            res = (
                query.order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
            return res.data or []
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error listing interviews: {str(e)}",
            )

    def update_interview(
        self,
        interview_id: UUID,
        data: InterviewUpdate,
        recruiter_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Update interview parameters (only non-None values)."""
        try:
            # Build update payload dynamically
            payload: Dict[str, Any] = {
                k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None
            }
            if not payload:
                return self.get_interview(interview_id)

            payload["updated_at"] = datetime.now(timezone.utc).isoformat()

            query = self.supabase.table("interviews").update(payload).eq("id", str(interview_id))
            if recruiter_id:
                query = query.eq("recruiter_id", str(recruiter_id))

            try:
                res = query.execute()
            except Exception as update_err:
                err_msg = str(update_err)
                retry_needed = False
                if "evaluation_criteria" in err_msg and "evaluation_criteria" in payload:
                    logger.warning("Remote 'interviews' table does not have 'evaluation_criteria' column yet. Falling back to update without it.")
                    payload.pop("evaluation_criteria", None)
                    retry_needed = True
                if "seniority" in err_msg and "seniority" in payload:
                    logger.warning("Remote 'interviews' table does not have 'seniority' column yet. Falling back to update without it.")
                    payload.pop("seniority", None)
                    retry_needed = True

                if retry_needed:
                    query = self.supabase.table("interviews").update(payload).eq("id", str(interview_id))
                    if recruiter_id:
                        query = query.eq("recruiter_id", str(recruiter_id))
                    res = query.execute()
                else:
                    raise update_err

            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Interview '{interview_id}' not found or unauthorized.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error updating interview: {str(e)}",
            )

    def delete_interview(
        self, interview_id: UUID, recruiter_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Delete an interview and its related sessions / data with resilient cascading."""
        try:
            # 1. Verify existence and authorization
            check = self.supabase.table("interviews").select("id, recruiter_id, job_title").eq("id", str(interview_id)).execute()
            if not check.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Interview '{interview_id}' not found.",
                )
            
            interview_row = check.data[0]
            if recruiter_id and str(interview_row.get("recruiter_id")) != str(recruiter_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to delete this interview.",
                )

            # 2. Resilient child cleanup in case DB does not have CASCADE enabled
            try:
                # Find all associated sessions
                sessions_res = self.supabase.table("interview_sessions").select("id").eq("interview_id", str(interview_id)).execute()
                session_ids = [s["id"] for s in (sessions_res.data or []) if "id" in s]

                for sid in session_ids:
                    # Clean up session-dependent records safely
                    for tbl in [
                        "transcript_turns",
                        "candidate_responses",
                        "interview_artifacts",
                        "evaluation_signals",
                        "evaluation_jobs",
                        "synthesis_snapshots",
                    ]:
                        try:
                            self.supabase.table(tbl).delete().eq("session_id", sid).execute()
                        except Exception:
                            pass

                # Delete sessions
                if session_ids:
                    self.supabase.table("interview_sessions").delete().eq("interview_id", str(interview_id)).execute()
            except Exception as e:
                logger.warning(f"Note during session cleanup for interview '{interview_id}': {e}")

            # Clean up interview-level children
            for tbl in ["technical_problems", "interview_evaluations"]:
                try:
                    self.supabase.table(tbl).delete().eq("interview_id", str(interview_id)).execute()
                except Exception:
                    pass

            # 3. Delete the interview itself
            res = self.supabase.table("interviews").delete().eq("id", str(interview_id)).execute()
            return {
                "message": f"Interview '{interview_row.get('job_title', str(interview_id))}' successfully deleted.",
                "id": str(interview_id),
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error deleting interview: {str(e)}",
            )

    # --------------------------------------------------------------------------
    # 3. Candidate Session Joining & Session Lifecycle
    # --------------------------------------------------------------------------

    def join_interview_by_code(
        self, join_data: InterviewJoin, candidate_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Validate 6-digit room code, join or create a candidate session, and transition
        interview state to ACTIVE.
        """
        try:
            # 1. Fetch interview by room code
            interview = self.get_interview_by_room_code(join_data.room_code)

            if interview["status"] in [InterviewStatus.COMPLETED.value, InterviewStatus.CANCELLED.value]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot join interview. The interview session is {interview['status']}.",
                )

            interview_id = interview["id"]

            # 2. Resolve candidate email (email or candidate_email)
            resolved_email = join_data.email or join_data.candidate_email
            if not resolved_email or not str(resolved_email).strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Candidate email address is required to join an interview.",
                )
            resolved_email = str(resolved_email).strip()

            # Check if an active or scheduled session already exists for this candidate email
            existing_session = (
                self.supabase.table("interview_sessions")
                .select("*")
                .eq("interview_id", interview_id)
                .eq("candidate_email", resolved_email)
                .order("created_at", desc=True)
                .execute()
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            session = None

            # Only resume if NOT a redo and the latest session is still ongoing/scheduled
            if existing_session.data and not join_data.redo:
                latest_session = existing_session.data[0]
                if latest_session["status"] in (InterviewStatus.SCHEDULED.value, InterviewStatus.ACTIVE.value):
                    session = latest_session
                    if session["status"] == InterviewStatus.SCHEDULED.value:
                        upd = (
                            self.supabase.table("interview_sessions")
                            .update({
                                "status": InterviewStatus.ACTIVE.value,
                                "started_at": now_iso,
                            })
                            .eq("id", session["id"])
                            .execute()
                        )
                        session = upd.data[0] if upd.data else session

            # If no active/resumable session exists or if redo was explicitly requested, create a fresh session
            if not session:
                session_payload = {
                    "interview_id": interview_id,
                    "candidate_id": str(candidate_id) if candidate_id else None,
                    "candidate_name": join_data.candidate_name,
                    "candidate_email": resolved_email,
                    "room_code": join_data.room_code,
                    "current_stage": InterviewStage.INTRO.value,
                    "status": InterviewStatus.ACTIVE.value,
                    "started_at": now_iso,
                }
                res = self.supabase.table("interview_sessions").insert(session_payload).execute()
                if not res.data:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to initialize interview session.",
                    )
                session = res.data[0]

            # 3. Mark parent interview as ACTIVE if it was SCHEDULED
            if interview["status"] == InterviewStatus.SCHEDULED.value:
                self.supabase.table("interviews").update({
                    "status": InterviewStatus.ACTIVE.value,
                    "updated_at": now_iso,
                }).eq("id", interview_id).execute()

            # 4. Attach stored candidate profile if available
            cand_profile_data = None
            try:
                from src.service.candidate import candidate_service
                cand_record = candidate_service.get_candidate_profile(
                    candidate_id=candidate_id,
                    email=resolved_email,
                )
                if cand_record.has_resume and cand_record.parsed_profile:
                    cand_profile_data = cand_record.model_dump(mode="json")
            except Exception as cand_err:
                logger.debug(f"Candidate profile pre-fetch on join bypassed: {cand_err}")

            return {
                "session": session,
                "interview": interview,
                "candidate_profile": cand_profile_data,
                "message": "Joined interview room successfully.",
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error joining interview: {str(e)}",
            )

    def get_session(self, session_id: UUID) -> Dict[str, Any]:
        """Retrieve interview session by ID."""
        try:
            res = (
                self.supabase.table("interview_sessions")
                .select("*")
                .eq("id", str(session_id))
                .execute()
            )
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Interview session '{session_id}' not found.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving session: {str(e)}",
            )

    def update_session_stage(
        self, session_id: UUID, stage: InterviewStage
    ) -> Dict[str, Any]:
        """Advance or update the current stage of an interview session."""
        try:
            res = (
                self.supabase.table("interview_sessions")
                .update({"current_stage": stage.value})
                .eq("id", str(session_id))
                .execute()
            )
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session '{session_id}' not found.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error updating session stage: {str(e)}",
            )

    def update_session_status(
        self, session_id: UUID, status_val: InterviewStatus
    ) -> Dict[str, Any]:
        """Update interview session status (e.g. ACTIVE, CANCELLED, COMPLETED)."""
        try:
            payload: Dict[str, Any] = {"status": status_val.value}
            if status_val == InterviewStatus.COMPLETED:
                payload["completed_at"] = datetime.now(timezone.utc).isoformat()

            res = (
                self.supabase.table("interview_sessions")
                .update(payload)
                .eq("id", str(session_id))
                .execute()
            )
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session '{session_id}' not found.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error updating session status: {str(e)}",
            )

    def complete_session(self, session_id: UUID) -> Dict[str, Any]:
        """Mark an interview session as COMPLETED."""
        return self.update_session_status(session_id, InterviewStatus.COMPLETED)

    # --------------------------------------------------------------------------
    # 4. Technical Problems & Code Exercises
    # --------------------------------------------------------------------------

    def create_technical_problem(
        self, data: TechnicalProblemCreate
    ) -> Dict[str, Any]:
        """Store a technical coding problem / review challenge for an interview session."""
        try:
            payload = {
                "session_id": str(data.session_id) if data.session_id else None,
                "interview_id": str(data.interview_id) if data.interview_id else None,
                "problem_type": data.problem_type.value,
                "title": data.title,
                "prompt_question": data.prompt_question,
                "context": data.context,
                "code_files": [f.model_dump() for f in data.code_files],
                "key_discussion_points": data.key_discussion_points,
                "expected_solution_summary": data.expected_solution_summary,
            }
            res = self.supabase.table("technical_problems").insert(payload).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to create technical problem.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating technical problem: {str(e)}",
            )

    def get_technical_problems(self, session_id: UUID) -> List[Dict[str, Any]]:
        """Retrieve all technical problems associated with an interview session, with interview_id fallback."""
        try:
            res = (
                self.supabase.table("technical_problems")
                .select("*")
                .eq("session_id", str(session_id))
                .order("created_at", desc=False)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return res.data

            # Fallback: Check parent interview template
            sess_res = (
                self.supabase.table("interview_sessions")
                .select("interview_id")
                .eq("id", str(session_id))
                .limit(1)
                .execute()
            )
            if sess_res.data and len(sess_res.data) > 0:
                interview_id = sess_res.data[0].get("interview_id")
                if interview_id:
                    p_res = (
                        self.supabase.table("technical_problems")
                        .select("*")
                        .eq("interview_id", str(interview_id))
                        .order("created_at", desc=True)
                        .execute()
                    )
                    if p_res.data and len(p_res.data) > 0:
                        # Auto-link this session to the latest problem
                        problem_id = p_res.data[0]["id"]
                        try:
                            self.supabase.table("technical_problems").update(
                                {"session_id": str(session_id)}
                            ).eq("id", str(problem_id)).execute()
                        except Exception:
                            pass
                        return p_res.data

            return []
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving technical problems: {str(e)}",
            )

    # --------------------------------------------------------------------------
    # 5. Interview Artifacts (Sample Codebases, Diagrams)
    # --------------------------------------------------------------------------

    def create_artifact(self, data: InterviewArtifactCreate) -> Dict[str, Any]:
        """Save a multi-file sample codebase or architecture diagram artifact."""
        try:
            payload = {
                "session_id": str(data.session_id) if data.session_id else None,
                "problem_id": str(data.problem_id) if data.problem_id else None,
                "artifact_type": data.artifact_type.value,
                "title": data.title,
                "content": data.content,
            }
            res = self.supabase.table("interview_artifacts").insert(payload).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to save interview artifact.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error saving artifact: {str(e)}",
            )

    def get_artifacts_by_session(self, session_id: UUID) -> List[Dict[str, Any]]:
        """Fetch all artifacts created for an interview session."""
        try:
            res = (
                self.supabase.table("interview_artifacts")
                .select("*")
                .eq("session_id", str(session_id))
                .order("created_at", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving artifacts: {str(e)}",
            )

    # --------------------------------------------------------------------------
    # 6. Candidate Responses & Live Scoring
    # --------------------------------------------------------------------------

    def record_candidate_response(
        self, data: CandidateResponseCreate
    ) -> Dict[str, Any]:
        """Record candidate's answer or code solution for a question / exercise."""
        try:
            payload = {
                "session_id": str(data.session_id),
                "problem_id": str(data.problem_id) if data.problem_id else None,
                "stage": data.stage.value,
                "question_text": data.question_text,
                "candidate_answer": data.candidate_answer,
            }
            res = self.supabase.table("candidate_responses").insert(payload).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to record candidate response.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error recording candidate response: {str(e)}",
            )

    def score_candidate_response(
        self, response_id: UUID, score: float, evaluation_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Assign rubric score (1.0 - 5.0) and evaluation notes to a recorded answer."""
        try:
            payload: Dict[str, Any] = {"score": score}
            if evaluation_notes is not None:
                payload["evaluation_notes"] = evaluation_notes

            res = (
                self.supabase.table("candidate_responses")
                .update(payload)
                .eq("id", str(response_id))
                .execute()
            )
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Candidate response '{response_id}' not found.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error scoring response: {str(e)}",
            )

    def get_candidate_responses(self, session_id: UUID) -> List[Dict[str, Any]]:
        """Fetch all answers recorded during a session."""
        try:
            res = (
                self.supabase.table("candidate_responses")
                .select("*")
                .eq("session_id", str(session_id))
                .order("created_at", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving candidate responses: {str(e)}",
            )

    # --------------------------------------------------------------------------
    # 7. Realtime Dialogue Transcripts
    # --------------------------------------------------------------------------

    def add_transcript_turn(self, data: TranscriptTurnCreate) -> Dict[str, Any]:
        """Log an individual conversational dialogue turn between interviewer and candidate."""
        try:
            payload = {
                "session_id": str(data.session_id),
                "speaker": data.speaker.value,
                "stage": data.stage.value,
                "content": data.content,
                "audio_url": data.audio_url,
            }
            res = self.supabase.table("transcript_turns").insert(payload).execute()
            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to log transcript turn.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error logging transcript turn: {str(e)}",
            )

    def get_transcript(self, session_id: UUID) -> List[Dict[str, Any]]:
        """Retrieve complete chronological transcript of the interview session."""
        try:
            res = (
                self.supabase.table("transcript_turns")
                .select("*")
                .eq("session_id", str(session_id))
                .order("created_at", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving transcript: {str(e)}",
            )

    # --------------------------------------------------------------------------
    # 8. Evaluation & Comprehensive Recruiter Reports
    # --------------------------------------------------------------------------

    def save_evaluation(self, data: InterviewEvaluationCreate) -> Dict[str, Any]:
        """Save or update comprehensive recruiter evaluation scorecard."""
        try:
            payload = {
                "session_id": str(data.session_id),
                "interview_id": str(data.interview_id),
                "candidate_id": str(data.candidate_id) if data.candidate_id else None,
                "candidate_name": data.candidate_name,
                "overall_score": data.overall_score,
                "recommendation": data.recommendation.value,
                "summary": data.summary,
                "key_strengths": data.key_strengths,
                "key_weaknesses": data.key_weaknesses,
                "rubric_scores": [r.model_dump(mode="json") for r in data.rubric_scores],
                "question_scores": [q.model_dump(mode="json") for q in data.question_scores],
            }
            if data.snapshot_id:
                payload["snapshot_id"] = str(data.snapshot_id)
            if data.audit_trail:
                payload["audit_trail"] = data.audit_trail
            if data.score_breakdown:
                payload["score_breakdown"] = data.score_breakdown

            try:
                res = (
                    self.supabase.table("interview_evaluations")
                    .upsert(payload, on_conflict="session_id")
                    .execute()
                )
            except Exception as upsert_err:
                # Fallback if optional migration 006 columns are not present on remote Supabase
                logger.warning(f"Initial upsert failed ({upsert_err}), falling back to base columns...")
                for col in ("snapshot_id", "audit_trail", "score_breakdown"):
                    payload.pop(col, None)
                res = (
                    self.supabase.table("interview_evaluations")
                    .upsert(payload, on_conflict="session_id")
                    .execute()
                )

            if not res.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to save interview evaluation.",
                )
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error saving evaluation: {str(e)}",
            )

    def get_evaluation_by_session(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        """Retrieve evaluation report for a given session."""
        try:
            res = (
                self.supabase.table("interview_evaluations")
                .select("*")
                .eq("session_id", str(session_id))
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving evaluation: {str(e)}",
            )

    def list_evaluations_for_interview(
        self, interview_id: UUID
    ) -> List[Dict[str, Any]]:
        """List all candidate evaluation reports under a specific interview template."""
        try:
            res = (
                self.supabase.table("interview_evaluations")
                .select("*")
                .eq("interview_id", str(interview_id))
                .order("completed_at", desc=True)
                .execute()
            )
            evals = res.data or []
            # Fallback: also check if any sessions belong to this interview that have evaluations
            if not evals:
                sess_res = (
                    self.supabase.table("interview_sessions")
                    .select("id")
                    .eq("interview_id", str(interview_id))
                    .execute()
                )
                if sess_res.data:
                    s_ids = [s["id"] for s in sess_res.data if s.get("id")]
                    if s_ids:
                        eval_res = (
                            self.supabase.table("interview_evaluations")
                            .select("*")
                            .in_("session_id", s_ids)
                            .order("completed_at", desc=True)
                            .execute()
                        )
                        evals = eval_res.data or []
            return evals
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error listing evaluations: {str(e)}",
            )


# Default singleton instance
interview_service = InterviewService()
