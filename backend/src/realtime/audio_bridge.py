import base64
import logging
from typing import Optional, Tuple, Union

logger = logging.getLogger("vetra.realtime.audio_bridge")

# Audio specs
CANDIDATE_SAMPLE_RATE = 16000  # 16kHz
CANDIDATE_CHANNELS = 1         # Mono
CANDIDATE_BIT_DEPTH = 16       # 16-bit (2 bytes per sample)
BYTES_PER_SAMPLE = CANDIDATE_BIT_DEPTH // 8  # 2 bytes

# 100ms chunks: 16000 samples/sec * 0.1 sec * 2 bytes = 3200 bytes
CHUNK_DURATION_MS = 100
EXPECTED_CHUNK_BYTES = int(CANDIDATE_SAMPLE_RATE * (CHUNK_DURATION_MS / 1000.0) * BYTES_PER_SAMPLE)

GEMINI_OUTPUT_SAMPLE_RATE = 24000  # 24kHz native model audio


def base64_to_pcm(base64_str: str) -> bytes:
    """Decode a base64 encoded audio string to raw PCM bytes."""
    try:
        return base64.b64decode(base64_str)
    except Exception as err:
        logger.error(f"Failed to decode base64 audio data: {err}")
        raise ValueError(f"Invalid base64 audio payload: {err}") from err


def pcm_to_base64(pcm_data: Union[bytes, str]) -> str:
    """Encode raw PCM bytes to a base64 string."""
    if isinstance(pcm_data, str):
        return pcm_data
    return base64.b64encode(pcm_data).decode("utf-8")


def validate_pcm_chunk(
    chunk: bytes,
    expected_sample_rate: int = CANDIDATE_SAMPLE_RATE,
    allow_partial: bool = True
) -> bool:
    """Verify that a PCM chunk contains valid 16-bit aligned byte data."""
    if not chunk:
        return False
    # Each sample is 2 bytes (16-bit)
    if len(chunk) % 2 != 0:
        logger.warning(f"PCM chunk has misaligned byte length: {len(chunk)}")
        return False
    return True


def slice_pcm_buffer(buffer: bytearray, chunk_size: int = EXPECTED_CHUNK_BYTES) -> Tuple[list[bytes], bytearray]:
    """Slice an accumulating bytearray into uniform PCM chunk segments.
    Returns (list_of_chunks, remaining_buffer).
    """
    chunks: list[bytes] = []
    while len(buffer) >= chunk_size:
        chunks.append(bytes(buffer[:chunk_size]))
        buffer = buffer[chunk_size:]
    return chunks, buffer
