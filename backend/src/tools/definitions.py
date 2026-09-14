from google.genai import types

# Tool Declarations for Gemini Live Session

GET_INTERVIEWER_STATE_DECLARATION = types.FunctionDeclaration(
    name="get_interviewer_state",
    description=(
        "Retrieve the current authoritative interview stage, question count, "
        "target competencies, strategic probing objectives, and stage transition eligibility."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={},
    ),
)

REQUEST_STAGE_TRANSITION_DECLARATION = types.FunctionDeclaration(
    name="request_stage_transition",
    description=(
        "Request a progression to the next interview stage (e.g., INTRO, RESUME_DEEP_DIVE, "
        "TECHNICAL_QA, TECHNICAL_EXERCISE, BEHAVIORAL, WRAP_UP, COMPLETED). "
        "The LangGraph orchestrator checks guard rules before approving or rejecting."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "target_stage": types.Schema(
                type=types.Type.STRING,
                description="Target stage to transition into (e.g., RESUME_DEEP_DIVE, TECHNICAL_QA, TECHNICAL_EXERCISE, BEHAVIORAL, WRAP_UP, COMPLETED)",
            ),
            "reason": types.Schema(
                type=types.Type.STRING,
                description="Conversational rationale for requesting the stage advance",
            ),
        },
        required=["target_stage"],
    ),
)

PRESENT_PROBLEM_DECLARATION = types.FunctionDeclaration(
    name="present_problem",
    description=(
        "Present the active coding challenge or architecture design problem to the candidate's workspace "
        "during the TECHNICAL_EXERCISE stage."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "problem_id": types.Schema(
                type=types.Type.STRING,
                description="Optional specific technical problem ID to present. If omitted, uses active session problem.",
            ),
        },
    ),
)

GET_WORKSPACE_CONTEXT_DECLARATION = types.FunctionDeclaration(
    name="get_workspace_context",
    description=(
        "Retrieve the candidate's active code review viewer state, file list, and code contents "
        "to discuss and evaluate their verbal analysis and technical walkthrough."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "file_path": types.Schema(
                type=types.Type.STRING,
                description="Optional specific file path in the workspace to inspect",
            ),
        },
    ),
)

RECORD_INTERVIEWER_OBSERVATION_DECLARATION = types.FunctionDeclaration(
    name="record_interviewer_observation",
    description=(
        "Record a lightweight real-time observation or conversational flag regarding candidate performance, "
        "self-correction, or technical concept mastery."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "observation": types.Schema(
                type=types.Type.STRING,
                description="Specific note or observation",
            ),
            "competency": types.Schema(
                type=types.Type.STRING,
                description="Competency tag associated with the observation (e.g., system_design, python, concurrency)",
            ),
            "sentiment": types.Schema(
                type=types.Type.STRING,
                description="Positive, Neutral, or Negative signal indicator",
            ),
        },
        required=["observation"],
    ),
)


def get_live_tools() -> list[types.Tool]:
    """Returns the list of tools declared for Gemini Live session."""
    return [
        types.Tool(
            function_declarations=[
                GET_INTERVIEWER_STATE_DECLARATION,
                REQUEST_STAGE_TRANSITION_DECLARATION,
                PRESENT_PROBLEM_DECLARATION,
                GET_WORKSPACE_CONTEXT_DECLARATION,
                RECORD_INTERVIEWER_OBSERVATION_DECLARATION,
            ]
        )
    ]
