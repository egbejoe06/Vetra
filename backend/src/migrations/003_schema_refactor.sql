-- ================================================================
-- Migration 003: Schema Refactor & Modernization (Delta Migration)
-- Vetra AI Technical Interviewer
-- Applies all updates onto a database with Migration 001 and 002 applied
-- ================================================================

-- 1. General Software Engineering Problem Types
-- Add missing general problem types to technical_problem_type enum
ALTER TYPE technical_problem_type ADD VALUE IF NOT EXISTS 'DEBUGGING';
ALTER TYPE technical_problem_type ADD VALUE IF NOT EXISTS 'IMPLEMENTATION';
ALTER TYPE technical_problem_type ADD VALUE IF NOT EXISTS 'PERFORMANCE';
ALTER TYPE technical_problem_type ADD VALUE IF NOT EXISTS 'REFACTORING';
ALTER TYPE technical_problem_type ADD VALUE IF NOT EXISTS 'API_DESIGN';
ALTER TYPE technical_problem_type ADD VALUE IF NOT EXISTS 'SECURITY_REVIEW';
ALTER TYPE technical_problem_type ADD VALUE IF NOT EXISTS 'DATA_STRUCTURES_AND_ALGORITHMS';

-- 2. Artifact Types
-- Add EVALUATION_BLUEPRINT to artifact_type enum (for private interviewer secret rubrics & AST plans)
ALTER TYPE artifact_type ADD VALUE IF NOT EXISTS 'EVALUATION_BLUEPRINT';

-- 3. Relax session_id constraint to allow pre-session template assets
-- When recruiters configure interviews, coding problems & blueprint artifacts are generated
-- and associated directly with interview_id before any candidate session begins.
ALTER TABLE public.technical_problems ALTER COLUMN session_id DROP NOT NULL;
ALTER TABLE public.interview_artifacts ALTER COLUMN session_id DROP NOT NULL;

-- 4. Update Row Level Security Policies for technical_problems
DROP POLICY IF EXISTS "View problems for session" ON public.technical_problems;
DROP POLICY IF EXISTS "View problems for session or interview" ON public.technical_problems;
DROP POLICY IF EXISTS "Recruiters manage problems" ON public.technical_problems;

-- Allow candidates to view problems in their session, and recruiters to view problems in their sessions/interviews
CREATE POLICY "View problems for session or interview"
    ON public.technical_problems
    FOR SELECT
    USING (
        (session_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM public.interview_sessions s
            WHERE s.id = technical_problems.session_id
            AND (
                s.candidate_id = auth.uid()
                OR EXISTS (
                    SELECT 1 FROM public.interviews i 
                    WHERE i.id = s.interview_id AND i.recruiter_id = auth.uid()
                )
            )
        ))
        OR (interview_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM public.interviews i 
            WHERE i.id = technical_problems.interview_id AND i.recruiter_id = auth.uid()
        ))
    );

-- Allow recruiters to manage (insert, update, delete) problems for their interviews
CREATE POLICY "Recruiters manage problems"
    ON public.technical_problems
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.interviews i 
            WHERE i.id = technical_problems.interview_id AND i.recruiter_id = auth.uid()
        )
    );

-- 5. Update Row Level Security Policies for interview_artifacts
DROP POLICY IF EXISTS "View artifacts for session" ON public.interview_artifacts;
DROP POLICY IF EXISTS "View artifacts for session or interview" ON public.interview_artifacts;
DROP POLICY IF EXISTS "Recruiters manage artifacts" ON public.interview_artifacts;

-- Allow candidates to view non-secret artifacts for their session, and recruiters to view all artifacts
CREATE POLICY "View artifacts for session or interview"
    ON public.interview_artifacts
    FOR SELECT
    USING (
        (session_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM public.interview_sessions s
            WHERE s.id = interview_artifacts.session_id
            AND (
                s.candidate_id = auth.uid()
                OR EXISTS (
                    SELECT 1 FROM public.interviews i 
                    WHERE i.id = s.interview_id AND i.recruiter_id = auth.uid()
                )
            )
        ))
        OR (problem_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM public.technical_problems p
            JOIN public.interviews i ON i.id = p.interview_id
            WHERE p.id = interview_artifacts.problem_id AND i.recruiter_id = auth.uid()
        ))
    );

-- Allow recruiters to manage artifacts for their problems/interviews
CREATE POLICY "Recruiters manage artifacts"
    ON public.interview_artifacts
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.technical_problems p
            JOIN public.interviews i ON i.id = p.interview_id
            WHERE p.id = interview_artifacts.problem_id AND i.recruiter_id = auth.uid()
        )
    );
