import re
from typing import Optional, Tuple

from src.models.enums import QuestionDifficulty


# Regex patterns matching seniority keywords with word boundaries
_TITLE_PATTERNS = [
    (re.compile(r"\b(principal|distinguished|fellow)\b", re.IGNORECASE), QuestionDifficulty.PRINCIPAL, "Job title specifies Principal level"),
    (re.compile(r"\b(staff|lead|tech\s*lead|director|manager|architect)\b", re.IGNORECASE), QuestionDifficulty.LEAD, "Job title specifies Staff/Lead level"),
    (re.compile(r"\b(senior|sr\.?|iii|3)\b", re.IGNORECASE), QuestionDifficulty.SENIOR, "Job title specifies Senior level"),
    (re.compile(r"\b(mid|intermediate|ii|2)\b", re.IGNORECASE), QuestionDifficulty.MID, "Job title specifies Mid level"),
    (re.compile(r"\b(junior|jr\.?|entry|intern|associate|i|1)\b", re.IGNORECASE), QuestionDifficulty.JUNIOR, "Job title specifies Junior level"),
]

_INSTRUCTION_PATTERNS = [
    (re.compile(r"\b(?:target\s+)?(?:level|seniority|difficulty)\s*[:=]?\s*principal\b", re.IGNORECASE), QuestionDifficulty.PRINCIPAL, "Recruiter instructions specify Principal level"),
    (re.compile(r"\b(?:target\s+)?(?:level|seniority|difficulty)\s*[:=]?\s*(?:lead|staff)\b", re.IGNORECASE), QuestionDifficulty.LEAD, "Recruiter instructions specify Lead/Staff level"),
    (re.compile(r"\b(?:target\s+)?(?:level|seniority|difficulty)\s*[:=]?\s*senior\b", re.IGNORECASE), QuestionDifficulty.SENIOR, "Recruiter instructions specify Senior level"),
    (re.compile(r"\b(?:target\s+)?(?:level|seniority|difficulty)\s*[:=]?\s*mid\b", re.IGNORECASE), QuestionDifficulty.MID, "Recruiter instructions specify Mid level"),
    (re.compile(r"\b(?:target\s+)?(?:level|seniority|difficulty)\s*[:=]?\s*(?:junior|entry)\b", re.IGNORECASE), QuestionDifficulty.JUNIOR, "Recruiter instructions specify Junior level"),
]


def resolve_seniority_tier(
    seniority: Optional[QuestionDifficulty | str] = None,
    job_title: str = "",
    years_of_experience: float = 0.0,
    instructions: str = "",
) -> Tuple[QuestionDifficulty, str]:
    """Resolves the candidate/role target seniority tier using a strict priority hierarchy:
    
    Priority 1 (Authoritative): Explicit recruiter seniority field or recruiter instruction directives.
    Priority 2: Word-boundary keyword detection on job_title ONLY (avoids false-positives from JD body text).
    Priority 3: Strict, non-overlapping YOE fallback:
      - 0 <= YOE <= 2 -> JUNIOR
      - 2 < YOE <= 5  -> MID
      - 5 < YOE <= 8  -> SENIOR
      - YOE > 8       -> LEAD (or PRINCIPAL if title indicates)
    """
    # Priority 1a: Direct recruiter seniority field
    if seniority:
        if isinstance(seniority, QuestionDifficulty):
            return seniority, f"Recruiter explicitly selected {seniority.value} difficulty"
        clean = str(seniority).strip().upper()
        for diff in QuestionDifficulty:
            if diff.value == clean or diff.name == clean:
                return diff, f"Recruiter explicitly configured {diff.value} difficulty"

    # Priority 1b: Explicit recruiter instruction directive
    if instructions:
        for pattern, diff, reason in _INSTRUCTION_PATTERNS:
            if pattern.search(instructions):
                return diff, reason

    # Priority 2: Keyword matching on job_title ONLY
    if job_title:
        for pattern, diff, reason in _TITLE_PATTERNS:
            if pattern.search(job_title):
                return diff, reason

    # Priority 3: Non-overlapping Years of Experience boundaries
    try:
        yoe = float(years_of_experience)
    except (ValueError, TypeError):
        yoe = 0.0

    if yoe <= 2.0:
        return QuestionDifficulty.JUNIOR, f"Derived from {yoe:.1f} YOE (0-2 years -> Junior)"
    elif yoe <= 5.0:
        return QuestionDifficulty.MID, f"Derived from {yoe:.1f} YOE (>2-5 years -> Mid)"
    elif yoe <= 8.0:
        return QuestionDifficulty.SENIOR, f"Derived from {yoe:.1f} YOE (>5-8 years -> Senior)"
    else:
        return QuestionDifficulty.LEAD, f"Derived from {yoe:.1f} YOE (>8 years -> Lead)"


def get_seniority_complexity_guidance(difficulty: QuestionDifficulty) -> str:
    """Returns shared seniority scaling guidance for coding and system design generators.
    Ensures uniform reasoning depth, defect locality, and diagnostic ambiguity expectations.
    """
    if difficulty == QuestionDifficulty.JUNIOR:
        return (
            "SENIORITY CONTRACT - JUNIOR (0–2 YOE):\n"
            "- Locality of Defect: Local to a single function or component boundary. Bug is in plain sight.\n"
            "- Clue & Symptom Quality: Direct error message, stack trace, or explicit telemetry pointing close to the defect line.\n"
            "- Diagnostic Ambiguity: 1 plausible symptom chain, single-hop reasoning within 1 service boundary.\n"
            "- Expected Solution: Correct syntax/logic fix, basic boundary check (e.g. null, empty collection, unhandled return code)."
        )
    elif difficulty == QuestionDifficulty.MID:
        return (
            "SENIORITY CONTRACT - MID (>2–5 YOE):\n"
            "- Locality of Defect: Cross-boundary interaction (caller -> callee or service -> state/cache adapter).\n"
            "- Clue & Symptom Quality: Symptom observed downstream, but root cause is 1 step upstream (e.g. state mutation, unexpected nil/empty return).\n"
            "- Diagnostic Ambiguity: 1–2 competing hypotheses, two-hop reasoning across service and dependency.\n"
            "- Expected Solution: Address the root cause without breaking calling contracts or introducing regression side-effects."
        )
    elif difficulty == QuestionDifficulty.SENIOR:
        return (
            "SENIORITY CONTRACT - SENIOR (>5–8 YOE):\n"
            "- Locality of Defect: Systemic / State Invariant breach across 2–3 interacting components under load or concurrency.\n"
            "- Clue & Symptom Quality: Misleading symptom (e.g. intermittent timeout, stale read, duplicate record, resource accumulation).\n"
            "- Diagnostic Ambiguity: 2–3 competing hypotheses requiring data/control flow tracing to isolate.\n"
            "- Expected Solution: Identify the broken invariant, evaluate immediate mitigation vs clean structural fix, and anticipate operational failure modes."
        )
    else:  # LEAD or PRINCIPAL
        return (
            "SENIORITY CONTRACT - LEAD / PRINCIPAL (>8 YOE):\n"
            "- Locality of Defect: Architectural tradeoff dilemma or subtle second-order failure propagation across components.\n"
            "- Clue & Symptom Quality: Emergent failure under scale, backpressure breakdown, or cascading retry failure.\n"
            "- Diagnostic Ambiguity: 2–3 plausible hypotheses with subtle interaction effects.\n"
            "- Expected Solution: Structural redesign, operational observability/telemetry strategy, and blast-radius mitigation."
        )
