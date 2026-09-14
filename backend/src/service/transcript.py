import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import time
from typing import Dict, List, Optional, Tuple
import uuid

from src.db.supabase import supabase
from src.models.enums import InterviewStage, TranscriptSpeaker
from src.orchestrator.engine import interview_orchestrator
from src.schemas.interview import TranscriptTurnCreate, TranscriptTurnResponse
from src.service.evaluation_queue import evaluation_queue
from src.service.evaluation_worker import evaluation_worker

logger = logging.getLogger("vetra.service.transcript")


class TranscriptService:
    """Buffers streaming transcription fragments from Gemini Live and persists finalized dialogue turns
    directly into Supabase public.transcript_turns table.
    """

    def __init__(self):
        # session_id -> { speaker: accumulated_text }
        self._streaming_buffers: Dict[str, Dict[TranscriptSpeaker, str]] = {}
        # session_id -> continuous sequential turn count
        self._session_turn_indices: Dict[str, int] = {}
        # session_id -> list of (speaker, content_hash, timestamp) for deduplication
        self._dedup_history: Dict[str, List[Tuple[TranscriptSpeaker, str, float]]] = {}

    def append_transcript_fragment(
        self, session_id: str, speaker: TranscriptSpeaker, text: str
    ) -> str:
        """Append an incoming streaming transcript fragment to the active speaker buffer."""
        if session_id not in self._streaming_buffers:
            self._streaming_buffers[session_id] = {
                TranscriptSpeaker.CANDIDATE: "",
                TranscriptSpeaker.INTERVIEWER: "",
            }

        self._streaming_buffers[session_id][speaker] += text
        return self._streaming_buffers[session_id][speaker]

    def get_current_buffer(
        self, session_id: str, speaker: TranscriptSpeaker
    ) -> str:
        """Get the current uncommitted transcript text for a speaker."""
        if session_id not in self._streaming_buffers:
            return ""
        return self._streaming_buffers[session_id].get(speaker, "")

    def clear_buffer(self, session_id: str, speaker: TranscriptSpeaker) -> None:
        """Reset the buffer for a speaker after committing a turn."""
        if session_id in self._streaming_buffers:
            self._streaming_buffers[session_id][speaker] = ""

    async def commit_turn(
        self,
        session_id: str,
        speaker: TranscriptSpeaker,
        stage: Optional[InterviewStage] = None,
        content: Optional[str] = None,
    ) -> Optional[TranscriptTurnResponse]:
        """Finalize and persist a complete dialogue turn into Supabase."""
        sess_key = str(session_id)
        # Use provided content or flush from buffer
        text_to_save = content if content is not None else self.get_current_buffer(session_id, speaker)
        text_to_save = text_to_save.strip()

        if not text_to_save:
            return None

        # Reset buffer immediately
        self.clear_buffer(session_id, speaker)

        # 1. Event / Turn Deduplication (5-second sliding window per speaker)
        now_ts = time.time()
        content_hash = hashlib.sha256(text_to_save.lower().encode("utf-8")).hexdigest()
        if sess_key not in self._dedup_history:
            self._dedup_history[sess_key] = []

        # Prune history older than 15s
        self._dedup_history[sess_key] = [
            entry for entry in self._dedup_history[sess_key]
            if now_ts - entry[2] < 15.0
        ]

        # Check for duplicate turn within last 5 seconds
        for prev_spk, prev_hash, prev_ts in self._dedup_history[sess_key]:
            if prev_spk == speaker and prev_hash == content_hash and (now_ts - prev_ts < 5.0):
                logger.info(
                    f"Deduplicated turn for session {sess_key} [{speaker.value}]: {text_to_save[:50]}..."
                )
                return None

        self._dedup_history[sess_key].append((speaker, content_hash, now_ts))

        # 2. Authoritative Stage Resolution: The orchestrator is the SINGLE source of truth
        current_stage: Optional[InterviewStage] = None
        try:
            state = await interview_orchestrator.get_state(session_id)
            if state and state.get("current_stage"):
                current_stage = InterviewStage(state["current_stage"])
        except Exception as err:
            logger.warning(f"Could not determine stage from orchestrator: {err}")

        if not current_stage:
            current_stage = stage or InterviewStage.INTRO

        turn_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Increment continuous sequential turn count for this session
        next_turn_index = self._session_turn_indices.get(sess_key, 0) + 1
        self._session_turn_indices[sess_key] = next_turn_index

        turn_record = {
            "id": str(turn_id),
            "session_id": sess_key,
            "speaker": speaker.value,
            "stage": current_stage.value,
            "content": text_to_save,
            "turn_index": next_turn_index,
            "created_at": now.isoformat(),
        }

        # Persist to Supabase in threadpool to prevent audio stream jitter
        if supabase:
            try:
                await asyncio.to_thread(
                    lambda: supabase.table("transcript_turns").insert(turn_record).execute()
                )
                logger.info(
                    f"Persisted transcript turn {turn_id} (turn_{next_turn_index:03d}) for session {session_id} "
                    f"[{speaker.value} - {current_stage.value}]: {text_to_save[:60]}..."
                )
            except Exception as err:
                logger.error(f"Failed to persist transcript turn to Supabase: {err}", exc_info=True)
        else:
            logger.warning(f"Supabase not initialized. Transcript turn {turn_id} logged in memory only.")

        # Trigger asynchronous evaluation queue check
        try:
            triggered_job = evaluation_queue.on_turn_committed(
                session_id=sess_key,
                turn_record=turn_record,
            )
            if triggered_job:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(evaluation_worker.process_job(triggered_job))
                except RuntimeError:
                    pass
        except Exception as q_err:
            logger.warning(f"Failed to check evaluation queue on turn {next_turn_index}: {q_err}")

        # Notify orchestrator of turns (both interviewer questions and candidate answers)
        try:
            await interview_orchestrator.record_question_asked(
                session_id=session_id,
                question_text=text_to_save,
                stage=current_stage.value,
                actor="CANDIDATE" if speaker == TranscriptSpeaker.CANDIDATE else "GEMINI",
            )
        except Exception as err:
            logger.warning(f"Failed to record turn in orchestrator: {err}")

        return TranscriptTurnResponse(
            id=turn_id,
            session_id=uuid.UUID(str(session_id)),
            speaker=speaker,
            stage=current_stage,
            content=text_to_save,
            created_at=now,
        )

    def cleanup_session(self, session_id: str) -> None:
        """Clear memory buffers when a session terminates."""
        self._streaming_buffers.pop(session_id, None)


# Default singleton instance
transcript_service = TranscriptService()
