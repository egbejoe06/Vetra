-- Migration 010: Make overall_score nullable in interview_evaluations
-- Reason: INCONCLUSIVE interviews (premature disconnects, no assessed rubric categories)
-- legitimately have no computable score. The NOT NULL constraint causes upsert failures
-- and must be relaxed to allow null scores alongside INCONCLUSIVE recommendations.

ALTER TABLE public.interview_evaluations
    ALTER COLUMN overall_score DROP NOT NULL;

-- Add a check constraint to enforce: if score is present it must be 0.0–10.0
-- (the existing NUMERIC(3,1) type already enforces precision, this adds range)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'interview_evaluations'
          AND constraint_name = 'check_overall_score_range'
    ) THEN
        ALTER TABLE public.interview_evaluations
            ADD CONSTRAINT check_overall_score_range
            CHECK (overall_score IS NULL OR (overall_score >= 0.0 AND overall_score <= 10.0));
    END IF;
END $$;
