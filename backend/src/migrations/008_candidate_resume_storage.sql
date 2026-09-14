-- ================================================================
-- Migration 008: Candidate Resume Storage & Parser Cache
-- Vetra AI Technical Interviewer
-- Adds structured resume and metadata columns to public.candidate_profiles
-- ================================================================

-- 1. Add resume storage columns to public.candidate_profiles if they do not exist
ALTER TABLE public.candidate_profiles 
    ADD COLUMN IF NOT EXISTS parsed_resume JSONB,
    ADD COLUMN IF NOT EXISTS resume_filename TEXT,
    ADD COLUMN IF NOT EXISTS resume_hash TEXT,
    ADD COLUMN IF NOT EXISTS raw_resume_text TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now());

-- 2. Create index on resume_hash for fast freeze-cache lookups
CREATE INDEX IF NOT EXISTS idx_candidate_profiles_resume_hash 
    ON public.candidate_profiles (resume_hash);

-- 3. Create index on email and user_id for fast candidate lookups
CREATE INDEX IF NOT EXISTS idx_candidate_profiles_user_id 
    ON public.candidate_profiles (user_id);

CREATE INDEX IF NOT EXISTS idx_candidate_profiles_email 
    ON public.candidate_profiles (email);
