from datetime import datetime, timezone
import hashlib
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from pydantic import BaseModel, Field

from src.schemas.planner import (
    CandidateProfile,
    CodingExerciseAsset,
    CodingExerciseContract,
    InterviewBlueprint,
    InterviewerGuidance,
    InterviewPlan,
    InterviewPlanCreate,
    InterviewQuestion,
    RubricCriterion,
    SystemDesignExercise,
)

logger = logging.getLogger("vetra.agents.planner_checkpoint")


class CheckpointStep(str):
    STEP_1_DRAFT = "STEP_1_PLAN_DRAFT"
    STEP_2A_CONTRACT = "STEP_2A_EXERCISE_CONTRACT"
    STEP_2_EXERCISES = "STEP_2_EXERCISES"
    STEP_3_FINAL_PLAN = "STEP_3_FINAL_PLAN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DiagnosticProviderError(BaseModel):
    provider: str  # "kimi", "gemini", "ast_validator", "schema"
    operation: str  # "coding_exercise", "system_design", "rubrics", "questions"
    attempt: int = 1
    error_type: str
    status_code: Optional[int] = None
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlannerCheckpoint(BaseModel):
    """Holds intermediate state across the 3-stage interview plan generator pipeline."""
    checkpoint_id: str
    candidate_hash: str
    job_spec_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    step: str = CheckpointStep.STEP_1_DRAFT
    status: str = "IN_PROGRESS"

    # Step 1 Artifacts
    blueprint: Optional[InterviewBlueprint] = None
    intro_questions: List[InterviewQuestion] = Field(default_factory=list)
    questions: List[InterviewQuestion] = Field(default_factory=list)
    behavioral_questions: List[InterviewQuestion] = Field(default_factory=list)

    # Step 2A Artifacts (Scenario contract preserved across code retries)
    exercise_contract: Optional[CodingExerciseContract] = None

    # Step 2 Artifacts (Preserved across any Step 3 failures)
    coding_exercise: Optional[CodingExerciseAsset] = None
    system_design_exercise: Optional[SystemDesignExercise] = None

    # Step 3 Artifacts
    rubrics: List[RubricCriterion] = Field(default_factory=list)
    interviewer_guidance: Optional[InterviewerGuidance] = None
    completed_plan: Optional[InterviewPlan] = None

    # Diagnostics & Error Telemetry
    diagnostic_errors: List[DiagnosticProviderError] = Field(default_factory=list)
    last_error: Optional[str] = None
    failed_step: Optional[str] = None

    def has_valid_exercises(self) -> bool:
        """Returns True if coding exercise or system design exercise was successfully generated."""
        has_coding = self.coding_exercise is not None and len(self.coding_exercise.code_files) > 0
        has_sys_design = self.system_design_exercise is not None
        return has_coding or has_sys_design


