import logging
from typing import Dict, List, Optional
from uuid import UUID

from src.orchestrator.state import GuidancePayload
from src.schemas.evaluator import (
    CompetencyAssessment,
    StrategicProbeObjective,
)

logger = logging.getLogger("vetra.agents.guidance_compiler")


class GuidanceCompiler:
    """Compiles verbose raw evaluator signals into a prioritized, actionable GuidancePayload
    for the LangGraph orchestrator and Gemini Live voice stream.
    
    Responsibilities:
    - Deduplicate similar probing objectives.
    - Expire stale probes past their turn horizon.
    - Mark satisfied probes as completed.
    - Enforce a strict cognitive budget: 1 primary objective, max 2 secondary objectives, and explicit 'avoid' guidance.
    """

    MAX_SECONDARY_OBJECTIVES = 2

    @classmethod
    def compile(
        cls,
        active_probes: List[StrategicProbeObjective],
        satisfied_probe_ids: List[str],
        assessments: Dict[str, CompetencyAssessment],
        current_turn_index: int,
        guidance_version: int = 1,
    ) -> GuidancePayload:
        """Transforms evaluator state into a clean GuidancePayload."""
        # 1. Update status of satisfied probes
        satisfied_set = set(satisfied_probe_ids)
        for probe in active_probes:
            if str(probe.id) in satisfied_set or str(probe.topic).lower() in [s.lower() for s in satisfied_set]:
                probe.status = "SATISFIED"

        # 2. Expire stale probes past their turn horizon or after 3 turns
        for probe in active_probes:
            if probe.status == "ACTIVE":
                if probe.expires_after_turn and current_turn_index >= probe.expires_after_turn:
                    probe.status = "EXPIRED"
                elif not probe.expires_after_turn:
                    # Default expiration: expire after 3 turns from creation
                    try:
                        created_turn_num = int(str(probe.created_from_turn_id).split("_")[-1])
                        if current_turn_index - created_turn_num >= 3:
                            probe.status = "EXPIRED"
                    except Exception:
                        pass

        # 3. Filter active and deduplicate
        viable_probes = [p for p in active_probes if p.status == "ACTIVE"]
        deduped_probes = cls._deduplicate_probes(viable_probes)

        # Filter out probes for competencies that already have sufficient evidence recorded
        filtered_probes = []
        for p in deduped_probes:
            target_assess = assessments.get(p.competency_target)
            if target_assess and target_assess.coverage_status == "SUFFICIENT":
                p.status = "SATISFIED"
                continue
            filtered_probes.append(p)

        # 4. Sort by priority: HIGH -> MEDIUM -> LOW
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        sorted_probes = sorted(
            filtered_probes,
            key=lambda p: (priority_order.get(p.priority, 3), p.created_from_turn_id),
        )

        # 5. Extract completed objectives list
        completed_objectives = [
            f"[{p.topic}] {p.objective}"
            for p in active_probes
            if p.status == "SATISFIED"
        ]

        # 6. Extract primary and secondary objectives
        primary_probe: Optional[StrategicProbeObjective] = sorted_probes[0] if sorted_probes else None
        secondary_probes = sorted_probes[1 : 1 + cls.MAX_SECONDARY_OBJECTIVES] if len(sorted_probes) > 1 else []

        # 7. Formulate avoid directives from satisfied or sufficient competencies
        avoid_topics = [
            p.topic
            for p in active_probes
            if p.status == "SATISFIED"
        ]
        for comp, assess in assessments.items():
            if assess.coverage_status == "SUFFICIENT" and comp not in avoid_topics:
                avoid_topics.append(comp)

        avoid_directive = ""
        if avoid_topics:
            avoid_directive = f" (Avoid repeating topics already validated: {', '.join(avoid_topics[:3])})"

        # 8. Compute numeric coverage ratio per competency and explicit covered/missing lists
        coverage_dict: Dict[str, float] = {}
        covered_list: List[str] = []
        missing_list: List[str] = []
        for comp, assess in assessments.items():
            if assess.coverage_status == "SUFFICIENT":
                coverage_dict[comp] = 1.0
                covered_list.append(comp)
            elif assess.coverage_status == "PARTIAL":
                coverage_dict[comp] = 0.5
                missing_list.append(comp)
            else:
                coverage_dict[comp] = 0.1
                missing_list.append(comp)

        # 9. Build actionable interviewer instructions (non-hijacking, quota-respecting)
        instructions_list: List[str] = []
        if covered_list:
            instructions_list.append(f"Do NOT ask another question on already covered topics: {', '.join(covered_list[:3])}.")
        if primary_probe:
            instructions_list.append(
                f"Optional follow-up probe (max 1 turn, only if within stage question limits): {primary_probe.suggested_direction or primary_probe.objective}."
            )
            instructions_list.append(
                "Do NOT rephrase or repeat previously asked questions. Continue with the next planned question or transition stages."
            )
        elif missing_list:
            instructions_list.append(f"Prioritize uncovered competencies if time permits: {', '.join(missing_list[:3])}.")

        # 10. Format output objectives
        pending_objectives_list: List[str] = []
        if primary_probe:
            pending_objectives_list.append(f"PRIMARY: {primary_probe.objective}")
        for sec in secondary_probes:
            pending_objectives_list.append(f"SECONDARY: {sec.objective}")

        topic = primary_probe.topic if primary_probe else "General Technical Verification"
        goal = primary_probe.objective if primary_probe else "Continue natural technical conversation."
        direction = primary_probe.suggested_direction if primary_probe else None
        if direction and avoid_directive:
            direction = f"{direction}{avoid_directive}"
        elif avoid_directive:
            direction = avoid_directive.strip()

        target_comp = primary_probe.competency_target if primary_probe else None
        rec_probe = primary_probe.suggested_direction if primary_probe else None

        return GuidancePayload(
            topic=topic,
            priority=primary_probe.priority if primary_probe else "MEDIUM",
            goal=goal,
            suggested_direction=direction,
            competency_target=target_comp,
            pending_objectives=pending_objectives_list,
            completed_objectives=completed_objectives,
            competency_coverage=coverage_dict,
            competencies_covered=covered_list,
            competencies_missing=missing_list,
            recommended_probe=rec_probe,
            instructions=instructions_list,
            version=guidance_version,
        )

    @classmethod
    def _deduplicate_probes(
        cls, probes: List[StrategicProbeObjective]
    ) -> List[StrategicProbeObjective]:
        """Deduplicates probes targeting the same competency and similar topics."""
        seen_targets = set()
        deduped = []
        for probe in probes:
            key = (probe.competency_target.strip().lower(), probe.topic.strip().lower())
            if key in seen_targets:
                continue
            seen_targets.add(key)
            deduped.append(probe)
        return deduped
