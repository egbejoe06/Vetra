<script setup lang="ts">
import type { QuestionScoreItem } from '@/types'

interface Props {
  questionScores: QuestionScoreItem[]
}

defineProps<Props>()
</script>

<template>
  <div class="bg-surface-container border border-outline-variant/30 rounded-2xl p-6 shadow-xl space-y-4">
    <div class="flex items-center justify-between border-b border-surface-container-highest pb-3">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-primary text-[20px]">quiz</span>
        <h3 class="text-xs font-semibold text-on-surface uppercase tracking-wider">
          Question-by-Question Breakdown
        </h3>
      </div>
      <span class="text-xs text-on-surface-variant font-mono">{{ questionScores.length }} questions scored</span>
    </div>

    <div class="space-y-3">
      <div
        v-for="(q, idx) in questionScores"
        :key="idx"
        class="bg-surface-container-low p-4 rounded-xl border border-outline-variant/20 flex flex-col md:flex-row md:items-start justify-between gap-4"
      >
        <div class="flex-1 space-y-2">
          <div class="flex items-start gap-2.5">
            <span class="w-6 h-6 rounded-lg bg-surface-container-highest flex items-center justify-center text-primary font-mono text-xs font-bold shrink-0">
              Q{{ idx + 1 }}
            </span>
            <h4 class="text-sm font-semibold text-on-surface leading-snug">
              {{ q.question_text }}
            </h4>
          </div>

          <p v-if="q.feedback" class="text-xs text-on-surface-variant pl-8 leading-relaxed">
            <span class="text-outline font-semibold">Evaluator Notes:</span> {{ q.feedback }}
          </p>

          <div v-if="q.verified_turn_ids && q.verified_turn_ids.length > 0" class="pl-8 flex items-center gap-1.5 pt-1">
            <span class="text-[10px] text-outline">Verified turns:</span>
            <span
              v-for="tId in q.verified_turn_ids"
              :key="tId"
              class="px-1.5 py-0.5 rounded bg-surface-container-high text-primary text-[10px] font-mono border border-outline-variant/20"
            >
              {{ tId }}
            </span>
          </div>
        </div>

        <div
          v-if="q.score != null && q.status !== 'NOT_ASSESSED'"
          class="flex items-baseline gap-1 bg-surface-container px-3 py-1.5 rounded-lg border border-outline-variant/20 shrink-0 self-start md:self-center"
        >
          <span class="text-base font-bold" :class="q.score >= 4.0 ? 'text-emerald-400' : q.score >= 3.0 ? 'text-primary' : 'text-amber-400'">
            {{ q.score.toFixed(1) }}
          </span>
          <span class="text-[10px] text-outline">/ 5.0</span>
        </div>
        <div
          v-else
          class="flex items-center gap-1 bg-surface-container px-2.5 py-1.5 rounded-lg border border-outline-variant/20 shrink-0 self-start md:self-center"
        >
          <span class="text-[11px] font-semibold text-outline tracking-wider uppercase">Not Assessed</span>
        </div>
      </div>
    </div>
  </div>
</template>
