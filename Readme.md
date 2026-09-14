AI Interview Platform — Project Document
1. Concept
A voice-driven AI interviewer that conducts full technical interviews end to end:

Reads a candidate's resume and grounds its questions in it (specific projects, claimed skills, employment gaps)
Asks technical and behavioral questions in natural conversation, using a realtime speech-to-speech model
Runs a code review / optimization segment — shows the candidate a snippet, asks what's wrong with it or how to improve it, and can react to live edits
Produces a structured, rubric-based evaluation for recruiters afterward, not just a transcript
2. System Architecture
Five components, each with a single responsibility:
ComponentResponsibilityResume parserResume file → structured CandidateProfile (skills, work history, projects, inferred gaps)Interview orchestratorOwns the interview state machine and stage transitions. Deterministic — the voice model requests transitions, orchestrator approves or rejects themRealtime voice sessionWraps the speech-to-speech API (OpenAI Realtime or Gemini Live). Exposes tools the model can call: get_current_code_state, advance_stage, flag_answer_for_reviewCode editor stateDebounced sync of the candidate's code editor into the voice session as text context — not raw audio, not every keystrokeAsync evaluation pipelineScores answers against rubrics after the interview turn, using a separate (non-realtime) LLM judge call — keeps the live conversation fast and keeps scoring consistentKey design decision: the realtime model never does live scoring or decides stage order on its own. It converses; the orchestrator and evaluator, both deterministic/async code paths, own correctness and fairness.

### 1. Configurable & Customizable Interviews
- **Tailored Assessments**: Design interviews customized to specific job roles, technical/soft skill requirements, and difficulty levels.
- **Flexible Setup**: Adjust question sets, evaluation criteria, duration, and structure to fit your organization's hiring process.
### 2. 6-Digit Room Access Code
- **Automatic Code Generation**: Upon interview creation, the system automatically generates a unique **6-digit access code**.
- **Secure Room Entry**: Interviewers and candidates use this 6-digit code to enter the designated interview room seamlessly.
### 3. Comprehensive Recruiter Reports & Analytics
- **Candidate Scoring & Metrics**: Detailed breakdown of candidate performance and scores across evaluated competencies.
- **Full Interview Transcripts**: Complete, line-by-line transcript recording the entire interview process.
- **Detailed Score Explanations**: In-depth explanations and rationale accompanying every score to provide clear, actionable insights for recruiters.


3. Backend Structure (FastAPI)
backend/
├── app/
│   ├── main.py
│   ├── core/                  # config, security, logging
│   ├── api/v1/routers/        # resumes, interviews, sessions, code, evaluations
│   ├── orchestrator/
│   │   ├── fsm.py              # stage transition rules (built)
│   │   ├── session_manager.py
│   │   ├── tool_registry.py
│   │   └── question_selector.py
│   ├── realtime/
│   │   ├── client.py           # wraps the realtime API
│   │   ├── bridge.py           # ws bridging frontend audio <-> realtime API
│   │   └── tool_handlers.py
│   ├── resume/                # parser.py, extractor.py
│   ├── code_sync/              # debouncer.py, diff.py
│   ├── evaluation/             # rubrics.py, scorer.py, aggregator.py
│   ├── workers/                # background jobs (celery/arq)
│   ├── models/
│   │   ├── db/                 # SQLAlchemy models
│   │   └── schemas.py           # Pydantic domain models (built)
│   ├── db/                     # session.py, alembic migrations
│   └── services/                # llm_client.py, storage.py, redis_client.py
└── tests/
Two files are already sketched:

app/models/schemas.py — CandidateProfile, InterviewStage, Question, InterviewSession, TranscriptTurn, CodeSnapshot, QuestionScore, InterviewEvaluation
app/orchestrator/fsm.py — the stage transition table, plus minimum-questions-per-stage guards so the model can't rush through a stage on a quiet candidate
4. Interview Flow
INTRO → RESUME_DEEP_DIVE → TECHNICAL_QA → CODING → BEHAVIORAL → WRAP_UP → COMPLETED
Forward-only, no skipping. Each stage (except INTRO/WRAP_UP) has a minimum question count before advance_stage is honored. CANCELLED is reachable from any stage.

5. Frontend UX
Google Meet-style call interface:

Default (discussion) view: candidate's camera as the main tile, a small "AI interviewer" audio tile in a corner
Coding stage: the IDE takes over the main tile — functionally identical to a screen share starting — and the candidate's video shrinks to a small picture-in-picture tile. When CODING ends, it reverses automatically
The layout state is driven by the same InterviewStage websocket event that drives the orchestrator and realtime tool availability — one event, two consumers (frontend layout + backend tool permissions)
Open question: keep the candidate's video live during coding (not just a static thumbnail) — recommended, since real interviewers watch candidates think while they talk through code
6. Tech Stack
Frontend: Vue 3, Pinia, Monaco or CodeMirror for the code editor
Backend: FastAPI, SQLAlchemy + Alembic, Redis (session state, debounce buffers), Celery or arq (async evaluation jobs)
Voice: Gemini Live API (speech-to-speech, native tool-calling mid-session)
Evaluation judge: separate LLM call, decoupled from the realtime model so it can use a different/stronger model without affecting conversation latency
7. Standout / Differentiating Features
Ideas beyond a standard "AI asks questions" interviewer — worth prioritizing a few of these as what actually differentiates the product:

Job-description-calibrated interviews. Feed a job posting in and have the orchestrator auto-adjust question difficulty, topic weighting, and rubric emphasis to that specific role, rather than a generic question bank. Since you already have a job-discovery pipeline in Orquesta with a role-intent interface, the same structured "role profile" concept could plug straight into question_selector.py here — parse a JD the way Orquesta parses job postings, and use it to seed the interview plan.
System-design whiteboard, not just code. A lot of real technical interviews need a diagram, not a code editor — architecture sketches, data flow, DB schema. You've already built a Konva-based infinite whiteboard with semantic-intent LLM output for Knovera's teaching engine; the same canvas + FSM pattern could become a second "shared surface" mode alongside the code editor, triggered the same way the IDE is.
Post-interview coaching report for the candidate, not just a recruiter scorecard — specific, constructive feedback on what to improve, in the same spirit as the "teach-back" feature you evaluated for Knovera. Turns a one-shot filter tool into something candidates get value from even when rejected, which is a real differentiator in a market where AI interviews are often experienced as adversarial.
Integrity signals without being invasive — tab-switch/paste-event detection during the coding segment, flagged to recruiters as a signal rather than an automatic disqualifier.
Adaptive difficulty within a session — if a candidate is breezing through technical questions, escalate difficulty in real time rather than working through a fixed list; if they're struggling, don't just keep drilling on the same gap.
Recruiter-side replay with synced transcript + code timeline — click any moment in the evaluation report and jump straight to that point in the audio/code history, rather than scrubbing a raw recording.
Bias/consistency auditing across candidates — track question coverage and scoring distribution per rubric across all candidates for a role, so recruiters can catch a stage that's systematically harder or easier than intended.
Worth being deliberate about which 1-2 of these become the actual pitch, rather than building all of them — the job-description calibration and the coaching report are the two that most directly leverage infrastructure you've already built elsewhere.

8. Open Questions
Candidate video during coding stage: live PiP 
How much of the evaluation rubric per-role configurable