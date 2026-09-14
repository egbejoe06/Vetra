import ast
import logging
import os
import re
from typing import List, Tuple

from src.models.enums import CodeLanguage
from src.schemas.planner import CodingExerciseAsset, InterviewPlan

logger = logging.getLogger(__name__)


class PlanValidationError(Exception):
    """Raised when an InterviewPlan or CodingExerciseAsset fails strict validation checks."""
    pass


SPOILER_COMMENT_PATTERNS = [
    re.compile(r'#\s*(BUG|FIXME|FIX\s*ME|TODO:\s*fix|TODO:\s*resolve|ISSUE|RACE\s*CONDITION|DEADLOCK|FLAW|VULNERABILITY):?.*$', re.IGNORECASE),
    re.compile(r'//\s*(BUG|FIXME|FIX\s*ME|TODO:\s*fix|TODO:\s*resolve|ISSUE|RACE\s*CONDITION|DEADLOCK|FLAW|VULNERABILITY):?.*$', re.IGNORECASE),
]

DUMMY_COMMENT_PATTERNS = [
    re.compile(r'(#|//)\s*(this is what will happen|what will happen here|logic goes here|put code here|implement logic here|dummy data|placeholder here)', re.IGNORECASE),
]

MANUFACTURED_BUG_PATTERNS = [
    re.compile(r'(sleep|setTimeout|delay)\s*\([^)]*Math\.random', re.IGNORECASE),
    re.compile(r'time\.sleep\s*\([^)]*random\.', re.IGNORECASE),
    re.compile(r'(#|//)\s*(artificial delay|simulate latency|simulate error|manufactured bug|planted defect)', re.IGNORECASE),
]


def sanitize_code_spoilers(content: str) -> str:
    """Removes spoiler comments that give away bugs, race conditions, or flaw hints to candidates."""
    lines = content.splitlines()
    cleaned_lines = []
    for line in lines:
        cleaned = line
        for pat in SPOILER_COMMENT_PATTERNS:
            if pat.search(cleaned.strip()):
                cleaned = pat.sub('', cleaned).rstrip()
        if cleaned.strip() or not line.strip():
            cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines)


def validate_codebase(exercise: CodingExerciseAsset) -> Tuple[bool, List[str]]:
    """Strictly validates that a generated coding exercise codebase adheres to Monaco contracts:
    - 2 to 3 code files.
    - Standard relative paths (e.g., 'src/main.py', 'retriever.py', NOT absolute 'C:\\...' or '/home/...').
    - Unique paths.
    - Non-empty content.
    - Automatic stripping of spoiler comments (# BUG:, # Race condition, etc.).
    - Prohibition of dummy placeholder comments (# this is what will happen here).
    - NO Markdown code fences inside file content strings (e.g. ```python ... ```).
    - Syntax validation for Python files.
    """
    errors: List[str] = []

    if not exercise.code_files:
        errors.append("Coding exercise must contain at least 2 code files, found 0.")
        return False, errors

    if len(exercise.code_files) < 2 or len(exercise.code_files) > 3:
        errors.append(f"Coding exercise must contain between 2 and 3 files. Found {len(exercise.code_files)}.")

    paths_seen = set()

    for idx, f in enumerate(exercise.code_files):
        # 1. Path format validation
        clean_path = f.path.strip()
        if not clean_path:
            errors.append(f"File #{idx+1} has an empty path.")
            continue

        if os.path.isabs(clean_path) or clean_path.startswith("/") or clean_path.startswith("\\") or ":" in clean_path:
            errors.append(f"File path '{clean_path}' must be a relative path (e.g. 'src/retriever.py'), not an absolute path.")

        norm_path = os.path.normpath(clean_path).replace("\\", "/")
        if norm_path in paths_seen:
            errors.append(f"Duplicate file path detected: '{norm_path}'.")
        paths_seen.add(norm_path)

        # 2. Content validation & spoiler sanitization
        content = f.content or ""
        if not content.strip():
            errors.append(f"File '{norm_path}' has empty content.")
            continue

        # Automatically sanitize any spoiler comments
        cleaned_content = sanitize_code_spoilers(content)
        f.content = cleaned_content
        content = cleaned_content

        # 3. Check for dummy text commentary
        for dummy_pat in DUMMY_COMMENT_PATTERNS:
            if dummy_pat.search(content):
                errors.append(
                    f"File '{norm_path}' contains placeholder text commentary ('{dummy_pat.pattern}'). "
                    "Provide fully written, syntactically valid, coherent code without placeholder comments."
                )
                break

        # 3b. Check for manufactured artificial defects
        for m_pat in MANUFACTURED_BUG_PATTERNS:
            if m_pat.search(content):
                errors.append(
                    f"File '{norm_path}' contains an artificial manufactured defect ('{m_pat.pattern}'). "
                    "Defects must plausibly arise from interacting component assumptions or realistic tradeoffs, NOT artificial sleep, random delays, or planted error comments."
                )
                break

        # 4. Markdown fence check
        if "```" in content:
            errors.append(
                f"File '{norm_path}' contains raw Markdown code fences ('```'). "
                "File content MUST be pure source code without markdown formatting."
            )

        # 5. Syntax validation (Python)
        if f.language == CodeLanguage.PYTHON or norm_path.endswith(".py"):
            try:
                ast.parse(content, filename=norm_path)
            except SyntaxError as syn_err:
                errors.append(
                    f"Python syntax error in '{norm_path}' at line {syn_err.lineno}: {syn_err.msg}"
                )

    # 6. Total codebase budget check (hard cap 300 LOC)
    total_loc = sum(
        len([line for line in (f.content or "").splitlines() if line.strip()])
        for f in exercise.code_files
    )
    if total_loc > 300:
        errors.append(
            f"Codebase total lines of code ({total_loc} LOC) exceeds the hard ceiling of 300 LOC. "
            "Please refine the codebase to the minimal code necessary to create the intended reasoning problem."
        )

    return len(errors) == 0, errors


