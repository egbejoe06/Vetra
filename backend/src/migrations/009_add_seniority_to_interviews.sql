-- ================================================================
-- Migration 009: Add Seniority to Interviews Table
-- Vetra AI Technical Interviewer
-- Adds optional seniority column to public.interviews for recruiter-specified target difficulty
-- ================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'interviews' 
        AND column_name = 'seniority'
    ) THEN
        ALTER TABLE public.interviews ADD COLUMN seniority TEXT;
    END IF;
END $$;
