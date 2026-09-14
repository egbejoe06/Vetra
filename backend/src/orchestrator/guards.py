from dataclasses import dataclass
from typing import Dict, List, Optional

from src.orchestrator.events import EventActor
from src.orchestrator.state import InterviewState, TransitionDecision

STAGE_ORDER: List[str] = [
    "INTRO",
    "RESUME_DEEP_DIVE",
    "TECHNICAL_QA",
    "TECHNICAL_EXERCISE",
    "BEHAVIORAL",
    "WRAP_UP",
    "COMPLETED",
]


@dataclass(frozen=True)
class StageRule:
    """Rules and minimum guard floors/ceilings for exiting an interview stage."""

    next_stage: Optional[str]
    min_questions: int = 0
    max_questions: int = 3
    require_problem_presented: bool = False
    require_problem_discussed: bool = False


STAGE_RULES: Dict[str, StageRule] = {
    "INTRO": StageRule(
        next_stage="RESUME_DEEP_DIVE",
        min_questions=1,
        max_questions=2,
    ),
    "RESUME_DEEP_DIVE": StageRule(
        next_stage="TECHNICAL_QA",
        min_questions=2,
        max_questions=3,
    ),
    "TECHNICAL_QA": StageRule(
        next_stage="TECHNICAL_EXERCISE",
        min_questions=2,
        max_questions=4,
    ),
    "TECHNICAL_EXERCISE": StageRule(
        next_stage="BEHAVIORAL",
        min_questions=1,
        max_questions=3,
        require_problem_presented=True,
        require_problem_discussed=True,
    ),
    "BEHAVIORAL": StageRule(
        next_stage="WRAP_UP",
        min_questions=2,
        max_questions=3,
    ),
    "WRAP_UP": StageRule(
        next_stage="COMPLETED",
        min_questions=1,
        max_questions=2,
    ),
    "COMPLETED": StageRule(
        next_stage=None,
        min_questions=0,
        max_questions=0,
    ),
}


def validate_transition_guard(
    state: InterviewState,
    requested_stage: str,
    requested_by: EventActor = "GEMINI",
    transition_reason: Optional[str] = None,
) -> TransitionDecision:
    """Evaluate whether moving to requested_stage is allowed by stage guards."""
    current_stage = state.get("current_stage", "INTRO")
    rule = STAGE_RULES.get(current_stage)

    # 1. Verify stage exists and has a next transition
    if not rule or not rule.next_stage:
        return TransitionDecision(
            allowed=False,
            current_stage=current_stage,
            requested_stage=requested_stage,
            requested_by=requested_by,
            reason=f"Stage '{current_stage}' is terminal and has no subsequent stage.",
            remaining_questions=0,
            next_allowed_stage=None,
        )

    # 2. Check forward progression order
    if requested_by not in ("RECRUITER", "SYSTEM"):
        if requested_stage not in STAGE_ORDER or current_stage not in STAGE_ORDER:
            return TransitionDecision(
                allowed=False,
                current_stage=current_stage,
                requested_stage=requested_stage,
                requested_by=requested_by,
                reason=f"Unknown interview stage: '{requested_stage}'.",
                remaining_questions=0,
                next_allowed_stage=rule.next_stage,
            )
        curr_idx = STAGE_ORDER.index(current_stage)
        target_idx = STAGE_ORDER.index(requested_stage)
        if target_idx <= curr_idx:
            return TransitionDecision(
                allowed=False,
                current_stage=current_stage,
                requested_stage=requested_stage,
                requested_by=requested_by,
                reason=(
                    f"Invalid backward transition from '{current_stage}' to '{requested_stage}'. "
                    f"Interview stages must progress forward."
                ),
                remaining_questions=0,
                next_allowed_stage=rule.next_stage,
            )

    # 3. Check minimum question floor
    questions_in_stage = state.get("stage_question_counts", {}).get(current_stage, 0)
    if questions_in_stage < rule.min_questions and requested_by not in ("RECRUITER", "SYSTEM"):
        rem = rule.min_questions - questions_in_stage
        return TransitionDecision(
            allowed=False,
            current_stage=current_stage,
            requested_stage=requested_stage,
            requested_by=requested_by,
            reason=(
                f"Minimum question requirement not reached for stage '{current_stage}'. "
                f"{rem} question(s) remaining."
            ),
            remaining_questions=rem,
            next_allowed_stage=rule.next_stage,
        )

    # 4. Enforce max question ceiling as an automatic override to prevent entrapment:
    # If the interviewer has asked max_questions or more, immediately permit transition.
    is_max_reached = (rule.max_questions > 0 and questions_in_stage >= rule.max_questions)

    # 5. Check candidate evidence & response quality gate (only if ceiling not reached)
    substantive_turns = state.get("stage_substantive_turn_counts", {}).get(current_stage, 0)
    if (
        not is_max_reached
        and current_stage in ("RESUME_DEEP_DIVE", "TECHNICAL_QA", "TECHNICAL_EXERCISE", "BEHAVIORAL")
        and substantive_turns == 0
        and questions_in_stage >= rule.min_questions
        and requested_by not in ("RECRUITER", "SYSTEM")
    ):
        return TransitionDecision(
            allowed=False,
            current_stage=current_stage,
            requested_stage=requested_stage,
            requested_by=requested_by,
            reason=(
                f"Cannot advance from '{current_stage}': No substantive candidate responses "
                f"have been recorded yet. Probe the candidate for technical evidence before transitioning."
            ),
            remaining_questions=1,
            next_allowed_stage=rule.next_stage,
        )

    # 6. Check problem presentation requirements (TECHNICAL_EXERCISE)
    if rule.require_problem_presented and not state.get("problem_presented", False) and requested_by != "RECRUITER" and not is_max_reached:
        return TransitionDecision(
            allowed=False,
            current_stage=current_stage,
            requested_stage=requested_stage,
            requested_by=requested_by,
            reason="Cannot exit TECHNICAL_EXERCISE before presenting a technical problem.",
            remaining_questions=0,
            next_allowed_stage=rule.next_stage,
        )

    # 7. Check problem discussion requirements (TECHNICAL_EXERCISE)
    # If interviewer has presented the challenge and asked/exchanged at least 1 question,
    # consider the challenge sufficiently discussed to avoid infinite loop deadlocks.
    if rule.require_problem_discussed and not state.get("problem_discussed", False) and requested_by != "RECRUITER" and not is_max_reached:
        if questions_in_stage < 1:
            return TransitionDecision(
                allowed=False,
                current_stage=current_stage,
                requested_stage=requested_stage,
                requested_by=requested_by,
                reason="Cannot exit TECHNICAL_EXERCISE before discussing the candidate's solution.",
                remaining_questions=0,
                next_allowed_stage=rule.next_stage,
            )

    # All guard criteria satisfied
    reason_text = transition_reason
    if is_max_reached and not reason_text:
        reason_text = f"Stage '{current_stage}' maximum question limit ({rule.max_questions}) reached. Advancing to next stage."
    elif not reason_text:
        reason_text = "Stage guard conditions fulfilled."

    return TransitionDecision(
        allowed=True,
        current_stage=current_stage,
        requested_stage=requested_stage,
        requested_by=requested_by,
        reason=reason_text,
        remaining_questions=0,
        next_allowed_stage=rule.next_stage,
    )
