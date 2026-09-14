import asyncio
from datetime import datetime, timezone
import logging
import re
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple
from google import genai
from google.genai import types

from config import settings
from src.db.supabase import supabase
from src.models.enums import TranscriptSpeaker
from src.tools.definitions import get_live_tools
from src.tools.gateway import tool_gateway

logger = logging.getLogger("vetra.realtime.gemini_live")

DEFAULT_SYSTEM_INSTRUCTION = """
You are Vetra, an expert, encouraging, and highly technical AI Interviewer conducting a real-time voice interview.

CRITICAL FACTUAL GROUNDING & ZERO-HALLUCINATION RULES (HIGHEST PRIORITY):
- Ground truth only: You may ONLY assert or state a candidate-specific fact, project component, or metric if it exists in CandidateProfile, ResumeEvidence, ProjectEvidence, or the candidate's spoken words.
- ZERO FABRICATION: Only state a candidate-specific fact, architecture name, metric, or pipeline detail if it literally appears in the candidate data provided in this session's system instruction or in the candidate's own spoken words in this conversation. If a detail is not in that data, do not mention it — ask an exploratory question instead.
- If exploring a candidate project, ask an exploratory question (e.g., 'Could you walk me through the high-level architecture of your project and what you owned?') rather than assuming implementation details.
- Never imply the candidate claimed something they did not claim.

CRITICAL TOOL CALLING & SILENT EXECUTION RULES (MANDATORY):
- Tool calls (`get_interviewer_state`, `request_stage_transition`, `present_problem`, `get_workspace_context`) are purely SILENT, INTERNAL operations.
- You must NEVER speak tool syntax, function names, parameters, or code aloud to the candidate.
- NEVER say or write 'call:request_stage_transition', 'call:', or JSON in your speech or text responses.
- When transitioning stages, state a natural, human conversational bridge (e.g. 'Thanks for walking me through that. I\'d now like to move to a different area and discuss system design.') and execute the tool call silently in the background.

RESPONSE QUALITY & CANDIDATE CADENCE GATE:
- If the candidate gives an initial greeting ('Hello', 'Hi', 'Can you hear me?'), acknowledge warmly (e.g. 'Yes, I can hear you clearly! How are you doing today?') and do NOT plunge into technical grilling until rapport is established.
- If an answer is vague, evasive, or 1-word, ask a focused clarifying question rather than advancing immediately.

CRITICAL VOICE CADENCE & BREVITY RULES (MANDATORY):
- STRICT 1-2 SENTENCE LIMIT: Never speak more than 1 or 2 concise sentences per turn. Never monologue, lecture, or speak in paragraphs.
- EXACTLY ONE QUESTION PER TURN: Ask only ONE direct question at a time. Never combine multiple questions, sub-questions, or compound clauses.
- NATURAL PING-PONG CADENCE: Briefly acknowledge the candidate's answer in 3-5 words (e.g., "Got it.", "That makes sense.", "Great."), ask your single question, and immediately stop speaking and yield the floor.

Your goals:
1. Conduct an authentic, high-signal technical conversation assessing deep software engineering skills, architectural thinking, and problem solving.
2. Adapt seamlessly between stages: Intro, Resume Deep Dive, Technical Q&A, Technical Exercise (verbal code review / architecture walkthrough), and Behavioral.
3. Keep responses conversational, concise, and natural. Stick to 2-3 focused questions per stage. NEVER exceed the stage maximum questions.
4. ZERO REPHRASING / ZERO LOOPING: NEVER ask the candidate to rephrase or repeat an answer. If answered, accept it and move to the next planned question or transition stages.
5. When you need current stage objectives, competency coverage, or want to transition stages, silently invoke the appropriate tools (`get_interviewer_state`, `request_stage_transition`, `present_problem`, `get_workspace_context`).
6. When entering Technical Exercise, call `present_problem` silently. There is ZERO code writing or typing in this interview—the candidate's workspace is a read-only code review surface. Prompt the candidate to inspect the code on screen, trace execution paths out loud, explain root causes or architectural bottlenecks, and verbally walk through how they would solve or refactor it.
7. Support natural pauses and handle interruptions gracefully.
"""


