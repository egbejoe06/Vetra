<script setup lang="ts">
import { CandidateRecommendation, type InterviewEvaluationResponse } from '@/types'
import Badge from '@/components/common/Badge.vue'

interface Props {
  evaluation: InterviewEvaluationResponse
  jobTitle?: string
  showHiringSignal?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showHiringSignal: true,
})

function getRecommendationVariant(rec: CandidateRecommendation) {
  switch (rec) {
    case CandidateRecommendation.STRONG_HIRE:
    case CandidateRecommendation.HIRE:
      return 'success'
    case CandidateRecommendation.LEAN_HIRE:
      return 'primary'
    case CandidateRecommendation.LEAN_REJECT:
      return 'warning'
    case CandidateRecommendation.REJECT:
      return 'error'
    case CandidateRecommendation.INCONCLUSIVE:
      return 'secondary'
    default:
      return 'secondary'
  }
}
</script>

<template>
  <div class="bg-surface-container border border-outline-variant/30 rounded-2xl p-6 shadow-xl space-y-6">
    <!-- Incomplete Interview Warning Banner -->
    <div
      v-if="evaluation.completion_status === 'INCOMPLETE' || evaluation.recommendation === CandidateRecommendation.INCONCLUSIVE"
      class="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs flex items-start gap-3"
    >
      <span class="material-symbols-outlined text-[22px] text-amber-400 shrink-0 mt-0.5">info</span>
      <div class="space-y-1">
        <div class="font-semibold text-amber-300 text-sm flex items-center gap-2">
          <span>Interview Incomplete — Inconclusive Evidence</span>
          <span
            v-if="evaluation.stages_not_reached && evaluation.stages_not_reached.length > 0"
            class="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 text-[10px] uppercase font-mono font-semibold"
          >
            {{ evaluation.stages_not_reached.length }} stage{{ evaluation.stages_not_reached.length > 1 ? 's' : '' }} unreached
          </span>
        </div>
        <p class="text-on-surface-variant leading-relaxed text-xs">
          This interview session concluded early before reaching all planned stages (e.g. Coding Exercise or Behavioral).
          Unreached stages are marked as <strong class="text-on-surface">Not Assessed</strong> without score penalty.
          The hiring signal is set to <strong class="text-amber-300">INCONCLUSIVE</strong> because holistic hiring criteria could not be fully verified.
        </p>
        <div v-if="evaluation.stages_not_reached && evaluation.stages_not_reached.length > 0" class="flex flex-wrap gap-1.5 pt-1">
          <span class="text-[11px] text-outline self-center">Stages Not Reached:</span>
          <span
            v-for="stg in evaluation.stages_not_reached"
            :key="stg"
            class="px-2 py-0.5 rounded bg-surface-container-highest text-on-surface-variant text-[10px] font-mono"
          >
            {{ stg }}
          </span>
        </div>
      </div>
    </div>

    <!-- Header Banner -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-surface-container-highest pb-6">
      <div class="flex items-center gap-4">
        <div class="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary text-xl font-bold shadow-inner">
          {{ evaluation.candidate_name.charAt(0).toUpperCase() }}
        </div>
        <div>
          <h2 class="text-xl font-bold text-on-surface">{{ evaluation.candidate_name }}</h2>
          <p class="text-xs text-on-surface-variant font-mono mt-0.5">
            {{ jobTitle || 'Senior Software Engineer' }} • Session ID: {{ evaluation.session_id.substring(0, 8) }}
          </p>
        </div>
      </div>

      <!-- Recommendation & Calibrated Score -->
      <div class="flex items-center gap-4">
        <div class="flex flex-col items-end">
          <span class="text-[11px] font-semibold text-outline uppercase tracking-wider">
            {{ showHiringSignal ? 'Hiring Signal' : 'Interview Status' }}
          </span>
          <Badge
            v-if="showHiringSignal"
            :variant="getRecommendationVariant(evaluation.recommendation)"
            size="md"
            class="mt-1 font-bold text-xs tracking-wider"
          >
            {{ evaluation.recommendation.replace('_', ' ') }}
          </Badge>
          <Badge
            v-else
            variant="success"
            size="md"
            class="mt-1 font-bold text-xs tracking-wider"
          >
            COMPLETED
          </Badge>
        </div>

        <div class="h-10 w-[1px] bg-surface-container-highest"></div>

        <div class="flex flex-col items-end">
          <span class="text-[11px] font-semibold text-outline uppercase tracking-wider">Overall Score</span>
          <div class="flex items-baseline gap-1 mt-0.5">
            <span class="text-2xl font-bold text-primary">
              {{ evaluation.overall_score != null ? evaluation.overall_score.toFixed(1) : 'N/A' }}
            </span>
            <span v-if="evaluation.overall_score != null" class="text-xs text-outline">/ 10.0</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Executive Summary -->
    <div class="space-y-2">
      <h3 class="text-xs font-semibold text-on-surface uppercase tracking-wider flex items-center gap-1.5">
        <span class="material-symbols-outlined text-primary text-[18px]">summarize</span>
        Executive Assessment Summary
      </h3>
      <p class="text-sm text-on-surface-variant leading-relaxed bg-surface-container-low p-4 rounded-xl border border-outline-variant/20">
        {{ evaluation.summary }}
      </p>
    </div>

    <!-- Strengths & Weaknesses Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <!-- Key Strengths -->
      <div class="bg-surface-container-low p-4 rounded-xl border border-emerald-500/20 space-y-2.5">
        <h4 class="text-xs font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
          <span class="material-symbols-outlined text-[18px]">verified</span>
          Demonstrated Strengths
        </h4>
        <ul class="space-y-1.5 text-xs text-on-surface-variant">
          <li
            v-for="(s, idx) in evaluation.key_strengths"
            :key="idx"
            class="flex items-start gap-2"
          >
            <span class="material-symbols-outlined text-emerald-400 text-[15px] shrink-0 mt-0.5">check</span>
            <span>{{ s }}</span>
          </li>
        </ul>
      </div>

      <!-- Key Weaknesses / Gaps -->
      <div class="bg-surface-container-low p-4 rounded-xl border border-amber-500/20 space-y-2.5">
        <h4 class="text-xs font-semibold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
          <span class="material-symbols-outlined text-[18px]">warning</span>
          Areas for Improvement & Gaps
        </h4>
        <ul class="space-y-1.5 text-xs text-on-surface-variant">
          <li
            v-for="(w, idx) in evaluation.key_weaknesses"
            :key="idx"
            class="flex items-start gap-2"
          >
            <span class="material-symbols-outlined text-amber-300 text-[15px] shrink-0 mt-0.5">arrow_right</span>
            <span>{{ w }}</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- Deterministic Mathematical Score Breakdown (if available) -->
    <div
      v-if="evaluation.score_breakdown"
      class="bg-surface-container-low p-4 rounded-xl border border-outline-variant/20 space-y-3"
    >
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-primary text-[18px]">calculate</span>
          <h4 class="text-xs font-semibold text-on-surface uppercase tracking-wider">
            Deterministic Weighting Formula
          </h4>
        </div>
        <span class="text-[11px] font-mono text-outline">
          Composite: {{ evaluation.score_breakdown.weighted_composite }} / 5.0 → Calibrated: {{ evaluation.overall_score != null ? evaluation.overall_score.toFixed(1) : 'N/A' }} / 10.0
        </span>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 pt-1">
        <div
          v-for="(weight, cat) in evaluation.score_breakdown.weights"
          :key="cat"
          class="bg-surface-container p-2.5 rounded-lg border border-outline-variant/10 text-center space-y-1"
        >
          <div class="text-[10px] text-outline uppercase truncate" :title="String(cat)">{{ cat }}</div>
          <div class="text-xs font-bold text-primary">{{ evaluation.score_breakdown.raw_category_scores[cat]?.toFixed(1) || '—' }} <span class="text-[10px] text-outline font-normal">/ 5</span></div>
          <div class="text-[10px] text-on-surface-variant font-mono">Weight: {{ Math.round(weight * 100) }}%</div>
        </div>
      </div>

      <div v-if="showHiringSignal && evaluation.snapshot_id" class="text-[10px] text-outline font-mono flex items-center gap-1 pt-1">
        <span class="material-symbols-outlined text-[12px]">lock</span>
        <span>Immutable Synthesis Snapshot ID: {{ evaluation.snapshot_id }}</span>
      </div>
    </div>
  </div>
</template>
