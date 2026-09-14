import hashlib
import logging
import threading
import time
from typing import Dict, Optional, Tuple

from src.schemas.planner import CandidateProfile

logger = logging.getLogger("vetra.agents.resume_cache")


class ResumeFreezeCache:
    """Thread-safe in-memory cache for frozen CandidateProfile structures.
    
    Prevents re-invoking multimodal/LLM resume parsing when candidate resume
    content has not changed between retries or job spec adjustments.
    """

    def __init__(self, default_ttl_seconds: float = 86400.0, max_entries: int = 200):
        self._cache: Dict[str, Tuple[CandidateProfile, float]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl_seconds
        self._max_entries = max_entries

    @staticmethod
    def compute_text_hash(text: str) -> str:
        """Computes SHA-256 fingerprint from normalized raw resume text."""
        normalized = " ".join(text.strip().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_bytes_hash(data: bytes) -> str:
        """Computes SHA-256 fingerprint from raw file bytes (e.g. PDF)."""
        return hashlib.sha256(data).hexdigest()

    def get(self, hash_key: str) -> Optional[CandidateProfile]:
        """Retrieves cached CandidateProfile if present and not expired."""
        with self._lock:
            entry = self._cache.get(hash_key)
            if not entry:
                return None

            profile, expires_at = entry
            if time.time() > expires_at:
                del self._cache[hash_key]
                logger.info(f"Resume freeze cache entry for {hash_key[:12]}... expired and removed.")
                return None

            logger.info(f"Resume freeze cache HIT for hash {hash_key[:12]}... (Candidate: {profile.candidate_name})")
            return profile

    def set(self, hash_key: str, profile: CandidateProfile, ttl_seconds: Optional[float] = None) -> None:
        """Stores CandidateProfile in cache with expiration."""
        ttl = ttl_seconds or self._default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            # Evict oldest entry if at capacity
            if len(self._cache) >= self._max_entries and hash_key not in self._cache:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]

            # Attach freeze hash to profile if attribute exists
            try:
                profile.freeze_hash = hash_key
            except Exception:
                pass
            self._cache[hash_key] = (profile, expires_at)
            logger.info(f"Resume freeze cache STORED for hash {hash_key[:12]}... (Candidate: {profile.candidate_name}, TTL: {ttl:.0f}s)")

    def invalidate(self, hash_key: str) -> bool:
        """Invalidates a specific resume cache entry."""
        with self._lock:
            if hash_key in self._cache:
                del self._cache[hash_key]
                logger.info(f"Resume freeze cache INVALIDATED for hash {hash_key[:12]}...")
                return True
            return False

    def clear(self) -> None:
        """Clears all cached resumes."""
        with self._lock:
            self._cache.clear()
            logger.info("Resume freeze cache CLEARED.")

    def size(self) -> int:
        """Returns the number of active cached items."""
        with self._lock:
            now = time.time()
            expired = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in expired:
                del self._cache[k]
            return len(self._cache)


# Global singleton instance
resume_freeze_cache = ResumeFreezeCache()
