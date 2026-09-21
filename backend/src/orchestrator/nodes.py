from datetime import datetime, timezone
from typing import Any, Dict, Literal
from langgraph.types import Command

from src.models.enums import (
    CandidateTurnIntent,
    QuestionLifecycleStatus,
    RecoveryReason,
    SpeechState,
    TurnCompletionStatus,
)
from src.orchestrator.guards import validate_transition_guard
from src.orchestrator.state import InterviewState
from src.service.intent_classifier import classify_candidate_turn


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
        case "QUESTION_ASKED" | "TRANSCRIPT_TURN_COMMITTED":
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
    """Authoritative semantic turn processing and question lifecycle management."""
    event = state.get("incoming_event", {})
    current_stage = event.get("stage") or state.get("current_stage", "INTRO")
    content = (event.get("question_text") or event.get("content") or "").strip()
    actor = event.get("actor", "GEMINI")
    completion_status = event.get("completion_status", TurnCompletionStatus.COMPLETE.value)

    # State copies
    speech_state = state.get("speech_state", SpeechState.NORMAL.value)
    recovery_required = state.get("recovery_required", False)
    recovery_reason = state.get("recovery_reason")
    max_recovery_attempts = state.get("max_recovery_attempts", 2)
    pending_question_id = state.get("pending_question_id")
    pending_question_text = state.get("pending_question_text")
    active_questions = dict(state.get("active_questions", {}))

    stage_slots = dict(state.get("stage_question_slots", {}))
    delivered_counts = dict(state.get("delivered_question_counts", {}))
    answered_counts = dict(state.get("answered_question_counts", {}))
    stage_question_counts = dict(state.get("stage_question_counts", {}))
    substantive_counts = dict(state.get("stage_substantive_turn_counts", {}))
    total_questions = state.get("total_questions_asked", 0)

    delivered_ids = list(state.get("delivered_question_ids", []))
    answered_ids = list(state.get("answered_question_ids", []))
    problem_discussed = state.get("problem_discussed", False)

    if actor == "CANDIDATE":
        intent, is_substantive = classify_candidate_turn(content)

        if intent in (CandidateTurnIntent.REPETITION_REQUEST, CandidateTurnIntent.AUDIO_CHECK):
            # Candidate indicated they could not hear or asked for repetition.
            # Trigger recovery; candidate turn does NOT consume re-delivery attempt.
            recovery_required = True
            recovery_reason = (
                RecoveryReason.AUDIO_INTERRUPTION.value
                if intent == CandidateTurnIntent.REPETITION_REQUEST
                else RecoveryReason.AUDIO_CHECK.value
            )
            speech_state = SpeechState.RECOVERY_REQUIRED.value
            # Substantive turn count is NOT incremented.

        elif intent == CandidateTurnIntent.CLARIFICATION_REQUEST:
            # Candidate asked for question clarification (e.g. 'What do you mean by scalable?').
            # Semantic clarification: blocks progression but consumes 0 delivery attempts.
            recovery_required = True
            recovery_reason = RecoveryReason.QUESTION_CLARIFICATION.value
            speech_state = SpeechState.RECOVERY_REQUIRED.value
            # Substantive turn count is NOT incremented.

        elif intent == CandidateTurnIntent.ANSWER:
            # Valid candidate technical answer
            substantive_counts[current_stage] = substantive_counts.get(current_stage, 0) + 1
            if current_stage == "TECHNICAL_EXERCISE":
                problem_discussed = True

            if pending_question_id:
                if pending_question_id in active_questions:
                    active_questions[pending_question_id]["status"] = QuestionLifecycleStatus.ANSWERED.value
                answered_counts[current_stage] = answered_counts.get(current_stage, 0) + 1
                if pending_question_id not in answered_ids:
                    answered_ids.append(pending_question_id)
                # Clear pending question upon substantive answer
                pending_question_id = None
                pending_question_text = None
                recovery_required = False
                recovery_reason = None
                speech_state = SpeechState.NORMAL.value

        else:
            # Neutral / greeting / interruption / off-topic turn
            pass

    else:
        # Interrupted Gemini speech
        if completion_status != TurnCompletionStatus.COMPLETE.value:
            if pending_question_id and pending_question_id in active_questions:
                q_info = active_questions[pending_question_id]
                q_info["status"] = QuestionLifecycleStatus.INTERRUPTED.value

                # If Gemini was already in a recovery attempt, this retry failed
                if recovery_required:
                    q_info["recovery_attempts"] = q_info.get("recovery_attempts", 0) + 1

                    if q_info["recovery_attempts"] >= max_recovery_attempts:
                        # Bounded recovery reached; escalate to COULD_NOT_DELIVER
                        q_info["status"] = QuestionLifecycleStatus.COULD_NOT_DELIVER.value
                        recovery_required = False
                        recovery_reason = RecoveryReason.RECOVERY_EXHAUSTED.value
                        pending_question_id = None
                        pending_question_text = None
                        speech_state = SpeechState.NORMAL.value
                    else:
                        recovery_required = True
                        recovery_reason = RecoveryReason.AUDIO_INTERRUPTION.value
                        speech_state = SpeechState.SPEECH_INTERRUPTED.value
                else:
                    recovery_required = True
                    recovery_reason = RecoveryReason.AUDIO_INTERRUPTION.value
                    speech_state = SpeechState.SPEECH_INTERRUPTED.value
            else:
                recovery_required = True
                recovery_reason = RecoveryReason.AUDIO_INTERRUPTION.value
                speech_state = SpeechState.SPEECH_INTERRUPTED.value
            # ZERO QUOTA CHANGE for interrupted speech

        else:
            # Gemini turn completed successfully
            is_question = "?" in content or content.lower().startswith(
                ("how", "what", "why", "could you", "can you", "tell me", "walk me through", "describe")
            )

            if is_question:
                if pending_question_id and pending_question_id in active_questions:
                    # Existing question re-delivered or clarified
                    q_info = active_questions[pending_question_id]
                    if recovery_reason == RecoveryReason.QUESTION_CLARIFICATION.value:
                        # Clarification was spoken; pending question awaits answer
                        recovery_required = False
                        recovery_reason = None
                        speech_state = SpeechState.NORMAL.value
                    else:
                        # Successfully re-delivered an interrupted question
                        q_info["status"] = QuestionLifecycleStatus.DELIVERED.value
                        recovery_required = False
                        recovery_reason = None
                        speech_state = SpeechState.NORMAL.value
                        if pending_question_id not in delivered_ids:
                            delivered_ids.append(pending_question_id)
                            delivered_counts[current_stage] = delivered_counts.get(current_stage, 0) + 1
                else:
                    # Allocate a brand-new stable question_id
                    current_slots = stage_slots.get(current_stage, 0) + 1
                    question_id = f"q_{current_stage.lower()}_{current_slots:02d}"
                    stage_slots[current_stage] = current_slots
                    stage_question_counts[current_stage] = current_slots
                    total_questions += 1

                    pending_question_id = question_id
                    pending_question_text = content
                    active_questions[question_id] = {
                        "status": QuestionLifecycleStatus.DELIVERED.value,
                        "recovery_attempts": 0,
                        "stage": current_stage,
                        "text": content,
                        "turn_ids": [],
                    }
                    if question_id not in delivered_ids:
                        delivered_ids.append(question_id)
                    delivered_counts[current_stage] = delivered_counts.get(current_stage, 0) + 1
                    recovery_required = False
                    recovery_reason = None
                    speech_state = SpeechState.NORMAL.value

    updates: Dict[str, Any] = {
        "speech_state": speech_state,
        "recovery_required": recovery_required,
        "recovery_reason": recovery_reason,
        "pending_question_id": pending_question_id,
        "pending_question_text": pending_question_text,
        "active_questions": active_questions,
        "stage_question_slots": stage_slots,
        "delivered_question_counts": delivered_counts,
        "answered_question_counts": answered_counts,
        "stage_question_counts": stage_question_counts,
        "stage_substantive_turn_counts": substantive_counts,
        "total_questions_asked": total_questions,
        "delivered_question_ids": delivered_ids,
        "answered_question_ids": answered_ids,
        "problem_discussed": problem_discussed,
    }

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
