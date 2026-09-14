import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.db.supabase import supabase
from src.realtime.event_router import RealtimeEventRouter
from src.realtime.session_manager import RealtimeSessionManager, active_sessions

logger = logging.getLogger("vetra.routes.websocket")

router = APIRouter(tags=["Realtime WebSocket"])


@router.websocket("/ws/interview/{session_id}")
async def interview_websocket_endpoint(websocket: WebSocket, session_id: str):
    """Realtime Media Bridge WebSocket endpoint connecting candidate browser
    with Google GenAI Live API (gemini-3.1-flash-live-preview).
    """
    await websocket.accept()
    logger.info(f"Accepted WebSocket connection for interview session: {session_id}")

    # Validate UUID format
    try:
        uuid.UUID(str(session_id))
    except (ValueError, TypeError):
        logger.warning(f"Invalid UUID session_id: {session_id}")
        await RealtimeEventRouter.send_error(
            websocket,
            message=f"Invalid session ID format: '{session_id}'. Must be a valid UUID.",
            code="INVALID_SESSION_ID",
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify session existence in Supabase
    if supabase:
        try:
            res = supabase.table("interview_sessions").select("id, status").eq("id", str(session_id)).limit(1).execute()
            if not res.data or len(res.data) == 0:
                logger.warning(f"Interview session {session_id} not found in database")
                await RealtimeEventRouter.send_error(
                    websocket,
                    message=f"Interview session '{session_id}' not found.",
                    code="SESSION_NOT_FOUND",
                )
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
        except Exception as err:
            logger.warning(f"Supabase check failed during WS handshake: {err}")

    # Terminate any existing connection for this session_id
    if session_id in active_sessions:
        logger.info(f"Replacing existing active WebSocket connection for session {session_id}")
        existing_mgr = active_sessions.pop(session_id, None)
        if existing_mgr:
            await existing_mgr.shutdown()

    manager = RealtimeSessionManager(session_id=session_id, websocket=websocket)
    active_sessions[session_id] = manager

    try:
        # Initialize Gemini Live connection and LangGraph state
        await manager.initialize()

        # Run continuous upstream & downstream message bridge
        await manager.run()

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for session {session_id}")
    except Exception as err:
        logger.error(f"Error in interview WebSocket lifecycle for session {session_id}: {err}", exc_info=True)
        try:
            await RealtimeEventRouter.send_error(
                websocket,
                message=f"Realtime session error: {str(err)}",
                code="SESSION_ERROR",
            )
        except Exception:
            pass
    finally:
        active_sessions.pop(session_id, None)
        await manager.shutdown()
        logger.info(f"Cleaned up WebSocket session for: {session_id}")
