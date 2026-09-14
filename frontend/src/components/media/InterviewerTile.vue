<script setup lang="ts">
import AudioVisualizer from './AudioVisualizer.vue'

interface Props {
  isSpeaking?: boolean
  audioLevel?: number
  isPiP?: boolean
}

withDefaults(defineProps<Props>(), {
  isSpeaking: false,
  audioLevel: 0,
  isPiP: false,
})
</script>

<template>
  <div
    class="relative rounded-2xl overflow-hidden bg-surface-container-low border transition-all duration-300 flex flex-col items-center justify-center shadow-lg"
    :class="[
      isPiP ? 'w-56 h-36 border-outline-variant/40' : 'w-full h-full border-outline-variant/20',
      isSpeaking ? 'ring-2 ring-primary/80 shadow-[0_0_30px_rgba(138,180,248,0.2)]' : ''
    ]"
  >
    <!-- Ambient glowing backdrop when speaking -->
    <div
      class="absolute inset-0 transition-opacity duration-500 pointer-events-none"
      :class="isSpeaking ? 'opacity-30' : 'opacity-10'"
    >
      <div
        class="absolute -top-10 -left-10 w-48 h-48 rounded-full bg-primary/40 blur-[80px] animate-pulse"
      />
      <div
        class="absolute -bottom-10 -right-10 w-48 h-48 rounded-full bg-tertiary/30 blur-[80px] animate-pulse"
      />
    </div>

    <!-- Central AI Avatar -->
    <div class="relative flex flex-col items-center justify-center gap-3 z-10">
      <!-- Pulsing Ring Outer Container -->
      <div class="relative flex items-center justify-center">
        <div
          v-if="isSpeaking"
          class="absolute inset-0 rounded-full ai-gradient-bg animate-ping opacity-30 scale-125"
        />
        <div
          class="rounded-full p-1 border border-outline-variant/40 bg-surface-container shadow-xl transition-transform duration-300"
          :class="[
            isPiP ? 'w-16 h-16' : 'w-28 h-28',
            isSpeaking ? 'scale-105 border-primary/50' : ''
          ]"
        >
          <div
            class="w-full h-full rounded-full flex items-center justify-center transition-all overflow-hidden relative"
            :class="isSpeaking ? 'ai-gradient-bg text-white' : 'bg-surface-container-highest text-primary'"
          >
            <span
              class="material-symbols-outlined select-none"
              :class="isPiP ? 'text-[28px]' : 'text-[44px]'"
              style="font-variation-settings: 'FILL' 1;"
            >
              psychology
            </span>
          </div>
        </div>
      </div>

      <!-- Speaking State Text / Waveform -->
      <div v-if="!isPiP" class="flex flex-col items-center gap-1 mt-1">
        <span class="text-sm font-semibold text-on-surface flex items-center gap-1.5">
          Vetra AI Interviewer
        </span>
        <div class="flex items-center gap-1.5 h-6">
          <AudioVisualizer :level="audioLevel" :bar-count="5" color="ai" />
          <span class="text-xs font-medium text-on-surface-variant">
            {{ isSpeaking ? 'Speaking...' : 'Listening...' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Bottom Tag (Google Meet style) -->
    <div
      class="absolute bottom-2.5 left-2.5 right-2.5 flex items-center justify-between pointer-events-none z-10"
    >
      <div
        class="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container-lowest/80 backdrop-blur-md border border-outline-variant/30 text-xs font-medium text-on-surface shadow-sm"
      >
        <span class="w-2 h-2 rounded-full ai-gradient-bg" />
        <span>Vetra AI</span>
      </div>

      <div
        v-if="isSpeaking"
        class="px-2 py-0.5 rounded-full bg-primary/20 border border-primary/40 text-primary text-[11px] font-medium backdrop-blur-md"
      >
        Live Voice
      </div>
    </div>
  </div>
</template>