class PlannerCheckpointManager:
    """Thread-safe in-memory manager for interview planner checkpoints with TTL expiration."""

    def __init__(self, ttl_seconds: float = 7200.0, max_entries: int = 300):
        self._checkpoints: Dict[str, PlannerCheckpoint] = {}
        self._hash_index: Dict[str, str] = {}  # composite_hash -> checkpoint_id
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries

    @staticmethod
    def compute_composite_hash(profile: CandidateProfile, job_spec: InterviewPlanCreate) -> Tuple[str, str, str]:
        """Computes deterministic candidate, job spec, and composite hashes."""
        cand_str = f"{profile.candidate_name}|{profile.years_of_experience}|{','.join(sorted(profile.skills))}"
        cand_hash = hashlib.sha256(cand_str.encode("utf-8")).hexdigest()[:16]

        prob_type_str = job_spec.problem_type.value if hasattr(job_spec.problem_type, "value") else str(job_spec.problem_type or "")
        spec_str = f"{job_spec.job_title}|{job_spec.years_of_experience}|{','.join(sorted(job_spec.technical_focus))}|{job_spec.description or ''}|{prob_type_str}"
        spec_hash = hashlib.sha256(spec_str.encode("utf-8")).hexdigest()[:16]

        composite = f"{cand_hash}:{spec_hash}"
        return cand_hash, spec_hash, composite

    def get_or_create(
        self,
        profile: CandidateProfile,
        job_spec: InterviewPlanCreate,
        checkpoint_id: Optional[str] = None,
        force_refresh: bool = False,
        session_id: Optional[str] = None,
    ) -> PlannerCheckpoint:
        """Retrieves an existing checkpoint by ID or composite hash, or initializes a new one."""
        cand_hash, spec_hash, composite = self.compute_composite_hash(profile, job_spec)
        if session_id:
            composite = f"{composite}:{session_id}"

        with self._lock:
            if not force_refresh:
                # 1. Lookup by explicit checkpoint_id
                if checkpoint_id and checkpoint_id in self._checkpoints:
                    cp = self._checkpoints[checkpoint_id]
                    logger.info(f"Retrieved existing planner checkpoint by ID: {checkpoint_id} (Step: {cp.step})")
                    return cp

                # 2. Lookup by composite hash
                if composite in self._hash_index:
                    existing_id = self._hash_index[composite]
                    if existing_id in self._checkpoints:
                        cp = self._checkpoints[existing_id]
                        logger.info(f"Retrieved existing planner checkpoint by hash index: {existing_id} (Step: {cp.step})")
                        return cp

            # 3. Create new checkpoint
            new_id = (None if force_refresh else checkpoint_id) or f"cp_{uuid.uuid4().hex[:12]}"
            cp = PlannerCheckpoint(
                checkpoint_id=new_id,
                candidate_hash=cand_hash,
                job_spec_hash=spec_hash,
                step=CheckpointStep.STEP_1_DRAFT,
                status="IN_PROGRESS",
            )
            self._checkpoints[new_id] = cp
            self._hash_index[composite] = new_id
            logger.info(f"Initialized new planner checkpoint: {new_id} for '{profile.candidate_name}' ({job_spec.job_title}) (force_refresh={force_refresh})")
            return cp

    def get(self, checkpoint_id: str) -> Optional[PlannerCheckpoint]:
        """Retrieves a checkpoint by ID."""
        with self._lock:
            return self._checkpoints.get(checkpoint_id)

    def save_step_1_draft(
        self,
        checkpoint_id: str,
        blueprint: InterviewBlueprint,
        intro_questions: List[InterviewQuestion],
        questions: List[InterviewQuestion],
        behavioral_questions: List[InterviewQuestion],
    ) -> None:
        """Saves Step 1 Blueprint & Questions draft to checkpoint."""
        with self._lock:
            cp = self._checkpoints.get(checkpoint_id)
            if cp:
                cp.blueprint = blueprint
                cp.intro_questions = intro_questions
                cp.questions = questions
                cp.behavioral_questions = behavioral_questions
                cp.step = CheckpointStep.STEP_2_EXERCISES
                cp.status = "STEP_1_COMPLETE"
                cp.updated_at = datetime.now(timezone.utc)
                logger.info(f"[Checkpoint {checkpoint_id}] Step 1 Draft saved (Blueprint + {len(questions)} questions).")

    def save_step_2a_contract(
        self,
        checkpoint_id: str,
        contract: CodingExerciseContract,
    ) -> None:
        """Saves Step 2A Exercise Contract to checkpoint.
        
        The contract is frozen and immutable across subsequent code generation attempts,
        ensuring code generation retries reuse the exact same scenario.
        """
        with self._lock:
            cp = self._checkpoints.get(checkpoint_id)
            if cp:
                cp.exercise_contract = contract
                cp.step = CheckpointStep.STEP_2A_CONTRACT
                cp.status = "STEP_2A_CONTRACT_SAVED"
                cp.updated_at = datetime.now(timezone.utc)
                logger.info(
                    f"[Checkpoint {checkpoint_id}] Step 2A Exercise Contract STORED. "
                    f"Contract ID: {contract.contract_id}, Domain: '{contract.scenario.domain}'."
                )

    def save_step_2_exercises(
        self,
        checkpoint_id: str,
        coding_exercise: CodingExerciseAsset,
        system_design_exercise: Optional[SystemDesignExercise] = None,
    ) -> None:
        """Saves Step 2 Exercises to checkpoint.
        
        CRITICAL: These exercises are safely stored so any subsequent failure in Step 3
        does NOT require re-generating exercises from Kimi or Gemini fallback.
        """
        with self._lock:
            cp = self._checkpoints.get(checkpoint_id)
            if cp:
                cp.coding_exercise = coding_exercise
                cp.system_design_exercise = system_design_exercise
                cp.step = CheckpointStep.STEP_3_FINAL_PLAN
                cp.status = "STEP_2_EXERCISES_SAVED"
                cp.updated_at = datetime.now(timezone.utc)
                logger.info(
                    f"[Checkpoint {checkpoint_id}] Step 2 Exercises STORED. Coding challenge: '{coding_exercise.title}' "
                    f"({len(coding_exercise.code_files)} files), SysDesign: {bool(system_design_exercise)}."
                )

    def save_step_3_complete(
        self,
        checkpoint_id: str,
        plan: InterviewPlan,
        rubrics: List[RubricCriterion],
        guidance: InterviewerGuidance,
    ) -> None:
        """Marks checkpoint as fully completed with final InterviewPlan."""
        with self._lock:
            cp = self._checkpoints.get(checkpoint_id)
            if cp:
                cp.completed_plan = plan
                cp.rubrics = rubrics
                cp.interviewer_guidance = guidance
                cp.step = CheckpointStep.COMPLETED
                cp.status = "COMPLETED"
                cp.updated_at = datetime.now(timezone.utc)
                logger.info(f"[Checkpoint {checkpoint_id}] Step 3 Complete. Plan finalized for '{plan.candidate_name}'.")

    def record_diagnostic_error(
        self,
        checkpoint_id: str,
        provider: str,
        operation: str,
        error_type: str,
        message: str,
        status_code: Optional[int] = None,
        attempt: int = 1,
    ) -> None:
        """Records a provider-level diagnostic error into the checkpoint."""
        with self._lock:
            cp = self._checkpoints.get(checkpoint_id)
            if cp:
                diag = DiagnosticProviderError(
                    provider=provider,
                    operation=operation,
                    attempt=attempt,
                    error_type=error_type,
                    status_code=status_code,
                    message=message,
                )
                cp.diagnostic_errors.append(diag)
                logger.warning(f"[Checkpoint {checkpoint_id}] Diagnostic error recorded: [{provider.upper()}] {error_type}: {message}")

    def record_step_failure(self, checkpoint_id: str, failed_step: str, error_msg: str) -> None:
        """Records a pipeline step failure on the checkpoint."""
        with self._lock:
            cp = self._checkpoints.get(checkpoint_id)
            if cp:
                cp.status = "FAILED"
                cp.failed_step = failed_step
                cp.last_error = error_msg
                cp.updated_at = datetime.now(timezone.utc)
                logger.error(f"[Checkpoint {checkpoint_id}] Pipeline failure recorded at {failed_step}: {error_msg}")

    def clear(self) -> None:
        """Clears all checkpoints."""
        with self._lock:
            self._checkpoints.clear()
            self._hash_index.clear()


# Global singleton instance
planner_checkpoint_manager = PlannerCheckpointManager()
