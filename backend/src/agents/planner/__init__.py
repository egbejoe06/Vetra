"""Interview Planner modular package.

Provides the multi-stage, checkpointed, evidence-driven pre-interview generation engine.
"""

from src.agents.planner.client import PlannerLLMClient
from src.agents.planner.ecosystem import (
    detect_target_programming_language,
    detect_technology_ecosystem,
    is_bug_problem_type,
)
from src.agents.planner.exceptions import (
    PlannerPipelineError,
    QuestionsContainer,
    RubricsAndGuidanceContainer,
)
from src.agents.planner.generators import (
    BlueprintGenerator,
    CodingExerciseGenerator,
    ExerciseContractGenerator,
    QuestionGenerator,
    RubricGenerator,
    SystemDesignGenerator,
)
from src.agents.planner.orchestrator import InterviewPlannerAgent

# Default singleton instance
interview_planner_agent = InterviewPlannerAgent()

__all__ = [
    "InterviewPlannerAgent",
    "interview_planner_agent",
    "PlannerPipelineError",
    "QuestionsContainer",
    "RubricsAndGuidanceContainer",
    "is_bug_problem_type",
    "detect_target_programming_language",
    "detect_technology_ecosystem",
    "PlannerLLMClient",
    "BlueprintGenerator",
    "ExerciseContractGenerator",
    "QuestionGenerator",
    "CodingExerciseGenerator",
    "SystemDesignGenerator",
    "RubricGenerator",
]
