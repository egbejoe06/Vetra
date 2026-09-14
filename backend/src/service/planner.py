import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException, status
from supabase import Client

from src.agents.interview_planner import PlannerPipelineError, interview_planner_agent
from src.agents.resume_cache import resume_freeze_cache
from src.agents.resume_parser import resume_parser_agent
from src.db.supabase import supabase
from src.agents.planner_checkpoint import planner_checkpoint_manager
from src.schemas.planner import (
    CandidateProfile,
    GeneratePlanRequest,
    GeneratePlanResponse,
    InterviewBlueprint,
    InterviewPlan,
    InterviewPlanCreate,
    WorkExperience,
)

logger = logging.getLogger(__name__)


class PlannerService:
    """Domain service managing the Pre-Interview Generator pipeline:
    1. Resume Parsing & Freeze Caching (Text / PDF) -> CandidateProfile
    2. 3-Stage Interview Plan Generation with Checkpointing -> InterviewPlan
    3. Asset Persistence -> Supabase (interviews, technical_problems, interview_artifacts)
    """

    def __init__(self, client: Client = supabase):
        self.supabase = client
        self.parser_agent = resume_parser_agent
        self.planner_agent = interview_planner_agent
        self.resume_cache = resume_freeze_cache

    def parse_resume_text(self, resume_text: str, force_refresh: bool = False) -> CandidateProfile:
        """Parse raw text resume into CandidateProfile using ResumeParserAgent with Freeze Caching."""
        try:
            hash_key = self.resume_cache.compute_text_hash(resume_text)
            if not force_refresh:
                cached = self.resume_cache.get(hash_key)
                if cached:
                    return cached

            profile = self.parser_agent.parse_text(resume_text=resume_text)
            self.resume_cache.set(hash_key, profile)
            return profile
        except Exception as e:
            logger.error(f"Failed to parse resume text: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to parse resume text: {str(e)}",
            )

    def parse_resume_file(self, file_bytes: bytes, filename: str, force_refresh: bool = False) -> CandidateProfile:
        """Parse PDF file resume into CandidateProfile using ResumeParserAgent with Freeze Caching."""
        try:
            hash_key = self.resume_cache.compute_bytes_hash(file_bytes)
            if not force_refresh:
                cached = self.resume_cache.get(hash_key)
                if cached:
                    return cached

            profile = self.parser_agent.parse_pdf_bytes(pdf_bytes=file_bytes, filename=filename)
            self.resume_cache.set(hash_key, profile)
            return profile
        except Exception as e:
            logger.error(f"Failed to parse resume file '{filename}': {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to parse resume file '{filename}': {str(e)}",
            )

    def generate_interview_plan(self, request: GeneratePlanRequest) -> GeneratePlanResponse:
        """Generate structured Candidate-tailored InterviewPlan with 3-stage checkpointing and asset persistence."""
        try:
            plan, checkpoint_id, reused_exercises = self.planner_agent.generate_plan(
                profile=request.candidate_profile,
                job_spec=request.job_spec,
                checkpoint_id=request.checkpoint_id,
                coding_exercise=request.coding_exercise,
                system_design_exercise=request.system_design_exercise,
                defer_exercises=request.defer_coding_exercise,
                force_refresh=request.force_refresh,
                session_id=str(request.session_id) if request.session_id else None,
            )

            interview_id = request.job_spec.interview_id

            if interview_id:
                self.persist_interview_plan_assets(
                    interview_id=interview_id,
                    plan=plan,
                    profile=request.candidate_profile,
                    session_id=request.session_id,
                )

            return GeneratePlanResponse(
                interview_id=interview_id,
                plan=plan,
                checkpoint_id=checkpoint_id,
                reused_from_checkpoint=reused_exercises,
                step="COMPLETED",
            )
        except PlannerPipelineError as pe:
            logger.error(f"Planner pipeline error in {pe.step} (Checkpoint: {pe.checkpoint_id}): {pe.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=pe.to_dict(),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error generating interview plan: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": f"Error generating interview plan: {str(e)}",
                    "step": "UNKNOWN",
                    "checkpoint_id": request.checkpoint_id,
                    "diagnostic_errors": [{"provider": "system", "message": str(e)}],
                    "can_retry_with_checkpoint": False,
                },
            )

    def persist_interview_plan_assets(
        self,
        interview_id: UUID,
        plan: InterviewPlan,
        profile: Optional[CandidateProfile] = None,
        session_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Persist generated coding exercise and rubrics into Supabase database."""
        try:
            # 1. Update interview template technical focus, behavioral focus, and instructions
            technical_focus = list(set([q.competency for q in plan.questions]))
            self.supabase.table("interviews").update(
                {
                    "technical_focus": technical_focus,
                    "instructions": f"Generated plan for {plan.candidate_name} ({plan.job_title})",
                }
            ).eq("id", str(interview_id)).execute()

            # 2. If coding exercise is present, persist to technical_problems and CODEBASE artifact
            problem_id = None
            if plan.coding_exercise:
                problem_data = plan.coding_exercise
                problem_payload = {
                    "interview_id": str(interview_id),
                    "session_id": str(session_id) if session_id else None,
                    "problem_type": problem_data.problem_type.value if hasattr(problem_data.problem_type, "value") else str(problem_data.problem_type),
                    "title": problem_data.title,
                    "prompt_question": problem_data.prompt_question,
                    "context": problem_data.context,
                    "code_files": [f.model_dump() for f in problem_data.code_files],
                    "key_discussion_points": problem_data.discussion_questions,
                    "expected_solution_summary": problem_data.evaluation.expected_solution_summary if problem_data.evaluation else "",
                }

                prob_res = self.supabase.table("technical_problems").insert(problem_payload).execute()
                problem_id = prob_res.data[0]["id"] if prob_res.data else None

                # Save multi-file sample codebase artifact (Candidate visible workspace)
                artifact_payload = {
                    "session_id": str(session_id) if session_id else None,
                    "problem_id": problem_id,
                    "artifact_type": "CODEBASE",
                    "title": f"{problem_data.title} - Boilerplate Workspace",
                    "content": {
                        "interview_id": str(interview_id),
                        "files": [f.model_dump() for f in problem_data.code_files],
                        "discussion_points": problem_data.discussion_questions,
                    },
                }
                self.supabase.table("interview_artifacts").insert(artifact_payload).execute()

            # 3. Save Interviewer-Only Evaluation Blueprint artifact (Private secrets)
            eval_blueprint_payload = {
                "session_id": str(session_id) if session_id else None,
                "problem_id": problem_id,
                "artifact_type": "EVALUATION_BLUEPRINT",
                "title": f"{plan.job_title} - Evaluation Blueprint & Secrets",
                "content": {
                    "interview_id": str(interview_id),
                    "blueprint": plan.blueprint.model_dump() if plan.blueprint else {},
                    "work_experience": [w.model_dump() for w in profile.work_experience] if profile and profile.work_experience else [],
                    "intro_questions": [q.model_dump() for q in plan.intro_questions],
                    "questions": [q.model_dump() for q in plan.questions],
                    "behavioral_questions": [q.model_dump() for q in plan.behavioral_questions],
                    "evaluation": plan.coding_exercise.evaluation.model_dump() if plan.coding_exercise and plan.coding_exercise.evaluation else {},
                    "system_design_exercise": plan.system_design_exercise.model_dump() if plan.system_design_exercise else None,
                    "rubrics": [r.model_dump() for r in plan.rubrics],
                    "guidance": plan.interviewer_guidance.model_dump() if hasattr(plan.interviewer_guidance, "model_dump") else plan.interviewer_guidance,
                    "exercises_deferred": plan.coding_exercise is None,
                },
            }
            self.supabase.table("interview_artifacts").insert(eval_blueprint_payload).execute()

            return {
                "interview_id": str(interview_id),
                "problem_id": problem_id,
                "status": "ASSETS_PERSISTED",
            }
        except Exception as e:
            logger.warning(f"Note: Error persisting assets to Supabase: {e}")
            return {"interview_id": str(interview_id), "status": "PERSISTENCE_FAILED_OR_SKIPPED", "error": str(e)}

    def generate_and_persist_exercises(
        self,
        interview_id: UUID,
        session_id: Optional[UUID] = None,
        checkpoint_id: Optional[str] = None,
        problem_type: Optional[Any] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """In-interview background task: Generates and persists the technical coding challenge
        and system design challenge into public.technical_problems and public.interview_artifacts.
        """
        try:
            logger.info(f"Starting in-interview background exercise generation for interview: {interview_id} (session: {session_id}, force_refresh={force_refresh})")

            # 1. Check if problem already exists for this specific session
            if session_id and not force_refresh:
                sess_existing = (
                    self.supabase.table("technical_problems")
                    .select("id")
                    .eq("session_id", str(session_id))
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if sess_existing.data and len(sess_existing.data) > 0:
                    problem_id = sess_existing.data[0]["id"]
                    logger.info(f"Technical problem already exists for session {session_id}: {problem_id}")
                    return {"status": "ALREADY_EXISTS", "problem_id": problem_id}
            elif not session_id and not force_refresh:
                existing = (
                    self.supabase.table("technical_problems")
                    .select("id")
                    .eq("interview_id", str(interview_id))
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if existing.data and len(existing.data) > 0:
                    problem_id = existing.data[0]["id"]
                    logger.info(f"Technical problem already exists for interview {interview_id}: {problem_id}")
                    if session_id:
                        try:
                            self.supabase.table("technical_problems").update({"session_id": str(session_id)}).eq("id", problem_id).execute()
                        except Exception as err:
                            logger.debug(f"Could not update session_id on problem: {err}")
                    return {"status": "ALREADY_EXISTS", "problem_id": problem_id}

            # Query all previously generated problem titles for this interview to avoid duplicates on redo
            previous_titles = []
            try:
                prev_problems = (
                    self.supabase.table("technical_problems")
                    .select("title")
                    .eq("interview_id", str(interview_id))
                    .execute()
                )
                previous_titles = [p["title"] for p in (prev_problems.data or []) if p.get("title")]
                if previous_titles:
                    logger.info(f"Found {len(previous_titles)} prior problem(s) for interview {interview_id}: {previous_titles}. Guaranteeing fresh scenario.")
            except Exception as prev_err:
                logger.debug(f"Could not query previous problems: {prev_err}")

            # 2. Retrieve parent interview and candidate details
            int_res = self.supabase.table("interviews").select("*").eq("id", str(interview_id)).limit(1).execute()
            if not int_res.data or len(int_res.data) == 0:
                raise ValueError(f"Interview {interview_id} not found.")
            int_data = int_res.data[0]

            # 3. Retrieve evaluation blueprint artifact to get extracted blueprint & work experience
            blueprint = None
            extracted_work_exp = []
            try:
                art_res = (
                    self.supabase.table("interview_artifacts")
                    .select("*")
                    .eq("artifact_type", "EVALUATION_BLUEPRINT")
                    .order("created_at", desc=True)
                    .limit(10)
                    .execute()
                )
                for art in (art_res.data or []):
                    c = art.get("content") or {}
                    if c.get("interview_id") == str(interview_id) or (session_id and art.get("session_id") == str(session_id)):
                        raw_bp = c.get("blueprint")
                        if raw_bp:
                            blueprint = InterviewBlueprint.model_validate(raw_bp)
                        raw_we = c.get("work_experience")
                        if raw_we:
                            extracted_work_exp = [WorkExperience.model_validate(w) for w in raw_we]
                        break
            except Exception as bp_err:
                logger.warning(f"Could not fetch blueprint from artifacts: {bp_err}")

            # 4. Check checkpoint for cached blueprint / profile
            if not blueprint and checkpoint_id:
                cp = planner_checkpoint_manager.get(checkpoint_id)
                if cp and cp.blueprint:
                    blueprint = cp.blueprint

            # Candidate name and email
            candidate_name = "Candidate"
            if session_id:
                sess_res = self.supabase.table("interview_sessions").select("candidate_name").eq("id", str(session_id)).limit(1).execute()
                if sess_res.data and len(sess_res.data) > 0:
                    candidate_name = sess_res.data[0].get("candidate_name") or candidate_name

            resolved_problem_type = problem_type or int_data.get("problem_type")

            job_spec = InterviewPlanCreate(
                interview_id=interview_id,
                job_title=int_data.get("job_title", "Software Engineer"),
                seniority=int_data.get("seniority"),
                years_of_experience=int_data.get("years_of_experience", 3),
                technical_focus=int_data.get("technical_focus") or [],
                behavioral_focus=int_data.get("behavioral_focus") or [],
                instructions=int_data.get("instructions"),
                description=int_data.get("description"),
                problem_type=resolved_problem_type,
            )

            profile = CandidateProfile(
                candidate_name=candidate_name,
                years_of_experience=job_spec.years_of_experience,
                skills=job_spec.technical_focus,
                work_experience=extracted_work_exp,
            )

            # If blueprint wasn't stored, generate a minimal blueprint
            if not blueprint:
                blueprint = self.planner_agent.blueprint_generator.generate(profile, job_spec)

            # 5. Generate Step 2 Exercises with AST validation (force fresh if session_id provided or force_refresh)
            coding_exercise, system_design_exercise, cp_id = self.planner_agent.generate_exercises_step(
                profile=profile,
                job_spec=job_spec,
                blueprint=blueprint,
                checkpoint_id=checkpoint_id,
                force_refresh=force_refresh or bool(session_id),
                session_id=str(session_id) if session_id else None,
                previous_exercises=previous_titles,
            )

            # 6. Persist to public.technical_problems
            problem_payload = {
                "interview_id": str(interview_id),
                "session_id": str(session_id) if session_id else None,
                "problem_type": coding_exercise.problem_type.value if hasattr(coding_exercise.problem_type, "value") else str(coding_exercise.problem_type),
                "title": coding_exercise.title,
                "prompt_question": coding_exercise.prompt_question,
                "context": coding_exercise.context,
                "code_files": [f.model_dump() for f in coding_exercise.code_files],
                "key_discussion_points": coding_exercise.discussion_questions,
                "expected_solution_summary": coding_exercise.evaluation.expected_solution_summary if coding_exercise.evaluation else "",
            }

            prob_res = self.supabase.table("technical_problems").insert(problem_payload).execute()
            problem_id = prob_res.data[0]["id"] if prob_res.data else None

            # 7. Persist CODEBASE artifact for Monaco editor workspace
            artifact_payload = {
                "session_id": str(session_id) if session_id else None,
                "problem_id": problem_id,
                "artifact_type": "CODEBASE",
                "title": f"{coding_exercise.title} - Boilerplate Workspace",
                "content": {
                    "interview_id": str(interview_id),
                    "files": [f.model_dump() for f in coding_exercise.code_files],
                    "discussion_points": coding_exercise.discussion_questions,
                },
            }
            self.supabase.table("interview_artifacts").insert(artifact_payload).execute()

            # 8. Update EVALUATION_BLUEPRINT artifact with problem_id and evaluation secrets
            try:
                art_query = (
                    self.supabase.table("interview_artifacts")
                    .select("id, content")
                    .eq("artifact_type", "EVALUATION_BLUEPRINT")
                    .order("created_at", desc=True)
                    .limit(5)
                    .execute()
                )
                for art in (art_query.data or []):
                    c = art.get("content") or {}
                    if c.get("interview_id") == str(interview_id):
                        c["evaluation"] = coding_exercise.evaluation.model_dump() if coding_exercise.evaluation else {}
                        c["system_design_exercise"] = system_design_exercise.model_dump() if system_design_exercise else None
                        c["exercises_deferred"] = False
                        self.supabase.table("interview_artifacts").update({
                            "problem_id": problem_id,
                            "session_id": str(session_id) if session_id else None,
                            "content": c,
                        }).eq("id", art["id"]).execute()
                        break
            except Exception as upd_err:
                logger.warning(f"Could not update EVALUATION_BLUEPRINT with problem_id: {upd_err}")

            logger.info(f"Background exercise generation completed for interview {interview_id}: problem_id={problem_id}")
            return {
                "status": "EXERCISES_GENERATED",
                "interview_id": str(interview_id),
                "session_id": str(session_id) if session_id else None,
                "problem_id": problem_id,
            }

        except Exception as e:
            logger.error(f"In-interview exercise background generation failed for interview {interview_id}: {e}", exc_info=True)
            return {
                "status": "FAILED",
                "interview_id": str(interview_id),
                "session_id": str(session_id) if session_id else None,
                "error": str(e),
            }



# Singleton instance
planner_service = PlannerService()
