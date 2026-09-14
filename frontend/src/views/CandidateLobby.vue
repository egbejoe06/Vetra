<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { useInterviewStore } from '@/stores/interview'
import { useCandidateStore } from '@/stores/candidate'
import AudioVisualizer from '@/components/media/AudioVisualizer.vue'
import VideoTile from '@/components/media/VideoTile.vue'
import Modal from '@/components/common/Modal.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const interviewStore = useInterviewStore()
const candidateStore = useCandidateStore()

const roomCode = ref('')
const candidateName = ref(authStore.candidateName || 'Alex Rivera')
const candidateEmail = ref(authStore.candidateEmail || 'alex.rivera@example.com')

// Camera & Mic states — start explicitly OFF (do not turn on automatically)
const isCameraEnabled = ref(false)
const isMicEnabled = ref(false)
const isMicMuted = ref(false)
const micLevel = ref(0)

const isJoining = ref(false)
const errorMessage = ref<string | null>(null)
const interviewDetails = ref<any | null>(null)
const showDeviceModal = ref(false)

let micStream: MediaStream | null = null
let audioCtx: AudioContext | null = null
let analyser: AnalyserNode | null = null
let animFrame: number | null = null

onMounted(async () => {
  // Check if room code passed in URL
  if (route.query.code) {
    roomCode.value = String(route.query.code)
    fetchInterviewByCode(roomCode.value)
  }
  // Load candidate profile
  await candidateStore.loadProfile()
  // Camera and mic remain strictly OFF on mount until candidate explicitly enables them.
})

onUnmounted(() => {
  stopMicCheck()
})

async function fetchInterviewByCode(code: string) {
  if (code.length !== 6) return
  try {
    const res = await api.getInterviewByCode(code)
    interviewDetails.value = res
  } catch (err: any) {
    interviewDetails.value = null
  }
}

async function enableCamera() {
  errorMessage.value = null
  try {
    // Probe camera access to prompt permission dialog and ensure availability
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: 'user',
      },
      audio: false,
    })
    // Release probe stream; VideoTile will manage its own stream via prop
    stream.getTracks().forEach((track) => track.stop())
    isCameraEnabled.value = true
  } catch (err: any) {
    console.warn('[Lobby] Camera permission denied:', err)
    errorMessage.value = 'Camera permission was denied. Please allow camera access in your browser settings.'
  }
}

function disableCamera() {
  isCameraEnabled.value = false
}

async function enableMicrophone() {
  errorMessage.value = null
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
    audioCtx = new AudioCtx()
    analyser = audioCtx.createAnalyser()
    analyser.fftSize = 256

    const source = audioCtx.createMediaStreamSource(micStream)
    source.connect(analyser)

    const dataArray = new Uint8Array(analyser.frequencyBinCount)
    const updateLevel = () => {
      if (analyser && isMicEnabled.value && !isMicMuted.value) {
        analyser.getByteFrequencyData(dataArray)
        let sum = 0
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i] ?? 0
        }
        const avg = sum / dataArray.length
        micLevel.value = Math.min(100, Math.round((avg / 255) * 200))
      } else {
        micLevel.value = 0
      }
      animFrame = requestAnimationFrame(updateLevel)
    }
    animFrame = requestAnimationFrame(updateLevel)
    isMicEnabled.value = true
    isMicMuted.value = false
  } catch (err: any) {
    console.warn('[Lobby] Microphone permission denied:', err)
    errorMessage.value = 'Microphone permission was denied. Please allow microphone access in your browser settings.'
  }
}

function disableMicrophone() {
  stopMicCheck()
  isMicEnabled.value = false
  micLevel.value = 0
}

async function enableBothDevices() {
  errorMessage.value = null
  await enableCamera()
  await enableMicrophone()
  if (isCameraEnabled.value && isMicEnabled.value) {
    showDeviceModal.value = false
  }
}