class GeminiLiveSession:
    """Manages an active bidirectional streaming session with the Google GenAI Live API
    (gemini-3.1-flash-live-preview) with Context Window Compression and Session Resumption.
    """

    def __init__(
        self,
        session_id: str,
        system_instruction: Optional[str] = None,
        voice_name: str = "Kore",
        resumption_handle: Optional[str] = None,
        on_audio: Optional[Callable[[bytes], Coroutine[Any, Any, None]]] = None,
        on_interrupted: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
        on_transcript: Optional[Callable[[TranscriptSpeaker, str, bool], Coroutine[Any, Any, None]]] = None,
        on_turn_complete: Optional[Callable[[TranscriptSpeaker], Coroutine[Any, Any, None]]] = None,
        on_resumption_update: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None,
        on_go_away: Optional[Callable[[Any], Coroutine[Any, Any, None]]] = None,
        on_stage_update: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None,
        on_problem_presented: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None,
        on_disconnect: Optional[Callable[[Optional[Exception]], Coroutine[Any, Any, None]]] = None,
    ):
        self.session_id = session_id
        self.system_instruction = system_instruction or DEFAULT_SYSTEM_INSTRUCTION
        self.voice_name = voice_name
        self.resumption_handle = resumption_handle
        self.model = settings.GEMINI_REALTIME_MODEL

        # Callbacks
        self.on_audio = on_audio
        self.on_interrupted = on_interrupted
        self.on_transcript = on_transcript
        self.on_turn_complete = on_turn_complete
        self.on_resumption_update = on_resumption_update
        self.on_go_away = on_go_away
        self.on_stage_update = on_stage_update
        self.on_problem_presented = on_problem_presented
        self.on_disconnect = on_disconnect

        # SDK Client & Active session handle
        self._client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self._session_context = None
        self._live_session = None
        self._is_active = False
        self._is_closing = False
        self._receive_task: Optional[asyncio.Task] = None
        self._last_handle_persisted: Optional[str] = None
        self._last_handle_persist_time: float = 0.0

    def _build_connect_config(self) -> types.LiveConnectConfig:
        """Construct the LiveConnectConfig with audio modality, compression, resumption, and tool definitions."""
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice_name)
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=self.system_instruction)]
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                turn_coverage="TURN_INCLUDES_ONLY_ACTIVITY",
            ),
            # Sliding window context compression eliminates 15-minute operational limit
            # Configured to slide when context reaches 25k tokens down to 10k tokens
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=25000,
                sliding_window=types.SlidingWindow(target_tokens=10000),
            ),
            # Session resumption allows recovery across connections within 2hr window
            session_resumption=types.SessionResumptionConfig(
                handle=self.resumption_handle
            ),
            tools=get_live_tools(),
        )

    async def connect(self) -> None:
        """Establish connection to Gemini Live API and start listening for downstream server content."""
        config = self._build_connect_config()
        logger.info(
            f"Establishing Gemini Live connection for session {self.session_id} "
            f"(resumption_handle={'present' if self.resumption_handle else 'none'})..."
        )

        try:
            self._session_context = self._client.aio.live.connect(
                model=self.model,
                config=config,
            )
            self._live_session = await self._session_context.__aenter__()

            self._is_active = True
            logger.info(f"Gemini Live session connected for session {self.session_id}")

            # Launch downstream receiver loop
            self._receive_task = asyncio.create_task(self._receive_loop())

        except Exception as err:
            logger.error(f"Failed to connect to Gemini Live for session {self.session_id}: {err}", exc_info=True)
            self._is_active = False
            if self._session_context:
                try:
                    await self._session_context.__aexit__(None, None, None)
                except Exception:
                    pass
                self._session_context = None
                self._live_session = None
            raise

    async def _receive_loop(self) -> None:
        """Continuous event processing loop receiving messages from Gemini Live."""
        try:
            if not self._live_session:
                return

            while self._is_active and self._live_session:
                async for response in self._live_session.receive():
                    if not self._is_active:
                        break

                    # 1. Server Content (Audio chunks, Barge-in Interruption, Transcriptions, Turn Complete)
                    if response.server_content:
                        content = response.server_content

                        # Interruption / Barge-in
                        if getattr(content, "interrupted", False):
                            logger.info(f"Candidate interrupted Gemini Live in session {self.session_id}")
                            if self.on_interrupted:
                                await self.on_interrupted()

                        # Model Audio Output Chunks
                        pcm_bytes = None
                        if getattr(response, "data", None):
                            pcm_bytes = response.data
                        elif getattr(content, "model_turn", None) and getattr(content.model_turn, "parts", None):
                            for part in content.model_turn.parts:
                                inline = getattr(part, "inline_data", None)
                                if inline is not None:
                                    data = getattr(inline, "data", None) if not isinstance(inline, dict) else inline.get("data")
                                    if data:
                                        pcm_bytes = data
                                        break

                        if pcm_bytes and self.on_audio:
                            await self.on_audio(pcm_bytes)

                        # Input Audio Transcription (Candidate speech)
                        if getattr(content, "input_transcription", None):
                            it = content.input_transcription
                            text = getattr(it, "text", "") or ""
                            is_final = bool(getattr(it, "finished", False))
                            if text and self.on_transcript:
                                await self.on_transcript(TranscriptSpeaker.CANDIDATE, text, is_final)

                        # Output Audio Transcription (Interviewer speech)
                        if getattr(content, "output_transcription", None):
                            ot = content.output_transcription
                            text = getattr(ot, "text", "") or ""
                            is_final = bool(getattr(ot, "finished", False))
                            if text:
                                clean_text, intercepted_tool = self._intercept_and_sanitize_tool_text(text)
                                if intercepted_tool:
                                    asyncio.create_task(self._execute_intercepted_tool(intercepted_tool))
                                if clean_text and self.on_transcript:
                                    await self.on_transcript(TranscriptSpeaker.INTERVIEWER, clean_text, is_final)

                        # Turn Complete Flag
                        if getattr(content, "turn_complete", False):
                            if self.on_turn_complete:
                                await self.on_turn_complete(TranscriptSpeaker.INTERVIEWER)

                    # 2. Tool Calls from Gemini Live
                    elif response.tool_call:
                        await self._handle_tool_call(response.tool_call)

                    # 3. Session Resumption Token Updates
                    elif response.session_resumption_update:
                        update = response.session_resumption_update
                        if getattr(update, "resumable", False) and getattr(update, "new_handle", None):
                            new_handle = update.new_handle
                            self.resumption_handle = new_handle
                            self._schedule_persist_resumption_handle(new_handle)
                            if self.on_resumption_update:
                                await self.on_resumption_update(new_handle)

                    # 4. Server GoAway Warning (Connection Lifetime Draining)
                    elif response.go_away is not None:
                        time_left = getattr(response.go_away, "time_left", None)
                        logger.warning(
                            f"Received GoAway from Gemini Live for session {self.session_id}. "
                            f"Time left: {time_left}"
                        )
                        if self.on_go_away:
                            await self.on_go_away(time_left)

                logger.debug(f"Gemini receive iterator completed for session {self.session_id}, re-entering receive loop")

        except asyncio.CancelledError:
            logger.debug(f"Gemini Live receive loop cancelled for session {self.session_id}")
        except Exception as err:
            if self._is_active and not self._is_closing:
                logger.error(f"Error in Gemini Live receive loop for session {self.session_id}: {err}", exc_info=True)
                if self.on_disconnect:
                    asyncio.create_task(self.on_disconnect(err))
            else:
                logger.debug(f"Gemini Live receive loop ended for session {self.session_id}: {err}")
        finally:
            was_active = self._is_active
            self._is_active = False
            if was_active and not self._is_closing and self.on_disconnect:
                asyncio.create_task(self.on_disconnect(None))

    def _intercept_and_sanitize_tool_text(self, text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Detect and strip internal tool calls leaking into interviewer speech/transcription.
        If a tool call (e.g. call:request_stage_transition{...}) is detected, returns cleaned spoken
        text and the extracted tool parameters for background execution.
        """
        pattern = re.compile(
            r"(?:call:)?(request_stage_transition|get_interviewer_state|present_problem|get_workspace_context)\s*(?:\{([^}]*)\}|\(([^)]*)\))?",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(text)
        intercepted: Optional[Dict[str, Any]] = None
        if match:
            tool_name = match.group(1).lower()
            raw_args = match.group(2) or match.group(3) or ""
            logger.warning(
                f"[GeminiLive] Intercepted leaked tool call in spoken text: '{tool_name}' with args: '{raw_args}'"
            )
            args_dict: Dict[str, Any] = {}
            if raw_args:
                try:
                    from src.utils.json_utils import safe_json_loads
                    parsed = safe_json_loads("{" + raw_args + "}" if not raw_args.strip().startswith("{") else raw_args)
                    if isinstance(parsed, dict):
                        args_dict = parsed
                except Exception:
                    kv_pairs = re.findall(r'(\w+)[\s:=]+["\']?([^,"\';}]+)["\']?', raw_args)
                    for k, v in kv_pairs:
                        args_dict[k.strip()] = v.strip()

            intercepted = {"tool": tool_name, "args": args_dict}

        # Strip all occurrences of tool call syntax from the spoken text
        clean_text = pattern.sub("", text).strip()
        clean_text = re.sub(r"call:\s*\{.*?\}", "", clean_text, flags=re.DOTALL | re.IGNORECASE).strip()
        return clean_text, intercepted

    async def _execute_intercepted_tool(self, tool_info: Dict[str, Any]) -> None:
        """Executes a tool call that accidentally leaked as text, ensuring orchestrator state transitions."""
        tool_name = tool_info.get("tool", "")
        args = tool_info.get("args", {})
        try:
            if tool_name == "request_stage_transition":
                target_stage = args.get("target_stage")
                reason = args.get("reason", "Stage assessment progression")
                from src.orchestrator.engine import interview_orchestrator
                from src.orchestrator.guards import STAGE_RULES
                if not target_stage:
                    state = await interview_orchestrator.get_state(self.session_id)
                    curr = state.get("current_stage", "INTRO") if state else "INTRO"
                    rule = STAGE_RULES.get(curr)
                    target_stage = rule.next_stage if rule else None

                if target_stage:
                    decision = await interview_orchestrator.request_stage_transition(
                        session_id=self.session_id,
                        target_stage=target_stage,
                        requested_by="GEMINI",
                        reason=reason,
                    )
                    logger.info(
                        f"[GeminiLive] Executed intercepted stage transition to '{target_stage}': allowed={decision.allowed}"
                    )
                    if decision.allowed and self.on_stage_update:
                        await self.on_stage_update({"target_stage": target_stage, "allowed": True})
            elif tool_name == "present_problem":
                from src.orchestrator.engine import interview_orchestrator
                prob_id = args.get("problem_id", "")
                await interview_orchestrator.present_problem(self.session_id, prob_id)
        except Exception as err:
            logger.error(f"[GeminiLive] Error executing intercepted tool {tool_name}: {err}", exc_info=True)

    async def _handle_tool_call(self, tool_call: types.LiveServerToolCall) -> None:
        """Executes function calls requested by Gemini Live and returns responses back over the Live connection."""
        if not tool_call.function_calls:
            return

        function_responses: List[types.FunctionResponse] = []

        for fc in tool_call.function_calls:
            try:
                response = await tool_gateway.execute_tool(
                    session_id=self.session_id,
                    function_call=fc,
                )
            except Exception as err:
                logger.error(f"Unexpected error executing tool '{fc.name}' (id={fc.id}): {err}", exc_info=True)
                response = types.FunctionResponse(
                    name=fc.name,
                    id=fc.id,
                    response={"result": {"error": f"Tool execution failed: {str(err)}"}},
                )

            # Ensure every requested function call ID receives a response
            function_responses.append(response)

            # Check if this tool invocation changed state or presented a problem
            res_dict = response.response.get("result", {}) if isinstance(response.response, dict) else {}
            if fc.name == "request_stage_transition" and res_dict.get("allowed") and self.on_stage_update:
                try:
                    await self.on_stage_update(res_dict)
                except Exception as err:
                    logger.error(f"Error in on_stage_update callback: {err}", exc_info=True)
            elif fc.name == "present_problem" and res_dict.get("success") and self.on_problem_presented:
                try:
                    await self.on_problem_presented(res_dict)
                except Exception as err:
                    logger.error(f"Error in on_problem_presented callback: {err}", exc_info=True)

        try:
            await self._live_session.send_tool_response(function_responses=function_responses)
            logger.debug(f"Sent tool responses for session {self.session_id}: {function_responses}")
        except Exception as err:
            logger.error(f"Failed to send tool response to Gemini Live: {err}", exc_info=True)

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Send candidate raw 16kHz 16-bit PCM audio chunk to Gemini Live."""
        if not self._is_active or not self._live_session:
            return

        blob = types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
        try:
            await self._live_session.send_realtime_input(audio=blob)
        except Exception as err:
            if self._is_active:
                logger.warning(f"Error sending audio to Gemini Live in session {self.session_id}: {err}")

    async def send_text(self, text: str, end_of_turn: bool = True) -> None:
        """Send text message or prompt input to Gemini Live using realtime input."""
        if not self._is_active or not self._live_session:
            return

        try:
            await self._live_session.send_realtime_input(text=text)
        except Exception as err:
            if self._is_active:
                logger.warning(f"Error sending text to Gemini Live in session {self.session_id}: {err}")

    async def send_video(self, frame_bytes: bytes, mime_type: str = "image/jpeg") -> None:
        """Send a single video/screen capture frame to Gemini Live."""
        if not self._is_active or not self._live_session:
            return

        blob = types.Blob(data=frame_bytes, mime_type=mime_type)
        try:
            await self._live_session.send_realtime_input(video=blob)
        except Exception as err:
            if self._is_active:
                logger.warning(f"Error sending video to Gemini Live in session {self.session_id}: {err}")

    def _schedule_persist_resumption_handle(self, handle: str, force: bool = False) -> None:
        """Throttle persistence of resumption tokens to avoid hammering Supabase with synchronous calls."""
        now = time.time()
        # Only persist to Supabase if at least 30s elapsed or force is True
        if not force and (now - self._last_handle_persist_time < 30.0):
            return
        if handle == self._last_handle_persisted and not force:
            return

        self._last_handle_persist_time = now
        self._last_handle_persisted = handle

        # Offload synchronous Supabase update to worker thread so receive loop never blocks
        asyncio.create_task(asyncio.to_thread(self._persist_resumption_handle_sync, handle))

    def _persist_resumption_handle_sync(self, handle: str) -> None:
        """Synchronous Supabase update helper run in threadpool."""
        if not supabase:
            return
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            supabase.table("interview_sessions").update({
                "resumption_handle": handle,
                "resumption_updated_at": now_iso,
            }).eq("id", str(self.session_id)).execute()
            logger.debug(f"Persisted resumption handle for session {self.session_id} to Supabase")
        except Exception as err:
            logger.warning(f"Failed to persist resumption handle to Supabase: {err}")

    async def close(self) -> None:
        """Gracefully close the active Gemini Live session."""
        self._is_closing = True
        self._is_active = False

        # Persist latest resumption handle on shutdown
        if self.resumption_handle and self.resumption_handle != self._last_handle_persisted:
            try:
                await asyncio.to_thread(self._persist_resumption_handle_sync, self.resumption_handle)
            except Exception:
                pass

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except (asyncio.CancelledError, Exception):
                pass
            self._receive_task = None

        if self._session_context:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception as err:
                logger.debug(f"Error during Gemini Live session close: {err}")
            finally:
                self._session_context = None
                self._live_session = None

    @property
    def is_active(self) -> bool:
        return self._is_active
