import re
from typing import Optional, Tuple


class EvaluationTriggerPolicy:
    """Deterministic, domain-agnostic evaluation trigger policy.
    
    Guarantees that evaluation batches are queued deterministically:
    1. Immediately when MAX_NEW_TURNS (5) unevaluated turns accumulate.
    2. When MIN_NEW_TURNS (3) turns accumulate AND a significant event is detected:
       - Substantive candidate dialogue volume (word count >= 45)
       - Explicit technical claim, causal diagnosis, or refutation
       - Candidate answering an active strategic probe
       - Stage transition requested
    3. When an interview stage completes (flushing any unevaluated turns >= 1).
    """

    MIN_NEW_TURNS: int = 3
    MAX_NEW_TURNS: int = 5

    # Regex patterns indicating explicit technical claims, causal explanations, or refutations
    # (High-signal dialogue regardless of length or domain)
    _EXPLICIT_CLAIM_PATTERNS = [
        re.compile(r"^(no|yes|actually|correct|incorrect|false|true)\b.*?\bbecause\b", re.IGNORECASE),
        re.compile(r"\b(the\s+(?:root\s+cause|bug|issue|problem|flaw|invariant|bottleneck)\s+is)\b", re.IGNORECASE),
        re.compile(r"\b(it\s+fails\s+(?:when|because|if))\b", re.IGNORECASE),
        re.compile(r"\b(instead\s+of\s+.*?\bwe\s+(?:should|need|must|can)\b)", re.IGNORECASE),
        re.compile(r"\b(?:not|isn't|cannot\s+be)\s+(?:atomic|consistent|thread-safe|idempotent|isolated|safe)\b", re.IGNORECASE),
        re.compile(r"\bviolates?\s+(?:the|an)\s+(?:invariant|contract|constraint|sla)\b", re.IGNORECASE),
        re.compile(r"\bleads?\s+to\s+(?:a\s+)?(?:deadlock|race\s+condition|data\s+loss|memory\s+leak|infinite\s+loop|stale\s+read)\b", re.IGNORECASE),
    ]

    @classmethod
    def should_evaluate(
        cls,
        new_turn_count: int,
        significant_event_detected: bool = False,
        is_stage_completion: bool = False,
    ) -> bool:
        """Evaluate whether a new evaluation batch should be triggered."""
        if is_stage_completion and new_turn_count >= 1:
            return True

        if new_turn_count >= cls.MAX_NEW_TURNS:
            return True

        if new_turn_count >= cls.MIN_NEW_TURNS and significant_event_detected:
            return True

        return False

    @classmethod
    def detect_significant_event(
        cls,
        speaker: str,
        content: str,
        code_diff_lines: int = 0,
        is_stage_transition_requested: bool = False,
        is_response_to_probe: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Determines if the latest turn or environment change qualifies as a significant event."""
        if is_stage_transition_requested:
            return True, "Stage transition initiated"

        # Candidate answering an active strategic probe
        if is_response_to_probe and speaker.upper() == "CANDIDATE":
            return True, "Candidate provided response to targeted strategic probe"

        # Only candidate turns are analyzed for substantive technical responses
        if speaker.upper() == "CANDIDATE":
            cleaned = content.strip()
            word_count = len(cleaned.split())

            # 1. Substantive dialogue volume (>= 45 words)
            if word_count >= 45:
                return True, f"Candidate completed substantive technical explanation ({word_count} words)"

            # 2. Explicit technical claim, causal diagnosis, or refutation (even if short, e.g. 7-15 words)
            for pattern in cls._EXPLICIT_CLAIM_PATTERNS:
                if pattern.search(cleaned):
                    return True, "Candidate articulated explicit technical claim or causal diagnosis"

        return False, None
