import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from src.agents.evaluator.evaluator import AsyncEvaluatorAgent
from src.agents.evaluator.guidance_compiler import GuidanceCompiler
from src.db.supabase import supabase
from src.models.enums import InterviewStage
from src.orchestrator.engine import interview_orchestrator
from src.schemas.evaluator import (
    CompetencyAssessment,
    EvaluatorBatchInput,
    EvaluatorBatchOutput,
    StrategicProbeObjective,
)
from src.service.evaluation_queue import evaluation_queue

logger = logging.getLogger("vetra.service.evaluation_worker")


class EvaluationWorkerService:
    """Asynchronous background worker service that executes durable evaluation jobs.
    
    Responsibilities:
    - Claims pending jobs from public.evaluation_jobs.
    - Gathers evaluation context (turns, code diffs, problem statement).
    - Invokes AsyncEvaluatorAgent (Kimi with Gemini Flash fallback).
    - Persists evaluation signals to public.evaluation_signals.
    - Runs GuidanceCompiler to produce concise GuidancePayload.
    - Injects guidance into LangGraph via interview_orchestrator.inject_guidance().
    """

    def __init__(self, evaluator_agent: Optional[AsyncEvaluatorAgent] = None):
        self.evaluator = evaluator_agent or AsyncEvaluatorAgent()
        self.supabase = supabase
        self._running = False
        self._poll_interval_seconds = 2.0

        # In-memory signal cache per session (for fast retrieval & fallback)
        self._session_probes: Dict[str, List[StrategicProbeObjective]] = {}
        self._session_assessments: Dict[str, Dict[str, CompetencyAssessment]] = {}
        self._guidance_versions: Dict[str, int] = {}

    def get_session_probes(self, session_id: str) -> List[StrategicProbeObjective]:
        return self._session_probes.get(str(session_id), [])

    def get_session_assessments(self, session_id: str) -> Dict[str, CompetencyAssessment]:
        return self._session_assessments.get(str(session_id), {})

    async def process_job(self, job_record: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single claimed evaluation job."""
        job_id = job_record["id"]
        session_id = str(job_record["session_id"])
        payload = job_record.get("payload") or {}

        try:
            # 1. Format dialogue turns
            raw_turns = payload.get("turns", [])
            formatted_turns = []
            for t in raw_turns:
                t_idx = t.get("turn_index", 1)
                formatted_turns.append(
                    {
                        "turn_id": f"turn_{t_idx:03d}",
                        "speaker": t.get("speaker", "UNKNOWN"),
                        "content": t.get("content", ""),
                        "stage": t.get("stage", "INTRO"),
                    }
                )

            # 2. Get current stage and competencies from orchestrator or default
            stage = InterviewStage.INTRO
            try:
                state = await interview_orchestrator.get_state(session_id)
                if state and state.get("current_stage"):
                    stage = InterviewStage(state["current_stage"])
            except Exception as err:
                logger.warning(f"Could not retrieve stage from orchestrator for {session_id}: {err}")

            active_competencies = [
                "Concurrency & Race Conditions",
                "Data Structures & Algorithms",
                "System Architecture & Scalability",
                "Code Quality & Maintainability",
                "Database Isolation & Indexing",
            ]
            eval_criteria = None

            if self.supabase:
                try:
                    s_res = await asyncio.to_thread(
                        lambda: self.supabase.table("interview_sessions").select("interview_id").eq("id", session_id).limit(1).execute()
                    )
                    if s_res.data and s_res.data[0].get("interview_id"):
                        int_id = s_res.data[0]["interview_id"]
                        i_res = await asyncio.to_thread(
                            lambda: self.supabase.table("interviews").select("evaluation_criteria, technical_focus").eq("id", int_id).limit(1).execute()
                        )
                        if i_res.data:
                            eval_criteria = i_res.data[0].get("evaluation_criteria")
                            tech_foc = i_res.data[0].get("technical_focus")
                            if tech_foc and len(tech_foc) > 0:
                                active_competencies = tech_foc
                except Exception as db_e:
                    logger.debug(f"Could not load interview criteria for session {session_id}: {db_e}")

            existing_assessments = self._session_assessments.get(session_id, {})
            active_probes = self._session_probes.get(session_id, [])

            batch_input = EvaluatorBatchInput(
                session_id=uuid.UUID(session_id),
                batch_index=job_record.get("batch_index", 1),
                current_stage=stage,
                recent_turns=formatted_turns,
                active_problem=None,
                code_diff_summary=None,
                active_competencies=active_competencies,
                existing_assessments=existing_assessments,
                active_probes=active_probes,
                evaluation_criteria=eval_criteria,
            )

            # 3. Execute evaluation
            eval_output: EvaluatorBatchOutput = await self.evaluator.evaluate_batch(batch_input)

            # 4. Update session probe & assessment state
            # Merge assessments
            if session_id not in self._session_assessments:
                self._session_assessments[session_id] = {}
            for comp, assess in eval_output.updated_assessments.items():
                self._session_assessments[session_id][comp] = assess

            # Merge probes
            current_probes = list(self._session_probes.get(session_id, []))
            # Add new probes
            for p in eval_output.new_probes:
                current_probes.append(p)
            self._session_probes[session_id] = current_probes

            # 5. Persist signals to Supabase public.evaluation_signals
            signal_record = {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "job_id": job_id,
                "turn_start_index": job_record.get("start_turn_index", 1),
                "turn_end_index": job_record.get("end_turn_index", 1),
                "competency_observations": [o.model_dump(mode="json") for o in eval_output.observations],
                "competency_assessments": {
                    k: v.model_dump(mode="json") for k, v in self._session_assessments[session_id].items()
                },
                "strategic_probes": [p.model_dump(mode="json") for p in current_probes],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            if self.supabase:
                try:
                    await asyncio.to_thread(
                        lambda: self.supabase.table("evaluation_signals").insert(signal_record).execute()
                    )
                except Exception as err:
                    logger.warning(f"Could not persist evaluation_signals to Supabase: {err}")

            # 6. Compile guidance via GuidanceCompiler
            current_turn_index = job_record.get("end_turn_index", 5)
            v = self._guidance_versions.get(session_id, 1) + 1
            self._guidance_versions[session_id] = v

            compiled_guidance = GuidanceCompiler.compile(
                active_probes=current_probes,
                satisfied_probe_ids=eval_output.satisfied_probe_ids,
                assessments=self._session_assessments[session_id],
                current_turn_index=current_turn_index,
                guidance_version=v,
            )

            # 7. Inject compiled guidance into LangGraph orchestrator
            try:
                await interview_orchestrator.inject_guidance(
                    session_id=session_id,
                    guidance=compiled_guidance,
                    actor="KIMI",
                )
                logger.info(
                    f"Successfully injected guidance v{v} into orchestrator for session {session_id}. "
                    f"Primary: {compiled_guidance.topic}"
                )
            except Exception as err:
                logger.warning(f"Failed to inject guidance into orchestrator: {err}")

            # 8. Mark job as COMPLETED
            result_payload = {
                "observations_count": len(eval_output.observations),
                "probes_count": len(eval_output.new_probes),
                "guidance_version": v,
                "primary_objective": compiled_guidance.topic,
            }
            await asyncio.to_thread(
                evaluation_queue.complete_job, job_id=job_id, result=result_payload
            )
            return result_payload

        except Exception as err:
            logger.error(f"Error processing evaluation job {job_id}: {err}", exc_info=True)
            await asyncio.to_thread(evaluation_queue.fail_job, job_id=job_id, error_message=str(err))
            return {"error": str(err)}

    async def run_worker_loop(self) -> None:
        """Continuous polling worker loop for processing queued evaluation jobs."""
        self._running = True
        logger.info("Starting EvaluationWorkerService polling loop...")
        while self._running:
            try:
                job = evaluation_queue.claim_next_pending_job()
                if job:
                    await self.process_job(job)
                else:
                    await asyncio.sleep(self._poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error(f"Error in evaluation worker polling loop: {err}")
                await asyncio.sleep(self._poll_interval_seconds)

    def stop_worker(self) -> None:
        """Stop worker polling."""
        self._running = False


# Default singleton instance
evaluation_worker = EvaluationWorkerService()
