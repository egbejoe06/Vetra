import logging
from typing import Optional
from supabase import create_client, Client
from config import settings

logger = logging.getLogger(__name__)

supabase: Optional[Client] = None

# Use service role key to bypass RLS for all backend queries.
# Falls back to SUPABASE_KEY if SUPABASE_SERVICE_KEY is not set (e.g. local dev).
_backend_key = settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY

if settings.SUPABASE_URL and _backend_key:
    try:
        supabase = create_client(settings.SUPABASE_URL, _backend_key)
        # supabase-py v2: explicitly inject the service_role key as the
        # PostgREST Authorization header so RLS is bypassed on every request.
        supabase.postgrest.auth(_backend_key)
    except Exception as e:
        logger.warning(f"Failed to initialize Supabase client: {e}")
        supabase = None

