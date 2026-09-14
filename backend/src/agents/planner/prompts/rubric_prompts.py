import json
from src.schemas.planner import InterviewBlueprint, InterviewPlanCreate
from src.utils.seniority import resolve_seniority_tier

RUBRIC_SYSTEM_INSTRUCTION = (
    "You are a Principal Assessment Bar Raiser at Vetra.\n"
    "Your task is to generate rigorous, observable scoring rubrics (1, 3, 5 levels) and interviewer guidance in JSON format.\n\n"
    "RUBRIC PHILOSOPHY: STRICT 1:1 MAPPING TIED TO BLUEPRINT COMPETENCIES:\n"
    "- Rubrics MUST map exactly 1:1 to the atomic competencies in the Interview Blueprint.\n"
    "- Generate EXACTLY one rubric criterion for each atomic competency in 'competencies'. Do NOT invent extraneous categories or omit any blueprint competency.\n"
    "- EVERY rubric criterion must define:\n"
    "  1. 'competency': The exact competency name from the blueprint.\n"
    "  2. 'observable_evidence': Concrete observable behaviors, mechanism explanations, or architectural proofs the interviewer evaluates.\n"
    "  3. 'description_level_1': Concrete anti-patterns (e.g. 'Names technologies but cannot explain component boundaries or failure modes').\n"
    "  4. 'description_level_3': Competent/Standard execution (e.g. 'Explains boundaries and tradeoffs relevant to the scenario').\n"
    "  5. 'description_level_5': Exemplary/Senior execution (e.g. 'Anticipates second-order effects, failure propagation, operational constraints, and proposes justified alternatives').\n"
    "  6. 'common_false_positives': Superficial signals that sound impressive on the surface but mask lack of depth (e.g. 'Dropping cloud service buzzwords without understanding state invariants or failure recovery').\n\n"
    "STRICT PROHIBITION ON GENERIC RUBRIC TEXT:\n"
    "- NEVER use lazy, non-measurable text like: 'Basic knowledge', 'Good understanding', 'Expert understanding'.\n"
    "- Every level MUST describe concrete observable technical mechanisms, component interactions, and failure modes.\n\n"
    "CRITICAL EXCLUSION:\n"
    "- Do NOT generate a Communication or Speech Articulation rubric category, as automated speech transcription may introduce transcription artifacts. Focus strictly on technical and engineering substance."
)


def build_rubrics_prompt(job_spec: InterviewPlanCreate, blueprint: InterviewBlueprint) -> str:
    competencies_repr = json.dumps([c.model_dump() for c in blueprint.competencies], indent=2) if blueprint.competencies else "[]"
    caps_repr = json.dumps(blueprint.capabilities_to_assess, indent=2) if blueprint.capabilities_to_assess else "[]"
    risks_repr = json.dumps(blueprint.risk_hypotheses, indent=2) if blueprint.risk_hypotheses else "[]"

    seniority_diff, seniority_reason = resolve_seniority_tier(
        seniority=getattr(job_spec, "seniority", None),
        job_title=job_spec.job_title,
        years_of_experience=job_spec.years_of_experience,
        instructions=job_spec.instructions or "",
    )

    num_competencies = len(blueprint.competencies) if blueprint.competencies else 3

    return (
        f"Target Role: {job_spec.job_title} ({seniority_diff.value} — {seniority_reason})\n"
        f"Role Archetype: {blueprint.role_archetype}\n"
        f"Job Technical Focus: {', '.join(job_spec.technical_focus)}\n"
        f"Job Behavioral Focus: {', '.join(job_spec.behavioral_focus)}\n"
        f"Job Description: {job_spec.description or ''}\n"
        f"Recruiter Evaluation Criteria: {job_spec.evaluation_criteria or ''}\n\n"
        f"INTERVIEW BLUEPRINT COMPETENCIES TO EVALUATE (EXACTLY {num_competencies} CRITERIA REQUIRED):\n{competencies_repr}\n\n"
        f"INTERVIEW BLUEPRINT CAPABILITIES TO ASSESS:\n{caps_repr}\n\n"
        f"INTERVIEW BLUEPRINT RISK HYPOTHESES:\n{risks_repr}\n\n"
        "OUTPUT INSTRUCTIONS:\n"
        f"Generate scoring rubrics with EXACTLY {num_competencies} criteria (one for each blueprint competency above: with competency, observable_evidence, description_level_1, description_level_3, description_level_5, and common_false_positives), followed by actionable interviewer guidance."
    )