def validate_interview_plan(
    plan: InterviewPlan, allow_deferred_exercises: bool = False
) -> Tuple[bool, List[str]]:
    """Enforces strict structural and content guarantees for a generated InterviewPlan."""
    errors: List[str] = []

    if not plan.questions:
        errors.append("Interview plan must contain at least 1 generated question.")

    # 1. Blueprint validation
    if plan.blueprint:
        if not (plan.blueprint.claims_to_verify or plan.blueprint.competencies or plan.blueprint.capabilities_to_assess):
            errors.append("Interview blueprint is missing both claims_to_verify and capabilities_to_assess.")
    else:
        errors.append("Interview plan is missing an InterviewBlueprint.")

    # 2. Questions validation
    for idx, q in enumerate(plan.questions):
        if not q.question_text or not q.question_text.strip():
            errors.append(f"Question #{idx+1} has empty text.")
        if not q.competency or not q.competency.strip():
            errors.append(f"Question #{idx+1} is missing target competency.")
        if q.question_type == "RESUME_DEEP_DIVE" and not q.candidate_evidence:
            logger.warning(f"Resume question '{q.id}' has empty candidate evidence.")

    # 3. Rubric rigor validation
    GENERIC_RUBRIC_PHRASES = ["basic knowledge", "good understanding", "expert understanding", "basic understanding"]
    for idx, r in enumerate(plan.rubrics):
        comp_name = r.competency or r.category or f"Rubric #{idx+1}"
        for phrase in GENERIC_RUBRIC_PHRASES:
            if (
                phrase in (r.description_level_1 or "").lower()
                or phrase in (r.description_level_3 or "").lower()
                or phrase in (r.description_level_5 or "").lower()
            ):
                errors.append(
                    f"Rubric '{comp_name}' contains generic, non-observable phrase '{phrase}'. "
                    "Rubrics must describe concrete observable mechanisms and failure modes."
                )
                break

    # 4. Validate exercise presence & codebase contract (skipped if deferred)
    if not allow_deferred_exercises and not plan.coding_exercise and not plan.system_design_exercise:
        errors.append("Interview plan must contain at least one exercise (coding_exercise or system_design_exercise).")

    if plan.coding_exercise:
        code_valid, code_errors = validate_codebase(plan.coding_exercise)
        if not code_valid:
            errors.extend(code_errors)

    return len(errors) == 0, errors

