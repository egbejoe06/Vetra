import logging
import random
import threading
import time
from typing import Any, Callable, Optional

from google import genai
from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)


class PlannerLLMClient:
    """Encapsulates LLM client initialization, concurrency locking,
    thread-safe rate limit pacing, and exponential backoff retry for Gemini & Kimi.
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        moonshot_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        kimi_model: Optional[str] = None,
        gemini_call_gap_seconds: Optional[float] = None,
    ):
        self.gemini_api_key = gemini_api_key or settings.GOOGLE_API_KEY
        self.moonshot_api_key = moonshot_api_key or settings.MOONSHOT_API_KEY
        self.gemini_flash_lite_model = getattr(settings, "GEMINI_FLASH_LITE_MODEL", "gemini-2.5-flash-lite")
        self.gemini_flash_model = gemini_model or getattr(settings, "GEMINI_PLANNER_MODEL", "gemini-2.5-flash")
        self.gemini_model = self.gemini_flash_model
        self.kimi_model = kimi_model or settings.KIMI_EXERCISE_MODEL
        self.enable_kimi_coding_fallback = getattr(settings, "ENABLE_KIMI_CODING_FALLBACK", False)
        self.gemini_call_gap_seconds = (
            gemini_call_gap_seconds if gemini_call_gap_seconds is not None else settings.GEMINI_CALL_GAP_SECONDS
        )
        self.gemini_max_retries = settings.GEMINI_MAX_RETRIES
        self.kimi_timeout_seconds = getattr(settings, "KIMI_TIMEOUT_SECONDS", 75.0)
        self.kimi_max_retries = getattr(settings, "KIMI_MAX_RETRIES", 2)
        self.thinking_budget = getattr(settings, "GEMINI_THINKING_BUDGET", 0)

        # Thread synchronization lock for rate limit pacing across concurrent requests
        self._lock = threading.Lock()
        self._last_gemini_call_timestamp: float = 0.0

        # Kimi concurrency lock to enforce strict 1-concurrency limit for Moonshot API tier
        self._kimi_lock = threading.Lock()

        # Gemini Client
        self.gemini_client: Optional[genai.Client] = None
        if self.gemini_api_key:
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")

        # Moonshot / Kimi Client (OpenAI SDK compatible)
        self.kimi_client: Optional[OpenAI] = None
        if self.moonshot_api_key and self.moonshot_api_key != "EMPTY_MOONSHOT_KEY":
            try:
                self.kimi_client = OpenAI(
                    api_key=self.moonshot_api_key,
                    base_url=settings.MOONSHOT_BASE_URL,
                    timeout=self.kimi_timeout_seconds,
                    max_retries=self.kimi_max_retries,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Kimi client: {e}")

    def pace_gemini_call(self) -> None:
        """Enforces a minimum time gap between sequential Gemini API calls to prevent rate limits.
        Thread-safe under concurrent requests using self._lock.
        """
        if self.gemini_call_gap_seconds <= 0:
            return

        with self._lock:
            elapsed = time.time() - self._last_gemini_call_timestamp
            if elapsed < self.gemini_call_gap_seconds:
                sleep_duration = self.gemini_call_gap_seconds - elapsed
                logger.debug(f"Pacing Gemini API call: sleeping for {sleep_duration:.2f}s to avoid rate limits.")
                time.sleep(sleep_duration)
            self._last_gemini_call_timestamp = time.time()

    def call_gemini_with_retry(self, fn: Callable[[], Any], operation_name: str = "Gemini Operation") -> Any:
        """Executes a Gemini API call with rate limit pacing and exponential backoff retry on 429/ResourceExhausted."""
        if not self.gemini_client:
            raise RuntimeError(f"Cannot execute '{operation_name}': Google API Key is not configured.")

        self.pace_gemini_call()

        for attempt in range(1, self.gemini_max_retries + 1):
            try:
                result = fn()
                with self._lock:
                    self._last_gemini_call_timestamp = time.time()
                return result
            except Exception as e:
                is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e).upper() or "quota" in str(e).lower()
                if is_rate_limit and attempt < self.gemini_max_retries:
                    backoff = (2 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(
                        f"Rate limit encountered in {operation_name} (Attempt {attempt}/{self.gemini_max_retries}). "
                        f"Backing off for {backoff:.2f}s... Error: {e}"
                    )
                    time.sleep(backoff)
                else:
                    with self._lock:
                        self._last_gemini_call_timestamp = time.time()
                    raise
