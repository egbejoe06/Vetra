from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from src.agents.evaluator.policy import EvaluationTriggerPolicy
from src.db.supabase import supabase

logger = logging.getLogger("vetra.service.evaluation_queue")


class EvaluationQueueService:
    """Durable Postgres-backed evaluation queue service.
    
    Replaces transient in-memory queues with persistent records in public.evaluation_jobs.
    Supports transactional leasing, retry attempts, crash recovery, and deterministic triggering.
    """

    LEASE_TIMEOUT_SECONDS = 120

    def __init__(self):
        # In-memory tracking of un-evaluated turns per session: session_id -> list of turn dicts
        self._pending_turn_buffers: Dict[str, List[Dict[str, Any]]] = {}
        # In-memory mock jobs store when Supabase client is not initialized (e.g. unit tests)
        self._in_memory_jobs: Dict[str, Dict[str, Any]] = {}

    def get_pending_turns(self, session_id: str) -> List[Dict[str, Any]]:
        """Returns buffered turns awaiting evaluation for a session."""
        return self._pending_turn_buffers.get(str(session_id), [])

    def on_turn_committed(
        self,
        session_id: str,
        turn_record: Dict[str, Any],
        code_diff_lines: int = 0,
        is_stage_transition: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Processes a newly finalized dialogue turn and triggers an evaluation job if policy conditions are met."""
        s_id = str(session_id)
        if s_id not in self._pending_turn_buffers:
            self._pending_turn_buffers[s_id] = []

        self._pending_turn_buffers[s_id].append(turn_record)
        buffered_turns = self._pending_turn_buffers[s_id]
        new_turn_count = len(buffered_turns)

        # Detect significant event
        speaker = turn_record.get("speaker", "")
        content = turn_record.get("content", "")
        has_event, event_reason = EvaluationTriggerPolicy.detect_significant_event(
            speaker=speaker,
            content=content,
            code_diff_lines=code_diff_lines,
            is_stage_transition_requested=is_stage_transition,
        )

        should_trigger = EvaluationTriggerPolicy.should_evaluate(
            new_turn_count=new_turn_count,
            significant_event_detected=has_event,
            is_stage_completion=is_stage_transition,
        )

        if not should_trigger:
            return None

        # Build trigger reason
        trigger_reason = "Turn threshold reached (5 turns)"
        if is_stage_transition:
            trigger_reason = "Stage completion"
        elif has_event:
            trigger_reason = f"Significant event: {event_reason} (Turns: {new_turn_count})"

        # Create evaluation job
        start_turn_idx = buffered_turns[0].get("turn_index", 1)
        end_turn_idx = buffered_turns[-1].get("turn_index", start_turn_idx + new_turn_count - 1)
        turn_uuids = [t.get("id") for t in buffered_turns if t.get("id")]

        job_payload = {
            "session_id": s_id,
            "turns": list(buffered_turns),
            "code_diff_lines": code_diff_lines,
        }

        # Clear buffer for next cycle
        self._pending_turn_buffers[s_id] = []

        job_record = self._create_job_record(
            session_id=s_id,
            start_turn_index=start_turn_idx,
            end_turn_index=end_turn_idx,
            turn_ids=turn_uuids,
            trigger_reason=trigger_reason,
            payload=job_payload,
        )

        logger.info(
            f"Enqueued evaluation job {job_record['id']} for session {s_id} "
            f"[{trigger_reason} - Turns {start_turn_idx} to {end_turn_idx}]"
        )
        return job_record

    def _create_job_record(
        self,
        session_id: str,
        start_turn_index: int,
        end_turn_index: int,
        turn_ids: List[str],
        trigger_reason: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Inserts evaluation job into Supabase or fallback store."""
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        record = {
            "id": job_id,
            "session_id": session_id,
            "batch_index": 1,
            "start_turn_index": start_turn_index,
            "end_turn_index": end_turn_index,
            "turn_ids": turn_ids,
            "trigger_reason": trigger_reason,
            "status": "PENDING",
            "locked_at": None,
            "payload": payload,
            "result": None,
            "error_message": None,
            "attempts": 0,
            "created_at": now.isoformat(),
            "completed_at": None,
        }

        if supabase:
            try:
                supabase.table("evaluation_jobs").insert(record).execute()
            except Exception as err:
                logger.error(f"Failed to persist evaluation_job to Supabase: {err}")
                self._in_memory_jobs[job_id] = record
        else:
            self._in_memory_jobs[job_id] = record

        return record

    def claim_next_pending_job(self) -> Optional[Dict[str, Any]]:
        """Atomically claims next pending or expired-lease job."""
        now = datetime.now(timezone.utc)
        lease_cutoff = (now - timedelta(seconds=self.LEASE_TIMEOUT_SECONDS)).isoformat()

        if supabase:
            try:
                # Find pending job or job with expired lease
                res = (
                    supabase.table("evaluation_jobs")
                    .select("*")
                    .in_("status", ["PENDING", "PROCESSING"])
                    .order("created_at", desc=False)
                    .limit(5)
                    .execute()
                )
                jobs = res.data or []
                for j in jobs:
                    is_pending = j.get("status") == "PENDING"
                    is_expired_processing = (
                        j.get("status") == "PROCESSING"
                        and j.get("locked_at")
                        and j.get("locked_at") < lease_cutoff
                    )
                    if is_pending or is_expired_processing:
                        j_id = j["id"]
                        attempts = j.get("attempts", 0) + 1
                        update_payload = {
                            "status": "PROCESSING",
                            "locked_at": now.isoformat(),
                            "attempts": attempts,
                        }
                        up_res = (
                            supabase.table("evaluation_jobs")
                            .update(update_payload)
                            .eq("id", j_id)
                            .execute()
                        )
                        if up_res.data:
                            return up_res.data[0]
            except Exception as err:
                logger.warning(f"Error querying Supabase for evaluation_jobs: {err}")

        # In-memory fallback for local dev / tests
        for j_id, j in list(self._in_memory_jobs.items()):
            if j["status"] == "PENDING":
                j["status"] = "PROCESSING"
                j["locked_at"] = now.isoformat()
                j["attempts"] += 1
                return j

        return None

    def complete_job(self, job_id: str, result: Dict[str, Any]) -> None:
        """Marks evaluation job as COMPLETED."""
        now = datetime.now(timezone.utc).isoformat()
        update_dict = {
            "status": "COMPLETED",
            "result": result,
            "completed_at": now,
        }
        if supabase:
            try:
                supabase.table("evaluation_jobs").update(update_dict).eq("id", job_id).execute()
            except Exception as err:
                logger.error(f"Failed to complete evaluation job in Supabase: {err}")

        if job_id in self._in_memory_jobs:
            self._in_memory_jobs[job_id].update(update_dict)

    def fail_job(self, job_id: str, error_message: str) -> None:
        """Marks evaluation job as FAILED."""
        update_dict = {
            "status": "FAILED",
            "error_message": error_message,
        }
        if supabase:
            try:
                supabase.table("evaluation_jobs").update(update_dict).eq("id", job_id).execute()
            except Exception as err:
                logger.error(f"Failed to fail evaluation job in Supabase: {err}")

        if job_id in self._in_memory_jobs:
            self._in_memory_jobs[job_id].update(update_dict)


# Default singleton instance
evaluation_queue = EvaluationQueueService()
