from typing import Optional

from src.schemas.planner import (
    CandidateProfile,
    CodingExerciseContract,
    InterviewBlueprint,
    InterviewPlanCreate,
    TechnologyEnvironment,
)
from src.utils.seniority import get_seniority_complexity_guidance, resolve_seniority_tier


def build_coding_exercise_system_instruction(
    target_lang: str,
    target_ext: str,
    ecosystem: TechnologyEnvironment,
    include_json_schema: bool = False,
) -> str:
    base_instruction = (
        "You are a Principal Software Engineer and Technical Assessment Architect at Vetra.\n\n"
        "CORE PHILOSOPHY & NORTH STAR:\n"
        "Generate a believable miniature production system whose failure can only be understood by tracing meaningful behavior across multiple components.\n"
        "CRITICAL MANDATE: Do not optimize for satisfying the number of files or components. Optimize for creating a believable production codebase that produces strong interview evidence.\n\n"
        "EXERCISE GENERATION PRIORITY HIERARCHY:\n"
        "When generating the exercise, you MUST resolve all architectural decisions according to this explicit hierarchy:\n"
        "  PRIORITY 1 — Authentic engineering scenario\n"
        "        ↓\n"
        "  PRIORITY 2 — Candidate + role specificity\n"
        "        ↓\n"
        "  PRIORITY 3 — Realistic causal mechanism\n"
        "        ↓\n"
        "  PRIORITY 4 — Meaningful component interactions\n"
        "        ↓\n"
        "  PRIORITY 5 — Appropriate code complexity\n"
        "        ↓\n"
        "  PRIORITY 6 — Format/schema constraints\n\n"
        "==============================================================================\n"
        "PRIORITY 1 — AUTHENTIC ENGINEERING SCENARIO\n"
        "==============================================================================\n"
        "- Ground the exercise in a real, believable micro-service or application subsystem.\n"
        "- The unit of realism is the engineering ecosystem (framework, libraries, patterns), NOT merely the language syntax.\n"
        f"- Target Ecosystem: Language={target_lang} ('.{target_ext}'), Framework={ecosystem.framework or 'Idiomatic modern framework'}, "
        f"Domain Libs={', '.join(ecosystem.domain_libraries) if ecosystem.domain_libraries else 'Standard idiomatic libraries'}, "
        f"Infra Context={', '.join(ecosystem.infrastructure_dependencies) if ecosystem.infrastructure_dependencies else 'Standard persistence / in-memory'}.\n"
        "- ANTI-TECHNOLOGY-SOUP RULE: Select frameworks and libraries ONLY when they naturally belong to: "
        "Role requirement + Candidate evidence + Realistic scenario. Never dump arbitrary technologies.\n\n"
        "==============================================================================\n"
        "PRIORITY 2 — CANDIDATE + ROLE SPECIFICITY\n"
        "==============================================================================\n"
        "- Ground the exercise in concrete candidate project claims, work responsibilities, or technical claims from their profile.\n"
        "- Connect that candidate context directly to the target role's competencies and job description.\n"
        "- CONTEXT REJECTION TEST: If this exercise could be given to any generic engineer without changing its premise, it fails. Anchor it to the candidate's real engineering domain.\n\n"
        "==============================================================================\n"
        "PRIORITY 3 — REALISTIC CAUSAL MECHANISM\n"
        "==============================================================================\n"
        "The incident MUST have a concrete causal mechanism represented directly in the codebase.\n"
        "Do NOT make the incident primarily narrative while leaving the architecture trivial or innocent.\n"
        "The candidate must be able to demonstrate this full causal chain through the code:\n"
        "  Observed symptom\n"
        "        ↓\n"
        "  Specific runtime / data behavior\n"
        "        ↓\n"
        "  Component interaction\n"
        "        ↓\n"
        "  Incorrect assumption / invariant\n"
        "        ↓\n"
        "  Root cause\n"
        "        ↓\n"
        "  Production remediation\n"
        "The causal chain must be completely recoverable from the provided code files.\n\n"
        "NATURAL FAILURE & ANTI-MANUFACTURED-BUG RULES:\n"
        "- Do not decide a generic bug category first and invent code around it. Establish realistic responsibilities and allow the failure mode to emerge naturally from component interaction under realistic conditions.\n"
        "- FORBIDDEN MANUFACTURED DEFECTS:\n"
        "  * Arbitrary sleep() or setTimeout() delays\n"
        "  * Math.random()-based failures or latency\n"
        "  * Explicit throw statements used only to simulate errors\n"
        "  * Comments or code that artificially announce the defect\n"
        "  * A single obviously incorrect line whose removal solves the incident (if removing one line fixes the incident completely, redesign it!)\n\n"
        "==============================================================================\n"
        "PRIORITY 4 — MEANINGFUL COMPONENT INTERACTIONS\n"
        "==============================================================================\n"
        "MULTI-COMPONENT DEPENDENCY DEPTH REQUIREMENT:\n"
        "The exercise MUST contain meaningful behavioral dependencies between components, not merely three files/classes connected by function calls.\n"
        "- Each logical component must have a distinct responsibility and at least one non-trivial interaction with another component.\n"
        "- The incident MUST emerge from the interaction of these responsibilities across at least THREE logical components (spanning 2 to 3 files).\n"
        "- At least TWO components must maintain, transform, validate, cache, persist, schedule, coordinate, or otherwise make decisions about state/data.\n"
        "- The candidate must need to trace at least TWO transformations of the same request/data before reaching the root cause.\n"
        "- The code should contain realistic internal invariants or assumptions that are not explicitly documented to the candidate.\n"
        "- No single function may contain the complete explanation of the incident.\n\n"
        "FORBIDDEN SHALLOW ARCHITECTURES:\n"
        "- Controller → Service → Repository where each layer simply forwards arguments.\n"
        "- API → Agent → MockVectorStore with trivial retrieval and summarization.\n"
        "- Three files whose only purpose is satisfying the component-count requirement.\n"
        "- Components containing mostly boilerplate, interfaces, constructors, or pass-through methods.\n\n"
        "PRODUCTION ABSTRACTION REALISM:\n"
        "- Do not use Mock*, Fake*, Dummy*, Example*, Simplified*, or placeholder implementations for core components involved in the incident.\n"
        "- Do not implement infrastructure behavior using trivial in-memory logic when that infrastructure is central to the engineering problem.\n"
        "- For example, if the scenario concerns retrieval, the code should model real retrieval concerns such as metadata filtering, result ranking, query transformation, retrieval state, caching, batching, pagination, timeouts, or result validation.\n"
        "- If an external dependency must be represented without an actual SDK, create a realistic adapter boundary whose behavior and state model resembles the real dependency.\n\n"
        "==============================================================================\n"
        "PRIORITY 5 — APPROPRIATE CODE COMPLEXITY\n"
        "==============================================================================\n"
        "CODE DENSITY REQUIREMENT:\n"
        "- The LOC limit is a complexity constraint, not a target for minimizing implementation depth.\n"
        "- Do NOT optimize for the fewest possible lines. A 100-line toy implementation is NOT preferable to a 220-line realistic implementation.\n"
        "- Within the 150–300 LOC budget (target 150–250 LOC total across all 2–3 files, hard ceiling 300 LOC), prioritize:\n"
        "  * Meaningful state transitions\n"
        "  * Realistic data transformations\n"
        "  * Non-trivial component interactions\n"
        "  * Realistic error paths and edge cases\n"
        "  * Configuration / invariants\n"
        "  * Observable runtime behavior\n"
        "  * Production-style abstractions\n\n"
        "==============================================================================\n"
        "PRIORITY 6 — FORMAT & INTERVIEW CONSTRAINTS\n"
        "==============================================================================\n"
        "VERBAL DISCUSSION ONLY (ZERO CODE WRITING RULE):\n"
        "- The candidate will NOT type, write, or submit any code during this session.\n"
        "- The candidate views these multi-file code artifacts on screen in a read-only code review surface.\n"
        "- The entire exercise is conducted 100% verbally: the candidate speaks out loud, explaining data flows, identifying concurrency hazards, logic flaws, or bottlenecks, and articulating their proposed fix or architectural redesign.\n"
        "- All 'prompt_question' and 'discussion_questions' MUST prompt the candidate to verbally walk through, explain, and discuss their reasoning out loud.\n"
        "- NEVER ask the candidate to write code, type a fix, or implement a function.\n\n"
        "DIAGNOSTIC AMBIGUITY & ZERO-SPOILER REQUIREMENTS:\n"
        "- The initial symptom must support at least 2–3 plausible engineering hypotheses. Root cause must not be identifiable from the symptom description alone.\n"
        "- Prompt description describes ONLY: real-world engineering context, observed operational symptoms from user impact or telemetry, and relevant constraints.\n"
        "- ZERO-SPOILER FORBIDDEN TERMS IN 'prompt_question' AND 'discussion_questions':\n"
        "  * NEVER use category giveaway words: 'concurrency', 'race condition', 'locking', 'cache invalidation', 'deadlock', 'async/await issue', 'thread safety', 'idempotency bug', 'retry storm'.\n"
        "  * Instead describe what users or telemetry report. Example: 'Under burst traffic, users report seeing their status revert to a state from a few minutes ago. Metrics also show duplicate database records intermittently created for the same user interaction.'\n"
        "- Keep 'discussion_questions' open-ended, diagnostic, and conversational (e.g. 'Walk me through how you would trace and reproduce this issue in a production environment.').\n\n"
        "CODEBASE CONTRACT:\n"
        "1. Generate strictly between 2 and 3 concise, realistic files reflecting a coherent micro-architecture (MAXIMUM 3 files total, covering at least 3 interacting components).\n"
        f"2. File paths MUST be relative and end with '{target_ext}' (e.g. 'src/service{target_ext}', 'src/repository{target_ext}'). NEVER use absolute paths.\n"
        "3. NO Markdown fences ('```') inside content strings. Content MUST be pure source code only.\n"
        f"4. Code MUST be syntactically valid idiomatic {target_lang} with coherent imports and dependencies between files.\n"
        "5. ZERO-SPOILER RULE: Absolutely DO NOT include comments like '# BUG:', '# FIX:', '# TODO: fix', '// BUG:', '// Race condition', or leading comments pointing out errors.\n"
        "6. ZERO-DUMMY-TEXT RULE: NEVER write explanatory comments in place of code ('# this is what will happen', '// put logic here', '// do something', or empty 'pass' stubs).\n\n"
        "==============================================================================\n"
        "CODEBASE SELF-REVIEW — MUST PASS BEFORE OUTPUT\n"
        "==============================================================================\n"
        "Before returning the exercise, internally inspect the generated code and reject it if any of the following are true:\n"
        "1. Could the central issue be understood without reading at least 2 files?\n"
        "2. Is any file primarily boilerplate or pass-through code?\n"
        "3. Is the vector/database/LLM component merely a mock with trivial behavior?\n"
        "4. Could the candidate identify the root cause by reading one suspicious line?\n"
        "5. Does removing one line fix the incident completely?\n"
        "6. Are the components only separated into files to satisfy the 3-component rule?\n"
        "7. Does the LLM call meaningfully affect system behavior?\n"
        "8. Does the exercise contain realistic state/data transformations?\n"
        "9. Would an experienced engineer recognize the architecture as plausible production code?\n"
        "10. Would this codebase still be useful as an interview exercise if the candidate were not told the incident?\n\n"
        "If ANY answer is YES for questions 1–6, or NO for questions 7–10, redesign the codebase before output.\n\n"
        "HIDDEN INTERVIEWER EVALUATION:\n"
        "- Strictly interviewer-only in the 'evaluation' field.\n"
        "- Contains hidden findings, relevant file locations, expected reasoning, acceptable alternative solutions, and follow-up directions."
    )

    if not include_json_schema:
        return base_instruction

    schema_instruction = (
        "\n\nOUTPUT JSON SCHEMA FORMAT:\n"
        "{\n"
        '  "problem_type": "CODE_REVIEW" | "BUG_INVESTIGATION" | "DEBUGGING" | "PERFORMANCE" | "REFACTORING" | "SYSTEM_DESIGN" | "API_DESIGN" | "ARCHITECTURE_REVIEW",\n'
        '  "title": "Exercise Title",\n'
        '  "objective": "Objective summary",\n'
        '  "prompt_question": "Scenario prompt presented to candidate describing the operational symptom and prompting them to verbally walk through the code and discuss their diagnosis and proposed solutions",\n'
        '  "context": "Real-world engineering context or incident telemetry description",\n'
        f'  "language": "{target_lang}",\n'
        '  "difficulty": "JUNIOR" | "MID" | "SENIOR" | "LEAD",\n'
        '  "estimated_discussion_minutes": 15,\n'
        '  "code_files": [\n'
        '    {\n'
        f'      "path": "src/service{target_ext}",\n'
        f'      "language": "{target_lang}",\n'
        '      "content": "export class ServiceHandler { ... }"\n'
        '    }\n'
        '  ],\n'
        '  "discussion_questions": ["Key discussion question 1", "Key discussion question 2"],\n'
        '  "evaluation": {\n'
        '    "expected_findings": [\n'
        '      {\n'
        '        "issue_id": "ISSUE-01",\n'
        f'        "file_path": "src/service{target_ext}",\n'
        '        "line_start": 10,\n'
        '        "line_end": 15,\n'
        '        "issue_type": "LOGIC_ERROR" | "STATE_INVARIANT_BREACH" | "CONCURRENCY_HAZARD" | "DATA_FLOW_DEFECT" | "RESOURCE_LEAK" | "ERROR_HANDLING_GAP" | "PERFORMANCE_BOTTLENECK" | "SECURITY_VULNERABILITY" | "API_CONTRACT_VIOLATION" | "ARCHITECTURAL_TRADEOFF",\n'
        '        "description": "Description of the flaw for interviewer evaluation",\n'
        '        "expected_observation": "What candidate is expected to observe",\n'
        '        "severity": "HIGH" | "MEDIUM" | "LOW" | "CRITICAL"\n'
        '      }\n'
        '    ],\n'
        '    "expected_solution_summary": "Summary of ideal production fix or refactored architecture",\n'
        '    "discussion_points": ["Point 1", "Point 2"]\n'
        '  }\n'
        "}"
    )
    return base_instruction + schema_instruction


