-- ================================================================
-- Migration 007: Add Evaluation Criteria to Interviews Table
-- Vetra AI Technical Interviewer
-- Adds optional evaluation_criteria column for recruiter scoring rubrics & focus areas
-- ================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'interviews' 
        AND column_name = 'evaluation_criteria'
    ) THEN
        ALTER TABLE public.interviews ADD COLUMN evaluation_criteria TEXT;
    END IF;
END $$;
