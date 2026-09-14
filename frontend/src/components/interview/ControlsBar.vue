<script setup lang="ts">
import { computed } from 'vue'
import { useRealtimeStore } from '@/stores/realtime'
import { useWorkspaceStore } from '@/stores/workspace'

interface Props {
  isTranscriptOpen?: boolean
  isProblemOpen?: boolean
}

withDefaults(defineProps<Props>(), {
  isTranscriptOpen: false,
  isProblemOpen: false,
})

const emit = defineEmits<{
  (e: 'toggle-transcript'): void
  (e: 'toggle-problem'): void
  (e: 'end-interview'): void
}>()

const realtimeStore = useRealtimeStore()
const workspaceStore = useWorkspaceStore()

const isCodingMode = computed(() => workspaceStore.layoutMode === 'coding')
</script>

<template>
  <div class="flex items-center justify-between px-6 py-3 bg-surface-container/95 backdrop-blur-md border-t border-surface-container-highest z-20">
    <!-- Left: Layout Switcher & Problem Drawer -->
    <div class="flex items-center gap-2">
      <!-- Discussion vs Coding Mode Button -->
      <button
        class="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold border transition-all"
        :class="[
          isCodingMode
            ? 'bg-primary/20 text-primary border-primary/40'
            : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface border-outline-variant/30'
        ]"
        @click="workspaceStore.toggleLayoutMode()"
      >
        <span class="material-symbols-outlined text-[18px]">
          {{ isCodingMode ? 'code' : 'co_present' }}
        </span>
        <span class="hidden sm:inline">
          {{ isCodingMode ? 'IDE Mode (Active)' : 'Discussion Mode' }}
        </span>
      </button>

      <!-- Problem Prompt Drawer Toggle -->
      <button
        class="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium border transition-all"
        :class="[
          isProblemOpen
            ? 'bg-tertiary/20 text-tertiary border-tertiary/40'
            : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface border-outline-variant/30'
        ]"
        @click="emit('toggle-problem')"
      >
        <span class="material-symbols-outlined text-[18px]">assignment</span>
        <span class="hidden sm:inline">Problem</span>
      </button>
    </div>

    <!-- Center: Main Call Audio/Video Controls (Google Meet Style) -->
    <div class="flex items-center gap-3">
      <!-- Microphone Toggle -->
      <button
        class="w-11 h-11 rounded-full flex items-center justify-center transition-all shadow-md"
        :class="[
          realtimeStore.isMicMuted
            ? 'bg-error text-white hover:bg-error/90'
            : 'bg-surface-container-highest text-on-surface hover:bg-surface-variant'
        ]"
        :title="realtimeStore.isMicMuted ? 'Unmute microphone' : 'Mute microphone'"
        @click="realtimeStore.toggleMute()"
      >
        <span class="material-symbols-outlined text-[20px]">
          {{ realtimeStore.isMicMuted ? 'mic_off' : 'mic' }}
        </span>
      </button>

      <!-- Camera Toggle -->
      <button
        class="w-11 h-11 rounded-full flex items-center justify-center transition-all shadow-md"
        :class="[
          !realtimeStore.isCameraEnabled
            ? 'bg-error text-white hover:bg-error/90'
            : 'bg-surface-container-highest text-on-surface hover:bg-surface-variant'
        ]"
        :title="realtimeStore.isCameraEnabled ? 'Turn camera off' : 'Turn camera on'"
        @click="realtimeStore.toggleCamera()"
      >
        <span class="material-symbols-outlined text-[20px]">
          {{ realtimeStore.isCameraEnabled ? 'videocam' : 'videocam_off' }}
        </span>
      </button>

      <!-- End Call Button -->
      <button
        class="w-14 h-11 rounded-full bg-error text-white hover:bg-error/90 flex items-center justify-center transition-all shadow-md ml-2"
        title="End Interview"
        @click="emit('end-interview')"
      >
        <span class="material-symbols-outlined text-[22px]">call_end</span>
      </button>
    </div>

    <!-- Right: Transcript & Info Drawers -->
    <div class="flex items-center gap-2">
      <!-- Transcript Drawer Toggle -->
      <button
        class="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-medium border transition-all"
        :class="[
          isTranscriptOpen
            ? 'bg-primary text-on-primary border-primary'
            : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface border-outline-variant/30'
        ]"
        @click="emit('toggle-transcript')"
      >
        <span class="material-symbols-outlined text-[18px]">chat</span>
        <span class="hidden sm:inline">Transcript</span>
      </button>
    </div>
  </div>
</template>
