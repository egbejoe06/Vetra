from typing import List, Optional

from src.schemas.planner import (
    CandidateProfile,
    InterviewBlueprint,
    InterviewPlanCreate,
    TechnologyEnvironment,
)
from src.utils.seniority import get_seniority_complexity_guidance, resolve_seniority_tier


def build_contract_system_instruction(
    target_lang: str,
    target_ext: str,
    ecosystem: TechnologyEnvironment,
    include_json_schema: bool = False,
) -> str:
    base_instruction = (
        "You are a Principal Distributed Systems Architect and Technical Assessment Designer at Vetra.\n\n"
        "CORE PHILOSOPHY & OBJECTIVE:\n"
        "Design a rigorous, realistic CODING EXERCISE CONTRACT (blueprint) for a technical assessment.\n"
        "CRITICAL INSTRUCTION: You are NOT writing source code in this step. You are designing the architectural specification and failure contract that a subsequent code generator will implement.\n\n"
        "DESIGN PRINCIPLES:\n"
        "1. GROUNDED IN CANDIDATE REALITY:\n"
        "   - Anchor the scenario in the candidate's actual claimed projects, domain experience, and tech stack.\n"
        "   - Rejection test: If this scenario could be given to any generic junior engineer without changing its domain, it fails. Make it domain-authentic.\n\n"
        "2. NON-OBVIOUS CAUSAL MECHANISM:\n"
        "   - The defect must NOT be a typo, syntax mistake, or single-line bug.\n"
        "   - The defect must emerge from subtle, realistic component interactions (e.g., stale cache race condition, uncoordinated read-modify-write, async state desynchronization, unhandled backpressure, leaky connection pooling).\n"
        "   - Deconstruct the defect into four explicit dimensions:\n"
        "     * trigger: The runtime concurrency or event sequence that provokes the defect.\n"
        "     * underlying_cause: The incorrect architectural assumption or state invariant breach.\n"
        "     * observable_symptom: The operational symptom seen by telemetry or users (WITHOUT revealing the cause).\n"
        "     * why_it_is_non_obvious: Why inspecting any single file or function alone will not reveal the issue.\n\n"
        "3. COHESIVE MULTI-COMPONENT ARCHITECTURE:\n"
        "   - Specify 2 to 3 distinct logical components (spanning 2 to 3 files) that interact non-trivially.\n"
        "   - Each component must have a real responsibility (e.g., Ingestion Pipeline, State Coordinator, Storage Repository, Cache Invalidator).\n"
        "   - Ban shallow pass-through architectures (Controller -> Service -> Repo where each method just forwards calls).\n\n"
        "4. ANTI-TOY & FORBIDDEN PATTERNS ('avoid'):\n"
        "   - Explicitly list domain-specific mock patterns and toy abstractions to forbid in the generated code.\n"
        "   - Examples: 'MockVectorStore', 'FakeLLM', 'InMemoryDatabase', 'random delays', 'sleep() simulation', 'placeholder pass methods'.\n\n"
        "5. INTERVIEWER EVALUATION STRATEGY:\n"
        "   - Opening question: A conversational, non-spoiler prompt that presents the observed symptoms and invites the candidate to diagnose.\n"
        "   - Expected reasoning: Sequential reasoning milestones the candidate should verbally hit.\n"
        "   - Follow-up areas: Trade-offs, edge cases, and production remediation questions.\n\n"
        "6. ARCHITECT THE TECHNOLOGY ENVIRONMENT:\n"
        "   - As part of the contract, YOU decide the optimal Technology Environment (primary_language, file_extension, framework, domain_libraries, infrastructure_dependencies, selection_rationale) that best exposes the defect and competencies.\n"
        "   - Do NOT settle for generic toy setups. Select authentic production packages and transport primitives that make the causal mechanism verifiable."
    )

    if not include_json_schema:
        return base_instruction

    schema_instruction = (
        "\n\nOUTPUT JSON SCHEMA FORMAT:\n"
        "{\n"
        '  "contract_id": "cnt_abc123",\n'
        '  "required": true,\n'
        '  "objective": "High-level assessment objective",\n'
        '  "scenario": {\n'
        '    "domain": "Detailed domain description (e.g., Distributed Document Indexing Service)",\n'
        '    "context": "Architectural background, throughput, and system topology",\n'
        '    "incident": "Observed production incident report and user symptoms"\n'
        '  },\n'
        '  "technology_environment": {\n'
        f'    "primary_language": "{target_lang}",\n'
        f'    "file_extension": "{target_ext}",\n'
        f'    "framework": "{ecosystem.framework or "FastAPI"}",\n'
        '    "domain_libraries": ["asyncio", "websockets", "pydantic"],\n'
        '    "infrastructure_dependencies": ["WebSocket Duplex Audio Stream"],\n'
        '    "selection_rationale": "Why this specific environment is optimal for probing this defect"\n'
        '  },\n'
        '  "candidate_should_be_tested_on": [\n'
        '    "Concurrency hazard identification",\n'
        '    "Cache invalidation semantics",\n'
        '    "State reconciliation under partial failures"\n'
        '  ],\n'
        '  "architecture_requirements": [\n'
        f'    "DocumentProcessor component in src/processor{target_ext} handling batch transformations",\n'
        f'    "CacheCoordinator component in src/coordinator{target_ext} maintaining versioned state",\n'
        f'    "RepositoryAdapter component in src/repository{target_ext} managing persistence"\n'
        '  ],\n'
        '  "failure_requirements": [\n'
        '    "Concurrent updates to identical keys create race conditions in coordinator version checks",\n'
        '    "Read-modify-write cycle reads stale version from local cache before write commit completes",\n'
        '    "Silent data overwrite occurs without triggering explicit database exception"\n'
        '  ],\n'
        '  "failure_mechanism": {\n'
        '    "trigger": "Two concurrent batch ingestion requests update the same document entity simultaneously",\n'
        '    "underlying_cause": "The coordinator checks version against local dirty cache instead of atomically validating storage commit",\n'
        '    "observable_symptom": "Intermittent data loss where earlier update overwrites later update during burst traffic",\n'
        '    "why_it_is_non_obvious": "Individual requests succeed with HTTP 200 and unit tests passing in isolation"\n'
        '  },\n'
        '  "interviewer_strategy": {\n'
        '    "opening_question": "During high traffic spikes, users report that updates to existing documents are intermittently lost despite 200 OK responses. How would you trace this through the codebase?",\n'
        '    "expected_reasoning": [\n'
        '      "Inspect the flow of an update from processor to coordinator",\n'
        '      "Identify that version checks rely on non-atomic in-memory cache state",\n'
        '      "Recognize the window between cache check and storage write where interleaving occurs",\n'
        '      "Propose atomic compare-and-swap or transactional locking"\n'
        '    ],\n'
        '    "follow_up_areas": [\n'
        '      "What are the performance tradeoffs of pessimistic locking vs optimistic concurrency in this pipeline?",\n'
        '      "How would you instrument telemetry to detect this race condition in production?"\n'
        '    ]\n'
        '  },\n'
        '  "implementation_constraints": {\n'
        '    "files": "2-3",\n'
        f'    "language": "{target_lang}",\n'
        '    "avoid": [\n'
        '      "MockVectorStore",\n'
        '      "InMemoryDatabase",\n'
        '      "FakeLLM",\n'
        '      "time.sleep",\n'
        '      "random.random",\n'
        '      "single-function simulation"\n'
        '    ]\n'
        '  }\n'
        "}"
    )
    return base_instruction + schema_instruction


