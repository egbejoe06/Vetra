<script setup lang="ts">
import { computed } from 'vue'
import { InterviewStage } from '@/types'

interface Props {
  currentStage: InterviewStage
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'select-stage', stage: InterviewStage): void
}>()

const stages = [
  { id: InterviewStage.INTRO, label: 'Intro', icon: 'waving_hand' },
  { id: InterviewStage.RESUME_DEEP_DIVE, label: 'Resume', icon: 'badge' },
  { id: InterviewStage.TECHNICAL_QA, label: 'Tech Q&A', icon: 'psychology' },
  { id: InterviewStage.TECHNICAL_EXERCISE, label: 'Coding IDE', icon: 'terminal' },
  { id: InterviewStage.BEHAVIORAL, label: 'Behavioral', icon: 'groups' },
  { id: InterviewStage.WRAP_UP, label: 'Wrap-up', icon: 'check_circle' },
]

const currentIndex = computed(() => {
  return stages.findIndex((s) => s.id === props.currentStage)
})
</script>

<template>
  <div class="flex items-center gap-1 sm:gap-2 px-3 py-1.5 bg-surface-container-low rounded-xl border border-outline-variant/20 overflow-x-auto max-w-full">
    <div
      v-for="(stage, idx) in stages"
      :key="stage.id"
      class="flex items-center gap-1 sm:gap-1.5"
    >
      <button
        class="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap"
        :class="[
          idx === currentIndex
            ? 'bg-primary text-on-primary shadow-sm font-semibold'
            : idx < currentIndex
              ? 'text-emerald-400 bg-surface-container hover:bg-surface-container-high'
              : 'text-outline hover:text-on-surface-variant hover:bg-surface-container-low'
        ]"
        @click="emit('select-stage', stage.id)"
      >
        <span
          class="material-symbols-outlined text-[15px]"
          :class="idx <= currentIndex ? 'fill' : ''"
        >
          {{ idx < currentIndex ? 'check_circle' : stage.icon }}
        </span>
        <span class="hidden md:inline">{{ stage.label }}</span>
      </button>

      <!-- Connector line -->
      <div
        v-if="idx < stages.length - 1"
        class="w-2 sm:w-4 h-[1px]"
        :class="idx < currentIndex ? 'bg-emerald-500/50' : 'bg-outline-variant/30'"
      />
    </div>
  </div>
</template>
