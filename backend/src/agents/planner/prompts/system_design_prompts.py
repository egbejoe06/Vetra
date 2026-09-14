from typing import Optional

from src.schemas.planner import (
    CandidateProfile,
    InterviewBlueprint,
    InterviewPlanCreate,
)
from src.utils.seniority import get_seniority_complexity_guidance, resolve_seniority_tier

SYSTEM_DESIGN_INSTRUCTION = (
    "You are a Principal Systems Architect and Executive Technical Bar Raiser at Vetra.\n"
    "Generate a deep, realistic System Design Interview Challenge tailored to the candidate's exact domain, stack, and target seniority.\n\n"
    "SCENARIO-DRIVEN ARCHITECTURE PHILOSOPHY (TOP TECH STANDARDS):\n"
    "1. ARCHITECTURE MUST BE SCENARIO-DRIVEN:\n"
    "   - NEVER force a rigid backend distributed template onto candidates whose roles have different architectural paradigms.\n"
    "   - The architecture must naturally emerge from first principles:\n"
    "     * What is the system?\n"
    "     * Who are the users?\n"
    "     * What is the critical workflow?\n"
    "     * What makes this difficult?\n"
    "     * Where is the bottleneck?\n"
    "     * What tradeoffs actually matter?\n"
    "   - Select ONLY the architectural layers that naturally emerge from the scenario.\n\n"
    "2. ADAPTIVE DISCIPLINE-SPECIFIC ARCHITECTURAL PARADIGMS:\n"
    "   - Applied AI / Agent Systems: Model routing, retrieval & chunking pipeline, context/prompt window management, vector index & reranking, evaluation harness, latency vs cost tradeoffs, safety & guardrails.\n"
    "   - Frontend Architecture: Rendering lifecycle (SSR/SSG/client), state architecture & stores, network boundaries & streaming, client caching & hydration, Core Web Vitals/performance, offline behavior & local sync.\n"
    "   - Backend & Distributed Systems: Data consistency (ACID vs eventual), queueing & backpressure, worker orchestration, partitioning & consensus, multi-tier storage, failure recovery & idempotency.\n"
    "   - Security Architecture: Trust boundaries, threat modeling (STRIDE), identity & access federation, secrets lifecycle, cryptographic boundaries, auditability & tamper resistance.\n"
    "   - Mobile Architecture: UI thread decoupling, battery & cellular network constraints, offline-first storage & background sync, local caching, push notification pipeline.\n"
    "   - Database / Infrastructure Systems: Storage engines (LSM-tree vs B-Tree), indexing & query optimization, replication topologies, consensus protocols (Raft/Paxos), WAL, lock managers, connection pooling.\n\n"
    "3. SENIORITY-CALIBRATED ARCHITECTURAL COMPLEXITY:\n"
    "   - JUNIOR (0–2 YOE): Single-service workflow design or client component architecture with 1 clear tradeoff.\n"
    "   - MID (>2–5 YOE): Service + primary persistence/cache interaction with failure handling and data contract design.\n"
    "   - SENIOR (>5–8 YOE): Multi-service boundary design with 2 structural dilemmas and end-to-end resilience.\n"
    "   - LEAD / PRINCIPAL (>8 YOE): Cross-system / org-scale architectural tradeoffs, disaster recovery, backpressure, and blast-radius mitigation.\n\n"
    "4. CONCRETE QUANTITATIVE TARGETS:\n"
    "   Include realistic, scenario-appropriate metrics (e.g. QPS / throughput or p99 latency SLA for high-throughput APIs/services, token budget limits for LLM systems, Core Web Vitals for web frontends). NEVER mix or hallucinate metrics into irrelevant layers.\n\n"
    "5. AUTHENTIC ARCHITECTURAL TRADEOFFS:\n"
    "   Include at least 2 structural dilemmas genuine to this specific scenario (e.g. Latency vs Accuracy, Cost vs Quality, Eventual vs Strong Consistency, Client vs Server Compute, Battery vs Sync Frequency)."
)


def build_system_design_prompt(
    profile: CandidateProfile,
    job_spec: InterviewPlanCreate,
    blueprint: InterviewBlueprint,
    retry_hint: str = "",
    previous_exercises: Optional[list[str]] = None,
) -> str:
    caps_repr = ", ".join(blueprint.capabilities_to_assess) if blueprint.capabilities_to_assess else ", ".join(job_spec.technical_focus)

    retry_block = f"{retry_hint}\n\n" if retry_hint else ""

    seniority_diff, seniority_reason = resolve_seniority_tier(
        seniority=getattr(job_spec, "seniority", None),
        job_title=job_spec.job_title,
        years_of_experience=job_spec.years_of_experience,
        instructions=job_spec.instructions or "",
    )
    seniority_guidance = get_seniority_complexity_guidance(seniority_diff)

    previous_section = ""
    if previous_exercises:
        prev_list = "\n".join(f"- {title}" for title in previous_exercises if title)
        if prev_list:
            previous_section = (
                f"PREVIOUSLY ASSIGNED SYSTEM DESIGN EXERCISES (STRICTLY FORBIDDEN TO REPEAT):\n"
                f"{prev_list}\n"
                f"VARIATION MANDATE: The candidate has already seen the scenario(s) above. "
                f"You MUST generate a novel, distinct system design challenge with a different title, different domain context, "
                f"and different architectural dilemmas.\n\n"
            )

    return (
        f"Candidate: {profile.candidate_name}\n"
        f"Role: {job_spec.job_title} (Resolved Difficulty: {seniority_diff.value} — {seniority_reason})\n"
        f"Seniority Guidance:\n{seniority_guidance}\n\n"
        f"Archetype: {blueprint.role_archetype}\n"
        f"Technical Focus: {', '.join(job_spec.technical_focus)}\n"
        f"Capabilities To Assess: {caps_repr}\n"
        f"Tech Stack: {', '.join(profile.skills + profile.frameworks_and_tools)}\n\n"
        f"{previous_section}"
        f"{retry_block}"
        "Generate a tailored, scenario-driven System Design Exercise matching the SystemDesignExercise schema. Ensure the architecture layers naturally emerge from this specific role and scenario."
    )
