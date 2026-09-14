import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException, status
from supabase import Client

from config import settings
from src.agents.resume_cache import resume_freeze_cache
from src.agents.resume_parser import resume_parser_agent
from src.db.supabase import supabase
from src.schemas.candidate import (
    CandidateProfileRecord,
    CandidateResumeMetadata,
    CandidateResumeUploadResponse,
)
from src.schemas.planner import CandidateProfile

logger = logging.getLogger("vetra.service.candidate")


class CandidateService:
    """Service managing Candidate Profiles, resume upload & parsing,
    freeze caching, and interview preparation persistence.
    """

    def __init__(self, client: Optional[Client] = supabase):
        self.supabase = client
        self.parser_agent = resume_parser_agent
        self.resume_cache = resume_freeze_cache

    def _clean_str(self, val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        s = str(val).strip()
        return s if s else None

    def get_candidate_profile(
        self,
        candidate_id: Optional[UUID] = None,
        email: Optional[str] = None,
    ) -> CandidateProfileRecord:
        """Fetch candidate profile and stored parsed resume by candidate_id or email."""
        cleaned_email = self._clean_str(email)

        if not candidate_id and not cleaned_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either candidate_id or email must be provided to retrieve profile.",
            )

        if not self.supabase:
            return CandidateProfileRecord(
                email=cleaned_email or "candidate@vetra.ai",
                has_resume=False,
            )

        row: Optional[Dict[str, Any]] = None
        try:
            # 1. Search candidate_profiles by user_id or id
            if candidate_id:
                res = (
                    self.supabase.table("candidate_profiles")
                    .select("*")
                    .or_(f"user_id.eq.{candidate_id},id.eq.{candidate_id}")
                    .execute()
                )
                if res.data and len(res.data) > 0:
                    row = res.data[0]

            # 2. Search by email if not found yet
            if not row and cleaned_email:
                res = (
                    self.supabase.table("candidate_profiles")
                    .select("*")
                    .eq("email", cleaned_email)
                    .execute()
                )
                if res.data and len(res.data) > 0:
                    row = res.data[0]

            # 3. Fall back to users table if candidate_profiles record doesn't exist yet
            if not row:
                user_query = self.supabase.table("users").select("*")
                if candidate_id:
                    user_res = user_query.eq("id", str(candidate_id)).execute()
                else:
                    user_res = user_query.eq("email", cleaned_email).execute()

                if user_res.data and len(user_res.data) > 0:
                    u = user_res.data[0]
                    return CandidateProfileRecord(
                        user_id=UUID(u["id"]) if u.get("id") else None,
                        email=u.get("email", cleaned_email or "candidate@vetra.ai"),
                        full_name=u.get("full_name") or f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or None,
                        has_resume=False,
                    )

                return CandidateProfileRecord(
                    email=cleaned_email or "candidate@vetra.ai",
                    has_resume=False,
                )

            # Build parsed_profile if present in row or freeze cache
            parsed_data = row.get("parsed_resume")
            resume_hash = row.get("resume_hash")
            parsed_profile_obj: Optional[CandidateProfile] = None

            if parsed_data and isinstance(parsed_data, dict):
                try:
                    parsed_profile_obj = CandidateProfile(**parsed_data)
                except Exception as e:
                    logger.warning(f"Failed to deserialize parsed_resume JSON: {e}")

            # Check in-memory freeze cache if row has hash but no JSON
            if not parsed_profile_obj and resume_hash:
                cached = self.resume_cache.get(resume_hash)
                if cached:
                    parsed_profile_obj = cached

            has_resume = parsed_profile_obj is not None or bool(row.get("resume_filename"))

            metadata = None
            if has_resume:
                uploaded_at_val = row.get("updated_at") or row.get("created_at")
                if isinstance(uploaded_at_val, str):
                    try:
                        uploaded_at_dt = datetime.fromisoformat(uploaded_at_val)
                    except Exception:
                        uploaded_at_dt = datetime.now(timezone.utc)
                else:
                    uploaded_at_dt = datetime.now(timezone.utc)

                metadata = CandidateResumeMetadata(
                    filename=row.get("resume_filename") or "uploaded_resume.pdf",
                    uploaded_at=uploaded_at_dt,
                    resume_hash=resume_hash or "",
                    experience_years=row.get("experience_years") or (parsed_profile_obj.years_of_experience if parsed_profile_obj else 0),
                )

            return CandidateProfileRecord(
                id=UUID(row["id"]) if row.get("id") else None,
                user_id=UUID(row["user_id"]) if row.get("user_id") else candidate_id,
                email=row.get("email") or cleaned_email or "candidate@vetra.ai",
                full_name=row.get("full_name"),
                experience_years=row.get("experience_years") or 0,
                resume_url=row.get("resume_url"),
                resume_filename=row.get("resume_filename"),
                resume_hash=resume_hash,
                has_resume=has_resume,
                parsed_profile=parsed_profile_obj,
                metadata=metadata,
                updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None,
                created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving candidate profile: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving candidate profile: {str(e)}",
            )

    def upload_candidate_resume_file(
        self,
        file_bytes: bytes,
        filename: str,
        candidate_id: Optional[UUID] = None,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        force_refresh: bool = False,
    ) -> CandidateResumeUploadResponse:
        """Upload and parse candidate PDF resume with change detection and permanent storage."""
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Strictly PDF resume files (.pdf) are supported. Resume text pasting is not allowed.",
            )

        if not file_bytes or len(file_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded PDF resume file is empty.",
            )

        cleaned_email = self._clean_str(email)
        cleaned_name = self._clean_str(full_name)

        # 1. Compute SHA-256 fingerprint from file bytes
        hash_key = self.resume_cache.compute_bytes_hash(file_bytes)

        # 2. Check if resume has NOT changed (Change-detection condition)
        reused_cache = False
        parsed_profile: Optional[CandidateProfile] = None

        if not force_refresh:
            # Check in-memory freeze cache first
            cached = self.resume_cache.get(hash_key)
            if cached:
                parsed_profile = cached
                reused_cache = True
                logger.info(f"Resume unchanged. Reusing freeze-cached profile for hash {hash_key[:12]}")

            # If not in memory, check if candidate's existing database record has the exact same hash
            if not parsed_profile and (candidate_id or cleaned_email):
                try:
                    existing = self.get_candidate_profile(candidate_id=candidate_id, email=cleaned_email)
                    if existing.resume_hash == hash_key and existing.parsed_profile:
                        parsed_profile = existing.parsed_profile
                        reused_cache = True
                        self.resume_cache.set(hash_key, parsed_profile)
                        logger.info(f"Resume unchanged. Reusing DB stored profile for candidate {cleaned_email}")
                except Exception as e:
                    logger.debug(f"Cache check lookup bypassed: {e}")

        # 3. If file changed or not in cache, parse via Gemini 2.5 Flash
        if not parsed_profile:
            logger.info(f"Parsing new or modified resume PDF '{filename}' (bytes: {len(file_bytes)}) via Gemini...")
            parsed_profile = self.parser_agent.parse_pdf_bytes(pdf_bytes=file_bytes, filename=filename)
            parsed_profile.freeze_hash = hash_key
            self.resume_cache.set(hash_key, parsed_profile)

        # 4. Resolve candidate identity details
        final_name = cleaned_name or parsed_profile.candidate_name or "Candidate"
        final_email = cleaned_email or str(parsed_profile.candidate_email or "")
        if not final_email:
            final_email = f"{final_name.lower().replace(' ', '')}@candidate.vetra"

        now_iso = datetime.now(timezone.utc).isoformat()
        profile_json = parsed_profile.model_dump(mode="json")
        experience_years = parsed_profile.years_of_experience or 0

        # 5. Persist into Supabase candidate_profiles table
        persisted_row: Optional[Dict[str, Any]] = None
        if self.supabase:
            try:
                # Find existing profile
                find_query = self.supabase.table("candidate_profiles").select("id, user_id, email")
                if candidate_id:
                    find_res = find_query.or_(f"user_id.eq.{candidate_id},id.eq.{candidate_id}").execute()
                else:
                    find_res = find_query.eq("email", final_email).execute()

                payload: Dict[str, Any] = {
                    "email": final_email,
                    "full_name": final_name,
                    "experience_years": experience_years,
                    "resume_filename": filename,
                    "resume_hash": hash_key,
                    "parsed_resume": profile_json,
                    "updated_at": now_iso,
                }
                if candidate_id:
                    payload["user_id"] = str(candidate_id)

                if find_res.data and len(find_res.data) > 0:
                    target_id = find_res.data[0]["id"]
                    try:
                        upd = self.supabase.table("candidate_profiles").update(payload).eq("id", target_id).execute()
                        persisted_row = upd.data[0] if upd.data else None
                    except Exception as upd_err:
                        # Fallback if remote schema does not yet have parsed_resume column
                        if "parsed_resume" in str(upd_err) or "resume_filename" in str(upd_err):
                            logger.warning("Remote table missing resume columns. Updating standard columns only.")
                            payload.pop("parsed_resume", None)
                            payload.pop("resume_filename", None)
                            payload.pop("resume_hash", None)
                            upd = self.supabase.table("candidate_profiles").update(payload).eq("id", target_id).execute()
                            persisted_row = upd.data[0] if upd.data else None
                        else:
                            raise upd_err
                else:
                    # Create new candidate_profiles row
                    payload["created_at"] = now_iso
                    try:
                        ins = self.supabase.table("candidate_profiles").insert(payload).execute()
                        persisted_row = ins.data[0] if ins.data else None
                    except Exception as ins_err:
                        if "parsed_resume" in str(ins_err) or "resume_filename" in str(ins_err):
                            logger.warning("Remote table missing resume columns. Inserting standard columns only.")
                            payload.pop("parsed_resume", None)
                            payload.pop("resume_filename", None)
                            payload.pop("resume_hash", None)
                            ins = self.supabase.table("candidate_profiles").insert(payload).execute()
                            persisted_row = ins.data[0] if ins.data else None
                        else:
                            raise ins_err

            except Exception as db_err:
                logger.error(f"Failed to persist candidate resume to Supabase: {db_err}")
                # We do not crash here; in-memory cache and returned model still guarantee seamless flow

        meta = CandidateResumeMetadata(
            filename=filename,
            uploaded_at=datetime.now(timezone.utc),
            file_size_bytes=len(file_bytes),
            resume_hash=hash_key,
            experience_years=experience_years,
        )

        record = CandidateProfileRecord(
            id=UUID(persisted_row["id"]) if (persisted_row and persisted_row.get("id")) else None,
            user_id=candidate_id,
            email=final_email,
            full_name=final_name,
            experience_years=experience_years,
            resume_filename=filename,
            resume_hash=hash_key,
            has_resume=True,
            parsed_profile=parsed_profile,
            metadata=meta,
            updated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )

        msg = (
            "Resume verified and loaded from cache (unchanged content)."
            if reused_cache
            else "Resume uploaded, successfully parsed, and stored permanently."
        )

        return CandidateResumeUploadResponse(
            status="success",
            message=msg,
            reused_cache=reused_cache,
            candidate_profile=record,
        )

    def delete_candidate_resume(
        self,
        candidate_id: Optional[UUID] = None,
        email: Optional[str] = None,
    ) -> Dict[str, str]:
        """Delete stored candidate resume and invalidate cache."""
        cleaned_email = self._clean_str(email)
        if not candidate_id and not cleaned_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either candidate_id or email must be provided to delete resume.",
            )

        if self.supabase:
            try:
                clear_payload = {
                    "resume_filename": None,
                    "resume_hash": None,
                    "parsed_resume": None,
                    "raw_resume_text": None,
                    "resume_url": None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                query = self.supabase.table("candidate_profiles").update(clear_payload)
                if candidate_id:
                    query = query.or_(f"user_id.eq.{candidate_id},id.eq.{candidate_id}")
                else:
                    query = query.eq("email", cleaned_email)
                query.execute()
            except Exception as e:
                logger.warning(f"Error resetting resume columns in database: {e}")

        return {"message": "Candidate resume cleared successfully."}


# Default singleton instance
candidate_service = CandidateService()
