-- Migration 006: Asynchronous Evaluation Loop & Phase 6 Synthesis Architecture
-- Supports:
-- 1. Deterministic sequential turn_index on transcript_turns
-- 2. Durable Postgres-backed evaluation_jobs queue
-- 3. Accumulated evaluation_signals
-- 4. Immutable synthesis_snapshots
-- 5. Audit trail & score breakdown on interview_evaluations

-- 1. Add turn_index to transcript_turns if not present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'transcript_turns' 
        AND column_name = 'turn_index'
    ) THEN
        ALTER TABLE public.transcript_turns ADD COLUMN turn_index INT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_transcript_turns_session_turn_index 
ON public.transcript_turns(session_id, turn_index);

-- 2. Durable Evaluation Queue (evaluation_jobs)
CREATE TABLE IF NOT EXISTS public.evaluation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    batch_index INT NOT NULL DEFAULT 1,
    start_turn_index INT NOT NULL,
    end_turn_index INT NOT NULL,
    turn_ids UUID[] NOT NULL DEFAULT '{}',
    trigger_reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'SUPERSEDED')),
    locked_at TIMESTAMP WITH TIME ZONE,
    payload JSONB,
    result JSONB,
    error_message TEXT,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_eval_jobs_status_created 
ON public.evaluation_jobs(status, created_at);

CREATE INDEX IF NOT EXISTS idx_eval_jobs_session_id 
ON public.evaluation_jobs(session_id);

-- 3. Accumulated Evaluation Signals
CREATE TABLE IF NOT EXISTS public.evaluation_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    job_id UUID REFERENCES public.evaluation_jobs(id) ON DELETE SET NULL,
    turn_start_index INT NOT NULL,
    turn_end_index INT NOT NULL,
    competency_observations JSONB NOT NULL DEFAULT '[]'::jsonb,
    competency_assessments JSONB NOT NULL DEFAULT '{}'::jsonb,
    strategic_probes JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eval_signals_session_id 
ON public.evaluation_signals(session_id, created_at);

-- 4. Immutable Synthesis Snapshots
CREATE TABLE IF NOT EXISTS public.synthesis_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    transcript_version INT NOT NULL DEFAULT 1,
    turn_ids UUID[] NOT NULL DEFAULT '{}',
    turn_labels TEXT[] NOT NULL DEFAULT '{}',
    code_snapshot_ids UUID[] NOT NULL DEFAULT '{}',
    signal_ids UUID[] NOT NULL DEFAULT '{}',
    blueprint_version TEXT NOT NULL DEFAULT 'v1',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_synthesis_snapshots_session_id 
ON public.synthesis_snapshots(session_id);

-- 5. Extend interview_evaluations with snapshot reference, audit trail, and score breakdown
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'interview_evaluations' 
        AND column_name = 'snapshot_id'
    ) THEN
        ALTER TABLE public.interview_evaluations 
        ADD COLUMN snapshot_id UUID REFERENCES public.synthesis_snapshots(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'interview_evaluations' 
        AND column_name = 'audit_trail'
    ) THEN
        ALTER TABLE public.interview_evaluations 
        ADD COLUMN audit_trail JSONB NOT NULL DEFAULT '[]'::jsonb;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'interview_evaluations' 
        AND column_name = 'score_breakdown'
    ) THEN
        ALTER TABLE public.interview_evaluations 
        ADD COLUMN score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb;
    END IF;
END $$;
