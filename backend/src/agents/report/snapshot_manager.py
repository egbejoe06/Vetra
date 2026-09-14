from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from src.db.supabase import supabase
from src.schemas.report import InterviewSynthesisSnapshot

logger = logging.getLogger("vetra.agents.report.snapshot")


class SnapshotManager:
    """Manages the creation and retrieval of immutable interview synthesis snapshots.
    
    Guarantees that Phase 6 final report generation evaluates a frozen, sealed state
    of dialogue turns, code artifacts, and evaluation signals.
    """

    def __init__(self):
        self._snapshots_cache: Dict[str, InterviewSynthesisSnapshot] = {}
        self._snapshot_data_cache: Dict[str, Dict[str, Any]] = {}

    def create_snapshot(
        self,
        session_id: str,
        transcript_turns: Optional[List[Dict[str, Any]]] = None,
        code_snapshots: Optional[List[Dict[str, Any]]] = None,
        evaluation_signals: Optional[List[Dict[str, Any]]] = None,
        blueprint_version: str = "v1",
    ) -> Tuple[InterviewSynthesisSnapshot, Dict[str, Any]]:
        """Atomically freezes an interview session state into an immutable snapshot."""
        s_id = str(session_id)
        snapshot_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # 1. Fetch transcript turns if not provided
        turns = transcript_turns
        if turns is None:
            turns = []
            if supabase:
                try:
                    res = (
                        supabase.table("transcript_turns")
                        .select("*")
                        .eq("session_id", s_id)
                        .order("turn_index", desc=False)
                        .execute()
                    )
                    turns = res.data or []
                except Exception as err:
                    logger.warning(f"Error fetching turns from Supabase for snapshot: {err}")

        # Ensure turns have sequential turn labels
        turn_ids: List[str] = []
        turn_labels: List[str] = []
        hydrated_turns: List[Dict[str, Any]] = []

        for idx, turn in enumerate(turns, start=1):
            t_id = str(turn.get("id", uuid.uuid4()))
            turn_ids.append(t_id)
            # Use turn_index from DB or sequence idx
            turn_num = turn.get("turn_index") or idx
            label = f"turn_{turn_num:03d}"
            turn_labels.append(label)

            hydrated_turns.append(
                {
                    "id": t_id,
                    "turn_id": label,
                    "speaker": turn.get("speaker", "UNKNOWN"),
                    "stage": turn.get("stage", "INTRO"),
                    "content": turn.get("content", ""),
                    "turn_index": turn_num,
                    "created_at": turn.get("created_at", now.isoformat()),
                }
            )

        # 2. Fetch code snapshots/artifacts if not provided
        codes = code_snapshots
        if codes is None:
            codes = []
            if supabase:
                try:
                    res = (
                        supabase.table("interview_artifacts")
                        .select("*")
                        .eq("session_id", s_id)
                        .execute()
                    )
                    codes = res.data or []
                except Exception as err:
                    logger.warning(f"Error fetching artifacts for snapshot: {err}")

        code_snapshot_ids = [uuid.UUID(str(c.get("id"))) for c in codes if c.get("id")]

        # 3. Fetch evaluation signals if not provided
        signals = evaluation_signals
        if signals is None:
            signals = []
            if supabase:
                try:
                    res = (
                        supabase.table("evaluation_signals")
                        .select("*")
                        .eq("session_id", s_id)
                        .order("created_at", desc=False)
                        .execute()
                    )
                    signals = res.data or []
                except Exception as err:
                    logger.warning(f"Error fetching evaluation signals for snapshot: {err}")

        signal_ids = [uuid.UUID(str(s.get("id"))) for s in signals if s.get("id")]

        # 3b. Detect reached vs unreached interview stages
        ALL_STANDARD_STAGES = [
            "INTRO",
            "RESUME_DEEP_DIVE",
            "TECHNICAL_QA",
            "TECHNICAL_EXERCISE",
            "BEHAVIORAL",
            "WRAP_UP",
        ]
        stages_present = {
            str(t.get("stage", "")).strip().upper()
            for t in hydrated_turns
            if t.get("stage")
        }
        stages_reached = [s for s in ALL_STANDARD_STAGES if s in stages_present]
        stages_not_reached = [s for s in ALL_STANDARD_STAGES if s not in stages_present]

        # 4. Construct snapshot model
        snapshot = InterviewSynthesisSnapshot(
            id=snapshot_id,
            session_id=uuid.UUID(s_id),
            transcript_version=len(turns),
            transcript_turn_ids=turn_ids,
            turn_labels=turn_labels,
            code_snapshot_ids=code_snapshot_ids,
            evaluation_signal_ids=signal_ids,
            stages_reached=stages_reached,
            stages_not_reached=stages_not_reached,
            blueprint_version=blueprint_version,
            created_at=now,
        )

        hydrated_data = {
            "snapshot": snapshot,
            "turns": hydrated_turns,
            "code_artifacts": codes,
            "evaluation_signals": signals,
            "stages_reached": stages_reached,
            "stages_not_reached": stages_not_reached,
            "is_incomplete": len(stages_not_reached) > 0 or "TECHNICAL_EXERCISE" not in stages_reached,
        }

        # 5. Persist to Supabase public.synthesis_snapshots
        record = {
            "id": str(snapshot_id),
            "session_id": s_id,
            "transcript_version": snapshot.transcript_version,
            "turn_ids": turn_ids,
            "turn_labels": turn_labels,
            "code_snapshot_ids": [str(cid) for cid in code_snapshot_ids],
            "signal_ids": [str(sid) for sid in signal_ids],
            "blueprint_version": blueprint_version,
            "created_at": now.isoformat(),
        }

        if supabase:
            try:
                supabase.table("synthesis_snapshots").insert(record).execute()
                logger.info(f"Persisted immutable synthesis snapshot {snapshot_id} for session {s_id}")
            except Exception as err:
                logger.warning(f"Failed to persist synthesis snapshot to Supabase: {err}")

        # Cache locally
        self._snapshots_cache[str(snapshot_id)] = snapshot
        self._snapshot_data_cache[str(snapshot_id)] = hydrated_data

        return snapshot, hydrated_data

    def get_snapshot_data(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve hydrated data for a sealed snapshot."""
        return self._snapshot_data_cache.get(str(snapshot_id))


# Default singleton instance
snapshot_manager = SnapshotManager()
