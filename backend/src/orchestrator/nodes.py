from datetime import datetime, timezone
from typing import Any, Dict, Literal
from langgraph.types import Command

from src.orchestrator.guards import validate_transition_guard
from src.orchestrator.state import InterviewState


def _finalize_updates(
    event: Dict[str, Any], updates: Dict[str, Any]
) -> Dict[str, Any]:
    """Helper to attach audit trail fields and clear incoming_event from state."""
    res: Dict[str, Any] = {
        "incoming_event": None,
        "event_history": [event] if event else [],
    }
    if event and event.get("event_id"):
        res["processed_event_ids"] = [event["event_id"]]
    res.update(updates)
    return res


def route_event(
    state: InterviewState,
) -> Command[
    Literal[
        "record_question",
        "inject_guidance",
        "present_problem",
        "mark_problem_discussed",
        "transition_stage",
        "complete_interview",
        "__end__",
    ]
]:
    """Route incoming orchestrator event to the appropriate state mutation handler."""
    event = state.get("incoming_event")
    if not event:
        return Command(goto="__end__")

    event_id = event.get("event_id")
    processed_ids = state.get("processed_event_ids", [])

    # Idempotency check: if already processed, terminate without duplicate mutation
    if event_id and event_id in processed_ids:
        return Command(goto="__end__", update={"incoming_event": None})

    event_type = event.get("type")
    match event_type:
        case "QUESTION_ASKED":
            goto = "record_question"
        case "GUIDANCE_RECEIVED":
            goto = "inject_guidance"
        case "PROBLEM_PRESENTED":
            goto = "present_problem"
        case "PROBLEM_DISCUSSED":
            goto = "mark_problem_discussed"
        case "TRANSITION_REQUESTED":
            goto = "transition_stage"
        case "INTERVIEW_COMPLETED":
            goto = "complete_interview"
        case "SESSION_INITIALIZED":
            return Command(goto="__end__", update={"incoming_event": None})
        case _:
            raise ValueError(f"Unsupported OrchestratorEvent type: {event_type}")

    return Command(goto=goto)


def record_question(state: InterviewState) -> Dict[str, Any]:
    """Increment stage and total question counters when a question is asked or answered."""
    event = state.get("incoming_event", {})
    current_stage = event.get("stage") or state.get("current_stage", "INTRO")
    content = event.get("question_text", "")
    actor = event.get("actor", "GEMINI")

    counts = dict(state.get("stage_question_counts", {}))
    substantive_counts = dict(state.get("stage_substantive_turn_counts", {}))
    total = state.get("total_questions_asked", 0)

    if actor == "CANDIDATE":
        words = content.strip().split()
        is_greeting = any(content.lower().startswith(g) for g in ["hello", "hi vetra", "hi there", "can you hear me"])
        if len(words) >= 6 and not is_greeting:
            substantive_counts[current_stage] = substantive_counts.get(current_stage, 0) + 1
    else:
        counts[current_stage] = counts.get(current_stage, 0) + 1
        total += 1

    updates: Dict[str, Any] = {
        "stage_question_counts": counts,
        "stage_substantive_turn_counts": substantive_counts,
        "total_questions_asked": total,
    }
    if current_stage == "TECHNICAL_EXERCISE":
        updates["problem_discussed"] = True

    return _finalize_updates(
        event,
        updates,
    )


def inject_guidance(state: InterviewState) -> Dict[str, Any]:
    """Apply dynamic topic focus, competency priorities, and probing directives."""
    event = state.get("incoming_event", {})
    payload = event.get("payload") or {}

    version = state.get("guidance_version", 0) + 1
    pending = payload.get("pending_objectives")
    completed = payload.get("completed_objectives", [])
    coverage_update = payload.get("competency_coverage", {})

    merged_coverage = dict(state.get("competency_coverage", {}))
    merged_coverage.update(coverage_update)

    updates: Dict[str, Any] = {
        "latest_guidance": payload,
        "guidance_version": version,
        "guidance_history": [
            {
                "version": version,
                "guidance": payload,
                "actor": event.get("actor", "KIMI"),
                "created_at": event.get("created_at", datetime.now(timezone.utc).isoformat()),
            }
        ],
        "competency_coverage": merged_coverage,
    }

    # Overwrite pending objectives if provided
    if pending is not None:
        updates["pending_objectives"] = pending

    # Additive completed objectives via reducer
    if completed:
        updates["completed_objectives"] = completed

    return _finalize_updates(event, updates)


def present_problem(state: InterviewState) -> Dict[str, Any]:
    """Record active technical challenge and set presentation flag."""
    event = state.get("incoming_event", {})
    problem_id = event.get("problem_id")

    return _finalize_updates(
        event,
        {
            "active_problem_id": problem_id,
            "problem_presented": True,
            "problem_discussed": False,
        },
    )


def mark_problem_discussed(state: InterviewState) -> Dict[str, Any]:
    """Flag that the technical challenge has been discussed with the candidate."""
    event = state.get("incoming_event", {})

    return _finalize_updates(
        event,
        {
            "problem_discussed": True,
        },
    )


def transition_stage(state: InterviewState) -> Dict[str, Any]:
    """Validate stage guards and execute stage progression."""
    event = state.get("incoming_event", {})
    target_stage = event.get("target_stage", "")
    requested_by = event.get("requested_by") or event.get("actor") or "GEMINI"
    reason = event.get("transition_reason")

    decision = validate_transition_guard(
        state=state,
        requested_stage=target_stage,
        requested_by=requested_by,
        transition_reason=reason,
    )

    now = datetime.now(timezone.utc).isoformat()
    updates: Dict[str, Any] = {
        "last_decision": decision.model_dump(),
    }

    if decision.allowed:
        updates["current_stage"] = target_stage
        updates["last_transition_error"] = None
        updates["stage_history"] = [
            {
                "stage": target_stage,
                "entered_at": now,
                "requested_by": requested_by,
                "reason": reason or decision.reason,
            }
        ]
        if target_stage == "COMPLETED":
            updates["is_completed"] = True
    else:
        updates["last_transition_error"] = decision.reason
        # Silently update guidance instructions to help Gemini continue smoothly without apologizing
        guidance = dict(state.get("latest_guidance") or {})
        existing_instructions = list(guidance.get("instructions", []))
        corrective_directive = (
            f"Stage transition to '{decision.requested_stage}' was not permitted ({decision.reason}). "
            f"Do not apologize. Continue naturally in '{decision.current_stage}' with another focused question."
        )
        if corrective_directive not in existing_instructions:
            existing_instructions.insert(0, corrective_directive)
        guidance["instructions"] = existing_instructions
        updates["latest_guidance"] = guidance

    return _finalize_updates(event, updates)


def complete_interview(state: InterviewState) -> Dict[str, Any]:
    """Mark the interview session as completed."""
    event = state.get("incoming_event", {})
    now = datetime.now(timezone.utc).isoformat()

    return _finalize_updates(
        event,
        {
            "current_stage": "COMPLETED",
            "is_completed": True,
            "last_transition_error": None,
            "stage_history": [
                {
                    "stage": "COMPLETED",
                    "entered_at": now,
                    "requested_by": event.get("requested_by", "SYSTEM"),
                    "reason": event.get("transition_reason", "Interview session finished"),
                }
            ],
        },
    )
