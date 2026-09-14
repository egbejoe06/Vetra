-- ================================================================
-- Migration 002: Interview System Schema (Updated Architecture)
-- Vetra AI Technical Interviewer
-- ================================================================

-- 1. Create Enums for Interview Stages, Speakers, Statuses, and Artifacts
DO $$ BEGIN
    CREATE TYPE interview_stage AS ENUM (
        'INTRO',
        'RESUME_DEEP_DIVE',
        'TECHNICAL_QA',
        'TECHNICAL_EXERCISE',
        'BEHAVIORAL',
        'WRAP_UP',
        'COMPLETED',
        'CANCELLED'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE transcript_speaker AS ENUM (
        'INTERVIEWER',
        'CANDIDATE',
        'SYSTEM'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE interview_status AS ENUM (
        'SCHEDULED',
        'ACTIVE',
        'COMPLETED',
        'CANCELLED'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE candidate_recommendation AS ENUM (
        'STRONG_HIRE',
        'HIRE',
        'LEAN_HIRE',
        'LEAN_REJECT',
        'REJECT'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE technical_problem_type AS ENUM (
        'CODE_REVIEW',
        'BUG_INVESTIGATION',
        'DEBUGGING',
        'IMPLEMENTATION',
        'PERFORMANCE',
        'REFACTORING',
        'SYSTEM_DESIGN',
        'ARCHITECTURE_REVIEW',
        'API_DESIGN',
        'CODEBASE_DISCUSSION',
        'SECURITY_REVIEW',
        'DATA_STRUCTURES_AND_ALGORITHMS',
        'ALTERNATIVE_IMPLEMENTATION'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE artifact_type AS ENUM (
        'CODEBASE',
        'CODE_SNIPPET',
        'SYSTEM_DIAGRAM',
        'ARCHITECTURE',
        'DATA_MODEL',
        'EVALUATION_BLUEPRINT'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2. Create public.interviews Table (Configured strictly by Recruiters)
-- room_code is numeric-only, 6 to 8 digits, generated server-side by FastAPI
CREATE TABLE IF NOT EXISTS public.interviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recruiter_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    job_id UUID,
    job_title TEXT NOT NULL,
    years_of_experience INT NOT NULL DEFAULT 0,
    room_code VARCHAR(8) UNIQUE NOT NULL CHECK (room_code ~ '^[0-9]{6,8}$'),
    status interview_status NOT NULL DEFAULT 'SCHEDULED',
    current_stage interview_stage NOT NULL DEFAULT 'INTRO',
    duration_minutes INT NOT NULL DEFAULT 10,
    questions_count INT NOT NULL DEFAULT 10,
    technical_focus TEXT[] DEFAULT '{}',
    behavioral_focus TEXT[] DEFAULT '{}',
    instructions TEXT,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 3. Create public.interview_sessions Table (Candidate Active Room Sessions)
CREATE TABLE IF NOT EXISTS public.interview_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interview_id UUID NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    candidate_name TEXT NOT NULL,
    candidate_email TEXT NOT NULL,
    room_code VARCHAR(8) NOT NULL,
    current_stage interview_stage NOT NULL DEFAULT 'INTRO',
    status interview_status NOT NULL DEFAULT 'SCHEDULED',
    started_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. Create public.technical_problems Table (Exercises/Challenges provided to Candidate)
CREATE TABLE IF NOT EXISTS public.technical_problems (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    interview_id UUID REFERENCES public.interviews(id) ON DELETE CASCADE,
    problem_type technical_problem_type NOT NULL,
    title TEXT NOT NULL,
    prompt_question TEXT NOT NULL,
    context TEXT,
    code_files JSONB DEFAULT '[]'::jsonb NOT NULL,
    key_discussion_points TEXT[] DEFAULT '{}',
    expected_solution_summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 5. Create public.interview_artifacts Table (Sample codebases, diagrams, architecture files)
-- Artifact content holds sample codebases (e.g. {"files": [{"path": "...", "content": "..."}]}) or diagrams
CREATE TABLE IF NOT EXISTS public.interview_artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    problem_id UUID REFERENCES public.technical_problems(id) ON DELETE SET NULL,
    artifact_type artifact_type NOT NULL,
    title TEXT NOT NULL,
    content JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 6. Create public.candidate_responses Table (Structured Problem -> Candidate Answer -> Evaluation)
CREATE TABLE IF NOT EXISTS public.candidate_responses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    problem_id UUID REFERENCES public.technical_problems(id) ON DELETE SET NULL,
    stage interview_stage NOT NULL DEFAULT 'TECHNICAL_EXERCISE',
    question_text TEXT NOT NULL,
    candidate_answer TEXT NOT NULL,
    evaluation_notes TEXT,
    score NUMERIC(3, 1) CHECK (score >= 1.0 AND score <= 5.0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 7. Create public.transcript_turns Table (Line-by-line dialogue history)
CREATE TABLE IF NOT EXISTS public.transcript_turns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    speaker transcript_speaker NOT NULL,
    stage interview_stage NOT NULL,
    content TEXT NOT NULL,
    audio_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 8. Create public.interview_evaluations Table (Post-interview comprehensive scoring)
CREATE TABLE IF NOT EXISTS public.interview_evaluations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID UNIQUE NOT NULL REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    interview_id UUID NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    candidate_name TEXT NOT NULL,
    overall_score NUMERIC(3, 1) NOT NULL, -- e.g. 8.5 out of 10.0
    recommendation candidate_recommendation NOT NULL,
    summary TEXT NOT NULL,
    key_strengths TEXT[] DEFAULT '{}',
    key_weaknesses TEXT[] DEFAULT '{}',
    rubric_scores JSONB DEFAULT '[]'::jsonb NOT NULL,
    question_scores JSONB DEFAULT '[]'::jsonb NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 9. Create Comprehensive Indexes for High-Speed Lookups & Foreign Keys
CREATE INDEX IF NOT EXISTS idx_interviews_room_code ON public.interviews(room_code);
CREATE INDEX IF NOT EXISTS idx_interviews_recruiter_id ON public.interviews(recruiter_id);

CREATE INDEX IF NOT EXISTS idx_interview_sessions_room_code ON public.interview_sessions(room_code);
CREATE INDEX IF NOT EXISTS idx_interview_sessions_interview_id ON public.interview_sessions(interview_id);
CREATE INDEX IF NOT EXISTS idx_interview_sessions_candidate_id ON public.interview_sessions(candidate_id);

CREATE INDEX IF NOT EXISTS idx_technical_problems_interview_id ON public.technical_problems(interview_id);
CREATE INDEX IF NOT EXISTS idx_technical_problems_session_id ON public.technical_problems(session_id);

CREATE INDEX IF NOT EXISTS idx_interview_artifacts_session_id ON public.interview_artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_interview_artifacts_problem_id ON public.interview_artifacts(problem_id);

CREATE INDEX IF NOT EXISTS idx_candidate_responses_session_id ON public.candidate_responses(session_id);
CREATE INDEX IF NOT EXISTS idx_candidate_responses_problem_id ON public.candidate_responses(problem_id);

CREATE INDEX IF NOT EXISTS idx_transcript_turns_session_id ON public.transcript_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_interview_evaluations_session_id ON public.interview_evaluations(session_id);
CREATE INDEX IF NOT EXISTS idx_interview_evaluations_interview_id ON public.interview_evaluations(interview_id);

-- 10. Enable Row Level Security (RLS)
ALTER TABLE public.interviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interview_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.technical_problems ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interview_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidate_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transcript_turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interview_evaluations ENABLE ROW LEVEL SECURITY;

-- 11. Strict Row Level Security Policies
-- (Notice: Interviews table is NOT exposed to arbitrary candidates. Candidates join via FastAPI POST /interviews/join)
CREATE POLICY "Recruiters can manage own interviews"
    ON public.interviews
    FOR ALL
    USING (auth.uid() = recruiter_id);

-- Sessions: Candidates can view their own session; Recruiters can view sessions under their interviews
CREATE POLICY "Users can view relevant sessions"
    ON public.interview_sessions
    FOR SELECT
    USING (
        auth.uid() = candidate_id 
        OR EXISTS (
            SELECT 1 FROM public.interviews i 
            WHERE i.id = interview_sessions.interview_id 
            AND i.recruiter_id = auth.uid()
        )
    );

-- Technical Problems: Visible to session participant or recruiter
CREATE POLICY "View problems for session"
    ON public.technical_problems
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.interview_sessions s
            WHERE s.id = technical_problems.session_id
            AND (
                s.candidate_id = auth.uid()
                OR EXISTS (
                    SELECT 1 FROM public.interviews i 
                    WHERE i.id = s.interview_id AND i.recruiter_id = auth.uid()
                )
            )
        )
    );

-- Artifacts: Visible to candidate in session or recruiter
CREATE POLICY "View artifacts for session"
    ON public.interview_artifacts
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.interview_sessions s
            WHERE s.id = interview_artifacts.session_id
            AND (
                s.candidate_id = auth.uid()
                OR EXISTS (
                    SELECT 1 FROM public.interviews i 
                    WHERE i.id = s.interview_id AND i.recruiter_id = auth.uid()
                )
            )
        )
    );

-- Candidate Responses: Visible to candidate in session or recruiter
CREATE POLICY "View candidate responses for session"
    ON public.candidate_responses
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.interview_sessions s
            WHERE s.id = candidate_responses.session_id
            AND (
                s.candidate_id = auth.uid()
                OR EXISTS (
                    SELECT 1 FROM public.interviews i 
                    WHERE i.id = s.interview_id AND i.recruiter_id = auth.uid()
                )
            )
        )
    );

-- Transcript Turns: Visible to candidate in session or recruiter
CREATE POLICY "View transcript turns for session"
    ON public.transcript_turns
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.interview_sessions s
            WHERE s.id = transcript_turns.session_id
            AND (
                s.candidate_id = auth.uid()
                OR EXISTS (
                    SELECT 1 FROM public.interviews i 
                    WHERE i.id = s.interview_id AND i.recruiter_id = auth.uid()
                )
            )
        )
    );

-- Evaluations: Recruiters can view evaluations for their interviews; Candidates can view their own
CREATE POLICY "Recruiters and candidates view evaluations"
    ON public.interview_evaluations
    FOR SELECT
    USING (
        auth.uid() = candidate_id 
        OR EXISTS (
            SELECT 1 FROM public.interviews i 
            WHERE i.id = interview_evaluations.interview_id 
            AND i.recruiter_id = auth.uid()
        )
    );