function stopMicCheck() {
  if (animFrame) cancelAnimationFrame(animFrame)
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop())
    micStream = null
  }
  if (audioCtx && audioCtx.state !== 'closed') {
    audioCtx.close()
    audioCtx = null
  }
}

async function handleJoinRoom() {
  errorMessage.value = null

  if (!roomCode.value || roomCode.value.length !== 6) {
    errorMessage.value = 'Please enter a valid 6-digit room code.'
    return
  }
  if (!candidateName.value.trim()) {
    errorMessage.value = 'Please enter your full name.'
    return
  }
  if (!candidateEmail.value.trim()) {
    errorMessage.value = 'Please enter your email address.'
    return
  }

  // Ensure BOTH camera and mic are enabled before allowing candidate to enter room
  if (!isCameraEnabled.value || !isMicEnabled.value) {
    showDeviceModal.value = true
    errorMessage.value = 'Camera and microphone must be enabled before you can enter the interview room.'
    return
  }

  isJoining.value = true

  try {
    authStore.setCandidate(candidateName.value.trim(), candidateEmail.value.trim())
    const isRedo = route.query.redo === 'true'
    const res = await interviewStore.joinInterviewByCode(
      roomCode.value.trim(),
      candidateName.value.trim(),
      candidateEmail.value.trim(),
      isRedo,
    )

    if ((res as any).candidate_profile) {
      candidateStore.hydrateFromJoin((res as any).candidate_profile)
    }

    // Stop lobby mic check before entering room
    stopMicCheck()

    // Navigate to live room
    router.push(`/session/${res.session.id}`)
  } catch (err: any) {
    errorMessage.value = err.message
  } finally {
    isJoining.value = false
  }
}
</script>

