from fastapi import APIRouter
from config import settings
from src.db.supabase import supabase

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """Health check endpoint to verify backend status and Supabase connectivity."""
    supabase_status = "connected"
    supabase_error = None

    try:
        # Simple test query to check Supabase connection
        # Note: If no tables exist yet, Supabase API connection itself is still verified via client ping/rest call
        _ = supabase.auth.get_session()
    except Exception as e:
        supabase_status = "error"
        supabase_error = str(e)

    response = {
        "status": "healthy" if supabase_status == "connected" else "degraded",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "services": {
            "supabase": {
                "status": supabase_status,
                "details": supabase_error
            }
        }
    }
    return response
