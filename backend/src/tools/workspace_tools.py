import logging
from typing import Any, Dict, Optional

from src.db.supabase import supabase
from src.orchestrator.engine import interview_orchestrator

logger = logging.getLogger("vetra.tools.workspace")


async def handle_present_problem(
    session_id: str, problem_id: Optional[str] = None
) -> Dict[str, Any]:
    """Present the technical coding challenge to the candidate's workspace."""
    try:
        problem_data: Optional[Dict[str, Any]] = None

        if supabase:
            for attempt in range(8):
                query = supabase.table("technical_problems").select("*")
                if problem_id:
                    query = query.eq("id", str(problem_id))
                else:
                    query = query.eq("session_id", str(session_id))
                
                res = query.order("created_at", desc=True).limit(1).execute()
                if res.data and len(res.data) > 0:
                    problem_data = res.data[0]
                    break
                else:
                    # Check if attached to the parent interview
                    sess_res = supabase.table("interview_sessions").select("interview_id").eq("id", str(session_id)).limit(1).execute()
                    if sess_res.data and len(sess_res.data) > 0:
                        interview_id = sess_res.data[0].get("interview_id")
                        if interview_id:
                            p_res = supabase.table("technical_problems").select("*").eq("interview_id", str(interview_id)).order("created_at", desc=True).limit(1).execute()
                            if p_res.data and len(p_res.data) > 0:
                                problem_data = p_res.data[0]
                                # Auto-link session_id to this problem record
                                try:
                                    supabase.table("technical_problems").update({"session_id": str(session_id)}).eq("id", str(problem_data["id"])).execute()
                                except Exception:
                                    pass
                                break
                
                # If still generating in background, wait briefly for it to complete
                if attempt < 7:
                    import asyncio
                    await asyncio.sleep(1.0)

        actual_problem_id = str(problem_data["id"]) if problem_data else (problem_id or "default_problem")

        # Mark in LangGraph orchestrator
        await interview_orchestrator.present_problem(
            session_id=session_id,
            problem_id=actual_problem_id,
            actor="GEMINI",
        )

        return {
            "success": True,
            "problem_id": actual_problem_id,
            "title": problem_data.get("title", "Technical Code Review & Architecture Walkthrough") if problem_data else "Technical Code Review",
            "problem_type": problem_data.get("problem_type", "CODE_REVIEW") if problem_data else "CODE_REVIEW",
            "prompt_question": problem_data.get("prompt_question", "") if problem_data else "Please inspect the code files on screen and walk through your analysis and proposed solutions out loud with the interviewer.",
            "instructions": (problem_data.get("context") or problem_data.get("instructions") or "") if problem_data else "",
            "code_files": problem_data.get("code_files", []) if problem_data else [],
            "key_discussion_points": problem_data.get("key_discussion_points", []) if problem_data else [],
        }
    except Exception as err:
        logger.error(f"Error presenting problem for session {session_id}: {err}")
        return {"success": False, "error": str(err)}


async def handle_get_workspace_context(
    session_id: str, file_path: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieve workspace context and code files for discussions."""
    try:
        if not supabase:
            return {"success": True, "files": [], "message": "Database not initialized"}

        res = supabase.table("technical_problems").select("*").eq("session_id", str(session_id)).limit(1).execute()
        files = []
        if res.data and len(res.data) > 0:
            files = res.data[0].get("code_files", [])

        if file_path:
            matching = [f for f in files if f.get("path") == file_path]
            return {
                "success": True,
                "file_path": file_path,
                "content": matching[0].get("content") if matching else None,
                "found": len(matching) > 0,
            }

        return {
            "success": True,
            "file_count": len(files),
            "files": [{"path": f.get("path"), "language": f.get("language")} for f in files],
        }
    except Exception as err:
        logger.error(f"Error fetching workspace context for session {session_id}: {err}")
        return {"success": False, "error": str(err)}
