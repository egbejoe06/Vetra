import re
from typing import Optional, Tuple

from src.models.enums import CandidateTurnIntent

# Reasoning and technical answer indicators that signal substantive speech even if starting with a control word
SUBSTANTIVE_ANSWER_INDICATORS = [
    "because",
    "in order to",
    "so that",
    "since we",
    "since it",
    "i would use",
    "i'd use",
    "my approach",
    "we can use",
    "we could use",
    "the reason is",
    "for example",
    "instead of",
    "actually i would",
    "actually i'd",
    "tradeoff",
    "complexity",
    "database",
    "cache",
    "redis",
    "latency",
    "throughput",
    "architecture",
]

AUDIO_CHECK_PREFIXES = [
    "can you hear me",
    "could you hear me",
    "am i audible",
    "is my mic",
    "is my microphone",
    "are you there",
    "can you hear me now",
    "mic check",
    "hello can you hear me",
]

REPETITION_PATTERNS = [
    r"^(?:can|could|would)\s+(?:you\s+)?(?:please\s+)?(?:repeat|say\s+that\s+again|say\s+again|rephrase)",
    r"^(?:please\s+)?repeat\s+(?:the\s+question|that|what\s+you\s+said)",
    r"^(?:pardon|pardon\s+me|come\s+again)",
    r"^(?:what\s+did\s+you\s+say|what\s+was\s+the\s+question|what\s+was\s+that)",
    r"^(?:i\s+)?(?:didn't|did\s+not|couldn't|could\s+not)\s+(?:quite\s+)?(?:catch|hear|understand)\s+(?:that|what\s+you|the\s+question)",
    r"^(?:you\s+)?(?:cut|are\s+cutting)\s+out",
    r"^(?:the\s+)?audio\s+(?:cut|broke|is\s+breaking)\s+out",
    r"^(?:i\s+)?missed\s+(?:that|the\s+last\s+part|the\s+question)",
    r"^sorry\s*,\?\s*(?:can\s+you\s+repeat|what\s+did\s+you\s+say|i\s+didn't\s+catch)",
    r"^say\s+(?:that\s+)?again",
]

CLARIFICATION_PATTERNS = [
    r"^(?:what\s+do\s+you\s+mean\s+by|what\s+is\s+meant\s+by)",
    r"^(?:could|can)\s+you\s+clarify\s+(?:what|whether|if|the)",
    r"^(?:are\s+you\s+asking|do\s+you\s+mean)\s+",
    r"^(?:do\s+you\s+mean\s+in\s+terms\s+of|are\s+we\s+talking\s+about)",
    r"^(?:when\s+you\s+say\s+.*,\s+do\s+you\s+mean)",
]

INTERRUPTION_STARTERS = [
    "wait",
    "hold on",
    "one second",
    "one sec",
    "just a second",
    "just a sec",
    "give me a moment",
    "give me a sec",
    "hang on",
]

GREETING_STARTERS = [
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "hi vetra",
    "hello vetra",
    "hey vetra",
]


def normalize_text(text: str) -> str:
    """Normalize input text for positional and structural evaluation."""
    if not text:
        return ""
    cleaned = text.strip().lower()
    # Normalize multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Strip leading punctuation (except quotes/parentheses)
    cleaned = re.sub(r"^[^\w\s]+", "", cleaned)
    return cleaned.strip()


def has_substantive_reasoning_structure(text: str) -> bool:
    """Check if the text contains connective conjunctions or technical phrasing
    characteristic of an actual engineering answer.
    """
    words = text.split()
    # If the text has significant length and contains reasoning markers, it's an answer
    for marker in SUBSTANTIVE_ANSWER_INDICATORS:
        if marker in text:
            return True
    return False


