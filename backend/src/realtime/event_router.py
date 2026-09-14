import json
import logging
from typing import Any, Dict, Optional, Tuple, Union
from fastapi import WebSocket

from src.models.enums import InterviewStage, TranscriptSpeaker
from src.realtime.audio_bridge import base64_to_pcm, pcm_to_base64, validate_pcm_chunk
from src.realtime.schemas import (
    ClientAudioMessage,
    ClientEndMessage,
    ClientMessage,
    ClientMessageType,
    ClientPingMessage,
    ClientStartMessage,
    ClientTextMessage,
    ServerAudioMessage,
    ServerErrorMessage,
    ServerInterruptedMessage,
    ServerMessage,
    ServerPongMessage,
    ServerProblemPresentedMessage,
    ServerSessionStatusMessage,
    ServerStageUpdateMessage,
    ServerTranscriptMessage,
    ServerTurnCompleteMessage,
)

logger = logging.getLogger("vetra.realtime.event_router")


class RealtimeEventRouter:
    """Parses inbound WebSocket client frames (text JSON or raw binary PCM)
    and serializes outbound server protocol messages.
    """

    @staticmethod
    def parse_client_message(raw_message: Union[str, bytes, dict]) -> Optional[ClientMessage]:
        """Parse incoming WebSocket message from candidate browser."""
        # 1. Raw Binary Audio Frame (16kHz PCM bytes)
        if isinstance(raw_message, (bytes, bytearray)):
            if validate_pcm_chunk(raw_message):
                b64 = pcm_to_base64(bytes(raw_message))
                return ClientAudioMessage(data=b64)
            return None

        # 2. Text / JSON Message
        data: Dict[str, Any]
        if isinstance(raw_message, str):
            try:
                data = json.loads(raw_message)
            except Exception as err:
                logger.warning(f"Failed to decode JSON client message: {err}")
                return None
        elif isinstance(raw_message, dict):
            data = raw_message
        else:
            return None

        msg_type = data.get("type")

        if msg_type in (ClientMessageType.AUDIO, "audio"):
            return ClientAudioMessage(
                data=data.get("data", ""),
                sample_rate=data.get("sample_rate", 16000),
            )
        elif msg_type in (ClientMessageType.TEXT, "text"):
            return ClientTextMessage(text=data.get("text", ""))
        elif msg_type in (ClientMessageType.PING, "ping"):
            return ClientPingMessage()
        elif msg_type in (ClientMessageType.START, "session_start"):
            raw_ctx = data.get("context")
            ctx_str = raw_ctx if isinstance(raw_ctx, str) else (json.dumps(raw_ctx) if raw_ctx is not None else None)
            return ClientStartMessage(context=ctx_str)
        elif msg_type in (ClientMessageType.END, "session_end"):
            return ClientEndMessage()
        else:
            logger.warning(f"Unrecognized client message type: {msg_type}")
            return None

    @staticmethod
    async def send_server_message(websocket: WebSocket, message: ServerMessage) -> None:
        """Serialize and transmit a protocol message to the client WebSocket."""
        try:
            payload = message.model_dump(mode="json")
            await websocket.send_json(payload)
        except Exception as err:
            logger.debug(f"Failed to send server message over WebSocket: {err}")

    @staticmethod
    async def send_audio_chunk(websocket: WebSocket, pcm_bytes: bytes) -> None:
        """Send 24kHz PCM audio chunk to browser."""
        b64 = pcm_to_base64(pcm_bytes)
        msg = ServerAudioMessage(data=b64)
        await RealtimeEventRouter.send_server_message(websocket, msg)

    @staticmethod
    async def send_interruption(websocket: WebSocket) -> None:
        """Send barge-in cutoff notification to browser."""
        msg = ServerInterruptedMessage()
        await RealtimeEventRouter.send_server_message(websocket, msg)

    @staticmethod
    async def send_transcript(
        websocket: WebSocket,
        speaker: TranscriptSpeaker,
        text: str,
        is_final: bool = False,
        stage: Optional[InterviewStage] = None,
        turn_id: Optional[str] = None,
    ) -> None:
        """Send streaming or final dialogue transcript turn."""
        msg = ServerTranscriptMessage(
            speaker=speaker,
            text=text,
            is_final=bool(is_final),
            stage=stage,
            turn_id=turn_id,
        )
        await RealtimeEventRouter.send_server_message(websocket, msg)

    @staticmethod
    async def send_turn_complete(websocket: WebSocket, speaker: TranscriptSpeaker) -> None:
        """Send turn completion notification."""
        msg = ServerTurnCompleteMessage(speaker=speaker)
        await RealtimeEventRouter.send_server_message(websocket, msg)

    @staticmethod
    async def send_stage_update(
        websocket: WebSocket, stage: InterviewStage, guidance: Optional[Dict[str, Any]] = None
    ) -> None:
        """Send stage update notification."""
        msg = ServerStageUpdateMessage(stage=stage, guidance=guidance)
        await RealtimeEventRouter.send_server_message(websocket, msg)

    @staticmethod
    async def send_problem_presented(
        websocket: WebSocket,
        problem_id: str,
        title: str,
        problem_type: str,
        prompt_question: str,
        code_files: list = None,
        instructions: Optional[str] = None,
    ) -> None:
        """Send problem presentation notification."""
        msg = ServerProblemPresentedMessage(
            problem_id=problem_id,
            title=title,
            problem_type=problem_type,
            prompt_question=prompt_question,
            instructions=instructions,
            code_files=code_files or [],
        )
        await RealtimeEventRouter.send_server_message(websocket, msg)

    @staticmethod
    async def send_session_status(
        websocket: WebSocket,
        session_id: str,
        status: str,
        resumed: bool = False,
        message: Optional[str] = None,
    ) -> None:
        """Send session status notification."""
        msg = ServerSessionStatusMessage(
            session_id=session_id,
            status=status,
            resumed=resumed,
            message=message,
        )
        await RealtimeEventRouter.send_server_message(websocket, msg)

    @staticmethod
    async def send_error(websocket: WebSocket, message: str, code: str = "ERROR") -> None:
        """Send error notification."""
        msg = ServerErrorMessage(message=message, code=code)
        await RealtimeEventRouter.send_server_message(websocket, msg)

    @staticmethod
    async def send_pong(websocket: WebSocket) -> None:
        """Send pong response."""
        msg = ServerPongMessage()
        await RealtimeEventRouter.send_server_message(websocket, msg)