def build_contract_user_prompt(
    profile: CandidateProfile,
    job_spec: InterviewPlanCreate,
    blueprint: InterviewBlueprint,
    target_lang: str,
    target_ext: str,
    ecosystem: TechnologyEnvironment,
    retry_hint: str = "",
    schema_target: str = "CodingExerciseContract",
    previous_contracts: Optional[List[str]] = None,
) -> str:
    projects_summary = "\n".join(
        f"* Project '{p.name}': {p.description} (Tech: {', '.join(p.tech_stack)})"
        for p in profile.projects
    ) if profile.projects else "No detailed projects provided."

    work_summary = "\n".join(
        f"* {w.role} at {w.company}: {'; '.join(w.responsibilities[:3])} (Tech: {', '.join(w.tech_stack)})"
        for w in profile.work_experience
    ) if profile.work_experience else "No detailed work history provided."

    job_desc = job_spec.description or "Senior engineering role focusing on robust, scalable backend architecture."

    previous_section = ""
    if previous_contracts:
        prev_list = "\n".join(f"- {c}" for c in previous_contracts if c)
        if prev_list:
            previous_section = (
                f"PREVIOUSLY ASSIGNED SCENARIOS (FORBIDDEN TO REPEAT):\n"
                f"{prev_list}\n"
                f"Generate a novel, distinct engineering incident with a different domain and failure mode.\n\n"
            )

    seniority_diff, seniority_reason = resolve_seniority_tier(
        seniority=getattr(job_spec, "seniority", None),
        job_title=job_spec.job_title,
        years_of_experience=job_spec.years_of_experience,
        instructions=job_spec.instructions or "",
    )
    seniority_guidance = get_seniority_complexity_guidance(seniority_diff)

    tech_focus_str = ', '.join(job_spec.technical_focus) if job_spec.technical_focus else 'General Backend / Distributed Systems'
    domain_libs_str = ', '.join(ecosystem.domain_libraries) if ecosystem.domain_libraries else 'Standard idiomatic libraries'
    infra_deps_str = ', '.join(ecosystem.infrastructure_dependencies) if ecosystem.infrastructure_dependencies else 'Standard persistence / in-memory'

    return (
        f"TARGET ROLE: {job_spec.job_title} (Resolved Difficulty: {seniority_diff.value} — {seniority_reason})\n"
        f"SENIORITY CONTRACT GUIDANCE:\n{seniority_guidance}\n\n"
        f"JOB DESCRIPTION:\n{job_desc}\n"
        f"ROLE TECHNICAL FOCUS: {tech_focus_str}\n"
        f"BASELINE TECHNOLOGY ENVIRONMENT:\n"
        f"- Target Primary Language: {target_lang} (Files should use '{target_ext}')\n"
        f"- Baseline Framework Reference: {ecosystem.framework or 'Idiomatic modern framework'}\n"
        f"- Baseline Libraries Reference: {domain_libs_str}\n"
        f"- Baseline Infra Reference: {infra_deps_str}\n\n"
        f"CANDIDATE NAME: {profile.candidate_name}\n"
        f"CANDIDATE TECH STACK: {', '.join(profile.skills + profile.frameworks_and_tools)}\n"
        f"WORK EXPERIENCE:\n{work_summary}\n"
        f"CLAIMED PROJECTS:\n{projects_summary}\n"
        f"ROLE ARCHETYPE: {blueprint.role_archetype}\n"
        f"{previous_section}"
        f"{retry_hint}\n\n"
        f"Generate the comprehensive {schema_target} adherence to all design principles:\n"
        f"1. Ground directly in the candidate's actual projects/experience and the target role ecosystem.\n"
        f"2. Architect the 'technology_environment' choosing the specific language ({target_lang}), framework, domain libraries, and infrastructure/transport that best exposes the defect.\n"
        f"3. Specify at least 2 distinct interacting components with realistic architectural responsibilities across 2-3 files.\n"
        f"4. Specify at least 3 failure requirements forming a non-obvious causal mechanism (trigger, cause, symptom, why non-obvious).\n"
        f"5. Define conversational interviewer diagnostic strategy and concrete follow-up areas.\n"
        f"6. Ban toy mocks and stubs in the implementation constraints avoid list."
    )
