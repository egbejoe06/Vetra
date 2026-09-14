from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator
from src.schemas.planner import (
    InterviewQuestion,
    InterviewerGuidance,
    RubricCriterion,
)


class PlannerPipelineError(RuntimeError):
    """Structured exception raised when an interview planner pipeline step fails.
    
    Carries the exact provider root-cause errors, failed step, and checkpoint ID
    for transparent debugging and checkpoint resumption.
    """
    def __init__(
        self,
        message: str,
        step: str,
        checkpoint_id: Optional[str] = None,
        diagnostic_errors: Optional[List[Dict[str, Any]]] = None,
        can_retry_with_checkpoint: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.step = step
        self.checkpoint_id = checkpoint_id
        self.diagnostic_errors = diagnostic_errors or []
        self.can_retry_with_checkpoint = can_retry_with_checkpoint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "step": self.step,
            "checkpoint_id": self.checkpoint_id,
            "diagnostic_errors": self.diagnostic_errors,
            "can_retry_with_checkpoint": self.can_retry_with_checkpoint,
        }


class QuestionsContainer(BaseModel):
    intro_questions: List[InterviewQuestion] = Field(default_factory=list)
    questions: List[InterviewQuestion] = Field(default_factory=list)
    behavioral_questions: List[InterviewQuestion] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def unwrap_root_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key in ("questions_container", "QuestionsContainer", "data", "payload", "interview_questions"):
                if key in data and isinstance(data[key], dict):
                    data = data[key]
                    break
        return data


class RubricsAndGuidanceContainer(BaseModel):
    rubrics: List[RubricCriterion] = Field(default_factory=list)
    interviewer_guidance: InterviewerGuidance = Field(default_factory=InterviewerGuidance)
