-- ================================================================
-- Migration 004: Session Resumption Handle for Live API Resilience
-- Vetra AI Technical Interviewer
-- ================================================================

ALTER TABLE public.interview_sessions 
ADD COLUMN IF NOT EXISTS resumption_handle TEXT,
ADD COLUMN IF NOT EXISTS resumption_updated_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS idx_interview_sessions_resumption_handle 
ON public.interview_sessions(resumption_handle) 
WHERE resumption_handle IS NOT NULL;
