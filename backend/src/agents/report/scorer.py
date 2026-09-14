import logging
from typing import Dict, List, Optional, Tuple

from src.models.enums import CandidateRecommendation
from src.schemas.report import GroundedRubricScore, ScoreBreakdown

logger = logging.getLogger("vetra.agents.report.scorer")


class DeterministicScorer:
    """Deterministic mathematical scoring engine.
    
    Prevents LLM score drift across runs by strictly computing the overall candidate score
    and hiring recommendation via deterministic weighted aggregation.
    """

    # Default calibrated rubric weights (must sum to 1.0)
    # Communication is intentionally excluded to prevent speech-to-text transcription artifacts from impacting scores.
    DEFAULT_RUBRIC_WEIGHTS: Dict[str, float] = {
        "Technical Depth & Mastery": 0.35,
        "Problem Solving & Algorithms": 0.30,
        "Code Quality & Architecture": 0.20,
        "Scalability & Failure Modes": 0.15,
    }

    # Alternate category name aliases for flexible rubric mapping
    CATEGORY_ALIASES: Dict[str, str] = {
        "technical depth": "Technical Depth & Mastery",
        "technical_depth": "Technical Depth & Mastery",
        "problem solving": "Problem Solving & Algorithms",
        "problem_solving": "Problem Solving & Algorithms",
        "code quality": "Code Quality & Architecture",
        "code_quality": "Code Quality & Architecture",
        "scalability": "Scalability & Failure Modes",
        "system design": "Scalability & Failure Modes",
        "system_design": "Scalability & Failure Modes",
    }

    @classmethod
    def compute_scorecard(
        cls,
        rubric_scores: List[GroundedRubricScore],
        is_incomplete: bool = False,
    ) -> Tuple[Optional[float], ScoreBreakdown, CandidateRecommendation]:
        """Calculates deterministic overall score, detailed breakdown, and recommendation.
        
        Strictly preserves the distinction between NOT_ASSESSED and ATTEMPTED:
        - NOT_ASSESSED rubrics are excluded from scoring math (never defaulted to 1/5).
        - If the interview was incomplete or any required category was NOT_ASSESSED,
          the recommendation is strictly guarded to INCONCLUSIVE.
        """
        raw_scores: Dict[str, float] = {}
        assigned_weights: Dict[str, float] = {}
        assessed_categories: List[str] = []
        unassessed_categories: List[str] = []

        # 1. Map incoming rubric scores to canonical categories & separate assessed vs unassessed
        for r in rubric_scores:
            canonical = cls.CATEGORY_ALIASES.get(r.category.lower().strip(), r.category)
            if r.status == "NOT_ASSESSED" or r.score is None:
                if canonical not in unassessed_categories:
                    unassessed_categories.append(canonical)
            else:
                score = max(1.0, min(5.0, float(r.score)))
                raw_scores[canonical] = score
                if canonical not in assessed_categories:
                    assessed_categories.append(canonical)

        # 2. Determine normalized weights for assessed categories
        total_weight = 0.0
        for cat in raw_scores:
            w = cls.DEFAULT_RUBRIC_WEIGHTS.get(cat, 1.0 / len(raw_scores))
            assigned_weights[cat] = w
            total_weight += w

        # Normalize weights to exactly 1.0 among assessed categories
        if total_weight > 0:
            for cat in assigned_weights:
                assigned_weights[cat] = round(assigned_weights[cat] / total_weight, 4)

        # 3. Compute weighted composite score (1.0 - 5.0 scale)
        if raw_scores:
            weighted_composite = sum(
                raw_scores[cat] * assigned_weights[cat] for cat in raw_scores
            )
            overall_score: Optional[float] = round(weighted_composite * 2.0, 1)
            overall_score = max(0.0, min(10.0, overall_score))
        else:
            weighted_composite = 0.0
            overall_score = None

        # 4. Derive deterministic recommendation with Incomplete Guard
        # If interview was incomplete or critical categories (coding) were unassessed,
        # constrain recommendation to INCONCLUSIVE (insufficient evidence).
        if is_incomplete or len(unassessed_categories) > 0 or overall_score is None:
            recommendation = CandidateRecommendation.INCONCLUSIVE
        else:
            recommendation = cls._derive_recommendation(overall_score)

        breakdown = ScoreBreakdown(
            weights=assigned_weights,
            raw_category_scores=raw_scores,
            weighted_composite=round(weighted_composite, 3),
            calibrated_overall_score=overall_score,
            assessed_categories=assessed_categories,
            unassessed_categories=unassessed_categories,
        )

        return overall_score, breakdown, recommendation

    @classmethod
    def _derive_recommendation(cls, overall_score: float) -> CandidateRecommendation:
        """Determines hiring recommendation based on strict calibrated score bands."""
        if overall_score >= 8.5:
            return CandidateRecommendation.STRONG_HIRE
        elif overall_score >= 7.0:
            return CandidateRecommendation.HIRE
        elif overall_score >= 5.5:
            return CandidateRecommendation.LEAN_HIRE
        elif overall_score >= 4.0:
            return CandidateRecommendation.LEAN_REJECT
        else:
            return CandidateRecommendation.REJECT

