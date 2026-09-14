<script setup lang="ts">
import type { RubricScoreItem } from '@/types'

interface Props {
  rubricScores: RubricScoreItem[]
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'navigate-turn', turnId: string): void
}>()
</script>

<template>
  <div class="bg-surface-container border border-outline-variant/30 rounded-2xl p-6 shadow-xl space-y-4">
    <div class="flex items-center justify-between border-b border-surface-container-highest pb-3">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-primary text-[20px]">grading</span>
        <h3 class="text-xs font-semibold text-on-surface uppercase tracking-wider">
          Grounded Competency Rubrics
        </h3>
      </div>
      <span class="text-xs text-on-surface-variant font-mono">Calibrated (1.0 - 5.0)</span>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div
        v-for="(rubric, idx) in rubricScores"
        :key="idx"
        class="bg-surface-container-low p-4 rounded-xl border border-outline-variant/20 flex flex-col justify-between gap-3"
      >
        <div>
          <div class="flex items-center justify-between">
            <h4 class="text-sm font-semibold text-on-surface">{{ rubric.category }}</h4>
            <div class="flex items-center gap-2">
              <span v-if="rubric.weight" class="text-[10px] text-outline font-mono">
                ({{ Math.round(rubric.weight * 100) }}% weight)
              </span>
              <div
                v-if="rubric.score != null && rubric.status !== 'NOT_ASSESSED'"
                class="flex items-baseline gap-1 bg-surface-container px-2 py-0.5 rounded-md border border-outline-variant/20"
              >
                <span class="text-sm font-bold text-primary">{{ rubric.score.toFixed(1) }}</span>
                <span class="text-[10px] text-outline">/ 5.0</span>
              </div>
              <div
                v-else
                class="flex items-center gap-1 bg-surface-container px-2 py-0.5 rounded-md border border-outline-variant/20"
              >
                <span class="text-[11px] font-semibold text-outline tracking-wider uppercase">Not Assessed</span>
              </div>
            </div>
          </div>

          <!-- Score Progress Bar -->
          <div class="w-full h-1.5 bg-surface-container-highest rounded-full overflow-hidden mt-2">
            <div
              v-if="rubric.score != null && rubric.status !== 'NOT_ASSESSED'"
              class="h-full rounded-full transition-all duration-500"
              :class="rubric.score >= 4.0 ? 'bg-emerald-400' : rubric.score >= 3.0 ? 'bg-primary' : 'bg-amber-400'"
              :style="{ width: `${(rubric.score / 5.0) * 100}%` }"
            />
            <div
              v-else
              class="h-full rounded-full bg-outline-variant/25"
              style="width: 100%"
            />
          </div>

          <!-- Qualitative Feedback -->
          <p class="text-xs text-on-surface-variant mt-3 leading-relaxed">
            {{ rubric.feedback }}
          </p>
        </div>

        <!-- Verified / Cited Turn IDs -->
        <div
          v-if="(rubric.verified_turn_ids && rubric.verified_turn_ids.length > 0) || (rubric.cited_turn_ids && rubric.cited_turn_ids.length > 0)"
          class="flex flex-wrap items-center gap-1.5 pt-2 border-t border-surface-container-highest/50"
        >
          <span class="text-[10px] text-outline">Evidence turns:</span>
          <button
            v-for="tId in (rubric.verified_turn_ids || rubric.cited_turn_ids || [])"
            :key="tId"
            class="px-1.5 py-0.5 rounded bg-surface-container-high hover:bg-primary/20 text-primary text-[10px] font-mono border border-outline-variant/20 hover:border-primary/40 transition-colors"
            @click="emit('navigate-turn', tId)"
          >
            {{ tId }}
          </button>
        </div>
        <div
          v-else-if="rubric.status === 'NOT_ASSESSED' || rubric.score == null"
          class="pt-2 border-t border-surface-container-highest/30 text-[10px] text-outline italic"
        >
          Stage not reached before interview ended — no evidence collected.
        </div>
      </div>
    </div>
  </div>
</template>
