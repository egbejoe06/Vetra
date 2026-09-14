<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { TranscriptSpeaker, type DialogueTurn } from '@/types'

interface Props {
  turns: DialogueTurn[]
  interimCandidateText?: string
  interimInterviewerText?: string
}

const props = withDefaults(defineProps<Props>(), {
  interimCandidateText: '',
  interimInterviewerText: '',
})

const emit = defineEmits<{
  (e: 'send-message', text: string): void
}>()

const scrollContainer = ref<HTMLDivElement | null>(null)
const typedInput = ref<string>('')

function scrollToBottom() {
  nextTick(() => {
    if (scrollContainer.value) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    }
  })
}

watch(
  () => [props.turns.length, props.interimCandidateText, props.interimInterviewerText],
  () => {
    scrollToBottom()
  },
  { deep: true },
)

function handleSendMessage() {
  if (!typedInput.value.trim()) return
  emit('send-message', typedInput.value.trim())
  typedInput.value = ''
  scrollToBottom()
}
</script>

<template>
  <div class="flex flex-col h-full bg-surface-container border border-outline-variant/30 rounded-2xl overflow-hidden shadow-lg">
    <!-- Header -->
    <div class="px-4 py-3 border-b border-surface-container-highest flex items-center justify-between bg-surface-container-low">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-primary text-[18px]">forum</span>
        <h3 class="text-xs font-semibold text-on-surface uppercase tracking-wider">Live Transcript Feed</h3>
      </div>
      <span class="text-[11px] font-mono text-on-surface-variant bg-surface-container-high px-2 py-0.5 rounded">
        {{ turns.length }} turns
      </span>
    </div>

    <!-- Message List -->
    <div ref="scrollContainer" class="flex-1 p-4 overflow-y-auto space-y-4">
      <!-- Empty placeholder -->
      <div
        v-if="turns.length === 0 && !interimCandidateText && !interimInterviewerText"
        class="h-full flex flex-col items-center justify-center text-center p-6 text-on-surface-variant gap-2"
      >
        <span class="material-symbols-outlined text-[32px] text-outline">graphic_eq</span>
        <p class="text-xs">Dialogue will appear here in real-time as you speak with the AI interviewer.</p>
      </div>

      <!-- Dialogue turns -->
      <div
        v-for="(turn, idx) in turns"
        :key="idx"
        class="flex flex-col gap-1 text-xs"
        :class="turn.speaker === TranscriptSpeaker.CANDIDATE ? 'items-end' : 'items-start'"
      >
        <!-- Speaker label & time -->
        <div class="flex items-center gap-1.5 px-1 text-[10px] text-on-surface-variant">
          <span
            v-if="turn.turn_id"
            class="font-mono text-outline bg-surface-container-highest px-1.5 py-0.2 rounded"
          >
            {{ turn.turn_id }}
          </span>
          <span class="font-medium" :class="turn.speaker === TranscriptSpeaker.CANDIDATE ? 'text-primary' : 'text-tertiary'">
            {{ turn.speaker === TranscriptSpeaker.CANDIDATE ? 'You' : turn.speaker === TranscriptSpeaker.INTERVIEWER ? 'Vetra AI' : 'System' }}
          </span>
        </div>

        <!-- Bubble -->
        <div
          class="max-w-[85%] rounded-2xl px-3.5 py-2.5 leading-relaxed"
          :class="[
            turn.speaker === TranscriptSpeaker.CANDIDATE
              ? 'bg-primary/20 text-on-surface border border-primary/30 rounded-tr-sm'
              : turn.speaker === TranscriptSpeaker.INTERVIEWER
                ? 'bg-surface-container-high text-on-surface border border-outline-variant/30 rounded-tl-sm'
                : 'bg-surface-container-lowest text-on-surface-variant italic border border-outline-variant/20'
          ]"
        >
          {{ turn.content }}
        </div>
      </div>

      <!-- Live Interim Candidate Speech (streaming) -->
      <div
        v-if="interimCandidateText"
        class="flex flex-col items-end gap-1 text-xs animate-pulse"
      >
        <div class="flex items-center gap-1 text-[10px] text-primary">
          <span>You (transcribing...)</span>
        </div>
        <div class="max-w-[85%] rounded-2xl px-3.5 py-2.5 bg-primary/10 text-on-surface border border-primary/20 rounded-tr-sm italic">
          {{ interimCandidateText }}
        </div>
      </div>

      <!-- Live Interim Interviewer Speech (streaming) -->
      <div
        v-if="interimInterviewerText"
        class="flex flex-col items-start gap-1 text-xs animate-pulse"
      >
        <div class="flex items-center gap-1 text-[10px] text-tertiary">
          <span>Vetra AI (speaking...)</span>
        </div>
        <div class="max-w-[85%] rounded-2xl px-3.5 py-2.5 bg-surface-container-high text-on-surface border border-outline-variant/30 rounded-tl-sm italic">
          {{ interimInterviewerText }}
        </div>
      </div>
    </div>

    <!-- Typed Message Input Bar (Backup / fallback chat) -->
    <div class="p-2.5 bg-surface-container-low border-t border-surface-container-highest">
      <form class="flex items-center gap-2" @submit.prevent="handleSendMessage">
        <input
          v-model="typedInput"
          type="text"
          placeholder="Type your response or question..."
          class="flex-1 bg-surface-container-high border border-outline-variant/30 rounded-full px-4 py-2 text-xs text-on-surface placeholder:text-outline focus:outline-none focus:border-primary/50"
        />
        <button
          type="submit"
          class="p-2 rounded-full bg-primary text-on-primary hover:bg-primary-fixed transition-colors disabled:opacity-40"
          :disabled="!typedInput.trim()"
        >
          <span class="material-symbols-outlined text-[16px]">send</span>
        </button>
      </form>
    </div>
  </div>
</template>