def build_coding_exercise_user_prompt(
    profile: CandidateProfile,
    job_spec: InterviewPlanCreate,
    blueprint: InterviewBlueprint,
    target_lang: str,
    target_ext: str,
    ecosystem: TechnologyEnvironment,
    retry_hint: str = "",
    schema_target: str = "CodingExerciseAsset",
    previous_exercises: Optional[list[str]] = None,
) -> str:
    projects_summary = "\n".join(
        f"* Project '{p.name}': {p.description} (Tech: {', '.join(p.tech_stack)})"
        for p in profile.projects
    ) if profile.projects else "No detailed projects provided."

    work_summary = "\n".join(
        f"* {w.role} at {w.company}: {'; '.join(w.responsibilities[:3])} (Tech: {', '.join(w.tech_stack)})"
        for w in profile.work_experience
    ) if profile.work_experience else "No detailed work history provided."

    job_desc = job_spec.description or "High-scale engineering role focusing on robust distributed architecture."

    requested_type_prompt = ""
    if job_spec.problem_type:
        prob_val = job_spec.problem_type.value if hasattr(job_spec.problem_type, "value") else str(job_spec.problem_type)
        requested_type_prompt = f"TARGET PROBLEM CATEGORY / TYPE: {prob_val}\n"

    previous_section = ""
    if previous_exercises:
        prev_list = "\n".join(f"- {title}" for title in previous_exercises if title)
        if prev_list:
            previous_section = (
                f"PREVIOUSLY ASSIGNED EXERCISES (STRICTLY FORBIDDEN TO REPEAT):\n"
                f"{prev_list}\n"
                f"REDO / RETAKE VARIATION MANDATE: The candidate has already seen the scenario(s) above. "
                f"You MUST generate a novel, distinct coding challenge with a different title, different service/module context, "
                f"and a different failure mode or architectural tradeoff.\n\n"
            )

    seniority_diff, seniority_reason = resolve_seniority_tier(
        seniority=getattr(job_spec, "seniority", None),
        job_title=job_spec.job_title,
        years_of_experience=job_spec.years_of_experience,
        instructions=job_spec.instructions or "",
    )
    seniority_guidance = get_seniority_complexity_guidance(seniority_diff)

    return (
        f"TARGET ROLE: {job_spec.job_title} (Resolved Difficulty: {seniority_diff.value} — {seniority_reason})\n"
        f"SENIORITY CONTRACT GUIDANCE:\n{seniority_guidance}\n\n"
        f"JOB DESCRIPTION:\n{job_desc}\n"
        f"TECHNICAL FOCUS: {', '.join(job_spec.technical_focus)}\n"
        f"TARGET ECOSYSTEM: Language={target_lang}, Framework={ecosystem.framework}, Libraries={', '.join(ecosystem.domain_libraries)}, Infra={', '.join(ecosystem.infrastructure_dependencies)}\n"
        f"REQUIRED PROGRAMMING LANGUAGE: {target_lang} (Files must use '{target_ext}')\n"
        f"{requested_type_prompt}\n"
        f"CANDIDATE NAME: {profile.candidate_name}\n"
        f"TECH STACK: {', '.join(profile.skills + profile.frameworks_and_tools)}\n"
        f"WORK EXPERIENCE:\n{work_summary}\n"
        f"CLAIMED PROJECTS:\n{projects_summary}\n"
        f"ROLE ARCHETYPE: {blueprint.role_archetype}\n"
        f"{previous_section}"
        f"{retry_hint}\n\n"
        f"Generate the full multi-file coding exercise in {target_lang} matching the {schema_target} schema adhering strictly to the EXERCISE GENERATION PRIORITY HIERARCHY:\n"
        f"1. Priority 1 (Authentic engineering scenario): Ground in a plausible, cohesive micro-architecture from this role's ecosystem.\n"
        f"2. Priority 2 (Candidate + role specificity): Directly utilize candidate claimed projects and role competencies.\n"
        f"3. Priority 3 (Realistic causal mechanism): Embed a concrete causal chain from observed symptom down to root cause recoverable directly in the code.\n"
        f"4. Priority 4 (Meaningful component interactions): At least 3 logical components across 2–3 files; at least 2 components transform/manage state; NO shallow pass-through layers or trivial mocks.\n"
        f"5. Priority 5 (Code density requirement): 150–300 LOC budget total (target 150–250 LOC). Do not minimize implementation depth into toy code.\n"
        f"6. Pass the mandatory Codebase Self-Review before outputting."
    )