<template>
  <div class="h-full flex items-center justify-center bg-surface p-4 sm:p-6 overflow-y-auto">
    <div class="w-full max-w-4xl grid grid-cols-1 lg:grid-cols-12 gap-6 bg-surface-container border border-outline-variant/30 rounded-3xl p-6 sm:p-8 shadow-2xl">
      <!-- Left: Device Preview & Verification (7 cols) -->
      <div class="lg:col-span-7 flex flex-col justify-between space-y-4">
        <div>
          <div class="flex items-center gap-2 text-primary font-semibold text-sm">
            <span class="material-symbols-outlined text-[20px]" style="font-variation-settings: 'FILL' 1;">psychology</span>
            <span>Vetra AI Candidate Lobby</span>
          </div>
          <h1 class="text-xl sm:text-2xl font-bold text-on-surface mt-1">Get Ready to Join</h1>
          <p class="text-xs text-on-surface-variant mt-1 leading-relaxed">
            Please enable your camera and microphone below before starting. Devices are kept off until you grant access.
          </p>
        </div>

        <!-- Video & Mic Preview Tile -->
        <div class="h-64 sm:h-72 w-full relative">
          <VideoTile
            :candidate-name="candidateName || 'Candidate'"
            :is-enabled="isCameraEnabled"
            :is-muted="isMicMuted || !isMicEnabled"
            :audio-level="micLevel"
          />

          <!-- Overlay notice when camera is disabled -->
          <div
            v-if="!isCameraEnabled"
            class="absolute inset-0 bg-surface-container/85 backdrop-blur-[2px] rounded-2xl flex flex-col items-center justify-center p-4 text-center space-y-3 pointer-events-none"
          >
            <div class="w-12 h-12 rounded-full bg-surface-container-highest flex items-center justify-center text-outline">
              <span class="material-symbols-outlined text-[26px]">videocam_off</span>
            </div>
            <div>
              <p class="text-xs font-semibold text-on-surface">Camera is currently turned off</p>
              <p class="text-[11px] text-on-surface-variant max-w-xs mt-0.5">
                Click "Enable Camera" below so your interviewer can see you.
              </p>
            </div>
          </div>
        </div>

        <!-- Device Status Checklist Bar -->
        <div class="grid grid-cols-2 gap-2 text-xs">
          <!-- Camera Status Card -->
          <div
            class="p-2.5 rounded-xl border flex items-center justify-between transition-all"
            :class="isCameraEnabled ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-surface-container-low border-outline-variant/30 text-on-surface-variant'"
          >
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[18px]">
                {{ isCameraEnabled ? 'check_circle' : 'cancel' }}
              </span>
              <span class="font-medium text-[11px]">{{ isCameraEnabled ? 'Camera Enabled' : 'Camera Off' }}</span>
            </div>
            <button
              type="button"
              class="px-2 py-1 rounded-lg text-[10px] font-semibold transition-all"
              :class="isCameraEnabled ? 'bg-surface-container hover:bg-surface-container-high text-on-surface' : 'bg-primary text-on-primary hover:bg-primary-fixed'"
              @click="isCameraEnabled ? disableCamera() : enableCamera()"
            >
              {{ isCameraEnabled ? 'Turn Off' : 'Enable' }}
            </button>
          </div>

          <!-- Microphone Status Card -->
          <div
            class="p-2.5 rounded-xl border flex items-center justify-between transition-all"
            :class="isMicEnabled ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-surface-container-low border-outline-variant/30 text-on-surface-variant'"
          >
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[18px]">
                {{ isMicEnabled ? 'check_circle' : 'cancel' }}
              </span>
              <span class="font-medium text-[11px]">{{ isMicEnabled ? 'Mic Enabled' : 'Mic Off' }}</span>
            </div>
            <button
              type="button"
              class="px-2 py-1 rounded-lg text-[10px] font-semibold transition-all"
              :class="isMicEnabled ? 'bg-surface-container hover:bg-surface-container-high text-on-surface' : 'bg-primary text-on-primary hover:bg-primary-fixed'"
              @click="isMicEnabled ? disableMicrophone() : enableMicrophone()"
            >
              {{ isMicEnabled ? 'Turn Off' : 'Enable' }}
            </button>
          </div>
        </div>

        <!-- Media Test & Control Bar -->
        <div class="flex items-center justify-between bg-surface-container-low p-3 rounded-2xl border border-outline-variant/20">
          <!-- Mic Controls & Live Visualizer -->
          <div class="flex items-center gap-3">
            <button
              type="button"
              class="w-10 h-10 rounded-full flex items-center justify-center transition-all"
              :class="!isMicEnabled ? 'bg-surface-container-highest text-outline cursor-not-allowed' : isMicMuted ? 'bg-error text-white' : 'bg-surface-container-highest text-on-surface hover:bg-surface-variant'"
              :disabled="!isMicEnabled"
              :title="!isMicEnabled ? 'Please enable microphone first' : isMicMuted ? 'Unmute microphone' : 'Mute microphone'"
              @click="isMicMuted = !isMicMuted"
            >
              <span class="material-symbols-outlined text-[18px]">
                {{ !isMicEnabled ? 'mic_off' : isMicMuted ? 'mic_off' : 'mic' }}
              </span>
            </button>
            <div class="flex flex-col">
              <span class="text-[11px] text-on-surface-variant font-medium">
                {{ isMicEnabled ? 'Mic Live Level' : 'Mic Disabled' }}
              </span>
              <AudioVisualizer :level="micLevel" :bar-count="5" color="primary" />
            </div>
          </div>

          <!-- Enable Both Action -->
          <button
            v-if="!isCameraEnabled || !isMicEnabled"
            type="button"
            class="px-3.5 py-1.5 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed transition-all flex items-center gap-1.5 shadow-sm"
            @click="enableBothDevices"
          >
            <span class="material-symbols-outlined text-[16px]">devices</span>
            <span>Enable Camera & Mic</span>
          </button>
          <div v-else class="flex items-center gap-1 text-emerald-400 text-xs font-semibold px-2 py-1 bg-emerald-500/10 rounded-xl border border-emerald-500/20">
            <span class="material-symbols-outlined text-[16px]">verified</span>
            <span>Devices Ready</span>
          </div>
        </div>
      </div>

      <!-- Right: Access Code & Details Form (5 cols) -->
      <div class="lg:col-span-5 flex flex-col justify-between bg-surface-container-low p-6 rounded-2xl border border-outline-variant/20 space-y-6">
        <form class="space-y-4" @submit.prevent="handleJoinRoom">
          <div class="flex items-center justify-between border-b border-surface-container-highest pb-2">
            <h2 class="text-sm font-semibold text-on-surface uppercase tracking-wider">
              Interview Access
            </h2>
            <router-link to="/candidate" class="text-[11px] text-primary hover:underline flex items-center gap-0.5">
              <span class="material-symbols-outlined text-[14px]">arrow_back</span>
              <span>Candidate Portal</span>
            </router-link>
          </div>

          <!-- Error Message -->
          <div v-if="errorMessage" class="p-3 bg-error/15 border border-error/30 rounded-xl text-error text-xs flex items-start gap-2 animate-fade-in">
            <span class="material-symbols-outlined text-[16px] shrink-0 mt-0.5">warning</span>
            <span>{{ errorMessage }}</span>
          </div>

          <!-- 6-digit Code Input with spacing -->
          <div class="space-y-1">
            <label class="text-xs font-medium text-on-surface-variant flex items-center justify-between">
              <span>6-Digit Access Code</span>
              <span class="text-[11px] text-outline font-mono">{{ roomCode.length }}/6</span>
            </label>
            <input
              v-model="roomCode"
              required
              maxlength="6"
              type="text"
              placeholder="8 4 9 2 0 1"
              class="w-full bg-surface-container-high border border-outline-variant/30 rounded-xl px-4 py-3 text-xl font-mono font-bold tracking-[0.45em] text-primary text-center focus:outline-none focus:border-primary uppercase transition-all"
              @input="fetchInterviewByCode(roomCode)"
            />
          </div>

          <!-- Verified Role Badge if found -->
          <div
            v-if="interviewDetails"
            class="p-3.5 rounded-xl bg-primary/10 border border-primary/20 text-xs space-y-1.5 animate-fade-in"
          >
            <div class="flex items-center justify-between">
              <span class="text-emerald-400 font-semibold text-[11px] flex items-center gap-1">
                <span class="material-symbols-outlined text-[16px]">verified</span>
                <span>Verified Interview</span>
              </span>
              <span class="font-mono text-primary font-bold text-xs tracking-wider">{{ interviewDetails.room_code }}</span>
            </div>
            <div class="font-bold text-sm text-on-surface">{{ interviewDetails.job_title }}</div>
          </div>

          <!-- Candidate Name -->
          <div class="space-y-1">
            <label class="text-xs font-medium text-on-surface-variant">Your Full Name</label>
            <input
              v-model="candidateName"
              required
              type="text"
              placeholder="e.g. Alex Rivera"
              class="w-full bg-surface-container-high border border-outline-variant/30 rounded-xl px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-primary"
            />
          </div>

          <!-- Candidate Email -->
          <div class="space-y-1">
            <label class="text-xs font-medium text-on-surface-variant">Email Address</label>
            <input
              v-model="candidateEmail"
              required
              type="email"
              placeholder="alex@example.com"
              class="w-full bg-surface-container-high border border-outline-variant/30 rounded-xl px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-primary"
            />
          </div>

          <!-- Mandatory Device Notice -->
          <div
            v-if="!isCameraEnabled || !isMicEnabled"
            class="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-300 text-xs flex items-center gap-2"
          >
            <span class="material-symbols-outlined text-[18px] shrink-0 text-amber-400">info</span>
            <span>Please enable both camera and microphone to unlock the entry button.</span>
          </div>

          <!-- Enter Button -->
          <button
            type="submit"
            class="w-full py-3.5 rounded-full text-xs font-semibold transition-all flex items-center justify-center gap-2 shadow-lg mt-2"
            :class="isCameraEnabled && isMicEnabled ? 'bg-primary text-on-primary hover:bg-primary-fixed cursor-pointer' : 'bg-surface-container-highest text-outline hover:bg-surface-variant'"
            :disabled="isJoining"
          >
            <span class="material-symbols-outlined text-[18px]">
              {{ isJoining ? 'sync' : isCameraEnabled && isMicEnabled ? 'meeting_room' : 'lock' }}
            </span>
            <span>
              {{
                isJoining
                  ? 'Connecting to Room...'
                  : isCameraEnabled && isMicEnabled
                  ? 'Enter Interview Room'
                  : 'Enable Camera & Mic to Enter'
              }}
            </span>
          </button>
        </form>

        <!-- Recruiter Switch -->
        <div class="text-center pt-2 border-t border-surface-container-highest">
          <router-link to="/recruiter" class="text-xs text-on-surface-variant hover:text-primary transition-colors">
            Are you a recruiter? Open Recruiter Dashboard →
          </router-link>
        </div>
      </div>
    </div>

    <!-- Explicit Device Prompt Modal (Appears if user tries to start without enabling both) -->
    <Modal
      :is-open="showDeviceModal"
      title="Camera & Microphone Required"
      max-width="max-w-md"
      @close="showDeviceModal = false"
    >
      <div class="space-y-4">
        <p class="text-xs text-on-surface-variant leading-relaxed">
          Vetra requires access to both your camera and microphone before starting the interview. This ensures the AI interviewer can interact with you naturally.
        </p>

        <div class="space-y-2.5">
          <!-- Camera Check -->
          <div class="flex items-center justify-between p-3 rounded-xl bg-surface-container-low border border-outline-variant/20">
            <div class="flex items-center gap-2.5">
              <span class="material-symbols-outlined text-[20px]" :class="isCameraEnabled ? 'text-emerald-400' : 'text-outline'">
                videocam
              </span>
              <div>
                <div class="text-xs font-semibold text-on-surface">Webcam Video</div>
                <div class="text-[10px] text-on-surface-variant">{{ isCameraEnabled ? 'Ready' : 'Not enabled yet' }}</div>
              </div>
            </div>
            <button
              v-if="!isCameraEnabled"
              type="button"
              class="px-3 py-1.5 rounded-lg bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed"
              @click="enableCamera"
            >
              Enable
            </button>
            <span v-else class="material-symbols-outlined text-emerald-400 text-[20px]">check_circle</span>
          </div>

          <!-- Mic Check -->
          <div class="flex items-center justify-between p-3 rounded-xl bg-surface-container-low border border-outline-variant/20">
            <div class="flex items-center gap-2.5">
              <span class="material-symbols-outlined text-[20px]" :class="isMicEnabled ? 'text-emerald-400' : 'text-outline'">
                mic
              </span>
              <div>
                <div class="text-xs font-semibold text-on-surface">Microphone</div>
                <div class="text-[10px] text-on-surface-variant">{{ isMicEnabled ? 'Ready' : 'Not enabled yet' }}</div>
              </div>
            </div>
            <button
              v-if="!isMicEnabled"
              type="button"
              class="px-3 py-1.5 rounded-lg bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed"
              @click="enableMicrophone"
            >
              Enable
            </button>
            <span v-else class="material-symbols-outlined text-emerald-400 text-[20px]">check_circle</span>
          </div>
        </div>
      </div>

      <template #footer>
        <button
          type="button"
          class="px-4 py-2 rounded-xl text-xs font-medium text-on-surface-variant hover:text-on-surface"
          @click="showDeviceModal = false"
        >
          Cancel
        </button>
        <button
          type="button"
          class="px-4 py-2 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed"
          @click="enableBothDevices"
        >
          Enable Both & Continue
        </button>
      </template>
    </Modal>
  </div>
</template>
