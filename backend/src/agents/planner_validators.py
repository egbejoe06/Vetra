import ast
import logging
import os
import re
from typing import List, Optional, Tuple

from src.models.enums import CodeLanguage
from src.schemas.planner import CodingExerciseAsset, CodingExerciseContract, InterviewPlan

logger = logging.getLogger(__name__)


class PlanValidationError(Exception):
    """Raised when an InterviewPlan, CodingExerciseContract, or CodingExerciseAsset fails strict validation checks."""
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

BASE_FORBIDDEN_PATTERNS = [
    (re.compile(r'\b(Mock|Fake|Stub|Dummy|InMemory)[A-Z0-9_]+', re.IGNORECASE), "Mock / Fake / Stub / InMemory implementation pattern"),
    (re.compile(r'(#|//)\s*TODO\b', re.IGNORECASE), "TODO comment"),
    (re.compile(r'def\s+[a-zA-Z0-9_]+\([^)]*\)(?:\s*->\s*[^:]+)?:\s*(?:"""[\s\S]*?"""\s*|\'\'\'[\s\S]*?\'\'\'\s*)?pass\s*(#.*)?$', re.MULTILINE), "Empty pass-only method placeholder"),
    (re.compile(r'raise\s+NotImplementedError\b', re.IGNORECASE), "NotImplementedError placeholder"),
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


def validate_contract(contract: CodingExerciseContract) -> Tuple[bool, List[str]]:
    """Strictly validates that a generated CodingExerciseContract adheres to design quality standards:
    - failure_requirements has >= 3 items.
    - architecture_requirements has >= 2 distinct components.
    - candidate_should_be_tested_on has >= 2 specific evaluation areas.
    - failure_mechanism has non-empty trigger, underlying_cause, observable_symptom, and why_it_is_non_obvious.
    - interviewer_strategy has non-empty opening_question and expected_reasoning.
    - implementation_constraints has language and files specified.
    """
    errors: List[str] = []

    if not contract.scenario.domain or len(contract.scenario.domain.strip()) < 5:
        errors.append("Contract scenario domain must describe a specific, realistic domain context (>= 5 chars).")

    if not contract.scenario.incident or len(contract.scenario.incident.strip()) < 15:
        errors.append("Contract scenario incident must describe a specific, observable incident (>= 15 chars).")

    if len(contract.failure_requirements) < 3:
        errors.append(f"Contract failure_requirements must contain at least 3 items, found {len(contract.failure_requirements)}.")

    if len(contract.architecture_requirements) < 2:
        errors.append(f"Contract architecture_requirements must specify at least 2 distinct components, found {len(contract.architecture_requirements)}.")

    if len(contract.candidate_should_be_tested_on) < 2:
        errors.append(f"Contract candidate_should_be_tested_on must specify at least 2 concrete competencies, found {len(contract.candidate_should_be_tested_on)}.")

    fm = contract.failure_mechanism
    if not fm.trigger or len(fm.trigger.strip()) < 10:
        errors.append("Contract failure_mechanism.trigger must describe the runtime trigger condition (>= 10 chars).")
    if not fm.underlying_cause or len(fm.underlying_cause.strip()) < 10:
        errors.append("Contract failure_mechanism.underlying_cause must describe the flawed invariant or synchronization error (>= 10 chars).")
    if not fm.observable_symptom or len(fm.observable_symptom.strip()) < 10:
        errors.append("Contract failure_mechanism.observable_symptom must describe the observable telemetry or defect (>= 10 chars).")
    if not fm.why_it_is_non_obvious or len(fm.why_it_is_non_obvious.strip()) < 10:
        errors.append("Contract failure_mechanism.why_it_is_non_obvious must explain why the bug cannot be spotted superficially (>= 10 chars).")

    if not contract.interviewer_strategy.opening_question or len(contract.interviewer_strategy.opening_question.strip()) < 10:
        errors.append("Contract interviewer_strategy.opening_question must be a substantial diagnostic question (>= 10 chars).")

    if not contract.interviewer_strategy.expected_reasoning:
        errors.append("Contract interviewer_strategy.expected_reasoning must contain at least 1 expected diagnostic step.")

    # Validate technology environment / language constraints
    if contract.technology_environment:
        te = contract.technology_environment
        if not te.primary_language or len(te.primary_language.strip()) == 0:
            errors.append("Contract technology_environment.primary_language must be specified.")
        # Synchronize implementation_constraints.language if empty
        if not contract.implementation_constraints.language and te.primary_language:
            contract.implementation_constraints.language = te.primary_language
    elif not contract.implementation_constraints.language:
        errors.append("Contract implementation_constraints must specify a target programming language.")

    return len(errors) == 0, errors


def validate_codebase(
    exercise: CodingExerciseAsset,
    contract: Optional[CodingExerciseContract] = None,
) -> Tuple[bool, List[str]]:
    """Multi-level validation of generated coding exercise codebase:
    - Level 1: Basic validity (file count 2-3, unique relative paths, non-empty, no markdown fences, AST syntax, <= 300 LOC).
    - Level 2: Anti-toy validation (BASE_FORBIDDEN_PATTERNS such as Mock*, Fake*, Stub*, InMemory*, TODO, pass placeholders).
    - Level 3: Contract fidelity (if contract provided, check implementation_constraints.avoid and language/architecture alignment).
    """
    errors: List[str] = []

    # =========================================================================
    # LEVEL 1 — BASIC VALIDITY
    # =========================================================================
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

        # =====================================================================
        # LEVEL 2 — ANTI-TOY VALIDATION (BASE_FORBIDDEN_PATTERNS)
        # =====================================================================
        for forbidden_pat, pattern_desc in BASE_FORBIDDEN_PATTERNS:
            match = forbidden_pat.search(content)
            if match:
                errors.append(
                    f"File '{norm_path}' violates Level 2 anti-toy contract: detected {pattern_desc} ('{match.group(0).strip()}'). "
                    "Production code must use realistic component implementations and domain boundaries, not mocks, fakes, or stubs."
                )
                break

        # =====================================================================
        # LEVEL 3 — CONTRACT SPECIFIC AVOID PATTERNS
        # =====================================================================
        if contract and contract.implementation_constraints and contract.implementation_constraints.avoid:
            for avoid_term in contract.implementation_constraints.avoid:
                clean_term = avoid_term.strip()
                if clean_term and len(clean_term) >= 3:
                    # Check whole word match or regex term
                    escaped_term = re.escape(clean_term)
                    if re.search(rf'\b{escaped_term}\b', content, re.IGNORECASE):
                        errors.append(
                            f"File '{norm_path}' violates contract implementation constraints: "
                            f"contains forbidden pattern '{clean_term}' explicitly banned by exercise contract."
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

    # Level 3 Language alignment check
    if contract and contract.implementation_constraints and contract.implementation_constraints.language:
        target_lang = contract.implementation_constraints.language.strip().lower()
        actual_lang = exercise.language.value.lower() if hasattr(exercise.language, "value") else str(exercise.language).lower()
        if target_lang != actual_lang:
            errors.append(
                f"Codebase language '{actual_lang}' does not match contract language requirement '{target_lang}'."
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
        code_valid, code_errors = validate_codebase(plan.coding_exercise, contract=plan.coding_exercise.contract)
        if not code_valid:
            errors.extend(code_errors)

    return len(errors) == 0, errors

