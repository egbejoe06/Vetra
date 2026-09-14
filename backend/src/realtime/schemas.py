from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator

from src.models.enums import InterviewStage, TranscriptSpeaker


class ClientMessageType(str, Enum):
    AUDIO = "audio"
    TEXT = "text"
    PING = "ping"
    START = "session_start"
    END = "session_end"


class ServerMessageType(str, Enum):
    AUDIO = "audio"
    INTERRUPTED = "interrupted"
    TRANSCRIPT = "transcript"
    TURN_COMPLETE = "turn_complete"
    STAGE_UPDATE = "stage_update"
    PROBLEM_PRESENTED = "problem_presented"
    SESSION_STATUS = "session_status"
    PONG = "pong"
    ERROR = "error"


# ==============================================================================
# Inbound Client Messages (Browser -> WebSocket)
# ==============================================================================

class ClientAudioMessage(BaseModel):
    type: Literal[ClientMessageType.AUDIO, "audio"] = ClientMessageType.AUDIO
    data: str = Field(..., description="Base64-encoded raw 16-bit PCM 16kHz mono audio chunk")
    sample_rate: int = Field(default=16000, description="Sample rate in Hz (default 16000)")


class ClientTextMessage(BaseModel):
    type: Literal[ClientMessageType.TEXT, "text"] = ClientMessageType.TEXT
    text: str = Field(..., description="User chat or typed input")


class ClientPingMessage(BaseModel):
    type: Literal[ClientMessageType.PING, "ping"] = ClientMessageType.PING


class ClientStartMessage(BaseModel):
    type: Literal[ClientMessageType.START, "session_start"] = ClientMessageType.START
    context: Optional[str] = Field(
        default=None,
        description="Serialized candidate profile and interview plan context to prime the AI interviewer"
    )


class ClientEndMessage(BaseModel):
    type: Literal[ClientMessageType.END, "session_end"] = ClientMessageType.END


ClientMessage = Union[
    ClientAudioMessage,
    ClientTextMessage,
    ClientPingMessage,
    ClientStartMessage,
    ClientEndMessage,
]


# ==============================================================================
# Outbound Server Messages (WebSocket -> Browser)
# ==============================================================================

class ServerAudioMessage(BaseModel):
    type: Literal[ServerMessageType.AUDIO, "audio"] = ServerMessageType.AUDIO
    data: str = Field(..., description="Base64-encoded 24kHz PCM audio chunk")
    sample_rate: int = Field(default=24000, description="Interviewer output sample rate (24000 Hz)")
    mime_type: str = Field(default="audio/pcm;rate=24000", description="MIME type")


class ServerInterruptedMessage(BaseModel):
    type: Literal[ServerMessageType.INTERRUPTED, "interrupted"] = ServerMessageType.INTERRUPTED
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of barge-in event"
    )
    reason: str = Field(default="Candidate interruption detected", description="Barge-in reason")


class ServerTranscriptMessage(BaseModel):
    type: Literal[ServerMessageType.TRANSCRIPT, "transcript"] = ServerMessageType.TRANSCRIPT
    speaker: TranscriptSpeaker = Field(..., description="Speaker: CANDIDATE, INTERVIEWER, or SYSTEM")
    text: str = Field(..., description="Streaming or finalized transcript fragment")
    is_final: bool = Field(default=False, description="Whether this completes a conversational turn")
    turn_id: Optional[str] = Field(default=None, description="Sequential authoritative turn ID")
    stage: Optional[InterviewStage] = Field(default=None, description="Interview stage active during turn")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("is_final", mode="before")
    @classmethod
    def coerce_is_final(cls, v: Any) -> bool:
        if v is None:
            return False
        return bool(v)


class ServerTurnCompleteMessage(BaseModel):
    type: Literal[ServerMessageType.TURN_COMPLETE, "turn_complete"] = ServerMessageType.TURN_COMPLETE
    speaker: TranscriptSpeaker = Field(..., description="Speaker whose speaking turn completed")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ServerStageUpdateMessage(BaseModel):
    type: Literal[ServerMessageType.STAGE_UPDATE, "stage_update"] = ServerMessageType.STAGE_UPDATE
    stage: InterviewStage = Field(..., description="Updated active interview stage")
    guidance: Optional[Dict[str, Any]] = Field(default=None, description="Active guidance and focus areas")
    transition_reason: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ServerProblemPresentedMessage(BaseModel):
    type: Literal[ServerMessageType.PROBLEM_PRESENTED, "problem_presented"] = ServerMessageType.PROBLEM_PRESENTED
    problem_id: str = Field(..., description="UUID or ID of the presented technical problem")
    title: str = Field(..., description="Title of the challenge")
    problem_type: str = Field(..., description="Category of technical problem")
    prompt_question: str = Field(..., description="Main problem question")
    instructions: Optional[str] = Field(default=None, description="Detailed candidate challenge instructions")
    code_files: List[Dict[str, Any]] = Field(default_factory=list, description="Boilerplate code files")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ServerSessionStatusMessage(BaseModel):
    type: Literal[ServerMessageType.SESSION_STATUS, "session_status"] = ServerMessageType.SESSION_STATUS
    status: str = Field(..., description="Session status: connected, resumed, reconnecting, completed, closed")
    session_id: str = Field(..., description="Interview Session ID")
    message: Optional[str] = None
    resumed: bool = Field(default=False, description="Whether the session was resumed with existing handle")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ServerPongMessage(BaseModel):
    type: Literal[ServerMessageType.PONG, "pong"] = ServerMessageType.PONG
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ServerErrorMessage(BaseModel):
    type: Literal[ServerMessageType.ERROR, "error"] = ServerMessageType.ERROR
    message: str = Field(..., description="Descriptive error message")
    code: Optional[str] = Field(default="INTERNAL_ERROR", description="Machine-readable error code")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


ServerMessage = Union[
    ServerAudioMessage,
    ServerInterruptedMessage,
    ServerTranscriptMessage,
    ServerTurnCompleteMessage,
    ServerStageUpdateMessage,
    ServerProblemPresentedMessage,
    ServerSessionStatusMessage,
    ServerPongMessage,
    ServerErrorMessage,
]
