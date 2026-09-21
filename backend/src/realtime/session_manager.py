import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import WebSocket, WebSocketDisconnect

from src.db.supabase import supabase
from src.models.enums import InterviewStage, TranscriptSpeaker, TurnCompletionStatus
from src.orchestrator.engine import interview_orchestrator
from src.realtime.audio_bridge import base64_to_pcm
from src.realtime.event_router import RealtimeEventRouter
from src.realtime.gemini_live import GeminiLiveSession
from src.realtime.schemas import (
    ClientAudioMessage,
    ClientEndMessage,
    ClientMessage,
    ClientPingMessage,
    ClientStartMessage,
    ClientTextMessage,
)
from src.service.transcript import transcript_service

logger = logging.getLogger("vetra.realtime.session_manager")


class RealtimeSessionManager:
    """Manages the full lifecycle of an active interview session, bridging the candidate's
    WebSocket connection with the Google GenAI Live session (gemini-3.1-flash-live-preview).
    """

    def __init__(self, session_id: str, websocket: WebSocket):
        self.session_id = session_id
        self.websocket = websocket
        self.gemini_session: Optional[GeminiLiveSession] = None
        self.is_running = False
        self._reconnecting = False
        self._system_instruction: Optional[str] = None
        self._candidate_name: str = "Candidate"
        self._interview_id: Optional[str] = None
        self._has_started: bool = False

    async def initialize(self) -> None:
        """Fetch session and candidate metadata from Supabase and LangGraph state."""
        # Query Supabase for candidate profile & interview context
        resumption_handle: Optional[str] = None

        if supabase:
            try:
                res = supabase.table("interview_sessions").select("*").eq("id", str(self.session_id)).limit(1).execute()
                if res.data and len(res.data) > 0:
                    sess = res.data[0]
                    self._candidate_name = sess.get("candidate_name", "Candidate")
                    self._interview_id = sess.get("interview_id")
                    resumption_handle = sess.get("resumption_handle")

                    # Mark session status ACTIVE if not already
                    if sess.get("status") == "SCHEDULED":
                        now = datetime.now(timezone.utc).isoformat()
                        supabase.table("interview_sessions").update({
                            "status": "ACTIVE",
                            "started_at": now,
                        }).eq("id", str(self.session_id)).execute()

            except Exception as err:
                logger.warning(f"Failed to query Supabase session for {self.session_id}: {err}")

        # Initialize LangGraph Orchestrator session if not active
        try:
            state = await interview_orchestrator.get_state(self.session_id)
            if not state:
                await interview_orchestrator.initialize_session(
                    session_id=self.session_id,
                    interview_id=self._interview_id or str(self.session_id),
                    candidate_name=self._candidate_name,
                    initial_stage="INTRO",
                )
        except Exception as err:
            logger.warning(f"Error initializing LangGraph session state: {err}")

        job_title = "Software Engineer"
        target_seniority = 3
        job_description = ""
        recruiter_instructions = ""
        evaluation_criteria = ""
        technical_focus = []
        behavioral_focus = []
        eval_blueprint: Dict[str, Any] = {}
        intro_questions_formatted = ""
        resume_questions_formatted = ""
        technical_questions_formatted = ""
        behavioral_questions_formatted = ""
        candidate_work_history_formatted = ""

        if supabase and self._interview_id:
            try:
                i_res = (
                    supabase.table("interviews")
                    .select("*")
                    .eq("id", str(self._interview_id))
                    .limit(1)
                    .execute()
                )
                if i_res.data and len(i_res.data) > 0:
                    i_row = i_res.data[0]
                    job_title = i_row.get("job_title") or job_title
                    target_seniority = i_row.get("years_of_experience") if i_row.get("years_of_experience") is not None else target_seniority
                    job_description = i_row.get("description") or ""
                    recruiter_instructions = i_row.get("instructions") or ""
                    evaluation_criteria = i_row.get("evaluation_criteria") or ""
                    technical_focus = i_row.get("technical_focus") or []
                    behavioral_focus = i_row.get("behavioral_focus") or []
            except Exception as err:
                logger.warning(f"Failed to query interview template for {self._interview_id}: {err}")

            try:
                # Query most recent EVALUATION_BLUEPRINT artifact
                art_res = (
                    supabase.table("interview_artifacts")
                    .select("*")
                    .eq("artifact_type", "EVALUATION_BLUEPRINT")
                    .order("created_at", desc=True)
                    .limit(5)
                    .execute()
                )
                if art_res.data:
                    for art in art_res.data:
                        content = art.get("content") or {}
                        if art.get("session_id") == str(self.session_id) or content.get("interview_id") == str(self._interview_id):
                            eval_blueprint = content
                            break
                        prob_id = art.get("problem_id")
                        if prob_id:
                            p_res = (
                                supabase.table("technical_problems")
                                .select("id")
                                .eq("id", prob_id)
                                .eq("interview_id", str(self._interview_id))
                                .execute()
                            )
                            if p_res.data:
                                eval_blueprint = content
                                break
                    # Do not fall back to an unrelated interview's blueprint!
                    # If no blueprint exists for this session or interview, eval_blueprint remains empty.

                # If no technical problem exists yet for this specific session, trigger background generation task
                try:
                    prob_check = (
                        supabase.table("technical_problems")
                        .select("id")
                        .eq("session_id", str(self.session_id))
                        .limit(1)
                        .execute()
                    )
                    if not prob_check.data or len(prob_check.data) == 0:
                        logger.info(
                            f"[SessionManager] No technical problem found for session {self.session_id}. "
                            "Triggering in-interview background exercise generation..."
                        )
                        from src.service.planner import planner_service
                        asyncio.create_task(
                            asyncio.to_thread(
                                planner_service.generate_and_persist_exercises,
                                interview_id=self._interview_id,
                                session_id=self.session_id,
                            )
                        )
                except Exception as bg_trig_err:
                    logger.warning(f"Could not trigger background exercise generation: {bg_trig_err}")

                if eval_blueprint:
                    work_exp_list = eval_blueprint.get("work_experience") or []
                    if work_exp_list:
                        candidate_work_history_formatted = "\n".join(
                            f"  - {w.get('role', 'Engineer')} at {w.get('company', 'Company')}: {'; '.join(w.get('responsibilities', [])[:3])}"
                            for w in work_exp_list
                        )
                    intro_qs = eval_blueprint.get("intro_questions") or []
                    if intro_qs:
                        intro_questions_formatted = "\n".join(
                            f"  - Q{i+1}: {q.get('question_text', '')}"
                            for i, q in enumerate(intro_qs[:2])
                        )
                    resume_qs = [
                        q for q in eval_blueprint.get("questions", [])
                        if q.get("stage") == "RESUME_DEEP_DIVE" or q.get("question_type") in ("RESUME_DEEP_DIVE", "PROJECT_DEEP_DIVE", "EXPERIENCE")
                    ]
                    if resume_qs:
                        resume_questions_formatted = "\n".join(
                            f"  - [{q.get('competency', 'Experience')}]: {q.get('question_text', '')}\n    Evidence: {'; '.join(q.get('candidate_evidence', []))}"
                            for q in resume_qs[:3]
                        )
                    technical_qs = [
                        q for q in eval_blueprint.get("questions", [])
                        if q.get("stage") == "TECHNICAL_QA" or (
                            q.get("stage") != "RESUME_DEEP_DIVE"
                            and q.get("question_type") not in ("RESUME_DEEP_DIVE", "PROJECT_DEEP_DIVE", "EXPERIENCE", "BEHAVIORAL")
                        )
                    ]
                    if technical_qs:
                        technical_questions_formatted = "\n".join(
                            f"  - [{q.get('competency', 'Technical')}]: {q.get('question_text', '')}\n    Key Points: {'; '.join(q.get('expected_key_points', [])[:3])}"
                            for q in technical_qs[:3]
                        )
                    beh_qs = (
                        eval_blueprint.get("behavioral_questions")
                        or [q for q in eval_blueprint.get("questions", []) if q.get("stage") == "BEHAVIORAL" or q.get("question_type") == "BEHAVIORAL"]
                    )
                    if beh_qs:
                        behavioral_questions_formatted = "\n".join(
                            f"  - Q{i+1} [{q.get('competency', 'Ownership & Leadership')}]: {q.get('question_text', '')}"
                            for i, q in enumerate(beh_qs[:2])
                        )
            except Exception as art_err:
                logger.warning(f"Failed to query evaluation blueprint for {self.session_id}: {art_err}")

        # Construct persona instructions with strict stage pacing & question limits
        seniority_label = (
            f"{target_seniority}+ YOE (Senior / Staff / Lead)" if target_seniority >= 5
            else f"{target_seniority} YOE (Mid-Level)" if target_seniority >= 3
            else f"{target_seniority} YOE (Junior / Entry)"
        )

        self._system_instruction = (
            f"You are Vetra, an expert, encouraging, and highly technical AI Interviewer conducting a live voice interview with {self._candidate_name}.\n"
            f"TARGET ROLE: {job_title} | SENIORITY LEVEL: {seniority_label}\n"
            + (f"JOB DESCRIPTION & CONTEXT:\n{job_description}\n\n" if job_description else "")
            + (f"TECHNICAL FOCUS SKILLS:\n{', '.join(technical_focus)}\n\n" if technical_focus else "")
            + (f"BEHAVIORAL DIMENSIONS:\n{', '.join(behavioral_focus)}\n\n" if behavioral_focus else "")
            + (f"QUESTIONING & PROBING FOCUS (What the recruiter wants you to ask about):\n{recruiter_instructions}\n\n" if recruiter_instructions else "")
            + (f"EVALUATION CRITERIA & SCORING PRIORITIES (How the candidate will be evaluated):\n{evaluation_criteria}\n\n" if evaluation_criteria else "")
            + f"CRITICAL FACTUAL GROUNDING & ZERO-HALLUCINATION RULES (HIGHEST PRIORITY):\n"
            f"1. GROUND TRUTH ONLY: You may ONLY state a candidate-specific fact, architecture, or metric if it exists in CandidateProfile, ResumeEvidence, ProjectEvidence, or the candidate's own spoken answers in this conversation.\n"
            f"2. ZERO FABRICATION: Only state a candidate-specific fact, architecture name, metric, or pipeline detail if it literally appears in the candidate data injected into this instruction (CANDIDATE WORK EXPERIENCE, TAILORED QUESTIONS sections below) or in the candidate's own spoken words in this conversation. If a detail is not in that data, do not mention it — ask an exploratory question instead.\n"
            f"3. ONE CONCEPT PER QUESTION: Ask exactly one focused question per turn. Do not combine unrelated technical concepts in a single sentence.\n"
            f"4. ROLE-APPROPRIATE QUESTIONS: Ask practical questions appropriate for this specific job description and tech stack. Do not assume distributed infrastructure scale unless the job description or candidate profile explicitly mentions it.\n"
            f"5. EXPLORATORY QUESTIONS: When asking about candidate projects, ask an open EXPLORATORY question (e.g. 'Could you walk me through the architecture of your project and what specific components you owned?') rather than asserting unverified technical claims.\n"
            f"6. NEVER imply the candidate claimed something they did not claim.\n\n"
            f"CRITICAL TOOL CALLING & SILENT EXECUTION RULES (MANDATORY):\n"
            f"1. SILENT TOOL CALLS: Tool calls (`get_interviewer_state`, `request_stage_transition`, `present_problem`, `get_workspace_context`) are STRICTLY SILENT, INTERNAL SDK OPERATIONS.\n"
            f"2. NEVER SPEAK TOOL CALLS: You must NEVER vocalize, speak, or output tool call syntax, function names, parameters, or code aloud to the candidate.\n"
            f"3. NEVER say or write 'call:request_stage_transition', 'call:', or JSON in your speech or text responses. Doing so is an architectural violation.\n"
            f"4. NATURAL TRANSITION BRIDGES: When transitioning stages, simply say a natural, human conversational sentence to the candidate (e.g. 'Thanks for walking me through that. I\\'d now like to explore how you approach ambiguity.') and trigger the tool silently via native function calling in the background.\n\n"
            f"RESPONSE QUALITY & CANDIDATE CADENCE GATE:\n"
            f"1. GREETINGS & SHORT RESPONSES: If the candidate says 'Hello', asks 'Can you hear me?', or gives a 1-word greeting, do NOT plunge immediately into deep technical grilling or advance stages. Acknowledge warmly and naturally (e.g. 'Yes, I can hear you clearly! How are you doing today?') and establish clear audio connection.\n"
            f"2. VAGUE OR EVASIVE ANSWERS: If a candidate gives an unclear, evasive, or 1-sentence superficial response, do NOT immediately advance to the next topic or stage. Ask a targeted clarifying question (e.g. 'Could you elaborate on how that was handled under high load?') to gather sufficient evidence first.\n\n"
            f"CRITICAL VOICE CADENCE & BREVITY RULES (HIGHEST PRIORITY - STRICT ENFORCEMENT):\n"
            f"1. MAXIMUM 1 TO 2 SENTENCES PER TURN: You must NEVER speak more than 1 or 2 concise sentences at a time. Under no circumstances should you speak in long paragraphs, monologue, or lecture.\n"
            f"2. EXACTLY ONE QUESTION PER TURN: Ask only ONE clear, focused question per turn. NEVER combine multiple questions, sub-questions, or compound clauses. Ask ONE thing, then immediately stop speaking.\n"
            f"3. NATURAL PING-PONG CADENCE: When the candidate finishes speaking, briefly acknowledge their answer in 3 to 5 words (e.g. 'That makes sense.', 'Got it.', 'Understood.', 'Thanks for walking me through that.'), ask your single follow-up question, and immediately yield the floor.\n"
            f"4. ZERO AGENDA / DURATION MONOLOGUES: NEVER list out the entire interview agenda, 45-50 minute duration, or stage breakdown in voice. Keep greetings and transitions short and natural.\n\n"
            f"CORE OPERATIONAL ARCHITECTURE & LANGGRAPH AUTHORITY:\n"
            f"You are the voice of Vetra. The backend LangGraph orchestrator and Kimi Evaluator govern interview state, competency coverage, and stage transitions.\n"
            f"1. You do not independently decide whether an interview stage is complete.\n"
            f"2. You do not transition stages unless authorized by the orchestration system.\n"
            f"3. Every 1-2 turns, call `get_interviewer_state` silently to receive dynamic guidance and competency updates.\n\n"
            f"STRICT STAGE TRANSITION GUARDRAILS (NEVER PRE-ANNOUNCE, NEVER LOOP):\n"
            f"- ZERO PRE-ANNOUNCEMENT: NEVER verbally announce you are moving to the next stage BEFORE calling `get_interviewer_state` and confirming `transition_allowed == True` or `should_transition_now == True`.\n"
            f"- When `transition_allowed == True` or `should_transition_now == True`: State a brief 1-sentence conversational bridge and silently invoke `request_stage_transition` immediately. Do NOT ask any more questions, follow-ups, or rephrasings in this stage!\n"
            f"- If `transition_allowed == False`: Ask the next planned question from the tailored questions bank below (or at most one brief follow-up if still within question budget).\n"
            f"- If `request_stage_transition` returns `allowed: false`: Pivot naturally to the next planned question without apologizing or backtracking.\n\n"
            f"COMPETENCY COVERAGE, ANTI-REPETITION & ANTI-LOOP RULES (HIGHEST PRIORITY):\n"
            f"1. ANCHOR TO PLANNED QUESTIONS: In every stage, your primary questions MUST come sequentially from the TAILORED QUESTIONS sections below (e.g. Q1, then Q2). Do NOT discard planned questions for dynamic follow-ups.\n"
            f"2. AT MOST ONE FOLLOW-UP PROBE PER QUESTION: If a candidate's answer has an interesting gap, you may ask AT MOST ONE brief follow-up probe (from `recommended_probe`). Once the candidate answers that follow-up, you MUST move on to the next planned question or transition stages. NEVER ask a second follow-up on the same topic.\n"
            f"3. ZERO REPHRASING / ZERO LOOPING (MANDATORY): NEVER ask the candidate to 'rephrase', 'explain again', or 'clarify what you meant earlier'. NEVER ask a similar version of a question you already asked. If the candidate gave a short or partial answer, ACCEPT IT, evaluate it as is, and MOVE FORWARD.\n"
            f"4. DO NOT REVISIT COVERED TOPICS: If a competency is listed in `competencies_covered`, DO NOT ask another question on that topic!\n\n"
            f"STRICT INTERVIEW STAGE PACING & PROGRESSION (1-2 SENTENCES PER TURN):\n"
            f"1. MANDATORY FULL STAGE PROGRESSION (ALL 6 STAGES MUST BE CONDUCTED IN ORDER):\n"
            f"   - Stage 1: INTRO (EXACTLY 2 SHORT TURNS):\n"
            f"     1. Question 1 (Warm Greeting - MAX 2 SHORT SENTENCES):\n"
            f"        Say: 'Hi {self._candidate_name}, welcome to Vetra! I\\'m Vetra, and I\\'ll be your interviewer today for the {job_title} role. How are you doing today?' Then STOP and wait for their answer.\n"
            f"     2. Question 2 (Initial Role Alignment - MAX 2 SHORT SENTENCES):\n"
            f"        After they reply, acknowledge briefly and ask ONE direct question: 'Glad to hear that. To kick off, could you briefly walk me through what you\\'ve been building recently?' Then STOP and wait for their answer.\n"
            f"     * After Q2, check `get_interviewer_state`. When `transition_allowed == True`, silently invoke `request_stage_transition` with target_stage='RESUME_DEEP_DIVE'.\n"
            f"   - Stage 2: RESUME_DEEP_DIVE (EXACTLY 2-3 QUESTIONS, ONE AT A TIME, MAX 2 SENTENCES EACH):\n"
            f"     * Ask questions from TAILORED RESUME, WORK EXPERIENCE & PROJECT QUESTIONS below. Check both past employment experience and projects.\n"
            f"     * At most 1 optional follow-up across this entire stage. Once 2-3 questions are asked, call `request_stage_transition` with target_stage='TECHNICAL_QA'.\n"
            f"   - Stage 3: TECHNICAL_QA (EXACTLY 2-3 QUESTIONS, ONE AT A TIME, MAX 2 SENTENCES EACH):\n"
            f"     * Ask ONE concise technical question at a time from TAILORED TECHNICAL Q&A QUESTIONS below.\n"
            f"     * At most 1 optional follow-up. NEVER exceed 3 questions (hard ceiling 4). As soon as `transition_allowed == True`, silently invoke `request_stage_transition` with target_stage='TECHNICAL_EXERCISE'.\n"
            f"   - Stage 4: TECHNICAL_EXERCISE (Interactive Codebase Walkthrough & Diagnostic Investigation):\n"
            f"     * When entering TECHNICAL_EXERCISE, IMMEDIATELY call `present_problem` silently.\n"
            f"     * STRICT VERBAL INTERACTION ONLY (NO CODE TYPING): There is ZERO code writing or typing in this interview! NEVER tell the candidate to 'type the code', 'write your fix in the editor', 'implement the solution', or wait in silence for them to type. The candidate's workspace is a read-only code viewer for inspection.\n"
            f"     * Verbally introduce the scenario in 1-2 short sentences using the symptoms described in the challenge. NEVER leak the root-cause label.\n"
            f"     * Direct the candidate to inspect the files on screen and talk through their thought process out loud. Discuss tradeoffs in 1-2 short turns.\n"
            f"     * Once discussed and `transition_allowed == True`, silently invoke `request_stage_transition` with target_stage='BEHAVIORAL'.\n"
            f"   - Stage 5: BEHAVIORAL (EXACTLY 2 QUESTIONS - ONE AT A TIME, MAX 2 SENTENCES EACH):\n"
            f"     * Ask ONE STAR behavioral question at a time from TAILORED BEHAVIORAL QUESTIONS below.\n"
            f"     * After 2 questions, silently invoke `request_stage_transition` with target_stage='WRAP_UP'.\n"
            f"   - Stage 6: WRAP_UP (CLOSING STAGE - MAX 2 SENTENCES PER TURN):\n"
            f"     * Ask: 'Do you have any questions for me about the team, role, or Vetra?' Answer concisely in 1-2 sentences.\n"
            f"     * Thank {self._candidate_name} warmly for their time and conclude the session.\n"
            f"2. DO NOT ASK ENDLESS QUESTIONS: Never exceed the maximum questions for any stage! As soon as minimum questions are answered or maximum is reached, transition immediately.\n"
            f"3. Check `get_interviewer_state` silently to verify `transition_allowed` and proceed swiftly through all stages."
        )

        if candidate_work_history_formatted:
            self._system_instruction += f"\n\nCANDIDATE WORK EXPERIENCE & EMPLOYMENT HISTORY (PROBE THIS IN RESUME_DEEP_DIVE):\n{candidate_work_history_formatted}"
        if intro_questions_formatted:
            self._system_instruction += f"\n\nTAILORED INTRODUCTORY QUESTIONS (ASK ONE AT A TIME, IN 1-2 SHORT SENTENCES):\n{intro_questions_formatted}"
        if resume_questions_formatted:
            self._system_instruction += f"\n\nTAILORED RESUME, WORK EXPERIENCE & PROJECT QUESTIONS (ASK ONE AT A TIME, IN 1-2 SHORT SENTENCES):\n{resume_questions_formatted}"
        if technical_questions_formatted:
            self._system_instruction += f"\n\nTAILORED TECHNICAL Q&A QUESTIONS (ASK ONE AT A TIME, IN 1-2 SHORT SENTENCES):\n{technical_questions_formatted}"
        if behavioral_questions_formatted:
            self._system_instruction += f"\n\nTAILORED BEHAVIORAL QUESTIONS (ASK ONE AT A TIME, IN 1-2 SHORT SENTENCES):\n{behavioral_questions_formatted}"

        # Setup Gemini Live Session with Supabase-persisted resumption handle
        try:
            await self._start_gemini_session(resumption_handle=resumption_handle)
        except Exception as err:
            if resumption_handle:
                logger.warning(
                    f"Failed to connect Gemini Live using resumption handle for session {self.session_id}: {err}. "
                    "Clearing stale handle in database and starting fresh session..."
                )
                self._clear_resumption_handle()
                await self._start_gemini_session(resumption_handle=None)
            else:
                raise

    def _clear_resumption_handle(self) -> None:
        """Clear expired or invalid resumption token in Supabase."""
        if not supabase:
            return
        try:
            now = datetime.now(timezone.utc).isoformat()
            supabase.table("interview_sessions").update({
                "resumption_handle": None,
                "resumption_updated_at": now,
            }).eq("id", str(self.session_id)).execute()
            logger.info(f"Cleared stale resumption handle for session {self.session_id} in Supabase")
        except Exception as err:
            logger.warning(f"Failed to clear resumption handle in Supabase for {self.session_id}: {err}")

    async def _start_gemini_session(self, resumption_handle: Optional[str] = None) -> None:
        """Create and connect the Gemini Live session wrapper."""
        if self.gemini_session:
            try:
                await self.gemini_session.close()
            except Exception:
                pass
            self.gemini_session = None

        self.gemini_session = GeminiLiveSession(
            session_id=self.session_id,
            system_instruction=self._system_instruction,
            voice_name="Kore",
            resumption_handle=resumption_handle,
            on_audio=self._handle_gemini_audio,
            on_interrupted=self._handle_gemini_interrupted,
            on_transcript=self._handle_gemini_transcript,
            on_turn_complete=self._handle_gemini_turn_complete,
            on_resumption_update=self._handle_gemini_resumption_update,
            on_go_away=self._handle_gemini_go_away,
            on_stage_update=self._handle_stage_update,
            on_problem_presented=self._handle_problem_presented,
            on_disconnect=self._handle_gemini_unexpected_disconnect,
        )

        await self.gemini_session.connect()
        logger.info(
            f"Gemini Live session connected for session {self.session_id} "
            f"(resumed={bool(resumption_handle)})"
        )

    # ==========================================================================
    # Downstream Callbacks from Gemini Live API
    # ==========================================================================

    async def _handle_gemini_audio(self, pcm_bytes: bytes) -> None:
        """Stream 24kHz native model audio chunk to candidate browser."""
        await RealtimeEventRouter.send_audio_chunk(self.websocket, pcm_bytes)

    async def _handle_gemini_interrupted(self) -> None:
        """Notify browser client to clear Web Audio playback queue on candidate barge-in."""
        # Commit pending interviewer buffer as INTERRUPTED so orchestrator tracks speech interruption
        interviewer_buf = transcript_service.get_current_buffer(self.session_id, TranscriptSpeaker.INTERVIEWER)
        if interviewer_buf and interviewer_buf.strip():
            await transcript_service.commit_turn(
                self.session_id,
                TranscriptSpeaker.INTERVIEWER,
                completion_status=TurnCompletionStatus.INTERRUPTED,
            )
        await RealtimeEventRouter.send_interruption(self.websocket)

    async def _handle_gemini_transcript(
        self, speaker: TranscriptSpeaker, text: str, is_final: bool = False
    ) -> None:
        """Stream transcription text to client and buffer for database persistence."""
        is_final = bool(is_final)
        # Strip any leaked internal tool call syntax before sending to client or buffer
        if speaker == TranscriptSpeaker.INTERVIEWER and self.gemini_session:
            text, _ = self.gemini_session._intercept_and_sanitize_tool_text(text)
            if not text:
                return

        transcript_service.append_transcript_fragment(self.session_id, speaker, text)
        await RealtimeEventRouter.send_transcript(
            self.websocket,
            speaker=speaker,
            text=text,
            is_final=is_final,
        )

        # If turn finished, commit to Supabase
        if is_final:
            turn = await transcript_service.commit_turn(self.session_id, speaker)
            if turn:
                await RealtimeEventRouter.send_transcript(
                    self.websocket,
                    speaker=speaker,
                    text=turn.content,
                    is_final=True,
                    stage=turn.stage,
                    turn_id=str(turn.id),
                )

    async def _handle_gemini_turn_complete(self, speaker: TranscriptSpeaker) -> None:
        """Commit dialogue turn to Supabase and send turn_complete event to browser."""
        # Only commit if uncommitted buffer remains (avoiding duplicate commit after is_final)
        buf = transcript_service.get_current_buffer(self.session_id, speaker)
        if buf and buf.strip():
            turn = await transcript_service.commit_turn(self.session_id, speaker)
            if turn:
                await RealtimeEventRouter.send_transcript(
                    self.websocket,
                    speaker=speaker,
                    text=turn.content,
                    is_final=True,
                    stage=turn.stage,
                    turn_id=str(turn.id),
                )
        await RealtimeEventRouter.send_turn_complete(self.websocket, speaker)

    async def _handle_gemini_resumption_update(self, handle: str) -> None:
        """Log that a new session resumption handle was recorded."""
        logger.debug(f"Session resumption handle updated for session {self.session_id}")

    async def _handle_gemini_go_away(self, time_left: Any) -> None:
        """Transparently reconnect upstream to Gemini Live before connection closes."""
        if self._reconnecting:
            return

        self._reconnecting = True
        logger.info(f"Proactively reconnecting Gemini Live session for {self.session_id} on GoAway...")
        try:
            await RealtimeEventRouter.send_session_status(
                self.websocket,
                session_id=self.session_id,
                status="reconnecting",
                message="Refreshing realtime audio bridge...",
            )

            old_session = self.gemini_session
            latest_handle = old_session.resumption_handle if old_session else None

            # Close old session
            if old_session:
                await old_session.close()

            # Re-establish upstream session using the latest valid handle
            try:
                await self._start_gemini_session(resumption_handle=latest_handle)
            except Exception as resume_err:
                if latest_handle:
                    logger.warning(
                        f"Failed to reconnect Gemini Live using handle on GoAway for {self.session_id}: {resume_err}. "
                        "Clearing handle and falling back to fresh session..."
                    )
                    self._clear_resumption_handle()
                    await self._start_gemini_session(resumption_handle=None)
                else:
                    raise resume_err

            await RealtimeEventRouter.send_session_status(
                self.websocket,
                session_id=self.session_id,
                status="resumed",
                resumed=True,
                message="Realtime bridge reconnected.",
            )
        except Exception as err:
            logger.error(f"Failed to reconnect Gemini Live session: {err}", exc_info=True)
            await RealtimeEventRouter.send_error(
                self.websocket,
                message="Realtime connection refresh failed.",
                code="RECONNECT_FAILED",
            )
        finally:
            self._reconnecting = False

    async def _handle_gemini_unexpected_disconnect(self, error: Optional[Exception] = None) -> None:
        """Transparently reconnect to Gemini Live using resumption_handle when WebSocket drops unexpectedly."""
        if self._reconnecting or not self.is_running:
            return

        self._reconnecting = True
        logger.warning(
            f"Unexpected Gemini Live disconnection for session {self.session_id} (error: {error}). "
            "Attempting automatic session resumption..."
        )
        # Flush any partial uncommitted interviewer speech as INTERRUPTED
        try:
            interviewer_buf = transcript_service.get_current_buffer(self.session_id, TranscriptSpeaker.INTERVIEWER)
            if interviewer_buf and interviewer_buf.strip():
                await transcript_service.commit_turn(
                    self.session_id,
                    TranscriptSpeaker.INTERVIEWER,
                    completion_status=TurnCompletionStatus.INTERRUPTED,
                )
        except Exception as flush_err:
            logger.debug(f"Error committing interrupted buffer on unexpected disconnect: {flush_err}")

        try:
            await RealtimeEventRouter.send_session_status(
                self.websocket,
                session_id=self.session_id,
                status="reconnecting",
                message="Re-establishing Gemini Live audio connection...",
            )

            old_session = self.gemini_session
            latest_handle = old_session.resumption_handle if old_session else None

            # Close old session resources safely
            if old_session:
                await old_session.close()

            # Attempt reconnection with retries
            max_retries = 3
            connected = False
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        f"Reconnection attempt {attempt}/{max_retries} for session {self.session_id} "
                        f"(handle={'present' if latest_handle else 'none'})..."
                    )
                    await self._start_gemini_session(resumption_handle=latest_handle)
                    connected = True
                    break
                except Exception as resume_err:
                    logger.warning(f"Reconnection attempt {attempt} failed for {self.session_id}: {resume_err}")
                    if latest_handle and attempt == 1:
                        # Stale or rejected resumption handle; clear and retry with fresh session
                        self._clear_resumption_handle()
                        latest_handle = None
                    if attempt < max_retries:
                        await asyncio.sleep(1.0 * attempt)

            if connected:
                logger.info(f"Successfully resumed Gemini Live session for {self.session_id}")
                await RealtimeEventRouter.send_session_status(
                    self.websocket,
                    session_id=self.session_id,
                    status="resumed",
                    resumed=True,
                    message="Realtime audio connection restored.",
                )
            else:
                logger.error(f"All reconnection attempts failed for session {self.session_id}")
                await RealtimeEventRouter.send_error(
                    self.websocket,
                    message="Realtime connection lost and could not be restored.",
                    code="RECONNECT_FAILED",
                )
        except Exception as err:
            logger.error(f"Error handling unexpected Gemini Live disconnect: {err}", exc_info=True)
        finally:
            self._reconnecting = False

    async def _handle_stage_update(self, stage_data: Dict[str, Any]) -> None:
        """Broadcast stage transition update to candidate browser."""
        target_stage_str = stage_data.get("target_stage") or stage_data.get("current_stage", "INTRO")
        try:
            stage_enum = InterviewStage(target_stage_str)
        except ValueError:
            stage_enum = InterviewStage.INTRO

        await RealtimeEventRouter.send_stage_update(
            self.websocket,
            stage=stage_enum,
            guidance=stage_data,
        )

    async def _handle_problem_presented(self, problem_data: Dict[str, Any]) -> None:
        """Broadcast technical problem presentation to browser code editor."""
        await RealtimeEventRouter.send_problem_presented(
            self.websocket,
            problem_id=str(problem_data.get("problem_id", "")),
            title=problem_data.get("title", ""),
            problem_type=problem_data.get("problem_type", ""),
            prompt_question=problem_data.get("prompt_question", ""),
            instructions=problem_data.get("instructions") or problem_data.get("context") or "",
            code_files=problem_data.get("code_files", []),
        )

    # ==========================================================================
    # Upstream Processing Loop (Browser WebSocket -> Gemini Live)
    # ==========================================================================

    async def run(self) -> None:
        """Main listening loop receiving frames from the candidate WebSocket."""
        self.is_running = True

        # Send initial connected status
        await RealtimeEventRouter.send_session_status(
            self.websocket,
            session_id=self.session_id,
            status="connected",
            message="Realtime Media Bridge established.",
        )

        try:
            while self.is_running:
                # Receive message (either raw binary bytes or text JSON)
                message = await self.websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    break

                raw_bytes = message.get("bytes")
                raw_text = message.get("text")

                # 1. Direct Binary Frame (Raw PCM bytes)
                if raw_bytes:
                    if self.gemini_session and self.gemini_session.is_active:
                        await self.gemini_session.send_audio(raw_bytes)
                    continue

                # 2. Text / JSON Protocol Frame
                if raw_text:
                    parsed_msg = RealtimeEventRouter.parse_client_message(raw_text)
                    if not parsed_msg:
                        continue

                    await self._process_client_message(parsed_msg)

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected by client for session {self.session_id}")
        except Exception as err:
            logger.error(f"Error in RealtimeSessionManager loop for session {self.session_id}: {err}", exc_info=True)
        finally:
            await self.shutdown()

    async def _process_client_message(self, msg: ClientMessage) -> None:
        """Dispatch parsed client message into Gemini Live session."""
        if isinstance(msg, ClientStartMessage):
            # Check if this is a reconnect event on an already active interview
            if self._has_started:
                logger.info(f"Received session_start on reconnect for session {self.session_id}. Resuming gracefully without re-greeting...")
                if self.gemini_session and self.gemini_session.is_active:
                    try:
                        state = await interview_orchestrator.get_state(self.session_id)
                        curr_stage = state.get("current_stage", "INTRO") if state else "INTRO"
                        resume_prompt = (
                            f"Realtime connection refreshed. You are currently in stage '{curr_stage}'. "
                            f"Continue the interview naturally from where you left off without repeating greetings, introductions, or previous questions."
                        )
                        await self.gemini_session.send_text(resume_prompt)
                    except Exception as err:
                        logger.warning(f"Failed to send reconnect resume prompt to Gemini Live: {err}")
                return

            self._has_started = True
            # Inject candidate context into Gemini Live to prime the AI before it speaks
            context = (msg.context or "").strip()
            if self.gemini_session and self.gemini_session.is_active:
                prompt = (
                    context
                    if context
                    else f"The interview is starting now. Please greet {self._candidate_name} warmly in 1-2 concise sentences as Vetra, and begin with Question 1 of the Introduction (ask how they are doing today)."
                )
                logger.info(f"Received initial session_start for session {self.session_id} (has_context={bool(context)}). Priming Gemini Live...")
                try:
                    await self.gemini_session.send_text(prompt)
                    logger.info(f"AI primed for session {self.session_id}")
                except Exception as err:
                    logger.warning(f"Failed to send session context to Gemini Live: {err}")
            else:
                logger.warning(f"session_start received for {self.session_id} but Gemini Live session is not active")
            return

        if not self.gemini_session or not self.gemini_session.is_active:
            return

        if isinstance(msg, ClientAudioMessage):
            pcm_bytes = base64_to_pcm(msg.data)
            await self.gemini_session.send_audio(pcm_bytes)

        elif isinstance(msg, ClientTextMessage):
            await self.gemini_session.send_text(msg.text)

        elif isinstance(msg, ClientPingMessage):
            await RealtimeEventRouter.send_pong(self.websocket)

        elif isinstance(msg, ClientEndMessage):
            logger.info(f"Client requested session end for session {self.session_id}")
            # Mark session complete in orchestrator
            await interview_orchestrator.complete_interview(
                session_id=self.session_id,
                requested_by="CANDIDATE",
                reason="Client ended interview",
            )
            # Mark session complete in Supabase and trigger Phase 6 report synthesis
            try:
                from src.service.interview import interview_service
                from src.service.report_synthesizer import report_synthesizer
                s_uuid = UUID(str(self.session_id))
                interview_service.complete_session(session_id=s_uuid)
                asyncio.create_task(
                    report_synthesizer.synthesize_session_report(
                        session_id=s_uuid,
                        candidate_name=self._candidate_name,
                    )
                )
                logger.info(f"Triggered background report synthesis for completed session {self.session_id}")
            except Exception as synth_err:
                logger.warning(f"Could not trigger background report synthesis: {synth_err}")

            await RealtimeEventRouter.send_session_status(
                self.websocket,
                session_id=self.session_id,
                status="completed",
                message="Interview session ended.",
            )
            self.is_running = False


    async def shutdown(self) -> None:
        """Tear down Gemini Live session, flush pending uncommitted transcripts, and clean up."""
        self.is_running = False

        # Flush any remaining uncommitted candidate/interviewer transcripts
        try:
            await transcript_service.commit_turn(self.session_id, TranscriptSpeaker.CANDIDATE)
            await transcript_service.commit_turn(self.session_id, TranscriptSpeaker.INTERVIEWER)
        except Exception as err:
            logger.debug(f"Error committing final transcripts during shutdown: {err}")

        transcript_service.cleanup_session(self.session_id)

        if self.gemini_session:
            await self.gemini_session.close()
            self.gemini_session = None

        logger.info(f"Session manager shut down for session {self.session_id}")


# Active sessions registry: session_id -> RealtimeSessionManager
active_sessions: Dict[str, RealtimeSessionManager] = {}
