-- ================================================================
-- Migration 011: Fix RLS Security Vulnerabilities
-- Vetra AI Technical Interviewer
--
-- Resolves Supabase Security Advisor errors:
--   - RLS Disabled in Public: evaluation_jobs
--   - RLS Disabled in Public: evaluation_signals
--   - RLS Disabled in Public: synthesis_snapshots
--   - Sensitive Columns Exposed: evaluation_jobs
--   - Sensitive Columns Exposed: evaluation_signals
--   - Sensitive Columns Exposed: synthesis_snapshots
--
-- These three tables are internal pipeline tables managed exclusively
-- by the FastAPI backend via the service role key (which bypasses RLS).
-- Enabling RLS with recruiter-scoped read policies:
--   - Prevents direct client/anon access via PostgREST
--   - Allows recruiters to query evaluation data for their own interviews
--   - Backend service role is unaffected (it always bypasses RLS)
-- ================================================================

-- 1. Enable Row Level Security on internal pipeline tables
ALTER TABLE public.evaluation_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evaluation_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.synthesis_snapshots ENABLE ROW LEVEL SECURITY;

-- ================================================================
-- 2. RLS Policies for evaluation_jobs
--    evaluation_jobs.session_id -> interview_sessions -> interviews.recruiter_id
-- ================================================================

-- Recruiters can view evaluation jobs for sessions under their interviews
CREATE POLICY "Recruiters can view evaluation jobs for their interviews"
    ON public.evaluation_jobs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1
            FROM public.interview_sessions s
            JOIN public.interviews i ON i.id = s.interview_id
            WHERE s.id = evaluation_jobs.session_id
              AND i.recruiter_id = auth.uid()
        )
    );

-- ================================================================
-- 3. RLS Policies for evaluation_signals
--    evaluation_signals.session_id -> interview_sessions -> interviews.recruiter_id
-- ================================================================

-- Recruiters can view evaluation signals for sessions under their interviews
CREATE POLICY "Recruiters can view evaluation signals for their interviews"
    ON public.evaluation_signals
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1
            FROM public.interview_sessions s
            JOIN public.interviews i ON i.id = s.interview_id
            WHERE s.id = evaluation_signals.session_id
              AND i.recruiter_id = auth.uid()
        )
    );

-- ================================================================
-- 4. RLS Policies for synthesis_snapshots
--    synthesis_snapshots.session_id -> interview_sessions -> interviews.recruiter_id
-- ================================================================

-- Recruiters can view synthesis snapshots for sessions under their interviews
CREATE POLICY "Recruiters can view synthesis snapshots for their interviews"
    ON public.synthesis_snapshots
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1
            FROM public.interview_sessions s
            JOIN public.interviews i ON i.id = s.interview_id
            WHERE s.id = synthesis_snapshots.session_id
              AND i.recruiter_id = auth.uid()
        )
    );
