import logging
from typing import Any, Dict
from google.genai import types

from src.tools.interview_tools import (
    handle_get_interviewer_state,
    handle_record_interviewer_observation,
    handle_request_stage_transition,
)
from src.tools.workspace_tools import (
    handle_get_workspace_context,
    handle_present_problem,
)

logger = logging.getLogger("vetra.tools.gateway")


class ToolGateway:
    """Dispatches Gemini Live tool function calls to domain services and LangGraph orchestrator."""

    async def execute_tool(
        self, session_id: str, function_call: types.FunctionCall
    ) -> types.FunctionResponse:
        """Executes a single function call from Gemini Live and returns a typed FunctionResponse."""
        name = function_call.name
        call_id = function_call.id
        args = function_call.args or {}

        logger.info(f"Executing Live tool '{name}' (id={call_id}) for session {session_id} with args: {args}")

        result: Dict[str, Any]

        try:
            if name == "get_interviewer_state":
                result = await handle_get_interviewer_state(session_id=session_id)
            elif name == "request_stage_transition":
                result = await handle_request_stage_transition(
                    session_id=session_id,
                    target_stage=args.get("target_stage", ""),
                    reason=args.get("reason"),
                )
            elif name == "present_problem":
                result = await handle_present_problem(
                    session_id=session_id,
                    problem_id=args.get("problem_id"),
                )
            elif name == "get_workspace_context":
                result = await handle_get_workspace_context(
                    session_id=session_id,
                    file_path=args.get("file_path"),
                )
            elif name == "record_interviewer_observation":
                result = await handle_record_interviewer_observation(
                    session_id=session_id,
                    observation=args.get("observation", ""),
                    competency=args.get("competency"),
                    sentiment=args.get("sentiment"),
                )
            else:
                logger.warning(f"Unknown tool call requested: '{name}'")
                result = {"error": f"Tool '{name}' is not recognized"}

        except Exception as err:
            logger.error(f"Unhandled error executing tool '{name}': {err}", exc_info=True)
            result = {"error": f"Tool execution failed: {str(err)}"}

        return types.FunctionResponse(
            name=name,
            id=call_id,
            response={"result": result},
        )


# Singleton Tool Gateway instance
tool_gateway = ToolGateway()
