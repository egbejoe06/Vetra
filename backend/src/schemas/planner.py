from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator, model_validator

from src.models.enums import (
    CodeLanguage,
    EvaluationIssueType,
    InterviewStage,
    QuestionDifficulty,
    QuestionType,
    TechnicalProblemType,
)
from src.schemas.interview import CodeFile


class WorkExperience(BaseModel):
    company: str
    role: str
    duration: Optional[str] = None
    responsibilities: List[str] = Field(default_factory=list)
    claimed_projects: List[str] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)


class CandidateProject(BaseModel):
    name: str
    description: str
    role: Optional[str] = None
    claimed_impact: Optional[str] = None
    tech_stack: List[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    institution: str
    degree: str
    year: Optional[str] = None


class DetectedGap(BaseModel):
    gap_type: str = Field(description="e.g. TIMELINE_GAP, SHORT_TENURE, UNVERIFIED_CLAIM, TECH_STACK_MISMATCH")
    description: str
    probe_angle: str


class CandidateProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    candidate_name: str
    candidate_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    years_of_experience: int = Field(default=0, ge=0)
    summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    frameworks_and_tools: List[str] = Field(default_factory=list)
    work_experience: List[WorkExperience] = Field(default_factory=list)
    projects: List[CandidateProject] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    detected_gaps: List[DetectedGap] = Field(default_factory=list)
    raw_resume_text: Optional[str] = None
    freeze_hash: Optional[str] = None

    @computed_field
    @property
    def name(self) -> str:
        return self.candidate_name

    @computed_field
    @property
    def primary_skills(self) -> List[str]:
        return self.skills

    @model_validator(mode="before")
    @classmethod
    def handle_frontend_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "name" in data and not data.get("candidate_name"):
                data["candidate_name"] = data["name"]
            if "primary_skills" in data and not data.get("skills"):
                data["skills"] = data["primary_skills"]
            if "work_experiences" in data and not data.get("work_experience"):
                data["work_experience"] = data["work_experiences"]
        return data


class FollowUpProbe(BaseModel):
    question: str = Field(..., description="Follow-up question text")
    purpose: str = Field(..., description="Probing intent or knowledge evaluated")
    trigger: str = Field(..., description="Candidate response trigger e.g. candidate gives superficial answer")


class ScoringCriterion(BaseModel):
    level: int = Field(..., ge=1, le=5)
    description: str
    key_signals: List[str] = Field(default_factory=list)


class InterviewQuestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    stage: InterviewStage = Field(default=InterviewStage.TECHNICAL_QA)
    question_type: QuestionType = Field(default=QuestionType.TECHNICAL_CONCEPT)
    competency: str
    topic: str
    difficulty: QuestionDifficulty = Field(default=QuestionDifficulty.MID)
    question_text: str
    rationale: str
    candidate_evidence: List[str] = Field(default_factory=list, description="Specific resume claims or facts that triggered this question")
    expected_key_points: List[str] = Field(default_factory=list)
    reasoning_dimensions: List[str] = Field(
        default_factory=list,
        description="Core reasoning dimensions expected for this question (e.g. mechanism, causality, failure_mode, decomposition, tradeoffs, invariants)",
    )
    follow_up_probes: List[FollowUpProbe] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    strong_signals: List[str] = Field(default_factory=list)
    scoring_criteria: List[ScoringCriterion] = Field(default_factory=list)


class EvaluationIssue(BaseModel):
    issue_id: str
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    issue_type: EvaluationIssueType = EvaluationIssueType.LOGIC_ERROR
    description: str
    expected_observation: str
    severity: str = Field(default="MEDIUM", description="LOW, MEDIUM, HIGH, CRITICAL")

    @field_validator("issue_type", mode="before")
    @classmethod
    def normalize_issue_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().upper()
            for it in EvaluationIssueType:
                if it.value == clean or it.name == clean:
                    return it
        return v


class CodingExerciseEvaluation(BaseModel):
    expected_findings: List[EvaluationIssue] = Field(default_factory=list)
    expected_solution_summary: str = ""
    discussion_points: List[str] = Field(default_factory=list)


class TechnologyEnvironment(BaseModel):
    primary_language: str = Field(default="python", description="Primary programming language")
    file_extension: Optional[str] = Field(default=None, description="Standard file extension including dot, e.g. .py, .ts, .go")
    framework: Optional[str] = Field(default=None, description="Primary runtime framework (e.g. FastAPI, NestJS, React, Express, Gin)")
    domain_libraries: List[str] = Field(default_factory=list, description="Specific ecosystem libraries (e.g. LangGraph, OpenAI SDK, Pydantic, Prisma, WebSockets)")
    infrastructure_dependencies: List[str] = Field(default_factory=list, description="Backing services or transport context (e.g. Redis, PostgreSQL, Vector DB, WebSocket duplex stream)")
    selection_rationale: Optional[str] = Field(default=None, description="Why this tech environment best exposes the competency and defect")



class ExerciseScenario(BaseModel):
    domain: str = Field(description="Believable micro-service or domain context grounded in candidate's experience")
    context: str = Field(description="Operational context, scale, and background architecture")
    incident: str = Field(description="Observed operational incident or user-impacting symptom")


class ExerciseFailureMechanism(BaseModel):
    trigger: str = Field(description="Runtime event or concurrent condition that activates the defect")
    underlying_cause: str = Field(description="Flawed invariant, state synchronization error, or incorrect assumption")
    observable_symptom: str = Field(description="Telemetry, data corruption, or degradation observed by candidate")
    why_it_is_non_obvious: str = Field(description="Why the issue cannot be diagnosed from a single line or superficial inspection")


class ExerciseInterviewerStrategy(BaseModel):
    opening_question: str = Field(description="Initial open-ended conversational prompt for candidate")
    expected_reasoning: List[str] = Field(default_factory=list, description="Diagnostic steps candidate should articulate out loud")
    follow_up_areas: List[str] = Field(default_factory=list, description="Targeted areas to probe deeper into trade-offs and edge cases")


class ExerciseImplementationConstraints(BaseModel):
    files: str = Field(default="2-3", description="File count constraint")
    language: str = Field(description="Target programming language")
    avoid: List[str] = Field(default_factory=list, description="Contract-specific forbidden patterns or domain anti-patterns")


class CodingExerciseContract(BaseModel):
    contract_id: str = Field(default_factory=lambda: f"cnt_{uuid4().hex[:10]}")
    required: bool = True
    objective: str
    scenario: ExerciseScenario
    technology_environment: Optional[TechnologyEnvironment] = Field(
        default=None,
        description="Planner-designed technology environment optimal for exposing the failure mechanism",
    )
    candidate_should_be_tested_on: List[str] = Field(default_factory=list)
    architecture_requirements: List[str] = Field(default_factory=list)
    failure_requirements: List[str] = Field(default_factory=list)
    failure_mechanism: ExerciseFailureMechanism
    interviewer_strategy: ExerciseInterviewerStrategy
    implementation_constraints: ExerciseImplementationConstraints

    @model_validator(mode="before")
    @classmethod
    def unwrap_root_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key in ("exercise_contract", "contract", "CodingExerciseContract", "data"):
                if key in data and isinstance(data[key], dict):
                    return data[key]
        return data


class CodingExerciseAsset(BaseModel):
    problem_type: TechnicalProblemType = TechnicalProblemType.CODE_REVIEW
    title: str
    objective: str = ""
    prompt_question: str
    context: Optional[str] = None
    language: CodeLanguage = CodeLanguage.PYTHON
    technology_environment: Optional[TechnologyEnvironment] = None
    difficulty: QuestionDifficulty = QuestionDifficulty.MID
    estimated_discussion_minutes: int = 15
    code_files: List[CodeFile] = Field(default_factory=list)
    discussion_questions: List[str] = Field(default_factory=list)
    evaluation: CodingExerciseEvaluation = Field(default_factory=CodingExerciseEvaluation)
    contract: Optional[CodingExerciseContract] = None

    @model_validator(mode="before")
    @classmethod
    def unwrap_root_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key in ("coding_exercise", "coding_exercise_asset", "CodingExerciseAsset", "exercise", "data"):
                if key in data and isinstance(data[key], dict):
                    return data[key]
        return data


class SystemDesignExercise(BaseModel):
    title: str
    objective: str
    scenario_prompt: str
    requirements_and_metrics: List[str] = Field(default_factory=list)
    architecture_components: List[str] = Field(default_factory=list)
    tradeoff_areas: List[str] = Field(default_factory=list)
    scaling_challenges: List[str] = Field(default_factory=list)
    evaluation: CodingExerciseEvaluation = Field(default_factory=CodingExerciseEvaluation)

    @model_validator(mode="before")
    @classmethod
    def unwrap_root_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key in ("system_design_exercise", "SystemDesignExercise", "exercise", "data"):
                if key in data and isinstance(data[key], dict):
                    return data[key]
        return data


class RubricCriterion(BaseModel):
    category: str = Field(default="", description="Category or competency name")
    competency: str = Field(default="", description="Specific competency evaluated from the blueprint")
    observable_evidence: str = Field(default="", description="Concrete observable behavior, mechanism explanation, or code patterns")
    description_level_1: str = Field(description="Poor / Unsatisfactory criteria with concrete anti-patterns")
    description_level_3: str = Field(description="Competent / Standard criteria with scenario-relevant tradeoffs")
    description_level_5: str = Field(description="Exemplary / Senior criteria anticipating second-order effects and operational failure modes")
    common_false_positives: List[str] = Field(default_factory=list, description="Superficial signals that seem impressive but mask shallow understanding")

    @model_validator(mode="before")
    @classmethod
    def sync_category_and_competency(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "competency" in data and not data.get("category"):
                data["category"] = data["competency"]
            elif "category" in data and not data.get("competency"):
                data["competency"] = data["category"]
        return data


class InterviewStageConfig(BaseModel):
    stage: InterviewStage
    objective: str
    target_questions_count: int = Field(default=2)


class StageFocusItem(BaseModel):
    stage: str = Field(..., description="Interview stage (e.g. TECHNICAL_QA, RESUME_DEEP_DIVE)")
    focus: str = Field(..., description="Core assessment focus or question strategy for this stage")


class InterviewCompetency(BaseModel):
    name: str
    importance: str = "HIGH"
    evidence: List[str] = Field(default_factory=list)
    target_level: str = "SENIOR"


class EvidenceClaim(BaseModel):
    claim: str = Field(..., description="High-stakes technical claim worth probing")
    source: str = Field(..., description="Source project, company, or role from candidate background")
    evidence_quote: str = Field(
        default="",
        description=(
            "A verbatim substring copied directly from the candidate's profile, work_experience, or projects text "
            "that supports this claim. Must be an exact character-sequence from the input data — not paraphrased. "
            "Leave empty only if no direct quote is available, which itself signals a thin or unverifiable claim."
        ),
    )
    what_candidate_claimed: str = Field(..., description="Concrete claimed architecture, scale, or metrics")
    why_it_matters: str = Field(..., description="Why this claim is critical for the target role")
    competency: str = Field(..., description="Underlying competency being tested")
    risk_or_uncertainty: str = Field(..., description="Potential exaggeration, shallow ownership, or unverified technical depth")
    validation_evidence: str = Field(..., description="Concrete technical explanation or architectural proof required to validate")


class InterviewBlueprint(BaseModel):
    candidate_summary: str = Field(default="")
    role_archetype: str = Field(default="Software Engineer")
    recommended_exercise_strategy: str = Field(
        default="CODING_ONLY",
        description="AI Planner exercise strategy recommendation: 'CODING_ONLY', 'SYSTEM_DESIGN_ONLY', or 'BOTH'",
    )
    claims_to_verify: List[EvidenceClaim] = Field(default_factory=list, description="Structured claims from resume/projects to probe")
    capabilities_to_assess: List[str] = Field(default_factory=list, description="Role-required technical capabilities")
    risk_hypotheses: List[str] = Field(default_factory=list, description="Hypotheses regarding potential gaps or unverified seniority")
    competencies: List[InterviewCompetency] = Field(default_factory=list)
    stage_focus: List[StageFocusItem] = Field(default_factory=list)
    probing_strategy: str = ""

    @model_validator(mode="before")
    @classmethod
    def handle_stage_focus_map(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key in ("interview_blueprint", "blueprint", "InterviewBlueprint", "data"):
                if key in data and isinstance(data[key], dict):
                    data = data[key]
                    break
            if "summary" in data and not data.get("candidate_summary"):
                data["candidate_summary"] = data["summary"]
            if "archetype" in data and not data.get("role_archetype"):
                data["role_archetype"] = data["archetype"]
            if "exercise_strategy" in data and not data.get("recommended_exercise_strategy"):
                data["recommended_exercise_strategy"] = data["exercise_strategy"]
            if "stage_focus_map" in data and not data.get("stage_focus"):
                raw_map = data.pop("stage_focus_map")
                if isinstance(raw_map, dict):
                    data["stage_focus"] = [
                        {"stage": str(k), "focus": str(v)} for k, v in raw_map.items()
                    ]
            # Harmonize competencies and capabilities_to_assess
            if "competencies" in data and isinstance(data["competencies"], list) and not data.get("capabilities_to_assess"):
                data["capabilities_to_assess"] = [
                    c["name"] if isinstance(c, dict) and "name" in c else str(c)
                    for c in data["competencies"]
                ]
            elif "capabilities_to_assess" in data and isinstance(data["capabilities_to_assess"], list) and not data.get("competencies"):
                data["competencies"] = [
                    {"name": cap, "importance": "HIGH", "evidence": [], "target_level": "SENIOR"}
                    for cap in data["capabilities_to_assess"]
                ]
        return data

    @property
    def stage_focus_map(self) -> Dict[str, str]:
        return {item.stage: item.focus for item in self.stage_focus}


class InterviewerGuidance(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pacing: str = Field(
        default="Spend ~5m intro, ~10m resume deep dive, ~15m technical exercise & QA, ~5m wrap-up.",
        description="Time allocation and pacing guidance across interview stages",
    )
    probing_tip: str = Field(
        default="Focus on mechanism choices and failure modes rather than definitions.",
        description="Probing techniques and tips for interviewing",
    )
    transition_guidance: str = Field(
        default="Smoothly bridge from background claims into hands-on architectural problem solving.",
        description="Guidance on transitioning between stages",
    )
    follow_up_strategy: str = Field(
        default="Challenge edge cases and ask for concrete metrics when answers are vague.",
        description="Strategy for probing follow-ups",
    )


class InterviewPlan(BaseModel):
    version: str = "2.0"
    job_title: str
    candidate_name: str
    interview_objective: str = ""
    blueprint: Optional[InterviewBlueprint] = None
    stage_configs: List[InterviewStageConfig] = Field(default_factory=list)
    intro_questions: List[InterviewQuestion] = Field(default_factory=list)
    questions: List[InterviewQuestion] = Field(default_factory=list)
    coding_exercise: Optional[CodingExerciseAsset] = None
    system_design_exercise: Optional[SystemDesignExercise] = None
    behavioral_questions: List[InterviewQuestion] = Field(default_factory=list)
    rubrics: List[RubricCriterion] = Field(default_factory=list)
    interviewer_guidance: InterviewerGuidance = Field(default_factory=InterviewerGuidance)


class InterviewPlanCreate(BaseModel):
    interview_id: Optional[UUID] = None
    job_id: Optional[UUID] = None
    job_title: str
    seniority: Optional[QuestionDifficulty] = None
    years_of_experience: int = Field(default=0, ge=0)
    questions_count: int = Field(default=10, ge=1, le=20)
    duration_minutes: int = Field(default=30, ge=10, le=120)
    technical_focus: List[str] = Field(default_factory=list)
    behavioral_focus: List[str] = Field(default_factory=list)
    instructions: Optional[str] = None
    description: Optional[str] = None
    evaluation_criteria: Optional[str] = None
    problem_type: Optional[TechnicalProblemType] = None

    @field_validator("seniority", mode="before")
    @classmethod
    def normalize_seniority(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().upper()
            for d in QuestionDifficulty:
                if d.value == clean or d.name == clean:
                    return d
        return v


class ParseResumeTextRequest(BaseModel):
    resume_text: str = Field(..., min_length=10, description="Raw plain text of candidate resume")
    force_refresh: bool = Field(default=False, description="If True, bypasses resume freeze cache")


class GeneratePlanRequest(BaseModel):
    candidate_profile: CandidateProfile
    job_spec: InterviewPlanCreate
    checkpoint_id: Optional[str] = Field(
        default=None,
        description="Optional checkpoint ID to resume from a previous partial or failed plan generation",
    )
    coding_exercise: Optional[CodingExerciseAsset] = Field(
        default=None,
        description="Pre-generated coding exercise to reuse directly, bypassing exercise generation",
    )
    system_design_exercise: Optional[SystemDesignExercise] = Field(
        default=None,
        description="Pre-generated system design exercise to reuse directly",
    )
    defer_coding_exercise: bool = Field(
        default=True,
        description="If True, defers coding and system design exercise generation to in-interview background task to cut plan generation latency",
    )
    session_id: Optional[UUID] = Field(
        default=None,
        description="Optional interview session ID",
    )
    force_refresh: bool = Field(
        default=False,
        description="If True, bypasses checkpoint cache to force a fresh plan/exercise generation (e.g. for interview redo)",
    )


class GenerateExercisesRequest(BaseModel):
    interview_id: UUID
    session_id: Optional[UUID] = None
    checkpoint_id: Optional[str] = None
    problem_type: Optional[TechnicalProblemType] = None
    force_refresh: bool = Field(
        default=False,
        description="If True, forces generating a fresh distinct exercise",
    )


class GeneratePlanResponse(BaseModel):
    interview_id: Optional[UUID] = None
    plan: InterviewPlan
    checkpoint_id: Optional[str] = Field(default=None, description="Active checkpoint ID for this interview plan")
    reused_from_checkpoint: bool = Field(default=False, description="True if exercises or drafts were reused from checkpoint")
    step: Optional[str] = Field(default="COMPLETED", description="Current execution step")
    created_at: datetime = Field(default_factory=datetime.utcnow)


