<script setup lang="ts">
import { computed, ref } from 'vue'
import { TranscriptSpeaker, type TranscriptTurnResponse } from '@/types'

interface Props {
  transcriptTurns: TranscriptTurnResponse[]
  highlightedTurnId?: string
}

const props = defineProps<Props>()

const searchQuery = ref('')
const selectedSpeaker = ref<string>('ALL')

const filteredTurns = computed(() => {
  return props.transcriptTurns.filter((turn) => {
    const matchesSpeaker =
      selectedSpeaker.value === 'ALL' || turn.speaker === selectedSpeaker.value
    const matchesSearch =
      !searchQuery.value.trim() ||
      turn.content.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      (turn.turn_id && turn.turn_id.toLowerCase().includes(searchQuery.value.toLowerCase()))
    return matchesSpeaker && matchesSearch
  })
})

function getTurnLabel(turn: TranscriptTurnResponse, idx: number): string {
  if (turn.turn_id) return turn.turn_id
  if (turn.turn_index) return `turn_${String(turn.turn_index).padStart(3, '0')}`
  return `turn_${String(idx + 1).padStart(3, '0')}`
}
</script>

<template>
  <div class="bg-surface-container border border-outline-variant/30 rounded-2xl p-6 shadow-xl space-y-4">
    <!-- Header & Filters -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-surface-container-highest pb-4">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-primary text-[20px]">history_edu</span>
        <h3 class="text-xs font-semibold text-on-surface uppercase tracking-wider">
          Chronological Audit Transcript
        </h3>
      </div>

      <!-- Search & Speaker Filter -->
      <div class="flex items-center gap-2">
        <div class="relative">
          <span class="material-symbols-outlined absolute left-2.5 top-2 text-outline text-[16px]">search</span>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search dialogue or turn ID..."
            class="bg-surface-container-low border border-outline-variant/30 rounded-lg pl-8 pr-3 py-1.5 text-xs text-on-surface placeholder:text-outline focus:outline-none focus:border-primary/50"
          />
        </div>

        <select
          v-model="selectedSpeaker"
          class="bg-surface-container-low border border-outline-variant/30 rounded-lg px-2.5 py-1.5 text-xs text-on-surface focus:outline-none focus:border-primary/50"
        >
          <option value="ALL">All Speakers</option>
          <option :value="TranscriptSpeaker.INTERVIEWER">Interviewer</option>
          <option :value="TranscriptSpeaker.CANDIDATE">Candidate</option>
          <option :value="TranscriptSpeaker.SYSTEM">System</option>
        </select>
      </div>
    </div>

    <!-- Transcript Stream -->
    <div class="space-y-3 max-h-[500px] overflow-y-auto pr-2">
      <div
        v-if="filteredTurns.length === 0"
        class="text-center py-8 text-on-surface-variant text-xs"
      >
        No dialogue turns found matching filters.
      </div>

      <div
        v-for="(turn, idx) in filteredTurns"
        :id="getTurnLabel(turn, idx)"
        :key="turn.id || idx"
        class="p-3.5 rounded-xl border transition-all duration-300 space-y-1.5"
        :class="[
          highlightedTurnId === getTurnLabel(turn, idx)
            ? 'bg-primary/10 border-primary shadow-[0_0_15px_rgba(138,180,248,0.2)]'
            : 'bg-surface-container-low border-outline-variant/20 hover:border-outline-variant/40'
        ]"
      >
        <!-- Speaker tag & metadata -->
        <div class="flex items-center justify-between text-[11px]">
          <div class="flex items-center gap-2">
            <span
              class="font-mono text-outline bg-surface-container-highest px-1.5 py-0.5 rounded text-[10px]"
            >
              {{ getTurnLabel(turn, idx) }}
            </span>
            <span
              class="font-semibold"
              :class="turn.speaker === TranscriptSpeaker.CANDIDATE ? 'text-primary' : turn.speaker === TranscriptSpeaker.INTERVIEWER ? 'text-tertiary' : 'text-on-surface-variant'"
            >
              {{ turn.speaker === TranscriptSpeaker.CANDIDATE ? 'Candidate' : turn.speaker === TranscriptSpeaker.INTERVIEWER ? 'Vetra AI' : 'System' }}
            </span>
            <span class="text-[10px] text-outline font-mono">
              [{{ turn.stage }}]
            </span>
          </div>

          <span class="text-[10px] text-outline font-mono">
            {{ new Date(turn.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }}
          </span>
        </div>

        <!-- Dialogue Content -->
        <p class="text-xs text-on-surface leading-relaxed whitespace-pre-wrap pl-1">
          {{ turn.content }}
        </p>
      </div>
    </div>
  </div>
</template>
