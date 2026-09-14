<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import AudioVisualizer from './AudioVisualizer.vue'

interface Props {
  candidateName: string
  isEnabled?: boolean
  isMuted?: boolean
  audioLevel?: number
  isPiP?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isEnabled: false,
  isMuted: false,
  audioLevel: 0,
  isPiP: false,
})

const videoElement = ref<HTMLVideoElement | null>(null)
let stream: MediaStream | null = null

async function startCamera() {
  if (!props.isEnabled) {
    stopCamera()
    return
  }

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: 'user',
      },
      audio: false,
    })

    if (videoElement.value) {
      videoElement.value.srcObject = stream
    }
  } catch (err) {
    console.warn('[VideoTile] Webcam access not available or permission denied:', err)
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop())
    stream = null
  }
  if (videoElement.value) {
    videoElement.value.srcObject = null
  }
}

watch(
  () => props.isEnabled,
  (enabled) => {
    if (enabled) startCamera()
    else stopCamera()
  },
)

onMounted(() => {
  if (props.isEnabled) {
    startCamera()
  }
})

onUnmounted(() => {
  stopCamera()
})
</script>

<template>
  <div
    class="relative rounded-2xl overflow-hidden bg-surface-container-low border transition-all duration-300 flex items-center justify-center shadow-lg"
    :class="[
      isPiP ? 'w-56 h-36 border-outline-variant/40' : 'w-full h-full border-outline-variant/20',
      audioLevel > 15 ? 'ring-2 ring-primary/60' : ''
    ]"
  >
    <!-- Video Stream Feed -->
    <video
      v-show="isEnabled"
      ref="videoElement"
      autoplay
      playsinline
      muted
      class="w-full h-full object-cover -scale-x-100"
    />

    <!-- Fallback Avatar when Camera is Off -->
    <div
      v-if="!isEnabled"
      class="flex flex-col items-center justify-center gap-3 w-full h-full bg-surface-container"
    >
      <div
        class="w-16 h-16 rounded-full bg-surface-container-highest border border-outline-variant/40 flex items-center justify-center text-on-surface font-semibold text-xl shadow-inner"
      >
        {{ candidateName.charAt(0).toUpperCase() }}
      </div>
      <span class="text-xs text-on-surface-variant">Camera Disabled</span>
    </div>

    <!-- Candidate Name Tag & Mic Indicator -->
    <div
      class="absolute bottom-2.5 left-2.5 right-2.5 flex items-center justify-between pointer-events-none z-10"
    >
      <div
        class="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container-lowest/80 backdrop-blur-md border border-outline-variant/30 text-xs font-medium text-on-surface shadow-sm"
      >
        <span class="truncate max-w-[120px]">{{ candidateName }} (You)</span>
      </div>

      <!-- Live Mic / Speaking Waveform -->
      <div class="flex items-center gap-1">
        <div
          v-if="isMuted"
          class="p-1 rounded-full bg-error/20 border border-error/40 text-error backdrop-blur-md"
        >
          <span class="material-symbols-outlined text-[14px]">mic_off</span>
        </div>
        <div
          v-else-if="audioLevel > 5"
          class="px-1 py-0.5 rounded-full bg-surface-container-lowest/80 backdrop-blur-md border border-outline-variant/30"
        >
          <AudioVisualizer :level="audioLevel" :bar-count="3" color="primary" />
        </div>
      </div>
    </div>
  </div>
</template>