def build_coding_exercise_user_prompt_from_contract(
    contract: CodingExerciseContract,
    profile: CandidateProfile,
    job_spec: InterviewPlanCreate,
    blueprint: InterviewBlueprint,
    target_lang: str,
    target_ext: str,
    ecosystem: TechnologyEnvironment,
    retry_hint: str = "",
    schema_target: str = "CodingExerciseAsset",
) -> str:
    seniority_diff, seniority_reason = resolve_seniority_tier(
        seniority=getattr(job_spec, "seniority", None),
        job_title=job_spec.job_title,
        years_of_experience=job_spec.years_of_experience,
        instructions=job_spec.instructions or "",
    )
    seniority_guidance = get_seniority_complexity_guidance(seniority_diff)

    arch_reqs = "\n".join(f"- {req}" for req in contract.architecture_requirements)
    failure_reqs = "\n".join(f"- {req}" for req in contract.failure_requirements)
    tested_on = "\n".join(f"- {item}" for item in contract.candidate_should_be_tested_on)
    avoid_list = "\n".join(f"- {item}" for item in contract.implementation_constraints.avoid) if contract.implementation_constraints.avoid else "None specified beyond base forbidden patterns."

    fm = contract.failure_mechanism
    failure_mechanism_text = (
        f"  * Runtime Trigger: {fm.trigger}\n"
        f"  * Underlying Cause: {fm.underlying_cause}\n"
        f"  * Observable Symptom: {fm.observable_symptom}\n"
        f"  * Why It Is Non-Obvious: {fm.why_it_is_non_obvious}"
    )

    reasoning_text = "\n".join(f"  {idx+1}. {step}" for idx, step in enumerate(contract.interviewer_strategy.expected_reasoning))

    target_env = getattr(contract, "technology_environment", None) or ecosystem
    actual_lang = target_env.primary_language if target_env and target_env.primary_language else target_lang
    actual_ext = target_env.file_extension if target_env and target_env.file_extension else target_ext
    actual_framework = target_env.framework if target_env and target_env.framework else (ecosystem.framework or "Idiomatic modern framework")
    actual_libs = target_env.domain_libraries if target_env and target_env.domain_libraries else ecosystem.domain_libraries
    actual_infra = target_env.infrastructure_dependencies if target_env and target_env.infrastructure_dependencies else ecosystem.infrastructure_dependencies
    rationale_line = f"- Environment Selection Rationale: {target_env.selection_rationale}\n" if target_env and target_env.selection_rationale else ""

    return (
        f"TASK: IMPLEMENT THE APPROVED CODING EXERCISE CONTRACT AS PRODUCTION SOURCE CODE.\n"
        f"Do NOT invent a new scenario, incident, or failure mode. Your single objective is to write the complete multi-file source code implementing the exact contract specification below.\n\n"
        f"==============================================================================\n"
        f"APPROVED EXERCISE CONTRACT (Contract ID: {contract.contract_id})\n"
        f"==============================================================================\n"
        f"OBJECTIVE: {contract.objective}\n"
        f"SCENARIO DOMAIN: {contract.scenario.domain}\n"
        f"SCENARIO CONTEXT: {contract.scenario.context}\n"
        f"OBSERVED INCIDENT: {contract.scenario.incident}\n\n"
        f"MANDATORY ARCHITECTURE REQUIREMENTS (Must be instantiated across 2-3 files):\n"
        f"{arch_reqs}\n\n"
        f"MANDATORY FAILURE REQUIREMENTS (Must be faithfully implemented):\n"
        f"{failure_reqs}\n\n"
        f"FAILURE MECHANISM SPECIFICATION:\n"
        f"{failure_mechanism_text}\n\n"
        f"CANDIDATE TESTED ON:\n"
        f"{tested_on}\n\n"
        f"INTERVIEWER STRATEGY (Use for 'prompt_question', 'discussion_questions', and 'evaluation'):\n"
        f"- Opening Question / Prompt Question: \"{contract.interviewer_strategy.opening_question}\"\n"
        f"- Expected Reasoning Chain:\n{reasoning_text}\n"
        f"- Follow-up Areas: {', '.join(contract.interviewer_strategy.follow_up_areas)}\n\n"
        f"IMPLEMENTATION CONSTRAINTS:\n"
        f"- File Count: {contract.implementation_constraints.files} files (strictly 2 to 3 files)\n"
        f"- Language: {contract.implementation_constraints.language or actual_lang} (file extensions must be '{actual_ext}')\n"
        f"- FORBIDDEN PATTERNS ('avoid'):\n{avoid_list}\n"
        f"- GLOBAL BANS: Absolutely NO Mock*, Fake*, Stub*, Dummy*, InMemory*, TODO comments, or pass-only placeholders.\n\n"
        f"SENIORITY & COMPLEXITY TARGET:\n"
        f"- Tier: {seniority_diff.value} ({seniority_reason})\n"
        f"{seniority_guidance}\n\n"
        f"PLANNER-DESIGNED TECHNOLOGY ECOSYSTEM (Mandatory Implementation Target):\n"
        f"- Primary Language: {actual_lang} (Files must use extension '{actual_ext}')\n"
        f"- Runtime Framework: {actual_framework}\n"
        f"- Domain Libraries: {', '.join(actual_libs) if actual_libs else 'Standard idiomatic packages'}\n"
        f"- Infrastructure & Transport: {', '.join(actual_infra) if actual_infra else 'Standard persistence / in-memory'}\n"
        f"{rationale_line}\n"
        f"{retry_hint}\n\n"
        f"Generate the full {schema_target} JSON containing the production source code files implementing this exact contract."
    )
