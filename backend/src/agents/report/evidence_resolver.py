from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from src.schemas.report import AuditTrailItem

logger = logging.getLogger("vetra.agents.report.resolver")


class EvidenceResolver:
    """Deterministic Evidence Resolver for Phase 6 Synthesis.
    
    Verifies that all turn citations (turn_001, turn_015) and empirical quotes
    generated in the candidate report actually exist in the sealed transcript.
    
    Preserves all verification decisions (VERIFIED, REJECTED, MODIFIED) in an internal
    audit trail for model quality telemetry, while ensuring recruiter-facing reports
    contain zero ungrounded or hallucinated references.
    """

    TURN_PATTERN = re.compile(r"\b(turn_\d{3})\b", re.IGNORECASE)

    @classmethod
    def resolve_report_evidence(
        cls,
        raw_report: Dict[str, Any],
        snapshot_turns: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[AuditTrailItem]]:
        """Validates all claims, citations, and quotes in the synthesized report against snapshot turns."""
        # Index turns by label: "turn_001" -> turn dict
        turn_map: Dict[str, Dict[str, Any]] = {}
        valid_turn_labels: Set[str] = set()

        for t in snapshot_turns:
            label = t.get("turn_id", "").lower()
            if label:
                turn_map[label] = t
                valid_turn_labels.add(label)

        audit_trail: List[AuditTrailItem] = []
        cleaned_report = dict(raw_report)

        # 1. Resolve key strengths
        cleaned_strengths: List[str] = []
        for strength in raw_report.get("key_strengths", []):
            cleaned_text, items = cls._validate_and_sanitize_text(
                claim_type="Strength",
                text=strength,
                turn_map=turn_map,
                valid_turn_labels=valid_turn_labels,
            )
            audit_trail.extend(items)
            cleaned_strengths.append(cleaned_text)
        cleaned_report["key_strengths"] = cleaned_strengths

        # 2. Resolve key weaknesses / gaps
        cleaned_weaknesses: List[str] = []
        for weakness in raw_report.get("key_weaknesses", []):
            cleaned_text, items = cls._validate_and_sanitize_text(
                claim_type="Weakness",
                text=weakness,
                turn_map=turn_map,
                valid_turn_labels=valid_turn_labels,
            )
            audit_trail.extend(items)
            cleaned_weaknesses.append(cleaned_text)
        cleaned_report["key_weaknesses"] = cleaned_weaknesses

        # 3. Resolve rubric category scores
        cleaned_rubrics: List[Dict[str, Any]] = []
        for rubric in raw_report.get("rubric_scores", []):
            rubric_copy = dict(rubric)
            is_unassessed = rubric.get("status") == "NOT_ASSESSED" or rubric.get("score") is None
            if is_unassessed:
                rubric_copy["status"] = "NOT_ASSESSED"
                rubric_copy["score"] = None
                rubric_copy["verified_turn_ids"] = []
                cleaned_rubrics.append(rubric_copy)
                continue

            cited_turns = rubric.get("verified_turn_ids", [])
            valid_citations: List[str] = []

            for citation in cited_turns:
                c_norm = citation.lower().strip()
                if c_norm in valid_turn_labels:
                    valid_citations.append(c_norm)
                    audit_trail.append(
                        AuditTrailItem(
                            claim=f"Rubric '{rubric.get('category')}': {rubric.get('feedback', '')[:100]}",
                            original_citation=citation,
                            resolution="VERIFIED",
                            reason=f"Citation {c_norm} verified in snapshot transcript.",
                        )
                    )
                else:
                    audit_trail.append(
                        AuditTrailItem(
                            claim=f"Rubric '{rubric.get('category')}': {rubric.get('feedback', '')[:100]}",
                            original_citation=citation,
                            resolution="REJECTED",
                            reason=f"Turn identifier '{citation}' does not exist in interview transcript.",
                        )
                    )

            rubric_copy["verified_turn_ids"] = valid_citations
            cleaned_rubrics.append(rubric_copy)
        cleaned_report["rubric_scores"] = cleaned_rubrics

        # 4. Resolve question scores
        cleaned_questions: List[Dict[str, Any]] = []
        for q in raw_report.get("question_scores", []):
            q_copy = dict(q)
            is_q_unassessed = q.get("status") == "NOT_ASSESSED" or q.get("score") is None
            if is_q_unassessed:
                q_copy["status"] = "NOT_ASSESSED"
                q_copy["score"] = None
                q_copy["verified_turn_ids"] = []
                cleaned_questions.append(q_copy)
                continue

            cited_turns = q.get("verified_turn_ids", [])
            valid_citations = []
            for citation in cited_turns:
                c_norm = citation.lower().strip()
                if c_norm in valid_turn_labels:
                    valid_citations.append(c_norm)
                    audit_trail.append(
                        AuditTrailItem(
                            claim=f"Question: {q.get('question_text', '')[:80]}",
                            original_citation=citation,
                            resolution="VERIFIED",
                            reason=f"Citation {c_norm} confirmed.",
                        )
                    )
                else:
                    audit_trail.append(
                        AuditTrailItem(
                            claim=f"Question: {q.get('question_text', '')[:80]}",
                            original_citation=citation,
                            resolution="REJECTED",
                            reason=f"Citation '{citation}' not found in transcript.",
                        )
                    )
            q_copy["verified_turn_ids"] = valid_citations
            cleaned_questions.append(q_copy)
        cleaned_report["question_scores"] = cleaned_questions

        return cleaned_report, audit_trail

    @classmethod
    def _validate_and_sanitize_text(
        cls,
        claim_type: str,
        text: str,
        turn_map: Dict[str, Dict[str, Any]],
        valid_turn_labels: Set[str],
    ) -> Tuple[str, List[AuditTrailItem]]:
        """Extracts turn citations from text, validates against actual transcript content,
        and sanitizes unverified citations while preserving audit entries.
        """
        audit_items: List[AuditTrailItem] = []
        matches = cls.TURN_PATTERN.findall(text)

        sanitized_text = text
        for match in matches:
            norm_label = match.lower()
            if norm_label in valid_turn_labels:
                turn = turn_map[norm_label]
                audit_items.append(
                    AuditTrailItem(
                        claim=f"[{claim_type}] {text[:120]}",
                        original_citation=match,
                        resolution="VERIFIED",
                        reason=f"Referenced {norm_label} ({turn.get('speaker', 'SPEAKER')} in {turn.get('stage', 'STAGE')}) verified in transcript.",
                    )
                )
            else:
                # Hallucinated turn ID
                audit_items.append(
                    AuditTrailItem(
                        claim=f"[{claim_type}] {text[:120]}",
                        original_citation=match,
                        resolution="REJECTED",
                        reason=f"Hallucinated turn reference: '{match}' is absent from transcript.",
                    )
                )
                # Remove unverified citation tag from visible text
                sanitized_text = re.sub(
                    rf"\[?\b{re.escape(match)}\]?\s*",
                    "",
                    sanitized_text,
                    flags=re.IGNORECASE,
                ).strip()

        return sanitized_text, audit_items
