-- Migration 008: Add INCONCLUSIVE to candidate_recommendation enum
DO $$
BEGIN
    ALTER TYPE candidate_recommendation ADD VALUE IF NOT EXISTS 'INCONCLUSIVE';
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