def looks_like_control_utterance(text: str) -> bool:
    """Routing heuristic: Determine if an utterance could be a control/clarification request.
    Length is treated purely as a routing heuristic, never as an exclusion criterion for ANSWER.
    """
    words = text.split()
    word_count = len(words)

    # 1. Very long utterances (> 20 words) with reasoning structure are almost never pure control phrases
    if word_count > 20 and has_substantive_reasoning_structure(text):
        return False

    # 2. Check if starts with common audio check or repetition phrases
    if any(text.startswith(prefix) for prefix in AUDIO_CHECK_PREFIXES):
        return True

    for pattern in REPETITION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    for pattern in CLARIFICATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    # 3. Interruption starters (e.g., "Wait", "Hold on")
    for starter in INTERRUPTION_STARTERS:
        if text == starter or text.startswith(starter + " ") or text.startswith(starter + ","):
            # If it starts with "Wait..." but continues into an explanation ("Wait, actually I would use Redis because..."),
            # it should be routed to ANSWER if substantive indicators exist
            if has_substantive_reasoning_structure(text):
                return False
            # If short without substantive reasoning, treat as interruption candidate
            if word_count <= 8:
                return True

    # 4. Standalone greetings
    for greeting in GREETING_STARTERS:
        if text == greeting or text.startswith(greeting + " ") or text.startswith(greeting + ","):
            if word_count <= 6:
                return True

    # 5. Short standalone questions/clarifications
    if word_count <= 10 and ("?" in text or text.endswith("?")):
        return True

    return False


def match_control_intent(text: str) -> Optional[CandidateTurnIntent]:
    """Positional and priority evaluation of control intent."""
    words = text.split()
    word_count = len(words)
    stripped_punct = re.sub(r"[^\w\s]", "", text).strip()

    # 1. AUDIO_CHECK: High precedence
    if any(stripped_punct.startswith(prefix) for prefix in AUDIO_CHECK_PREFIXES):
        return CandidateTurnIntent.AUDIO_CHECK
    if stripped_punct in ("can you hear me", "hello can you hear me", "am i audible", "mic check", "is my mic working"):
        return CandidateTurnIntent.AUDIO_CHECK

    # 2. REPETITION_REQUEST: High precedence
    for pattern in REPETITION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return CandidateTurnIntent.REPETITION_REQUEST
    if stripped_punct in ("pardon", "repeat", "repeat that", "what did you say", "say again", "you cut out"):
        return CandidateTurnIntent.REPETITION_REQUEST

    # 3. INTERRUPTION: Must not have substantive answer structure
    for starter in INTERRUPTION_STARTERS:
        if text == starter or text.startswith(starter + " ") or text.startswith(starter + ","):
            if not has_substantive_reasoning_structure(text) and word_count <= 8:
                return CandidateTurnIntent.INTERRUPTION

    # 4. CLARIFICATION_REQUEST
    for pattern in CLARIFICATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return CandidateTurnIntent.CLARIFICATION_REQUEST
    if text.endswith("?") and (
        text.startswith("what is ") or text.startswith("what do ") or text.startswith("clarify ") or "in what sense" in text
    ):
        return CandidateTurnIntent.CLARIFICATION_REQUEST

    # 5. GREETING
    for greeting in GREETING_STARTERS:
        if stripped_punct == greeting or stripped_punct.startswith(greeting + " ") or stripped_punct.startswith(greeting + ","):
            if word_count <= 5 and not has_substantive_reasoning_structure(text):
                return CandidateTurnIntent.GREETING

    return None


def classify_candidate_turn(text: str) -> Tuple[CandidateTurnIntent, bool]:
    """Authoritative classifier for candidate speech turns.
    Returns:
        (CandidateTurnIntent, is_substantive: bool)
    
    Principles:
    - Length is a routing heuristic, never an exclusion criterion for ANSWER.
    - Short answers like 'Redis.' or 'Python.' are classified as ANSWER (is_substantive=True).
    - Control intents (REPETITION_REQUEST, AUDIO_CHECK, CLARIFICATION_REQUEST, INTERRUPTION, GREETING)
      are non-substantive (is_substantive=False).
    """
    normalized = normalize_text(text)
    if not normalized:
        return CandidateTurnIntent.OFF_TOPIC, False

    if looks_like_control_utterance(normalized):
        intent = match_control_intent(normalized)
        if intent is not None:
            return intent, False

    # Default fallback: If not a control utterance, it is a valid ANSWER
    return CandidateTurnIntent.ANSWER, True
