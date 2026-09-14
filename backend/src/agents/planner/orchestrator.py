import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.agents.planner.client import PlannerLLMClient
from src.agents.planner.ecosystem import is_bug_problem_type
from src.agents.planner.exceptions import PlannerPipelineError
from src.agents.planner.generators import (
    BlueprintGenerator,
    CodingExerciseGenerator,
    QuestionGenerator,
    RubricGenerator,
    SystemDesignGenerator,
)
from src.agents.planner_checkpoint import CheckpointStep, planner_checkpoint_manager
from src.agents.planner_validators import validate_interview_plan
from src.models.enums import InterviewStage
from src.schemas.planner import (
    CandidateProfile,
    CodingExerciseAsset,
    InterviewBlueprint,
    InterviewPlan,
    InterviewPlanCreate,
    InterviewQuestion,
    InterviewStageConfig,
    InterviewerGuidance,
    RubricCriterion,
    SystemDesignExercise,
)

logger = logging.getLogger(__name__)


class InterviewPlannerAgent:
    """Multi-Stage Interview Planner Engine for Vetra.
    Decomposes generation into:
    1. Interview Blueprint (Gemini Flash-Lite - Competencies & evidence claims extraction)
    2. Evidence-Driven Questions (Gemini Flash - Probing mechanisms, tradeoffs, follow-up trees, red flags)
    3. Technical Coding Exercise (Gemini Flash primary / Kimi fallback - Monaco-safe multi-file codebase)
    4. System Design Exercise (Gemini Flash primary / Kimi fallback - Architecture scenario, scaling & tradeoffs)
    5. Scoring Rubrics & Live Guidance (Gemini Flash-Lite)
    6. Code & Schema Validation Node (AST validation with automatic retry)

    Includes thread-safe inter-call pacing and exponential backoff on Gemini API calls to avoid rate limits.
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        moonshot_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        kimi_model: Optional[str] = None,
        gemini_call_gap_seconds: Optional[float] = None,
    ):
        self.llm_client = PlannerLLMClient(
            gemini_api_key=gemini_api_key,
            moonshot_api_key=moonshot_api_key,
            gemini_model=gemini_model,
            kimi_model=kimi_model,
            gemini_call_gap_seconds=gemini_call_gap_seconds,
        )

        # Expose legacy attributes for backwards compatibility
        self.gemini_api_key = self.llm_client.gemini_api_key
        self.moonshot_api_key = self.llm_client.moonshot_api_key
        self.gemini_flash_lite_model = self.llm_client.gemini_flash_lite_model
        self.gemini_flash_model = self.llm_client.gemini_flash_model
        self.gemini_model = self.llm_client.gemini_model
        self.kimi_model = self.llm_client.kimi_model
        self.enable_kimi_coding_fallback = self.llm_client.enable_kimi_coding_fallback
        self.gemini_call_gap_seconds = self.llm_client.gemini_call_gap_seconds
        self.gemini_max_retries = self.llm_client.gemini_max_retries
        self.kimi_timeout_seconds = self.llm_client.kimi_timeout_seconds
        self.kimi_max_retries = self.llm_client.kimi_max_retries
        self.thinking_budget = self.llm_client.thinking_budget
        self._lock = self.llm_client._lock
        self._kimi_lock = self.llm_client._kimi_lock
        self.gemini_client = self.llm_client.gemini_client
        self.kimi_client = self.llm_client.kimi_client

        # Sub-generators
        self.blueprint_generator = BlueprintGenerator(self.llm_client)
        self.question_generator = QuestionGenerator(self.llm_client)
        self.coding_generator = CodingExerciseGenerator(self.llm_client)
        self.system_design_generator = SystemDesignGenerator(self.llm_client)
        self.rubric_generator = RubricGenerator(self.llm_client)

    def _pace_gemini_call(self) -> None:
        self.llm_client.pace_gemini_call()

    def _call_gemini_with_retry(self, fn: Callable[[], Any], operation_name: str = "Gemini Operation") -> Any:
        return self.llm_client.call_gemini_with_retry(fn, operation_name)

    # Sub-generator backward-compatible delegation methods
    def _generate_blueprint(self, profile: CandidateProfile, job_spec: InterviewPlanCreate) -> InterviewBlueprint:
        return self.blueprint_generator.generate(profile, job_spec)

    def _generate_blueprint_gemini(self, profile: CandidateProfile, job_spec: InterviewPlanCreate) -> InterviewBlueprint:
        return self.blueprint_generator.generate_gemini(profile, job_spec)

    def _generate_blueprint_kimi(self, profile: CandidateProfile, job_spec: InterviewPlanCreate) -> Optional[InterviewBlueprint]:
        return self.blueprint_generator.generate_kimi(profile, job_spec)

    def _generate_questions(
        self, profile: CandidateProfile, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Tuple[List[InterviewQuestion], List[InterviewQuestion], List[InterviewQuestion]]:
        return self.question_generator.generate(profile, job_spec, blueprint)

    def _generate_questions_gemini(
        self, profile: CandidateProfile, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Tuple[List[InterviewQuestion], List[InterviewQuestion], List[InterviewQuestion]]:
        return self.question_generator.generate_gemini(profile, job_spec, blueprint)

    def _generate_questions_kimi(
        self, profile: CandidateProfile, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Optional[Tuple[List[InterviewQuestion], List[InterviewQuestion], List[InterviewQuestion]]]:
        return self.question_generator.generate_kimi(profile, job_spec, blueprint)

    def _generate_coding_exercise_gemini(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        retry_hint: str = "",
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
    ) -> CodingExerciseAsset:
        return self.coding_generator.generate_gemini(profile, job_spec, blueprint, retry_hint, diagnostic_list)

    def _generate_coding_exercise_kimi(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        retry_hint: str = "",
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[CodingExerciseAsset]:
        return self.coding_generator.generate_kimi(profile, job_spec, blueprint, retry_hint, diagnostic_list)

    def _generate_system_design_exercise(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[SystemDesignExercise]:
        return self.system_design_generator.generate_kimi(profile, job_spec, blueprint, diagnostic_list)

    def _generate_system_design_exercise_gemini(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        retry_hint: str = "",
        diagnostic_list: Optional[List[Dict[str, Any]]] = None,
    ) -> SystemDesignExercise:
        return self.system_design_generator.generate_gemini(profile, job_spec, blueprint, retry_hint, diagnostic_list)

    def _generate_rubrics_and_guidance(
        self, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Tuple[List[RubricCriterion], InterviewerGuidance]:
        return self.rubric_generator.generate(job_spec, blueprint)

    def _generate_rubrics_and_guidance_gemini(
        self, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Tuple[List[RubricCriterion], InterviewerGuidance]:
        return self.rubric_generator.generate_gemini(job_spec, blueprint)

    def _generate_rubrics_and_guidance_kimi(
        self, job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint
    ) -> Optional[Tuple[List[RubricCriterion], InterviewerGuidance]]:
        return self.rubric_generator.generate_kimi(job_spec, blueprint)

    def generate_plan(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        checkpoint_id: Optional[str] = None,
        coding_exercise: Optional[CodingExerciseAsset] = None,
        system_design_exercise: Optional[SystemDesignExercise] = None,
        defer_exercises: bool = True,
        force_refresh: bool = False,
        session_id: Optional[str] = None,
    ) -> Tuple[InterviewPlan, str, bool]:
        """Synthesizes Candidate Profile and Job Specification into a structured, evidence-driven InterviewPlan
        using a 3-stage checkpointed pipeline:
          Step 1: Plan Draft (Blueprint + Intro/Technical/Behavioral Questions)
          Step 2: Exercises (Coding + System Design Challenge) -> Saved to Checkpoint immediately (or deferred)
          Step 3: Final Plan Assembly (Rubrics, Guidance, Validation)
        
        Returns (plan, checkpoint_id, reused_from_checkpoint).
        """
        logger.info(f"Generating evidence-driven InterviewPlan for '{profile.candidate_name}' ({job_spec.job_title}) (defer_exercises={defer_exercises}, force_refresh={force_refresh})...")
        return self._do_generate_plan(
            profile=profile,
            job_spec=job_spec,
            checkpoint_id=checkpoint_id,
            pre_generated_coding_exercise=coding_exercise,
            pre_generated_system_design=system_design_exercise,
            defer_exercises=defer_exercises,
            force_refresh=force_refresh,
            session_id=session_id,
        )

    def generate_exercises_step(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        blueprint: InterviewBlueprint,
        checkpoint_id: Optional[str] = None,
        force_refresh: bool = False,
        session_id: Optional[str] = None,
        previous_exercises: Optional[List[str]] = None,
    ) -> Tuple[CodingExerciseAsset, Optional[SystemDesignExercise], str]:
        """Executes Step 2: Technical coding and optional system design challenge generation,
        validates codebase with AST, and stores them into planner checkpoint.
        
        Returns (coding_exercise, system_design_exercise, checkpoint_id).
        """
        checkpoint = planner_checkpoint_manager.get_or_create(
            profile=profile,
            job_spec=job_spec,
            checkpoint_id=checkpoint_id,
            force_refresh=force_refresh,
            session_id=session_id,
        )
        cp_id = checkpoint.checkpoint_id

        if not force_refresh and checkpoint.has_valid_exercises():
            logger.info(f"[Checkpoint {cp_id}] Reusing valid exercises from checkpoint: '{checkpoint.coding_exercise.title}'")
            return checkpoint.coding_exercise, checkpoint.system_design_exercise, cp_id

        logger.info(f"[Checkpoint {cp_id}] Executing Step 2: Generating Coding Challenge & System Design Exercise...")
        diagnostic_errors: List[Dict[str, Any]] = []

        skip_system_design = is_bug_problem_type(job_spec.problem_type)
        if skip_system_design:
            logger.info(
                f"[Checkpoint {cp_id}] Requested problem category is '{job_spec.problem_type}' (Bug category). "
                "Skipping system design exercise generation as technical assessment is focused on hands-on codebase investigation."
            )

        # Generate coding exercise
        coding_exercise = self.coding_generator.generate(
            profile=profile,
            job_spec=job_spec,
            blueprint=blueprint,
            diagnostic_list=diagnostic_errors,
            previous_exercises=previous_exercises,
        )

        if not coding_exercise:
            diag_lines = [
                f"  - [{d.get('provider', '').upper()}] {d.get('error_type', 'Error')}: {d.get('message', '')}"
                for d in diagnostic_errors
            ]
            diag_summary = "\n".join(diag_lines) if diag_lines else "No provider error telemetry captured."
            err_msg = f"Failed to generate coding exercise using Gemini Flash after retries.\nDiagnostic details:\n{diag_summary}"
            planner_checkpoint_manager.record_step_failure(cp_id, CheckpointStep.STEP_2_EXERCISES, err_msg)
            raise PlannerPipelineError(
                message=err_msg,
                step=CheckpointStep.STEP_2_EXERCISES,
                checkpoint_id=cp_id,
                diagnostic_errors=diagnostic_errors,
                can_retry_with_checkpoint=True,
            )

        # Determine whether system design is needed
        system_design_exercise = None
        if not skip_system_design:
            if is_bug_problem_type(coding_exercise.problem_type):
                logger.info(
                    f"[Checkpoint {cp_id}] Generated coding exercise problem type is '{coding_exercise.problem_type}' (Bug category). "
                    "Skipping system design exercise generation."
                )
                system_design_exercise = None
            else:
                system_design_exercise = self.system_design_generator.generate(
                    profile=profile,
                    job_spec=job_spec,
                    blueprint=blueprint,
                    diagnostic_list=diagnostic_errors,
                    previous_exercises=previous_exercises,
                )
                if not system_design_exercise:
                    diag_lines = [
                        f"  - [{d.get('provider', '').upper()}] {d.get('error_type', 'Error')}: {d.get('message', '')}"
                        for d in diagnostic_errors
                    ]
                    diag_summary = "\n".join(diag_lines) if diag_lines else "No provider error telemetry captured."
                    err_msg = f"Failed to generate system design exercise using Gemini Flash after retries.\nDiagnostic details:\n{diag_summary}"
                    planner_checkpoint_manager.record_step_failure(cp_id, CheckpointStep.STEP_2_EXERCISES, err_msg)
                    raise PlannerPipelineError(
                        message=err_msg,
                        step=CheckpointStep.STEP_2_EXERCISES,
                        checkpoint_id=cp_id,
                        diagnostic_errors=diagnostic_errors,
                        can_retry_with_checkpoint=True,
                    )

        # STORE EXERCISES INTO CHECKPOINT IMMEDIATELY
        planner_checkpoint_manager.save_step_2_exercises(
            checkpoint_id=cp_id,
            coding_exercise=coding_exercise,
            system_design_exercise=system_design_exercise,
        )
        logger.info(
            f"[Checkpoint {cp_id}] Step 2 Exercises successfully STORED in checkpoint "
            f"(Coding: '{coding_exercise.title}', SysDesign: {bool(system_design_exercise)})."
        )
        return coding_exercise, system_design_exercise, cp_id

    def _do_generate_plan(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        checkpoint_id: Optional[str] = None,
        pre_generated_coding_exercise: Optional[CodingExerciseAsset] = None,
        pre_generated_system_design: Optional[SystemDesignExercise] = None,
        defer_exercises: bool = True,
        force_refresh: bool = False,
        session_id: Optional[str] = None,
    ) -> Tuple[InterviewPlan, str, bool]:
        # Initialize or retrieve checkpoint
        checkpoint = planner_checkpoint_manager.get_or_create(
            profile=profile,
            job_spec=job_spec,
            checkpoint_id=checkpoint_id,
            force_refresh=force_refresh,
            session_id=session_id,
        )
        cp_id = checkpoint.checkpoint_id
        reused_exercises = False

        # =====================================================================
        # STEP 1: PLAN DRAFT (Blueprint + Questions)
        # =====================================================================
        blueprint = checkpoint.blueprint
        intro_questions = checkpoint.intro_questions
        questions = checkpoint.questions
        behavioral_questions = checkpoint.behavioral_questions

        if not (blueprint and questions):
            logger.info(f"[Checkpoint {cp_id}] Executing Step 1: Generating Blueprint and Questions...")
            try:
                blueprint = self.blueprint_generator.generate(profile, job_spec)
                intro_questions, questions, behavioral_questions = self.question_generator.generate(profile, job_spec, blueprint)
                planner_checkpoint_manager.save_step_1_draft(
                    checkpoint_id=cp_id,
                    blueprint=blueprint,
                    intro_questions=intro_questions,
                    questions=questions,
                    behavioral_questions=behavioral_questions,
                )
            except Exception as e:
                err_msg = f"Step 1 Plan Draft generation failed: {str(e)}"
                planner_checkpoint_manager.record_step_failure(cp_id, CheckpointStep.STEP_1_DRAFT, err_msg)
                raise PlannerPipelineError(
                    message=err_msg,
                    step=CheckpointStep.STEP_1_DRAFT,
                    checkpoint_id=cp_id,
                    diagnostic_errors=[{"provider": "gemini", "operation": "draft_questions", "message": str(e)}],
                    can_retry_with_checkpoint=False,
                ) from e
        else:
            logger.info(f"[Checkpoint {cp_id}] Reusing Step 1 Plan Draft from checkpoint (Blueprint + {len(questions)} questions).")

        # =====================================================================
        # STEP 2: EXERCISES GENERATION & CHECKPOINT STORAGE
        # =====================================================================
        coding_exercise = pre_generated_coding_exercise or checkpoint.coding_exercise
        system_design_exercise = pre_generated_system_design or checkpoint.system_design_exercise

        if coding_exercise:
            logger.info(f"[Checkpoint {cp_id}] Reusing existing coding exercise: '{coding_exercise.title}' (Checkpoint / Request payload).")
            reused_exercises = True
            if is_bug_problem_type(job_spec.problem_type) or is_bug_problem_type(coding_exercise.problem_type):
                logger.info(
                    f"[Checkpoint {cp_id}] Problem category is Bug ({coding_exercise.problem_type}). "
                    "Skipping system design exercise."
                )
                system_design_exercise = None
        elif defer_exercises:
            logger.info(f"[Checkpoint {cp_id}] Deferring Step 2 Exercises to in-interview background generation.")
            coding_exercise = None
            system_design_exercise = None
        else:
            coding_exercise, system_design_exercise, _ = self.generate_exercises_step(
                profile=profile,
                job_spec=job_spec,
                blueprint=blueprint,
                checkpoint_id=cp_id,
            )

        # =====================================================================
        # STEP 3: FINAL PLAN ASSEMBLY & RUBRICS
        # =====================================================================
        logger.info(f"[Checkpoint {cp_id}] Executing Step 3: Generating Rubrics & Guidance, Assembling Final Plan...")
        try:
            rubrics, guidance = self.rubric_generator.generate(job_spec, blueprint)

            # Build Stage Configs
            stage_configs = [
                InterviewStageConfig(stage=InterviewStage.INTRO, objective="Warm welcome, role overview, and tailored background alignment to role challenges", target_questions_count=2),
                InterviewStageConfig(stage=InterviewStage.RESUME_DEEP_DIVE, objective="Probing claimed experience, project architecture descriptions, and evidence", target_questions_count=3),
                InterviewStageConfig(stage=InterviewStage.TECHNICAL_QA, objective="Evaluating core competencies, tradeoffs, and failure modes", target_questions_count=4),
                InterviewStageConfig(stage=InterviewStage.TECHNICAL_EXERCISE, objective="Hands-on multi-file codebase review, debugging, or system design", target_questions_count=1),
                InterviewStageConfig(stage=InterviewStage.BEHAVIORAL, objective="Evaluating leadership, ownership, teamwork, and problem navigation", target_questions_count=2),
                InterviewStageConfig(stage=InterviewStage.WRAP_UP, objective="Candidate questions and closing remarks", target_questions_count=1),
            ]

            # Combine intro questions with technical questions so plan.questions contains all stages
            combined_questions = []
            for iq in intro_questions:
                iq.stage = InterviewStage.INTRO
                combined_questions.append(iq)
            for q in questions:
                combined_questions.append(q)

            plan = InterviewPlan(
                version="2.0",
                job_title=job_spec.job_title,
                candidate_name=profile.candidate_name,
                interview_objective=f"Evaluate whether candidate {profile.candidate_name} satisfies requirements for {job_spec.job_title} ({job_spec.years_of_experience}+ YOE)",
                blueprint=blueprint,
                stage_configs=stage_configs,
                intro_questions=intro_questions,
                questions=combined_questions,
                coding_exercise=coding_exercise,
                system_design_exercise=system_design_exercise,
                behavioral_questions=behavioral_questions,
                rubrics=rubrics,
                interviewer_guidance=guidance,
            )

            plan_valid, plan_errors = validate_interview_plan(plan, allow_deferred_exercises=defer_exercises)
            if not plan_valid:
                logger.warning(f"Interview plan validation warnings: {plan_errors}")

            planner_checkpoint_manager.save_step_3_complete(
                checkpoint_id=cp_id,
                plan=plan,
                rubrics=rubrics,
                guidance=guidance,
            )

            return plan, cp_id, reused_exercises

        except Exception as e:
            err_msg = f"Step 3 Final Plan generation failed: {str(e)}"
            planner_checkpoint_manager.record_step_failure(cp_id, CheckpointStep.STEP_3_FINAL_PLAN, err_msg)
            # CRITICAL: Note that Step 2 exercises were already preserved!
            raise PlannerPipelineError(
                message=f"Error in final plan assembly: {str(e)}. (Note: Coding and system design exercises were successfully generated and safely preserved in checkpoint '{cp_id}'. You can resume from this checkpoint.)",
                step=CheckpointStep.STEP_3_FINAL_PLAN,
                checkpoint_id=cp_id,
                diagnostic_errors=[{"provider": "gemini", "operation": "rubrics_and_guidance", "message": str(e)}],
                can_retry_with_checkpoint=True,
            ) from e
