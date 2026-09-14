import logging
from typing import Optional
from supabase import create_client, Client
from config import settings

logger = logging.getLogger(__name__)

supabase: Optional[Client] = None

if settings.SUPABASE_URL and settings.SUPABASE_KEY:
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        # supabase-py v2: explicitly inject the service_role key as the
        # PostgREST Authorization header so RLS is bypassed on every request.
        supabase.postgrest.auth(settings.SUPABASE_KEY)
    except Exception as e:
        logger.warning(f"Failed to initialize Supabase client: {e}")
        supabase = None

