import logging
from typing import Any, Dict, Optional

from src.orchestrator.engine import interview_orchestrator

logger = logging.getLogger("vetra.tools.interview")


async def handle_get_interviewer_state(session_id: str) -> Dict[str, Any]:
    """Retrieve the authoritative interview state and guidance for Gemini Live."""
    try:
        ctx = await interview_orchestrator.get_interviewer_state(session_id)
        limit_reached = (ctx.maximum_questions > 0 and ctx.questions_asked_in_stage >= ctx.maximum_questions)
        min_reached = ctx.questions_asked_in_stage >= ctx.minimum_questions
        transition_allowed = ctx.transition_allowed or limit_reached
        should_transition = limit_reached or (min_reached and transition_allowed)

        if limit_reached:
            directive = (
                f"STAGE MAXIMUM QUESTIONS REACHED: You have asked {ctx.questions_asked_in_stage}/{ctx.maximum_questions} "
                f"questions in stage '{ctx.stage}'. You MUST transition to the next stage immediately by calling "
                f"request_stage_transition. Do NOT ask any more questions, follow-ups, or rephrasings in this stage."
            )
        elif min_reached and transition_allowed:
            directive = (
                f"STAGE QUESTION QUOTA MET: You have asked {ctx.questions_asked_in_stage}/{ctx.maximum_questions} "
                f"questions in '{ctx.stage}' (minimum required: {ctx.minimum_questions}). "
                f"Stage transition is APPROVED. Wrap up this stage with a brief conversational bridge and call "
                f"request_stage_transition."
            )
        else:
            directive = (
                f"Currently in {ctx.stage} ({ctx.questions_asked_in_stage}/{ctx.maximum_questions} questions asked, "
                f"minimum required: {ctx.minimum_questions})."
            )

        instructions = (
            ["STAGE LIMIT REACHED: Silently invoke request_stage_transition now. Do NOT ask more questions."]
            if limit_reached
            else ctx.instructions
        )
        recommended_probe = None if limit_reached else ctx.recommended_probe

        return {
            "success": True,
            "stage": ctx.stage,
            "questions_asked_in_stage": ctx.questions_asked_in_stage,
            "minimum_questions_required": ctx.minimum_questions,
            "maximum_questions_allowed": ctx.maximum_questions,
            "transition_eligible": should_transition,
            "should_transition_now": should_transition,
            "directive": directive,
            "active_problem_id": ctx.active_problem_id,
            "problem_presented": ctx.problem_presented,
            "problem_discussed": ctx.problem_discussed,
            "guidance": (
                ctx.guidance.model_dump()
                if hasattr(ctx.guidance, "model_dump")
                else ctx.guidance
            ),
            "competency_coverage": ctx.competency_coverage,
            "competencies_covered": ctx.competencies_covered,
            "competencies_missing": ctx.competencies_missing,
            "transition_allowed": transition_allowed,
            "recommended_probe": recommended_probe,
            "instructions": instructions,
            "pending_objectives": ctx.pending_objectives,
            "completed_objectives": ctx.completed_objectives,
        }
    except Exception as err:
        logger.error(f"Error in handle_get_interviewer_state for session {session_id}: {err}")
        return {"success": False, "error": str(err)}


async def handle_request_stage_transition(
    session_id: str, target_stage: str, reason: Optional[str] = None
) -> Dict[str, Any]:
    """Request a stage transition through the LangGraph guard system."""
    try:
        decision = await interview_orchestrator.request_stage_transition(
            session_id=session_id,
            target_stage=target_stage,
            requested_by="GEMINI",
            reason=reason,
        )
        instruction = (
            f"Stage transition to '{decision.requested_stage}' approved. Introduce the new stage smoothly."
            if decision.allowed
            else (
                f"Stage transition to '{decision.requested_stage}' is NOT permitted yet ({decision.reason}). "
                f"Continue naturally in current stage '{decision.current_stage}'. "
                f"Ask another focused question without apologizing or mentioning the system."
            )
        )
        return {
            "success": decision.allowed,
            "allowed": decision.allowed,
            "current_stage": decision.current_stage,
            "requested_stage": decision.requested_stage,
            "target_stage": decision.requested_stage if decision.allowed else decision.current_stage,
            "reason": decision.reason,
            "instruction": instruction,
            "remaining_questions": decision.remaining_questions,
            "next_allowed_stage": decision.next_allowed_stage,
        }
    except Exception as err:
        logger.error(f"Error requesting stage transition for session {session_id}: {err}")
        return {"success": False, "allowed": False, "error": str(err)}


async def handle_record_interviewer_observation(
    session_id: str,
    observation: str,
    competency: Optional[str] = None,
    sentiment: Optional[str] = None,
) -> Dict[str, Any]:
    """Record dynamic observation notes from the interviewer."""
    try:
        logger.info(
            f"Observation recorded for session {session_id}: [{sentiment or 'INFO'}] "
            f"({competency or 'General'}) {observation}"
        )
        return {
            "success": True,
            "message": "Observation recorded successfully",
            "observation": observation,
            "competency": competency,
            "sentiment": sentiment,
        }
    except Exception as err:
        logger.error(f"Error recording observation for session {session_id}: {err}")
        return {"success": False, "error": str(err)}
