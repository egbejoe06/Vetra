<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useCandidateStore } from '@/stores/candidate'
import { api } from '@/services/api'
import type { InterviewResponse } from '@/types'
import Badge from '@/components/common/Badge.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const candidateStore = useCandidateStore()

// Active portal tab: 'access' (join code) | 'profile' (profile & resume)
const activeTab = ref<'access' | 'profile'>('access')

// 6-digit spaced input state
const digits = ref<string[]>(['', '', '', '', '', ''])
const inputRefs = ref<HTMLInputElement[]>([])

const isFetching = ref(false)
const interviewDetails = ref<InterviewResponse | null>(null)
const error = ref<string | null>(null)

// Resume upload state
const fileInputRef = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const uploadSuccessBanner = ref<string | null>(null)
const uploadErrorBanner = ref<string | null>(null)
const isReplacing = ref(false)

const fullCode = computed(() => digits.value.join('').trim().toUpperCase())

onMounted(async () => {
  if (route.query.tab === 'profile') {
    activeTab.value = 'profile'
  }
  // Load candidate profile from API / storage
  await candidateStore.loadProfile()
})

function setInputRef(el: any, index: number) {
  if (el) {
    inputRefs.value[index] = el
  }
}

function onDigitInput(index: number, event: Event) {
  const input = event.target as HTMLInputElement
  const raw = input.value.replace(/[^a-zA-Z0-9]/g, '').toUpperCase()

  if (raw.length > 1) {
    const chars = raw.split('').slice(0, 6)
    for (let i = 0; i < 6; i++) {
      digits.value[i] = chars[i] || ''
    }
    const nextIdx = Math.min(chars.length, 5)
    inputRefs.value[nextIdx]?.focus()
  } else {
    digits.value[index] = raw
    if (raw && index < 5) {
      inputRefs.value[index + 1]?.focus()
    }
  }
}

function onDigitKeyDown(index: number, event: KeyboardEvent) {
  if (event.key === 'Backspace') {
    if (!digits.value[index] && index > 0) {
      digits.value[index - 1] = ''
      inputRefs.value[index - 1]?.focus()
    } else {
      digits.value[index] = ''
    }
  } else if (event.key === 'ArrowLeft' && index > 0) {
    inputRefs.value[index - 1]?.focus()
  } else if (event.key === 'ArrowRight' && index < 5) {
    inputRefs.value[index + 1]?.focus()
  }
}

function onDigitPaste(event: ClipboardEvent) {
  event.preventDefault()
  const pasted = event.clipboardData?.getData('text') || ''
  const clean = pasted.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 6)
  if (clean) {
    for (let i = 0; i < 6; i++) {
      digits.value[i] = clean[i] || ''
    }
    const focusIdx = Math.min(clean.length, 5)
    inputRefs.value[focusIdx]?.focus()
  }
}

// Watch for code completion and live-fetch interview details
watch(fullCode, async (newCode) => {
  error.value = null
  if (newCode.length === 6) {
    await fetchInterviewLive(newCode)
  } else {
    interviewDetails.value = null
  }
})

async function fetchInterviewLive(code: string) {
  isFetching.value = true
  error.value = null
  interviewDetails.value = null

  try {
    const res = await api.getInterviewByCode(code)
    interviewDetails.value = res
  } catch (err: any) {
    interviewDetails.value = null
    error.value = `No active interview found for code ${code}. Please check the code and try again.`
  } finally {
    isFetching.value = false
  }
}

function handleJoinInterview() {
  if (fullCode.value.length !== 6) {
    error.value = 'Please enter all 6 digits of your interview access code.'
    return
  }
  router.push(`/join?code=${fullCode.value}`)
}

// ----------------------------------------------------------------------------
// Resume Upload Handlers (PDF Only)
// ----------------------------------------------------------------------------
function triggerFileInput() {
  uploadErrorBanner.value = null
  uploadSuccessBanner.value = null
  fileInputRef.value?.click()
}

async function handleFileSelected(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files && target.files[0]) {
    await processPdfUpload(target.files[0])
  }
  // Reset input value so re-selecting same file triggers change if needed
  if (target) target.value = ''
}

function onDragOver(event: DragEvent) {
  event.preventDefault()
  isDragging.value = true
}

function onDragLeave() {
  isDragging.value = false
}

async function onDrop(event: DragEvent) {
  event.preventDefault()
  isDragging.value = false
  if (event.dataTransfer?.files && event.dataTransfer.files[0]) {
    await processPdfUpload(event.dataTransfer.files[0])
  }
}

async function processPdfUpload(file: File) {
  uploadErrorBanner.value = null
  uploadSuccessBanner.value = null

  if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
    uploadErrorBanner.value = 'Only PDF resume files (.pdf) are accepted. Text pasting is disabled.'
    return
  }

  if (file.size > 15 * 1024 * 1024) {
    uploadErrorBanner.value = 'File is too large. Maximum PDF resume size is 15 MB.'
    return
  }

  try {
    const res = await candidateStore.uploadResumeFile(file, isReplacing.value)
    isReplacing.value = false
    uploadSuccessBanner.value = res.reused_cache
      ? `Resume verified: Same resume content detected. Reused parsed profile instantly.`
      : `Resume uploaded and parsed successfully! ${file.name} is now saved to your profile.`
  } catch (err: any) {
    uploadErrorBanner.value = err.message || 'Failed to upload and parse resume.'
  }
}

function handleReplaceResume() {
  isReplacing.value = true
  triggerFileInput()
}

async function handleRemoveResume() {
  if (confirm('Are you sure you want to remove your stored resume? You will need to upload a resume again before your interview.')) {
    uploadSuccessBanner.value = null
    uploadErrorBanner.value = null
    try {
      await candidateStore.clearResume()
      uploadSuccessBanner.value = 'Stored resume removed successfully.'
    } catch (err: any) {
      uploadErrorBanner.value = err.message || 'Failed to remove resume.'
    }
  }
}

function formatBytes(bytes?: number) {
  if (!bytes) return ''
  const k = 1024
  const sizes = ['B', 'KB', 'MB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function formatDate(iso?: string) {
  if (!iso) return 'Recently'
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return 'Recently'
  }
}
</script>

<template>
  <div class="flex-1 min-h-0 h-full w-full flex flex-col overflow-y-auto bg-surface p-6 lg:p-8 space-y-6">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <h1 class="text-2xl font-bold text-on-surface">Candidate Portal</h1>
          <Badge variant="primary" size="sm">Candidate</Badge>
        </div>
        <p class="text-sm text-on-surface-variant mt-1">
          Manage your profile and enter technical interview rooms.
        </p>
      </div>
    </div>

    <!-- Navigation Tabs -->
    <div class="flex items-center gap-2 border-b border-surface-container-highest pb-2">
      <button
        class="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer"
        :class="activeTab === 'access'
          ? 'bg-primary text-on-primary shadow-sm'
          : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high'"
        @click="activeTab = 'access'"
      >
        <span class="material-symbols-outlined text-[18px]">meeting_room</span>
        <span>Interview Access</span>
      </button>

      <button
        class="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer relative"
        :class="activeTab === 'profile'
          ? 'bg-primary text-on-primary shadow-sm'
          : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high'"
        @click="activeTab = 'profile'"
      >
        <span class="material-symbols-outlined text-[18px]">badge</span>
        <span>My Profile & Resume</span>

        <!-- Status indicator badge -->
        <span
          v-if="candidateStore.hasStoredResume"
          class="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 ml-1"
        >
          ✓ Ready
        </span>
        <span
          v-else
          class="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 ml-1"
        >
          Upload Needed
        </span>
      </button>
    </div>

    <!-- ======================================================================
         TAB 1: INTERVIEW ACCESS (6-digit code entry)
         ====================================================================== -->
    <div v-if="activeTab === 'access'" class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <!-- Join Interview Action Box (7 cols) -->
      <div class="lg:col-span-7 bg-surface-container border border-outline-variant/30 rounded-3xl p-6 sm:p-8 shadow-xl flex flex-col justify-between space-y-6">
        <div class="space-y-2">
          <div class="flex items-center gap-2 text-primary font-semibold text-xs uppercase tracking-wider">
            <span class="material-symbols-outlined text-[18px]">meeting_room</span>
            <span>Interview Access</span>
          </div>
          <h2 class="text-xl font-bold text-on-surface">Enter Your 6-Digit Access Code</h2>
          <p class="text-xs text-on-surface-variant leading-relaxed">
            Enter the 6-digit access code from your invitation. Interview details will load live as soon as you enter the code.
          </p>
        </div>

        <form class="space-y-5" @submit.prevent="handleJoinInterview">
          <!-- Error banner -->
          <div v-if="error" class="p-3.5 rounded-xl bg-error/15 border border-error/30 text-error text-xs flex items-center gap-2 animate-fade-in">
            <span class="material-symbols-outlined text-[18px] shrink-0">error</span>
            <span>{{ error }}</span>
          </div>

          <!-- Spaced 6-digit input boxes with gap -->
          <div class="space-y-2">
            <label class="text-xs font-medium text-on-surface-variant flex items-center justify-between">
              <span>Access Code</span>
              <span class="text-[11px] text-outline font-mono">{{ fullCode.length }}/6 digits</span>
            </label>

            <div class="flex items-center justify-center gap-2 sm:gap-3 p-4 bg-surface-container-low border border-outline-variant/30 rounded-2xl">
              <!-- First 3 digits -->
              <input
                v-for="i in 3"
                :key="i - 1"
                :ref="(el) => setInputRef(el, i - 1)"
                :value="digits[i - 1]"
                type="text"
                maxlength="1"
                placeholder="•"
                class="w-11 sm:w-13 h-14 bg-surface-container-high border-2 rounded-xl text-center text-xl font-mono font-bold text-primary focus:outline-none transition-all"
                :class="digits[i - 1] ? 'border-primary/70 bg-primary/10' : 'border-outline-variant/40 focus:border-primary'"
                @input="(e) => onDigitInput(i - 1, e)"
                @keydown="(e) => onDigitKeyDown(i - 1, e)"
                @paste="onDigitPaste"
              />

              <!-- Separator dash between groups of 3 -->
              <span class="text-outline font-bold text-xl px-1 sm:px-2 select-none">—</span>

              <!-- Last 3 digits -->
              <input
                v-for="i in [4, 5, 6]"
                :key="i - 1"
                :ref="(el) => setInputRef(el, i - 1)"
                :value="digits[i - 1]"
                type="text"
                maxlength="1"
                placeholder="•"
                class="w-11 sm:w-13 h-14 bg-surface-container-high border-2 rounded-xl text-center text-xl font-mono font-bold text-primary focus:outline-none transition-all"
                :class="digits[i - 1] ? 'border-primary/70 bg-primary/10' : 'border-outline-variant/40 focus:border-primary'"
                @input="(e) => onDigitInput(i - 1, e)"
                @keydown="(e) => onDigitKeyDown(i - 1, e)"
                @paste="onDigitPaste"
              />
            </div>
          </div>

          <!-- Live Fetching Indicator -->
          <div
            v-if="isFetching"
            class="p-4 rounded-2xl bg-surface-container-low border border-outline-variant/30 flex items-center justify-center gap-3 animate-fade-in"
          >
            <span class="material-symbols-outlined text-primary text-[20px] animate-spin">sync</span>
            <span class="text-xs text-on-surface-variant font-mono">Fetching interview details live...</span>
          </div>

          <!-- Live Fetched Interview Details Card -->
          <div
            v-else-if="interviewDetails"
            class="p-5 rounded-2xl bg-primary/5 border border-primary/30 space-y-4 animate-fade-in shadow-inner"
          >
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="flex items-center gap-1.5 text-emerald-400 text-xs font-semibold">
                  <span class="material-symbols-outlined text-[18px]">verified</span>
                  <span>Matched Interview</span>
                </div>
                <h3 class="text-base sm:text-lg font-bold text-on-surface mt-1">{{ interviewDetails.job_title }}</h3>
              </div>
              <span class="px-3 py-1.5 rounded-xl bg-primary/15 border border-primary/30 text-primary font-mono font-bold text-sm tracking-wider">
                {{ interviewDetails.room_code }}
              </span>
            </div>

            <!-- Click to Join Button -->
            <button
              type="submit"
              class="w-full py-3.5 rounded-2xl bg-primary text-on-primary text-xs font-bold hover:bg-primary-fixed transition-all flex items-center justify-center gap-2 shadow-lg cursor-pointer"
            >
              <span class="material-symbols-outlined text-[18px]">meeting_room</span>
              <span>Join Interview Room →</span>
            </button>
          </div>

          <!-- Join Button when details haven't loaded yet -->
          <div v-else class="pt-1">
            <button
              type="submit"
              class="w-full py-3.5 rounded-2xl bg-surface-container-high text-outline text-xs font-semibold hover:bg-surface-container-highest transition-all flex items-center justify-center gap-2"
              :disabled="fullCode.length !== 6"
            >
              <span class="material-symbols-outlined text-[18px]">arrow_forward</span>
              <span>{{ fullCode.length === 6 ? 'Fetch & Join Interview' : 'Enter 6-Digit Code Above' }}</span>
            </button>
          </div>
        </form>
      </div>

      <!-- Readiness & Device Preparation Guide (5 cols) -->
      <div class="lg:col-span-5 bg-surface-container border border-outline-variant/30 rounded-3xl p-6 sm:p-8 shadow-xl space-y-5 flex flex-col justify-between">
        <div>
          <div class="flex items-center gap-2 text-primary font-semibold text-xs uppercase tracking-wider">
            <span class="material-symbols-outlined text-[18px]">verified_user</span>
            <span>Pre-Interview Checklist</span>
          </div>
          <h2 class="text-lg font-bold text-on-surface mt-1">Preparation & Requirements</h2>
          <p class="text-xs text-on-surface-variant mt-1 leading-relaxed">
            Before entering, make sure your hardware and profile are prepared for an optimal session.
          </p>
        </div>

        <div class="space-y-3 text-xs">
          <div class="flex items-start gap-3 p-3 rounded-xl bg-surface-container-low border border-outline-variant/20">
            <span class="material-symbols-outlined text-primary text-[20px] shrink-0 mt-0.5">videocam</span>
            <div>
              <span class="font-semibold text-on-surface">Working Camera</span>
              <p class="text-[11px] text-on-surface-variant mt-0.5">
                You will be prompted to verify your camera before entering the room.
              </p>
            </div>
          </div>

          <div class="flex items-start gap-3 p-3 rounded-xl bg-surface-container-low border border-outline-variant/20">
            <span class="material-symbols-outlined text-primary text-[20px] shrink-0 mt-0.5">mic</span>
            <div>
              <span class="font-semibold text-on-surface">Working Microphone</span>
              <p class="text-[11px] text-on-surface-variant mt-0.5">
                Voice interaction is core to the interview. Use a headset or quiet room for best clarity.
              </p>
            </div>
          </div>

          <!-- Stored Resume Status Card -->
          <div
            class="flex items-start gap-3 p-3 rounded-xl border transition-all"
            :class="candidateStore.hasStoredResume
              ? 'bg-emerald-500/10 border-emerald-500/30'
              : 'bg-amber-500/10 border-amber-500/30'"
          >
            <span
              class="material-symbols-outlined text-[20px] shrink-0 mt-0.5"
              :class="candidateStore.hasStoredResume ? 'text-emerald-400' : 'text-amber-400'"
            >
              {{ candidateStore.hasStoredResume ? 'task' : 'upload_file' }}
            </span>
            <div class="flex-1">
              <div class="flex items-center justify-between">
                <span class="font-semibold text-on-surface">
                  {{ candidateStore.hasStoredResume ? 'Resume Ready in Profile' : 'Resume Not Uploaded' }}
                </span>
                <span
                  v-if="candidateStore.hasStoredResume"
                  class="text-[10px] text-emerald-400 font-mono font-bold"
                >
                  INSTANT START
                </span>
              </div>
              <p class="text-[11px] text-on-surface-variant mt-0.5">
                <template v-if="candidateStore.hasStoredResume">
                  {{ candidateStore.resumeMetadata?.filename || 'Uploaded Resume' }} is parsed and ready. Your interview starts immediately without delay.
                </template>
                <template v-else>
                  Upload your resume PDF in your profile so interview questions are grounded in your actual background.
                </template>
              </p>
              <button
                type="button"
                class="mt-2 text-primary hover:underline font-semibold flex items-center gap-1 cursor-pointer text-[11px]"
                @click="activeTab = 'profile'"
              >
                <span>{{ candidateStore.hasStoredResume ? 'View or Change Resume →' : 'Upload Resume PDF Now →' }}</span>
              </button>
            </div>
          </div>
        </div>

        <div class="pt-2 text-center border-t border-surface-container-highest">
          <router-link to="/join" class="text-xs text-primary hover:underline font-semibold flex items-center justify-center gap-1">
            <span>Open Device Setup Lobby</span>
            <span class="material-symbols-outlined text-[14px]">arrow_forward</span>
          </router-link>
        </div>
      </div>
    </div>

    <!-- ======================================================================
         TAB 2: CANDIDATE PROFILE & RESUME SECTION
         ====================================================================== -->
    <div v-else-if="activeTab === 'profile'" class="space-y-6 animate-fade-in">
      <!-- Hidden file input strictly for PDF files -->
      <input
        ref="fileInputRef"
        type="file"
        accept=".pdf,application/pdf"
        class="hidden"
        @change="handleFileSelected"
      />

      <!-- Success & Error Alerts -->
      <div
        v-if="uploadSuccessBanner"
        class="p-4 rounded-2xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between gap-3 animate-fade-in"
      >
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-[20px] text-emerald-400">check_circle</span>
          <span>{{ uploadSuccessBanner }}</span>
        </div>
        <button class="text-emerald-400 hover:text-emerald-300 cursor-pointer" @click="uploadSuccessBanner = null">✕</button>
      </div>

      <div
        v-if="uploadErrorBanner"
        class="p-4 rounded-2xl bg-error/15 border border-error/30 text-error text-xs flex items-center justify-between gap-3 animate-fade-in"
      >
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-[20px]">error</span>
          <span>{{ uploadErrorBanner }}</span>
        </div>
        <button class="text-error hover:underline cursor-pointer" @click="uploadErrorBanner = null">✕</button>
      </div>

      <!-- Profile Header Summary Card -->
      <div class="bg-surface-container border border-outline-variant/30 rounded-3xl p-6 sm:p-8 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div class="flex items-center gap-4">
          <div class="w-16 h-16 rounded-2xl bg-primary/20 border border-primary/30 flex items-center justify-center text-primary font-bold text-2xl shadow-inner">
            {{ (candidateStore.candidateFullName || 'C').charAt(0).toUpperCase() }}
          </div>
          <div class="space-y-1">
            <div class="flex items-center gap-2">
              <h2 class="text-xl font-bold text-on-surface">{{ candidateStore.candidateFullName }}</h2>
              <span
                v-if="candidateStore.hasStoredResume"
                class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                Resume Active
              </span>
              <span
                v-else
                class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-surface-container-highest text-outline border border-outline-variant/30"
              >
                No Resume Stored
              </span>
            </div>
            <p class="text-xs text-on-surface-variant font-mono">{{ candidateStore.candidateEmailAddress }}</p>
            <p v-if="candidateStore.detectedExperienceYears > 0" class="text-xs text-primary font-medium">
              {{ candidateStore.detectedExperienceYears }} Years Engineering Experience
            </p>
          </div>
        </div>

        <!-- Quick Action on Header -->
        <div class="flex items-center gap-3">
          <button
            v-if="candidateStore.hasStoredResume"
            class="px-4 py-2.5 rounded-xl bg-surface-container-high border border-outline-variant/30 text-xs font-semibold text-on-surface hover:bg-surface-container-highest transition-all flex items-center gap-2 cursor-pointer"
            :disabled="candidateStore.isUploading"
            @click="handleReplaceResume"
          >
            <span class="material-symbols-outlined text-[18px] text-primary">sync</span>
            <span>Replace Resume PDF</span>
          </button>
          <button
            v-else
            class="px-5 py-2.5 rounded-xl bg-primary text-on-primary text-xs font-bold hover:bg-primary-fixed transition-all flex items-center gap-2 shadow-md cursor-pointer"
            :disabled="candidateStore.isUploading"
            @click="triggerFileInput"
          >
            <span class="material-symbols-outlined text-[18px]">upload_file</span>
            <span>Upload Resume PDF</span>
          </button>
        </div>
      </div>

      <!-- Uploading / Parsing Overlay State -->
      <div
        v-if="candidateStore.isUploading"
        class="bg-surface-container border border-primary/40 rounded-3xl p-10 shadow-2xl flex flex-col items-center justify-center space-y-4 text-center animate-fade-in"
      >
        <div class="relative flex items-center justify-center">
          <div class="w-16 h-16 rounded-full border-4 border-primary/20 border-t-primary animate-spin"></div>
          <span class="material-symbols-outlined text-primary text-[28px] absolute">psychology</span>
        </div>
        <div class="space-y-1">
          <h3 class="text-base font-bold text-on-surface">Parsing & Storing Resume</h3>
          <p class="text-xs text-on-surface-variant max-w-md">
            Analyzing your engineering background, architectural decisions, and project tech stack.
            This content will be permanently available for instant interview starts.
          </p>
        </div>
        <span class="text-[11px] text-primary font-mono animate-pulse">Processing resume PDF...</span>
      </div>

      <!-- If NO resume uploaded: PDF Upload Dropzone (Strictly No Pasting) -->
      <div
        v-else-if="!candidateStore.hasStoredResume"
        class="bg-surface-container border border-outline-variant/30 rounded-3xl p-8 sm:p-12 shadow-xl space-y-8"
      >
        <div class="max-w-xl mx-auto text-center space-y-2">
          <div class="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 text-primary flex items-center justify-center mx-auto">
            <span class="material-symbols-outlined text-[28px]">upload_file</span>
          </div>
          <h2 class="text-xl font-bold text-on-surface">Upload Your Resume (PDF)</h2>
          <p class="text-xs text-on-surface-variant leading-relaxed">
            Upload your resume PDF once. Vetra extracts your technical competencies, frameworks, and project architectures
            so every interview session is grounded in your actual work experience without having to re-upload.
          </p>
        </div>

        <!-- Drag & Drop Zone -->
        <div
          class="max-w-xl mx-auto border-2 border-dashed rounded-3xl p-8 sm:p-10 flex flex-col items-center justify-center gap-4 transition-all cursor-pointer select-none"
          :class="isDragging
            ? 'border-primary bg-primary/10 scale-[1.01]'
            : 'border-outline-variant/40 hover:border-primary/50 bg-surface-container-low hover:bg-surface-container-high/50'"
          @click="triggerFileInput"
          @dragover="onDragOver"
          @dragleave="onDragLeave"
          @drop="onDrop"
        >
          <div class="w-14 h-14 rounded-full bg-primary/15 text-primary flex items-center justify-center">
            <span class="material-symbols-outlined text-[32px]">picture_as_pdf</span>
          </div>
          <div class="text-center space-y-1">
            <span class="text-sm font-semibold text-on-surface">Click to browse or drag and drop your PDF resume</span>
            <p class="text-[11px] text-on-surface-variant">PDF format only (up to 15 MB). Text pasting is disabled.</p>
          </div>
          <button
            type="button"
            class="px-5 py-2 rounded-xl bg-primary text-on-primary text-xs font-bold hover:bg-primary-fixed transition-all flex items-center gap-2 shadow pointer-events-none"
          >
            <span class="material-symbols-outlined text-[16px]">add</span>
            <span>Select PDF File</span>
          </button>
        </div>

        <!-- Explanatory Feature Cards -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-3xl mx-auto pt-4 border-t border-surface-container-highest text-xs">
          <div class="p-4 rounded-2xl bg-surface-container-low border border-outline-variant/20 space-y-1.5">
            <div class="flex items-center gap-2 text-primary font-semibold">
              <span class="material-symbols-outlined text-[18px]">bolt</span>
              <span>Instant Room Entry</span>
            </div>
            <p class="text-[11px] text-on-surface-variant">
              Because your resume is pre-parsed and cached, interview sessions start immediately without waiting for parsing.
            </p>
          </div>

          <div class="p-4 rounded-2xl bg-surface-container-low border border-outline-variant/20 space-y-1.5">
            <div class="flex items-center gap-2 text-primary font-semibold">
              <span class="material-symbols-outlined text-[18px]">architecture</span>
              <span>Architecture Grounding</span>
            </div>
            <p class="text-[11px] text-on-surface-variant">
              Questions and coding challenges probe your actual system design decisions, scaling bottlenecks, and projects.
            </p>
          </div>

          <div class="p-4 rounded-2xl bg-surface-container-low border border-outline-variant/20 space-y-1.5">
            <div class="flex items-center gap-2 text-primary font-semibold">
              <span class="material-symbols-outlined text-[18px]">lock_reset</span>
              <span>Changes Only When You Want</span>
            </div>
            <p class="text-[11px] text-on-surface-variant">
              Your resume profile stays permanent and only updates when you explicitly replace it with a new PDF.
            </p>
          </div>
        </div>
      </div>

      <!-- If Resume IS Stored: Verified Document Card & Parsed Details Explorer -->
      <div v-else class="space-y-6">
        <!-- Document Metadata & Control Bar -->
        <div class="bg-surface-container border border-outline-variant/30 rounded-3xl p-6 sm:p-8 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div class="flex items-center gap-4">
            <div class="w-12 h-12 rounded-2xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center shrink-0">
              <span class="material-symbols-outlined text-[26px]">verified</span>
            </div>
            <div>
              <div class="flex items-center gap-2">
                <h3 class="text-base font-bold text-on-surface">
                  {{ candidateStore.resumeMetadata?.filename || 'Stored Resume Document' }}
                </h3>
                <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/20 text-emerald-300 font-bold">
                  ACTIVE
                </span>
              </div>
              <p class="text-xs text-on-surface-variant mt-0.5 flex items-center gap-3">
                <span>Last updated: {{ formatDate(candidateStore.resumeMetadata?.uploaded_at) }}</span>
                <span v-if="candidateStore.resumeMetadata?.file_size_bytes">• {{ formatBytes(candidateStore.resumeMetadata?.file_size_bytes) }}</span>
                <span v-if="candidateStore.resumeMetadata?.resume_hash" class="font-mono text-[10px] text-outline">
                  SHA: {{ candidateStore.resumeMetadata.resume_hash.slice(0, 10) }}...
                </span>
              </p>
            </div>
          </div>

          <!-- Actions: Replace / Remove -->
          <div class="flex items-center gap-2.5 self-start md:self-auto">
            <button
              type="button"
              class="px-4 py-2 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed transition-all flex items-center gap-1.5 cursor-pointer shadow-sm"
              @click="handleReplaceResume"
            >
              <span class="material-symbols-outlined text-[16px]">upload_file</span>
              <span>Upload New PDF</span>
            </button>
            <button
              type="button"
              class="px-3.5 py-2 rounded-xl bg-surface-container-high border border-outline-variant/30 text-xs font-semibold text-error hover:bg-error/10 transition-all flex items-center gap-1 cursor-pointer"
              @click="handleRemoveResume"
            >
              <span class="material-symbols-outlined text-[16px]">delete</span>
              <span>Remove</span>
            </button>
          </div>
        </div>

        <!-- Parsed Resume Content Details -->
        <div v-if="candidateStore.storedProfile" class="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <!-- Left Column (8 cols): Work Experience & Projects -->
          <div class="lg:col-span-8 space-y-6">
            <!-- Work Experience Section -->
            <div
              v-if="candidateStore.storedProfile.work_experience?.length || (candidateStore.storedProfile as any).work_experiences?.length"
              class="bg-surface-container border border-outline-variant/30 rounded-3xl p-6 sm:p-8 shadow-xl space-y-5"
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2 text-primary font-semibold text-xs uppercase tracking-wider">
                  <span class="material-symbols-outlined text-[18px]">work</span>
                  <span>Work Experience</span>
                </div>
                <span class="text-xs text-on-surface-variant font-mono">
                  {{ ((candidateStore.storedProfile.work_experience || (candidateStore.storedProfile as any).work_experiences) || []).length }} Positions
                </span>
              </div>

              <div class="space-y-4">
                <div
                  v-for="(job, idx) in (candidateStore.storedProfile.work_experience || (candidateStore.storedProfile as any).work_experiences || [])"
                  :key="idx"
                  class="p-4 rounded-2xl bg-surface-container-low border border-outline-variant/20 space-y-2"
                >
                  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                    <h4 class="text-sm font-bold text-on-surface">{{ job.role }}</h4>
                    <span class="text-xs text-primary font-semibold">{{ job.company }}</span>
                  </div>
                  <div v-if="job.duration" class="text-[11px] text-outline font-mono">
                    {{ job.duration }}
                  </div>

                  <!-- Responsibilities -->
                  <ul v-if="job.responsibilities?.length" class="space-y-1 text-xs text-on-surface-variant list-disc list-inside">
                    <li v-for="(resp, rIdx) in job.responsibilities" :key="rIdx" class="leading-relaxed">
                      {{ resp }}
                    </li>
                  </ul>

                  <!-- Tech stack chips -->
                  <div v-if="job.tech_stack?.length" class="flex flex-wrap gap-1.5 pt-1">
                    <span
                      v-for="(tech, tIdx) in job.tech_stack"
                      :key="tIdx"
                      class="px-2 py-0.5 rounded-lg bg-surface-container-highest text-[10px] font-mono text-on-surface-variant"
                    >
                      {{ tech }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Claimed Projects Section -->
            <div
              v-if="candidateStore.storedProfile.projects?.length"
              class="bg-surface-container border border-outline-variant/30 rounded-3xl p-6 sm:p-8 shadow-xl space-y-5"
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2 text-primary font-semibold text-xs uppercase tracking-wider">
                  <span class="material-symbols-outlined text-[18px]">terminal</span>
                  <span>Featured Engineering Projects</span>
                </div>
                <span class="text-xs text-on-surface-variant font-mono">
                  {{ candidateStore.storedProfile.projects.length }} Projects
                </span>
              </div>

              <div class="space-y-4">
                <div
                  v-for="(proj, pIdx) in candidateStore.storedProfile.projects"
                  :key="pIdx"
                  class="p-4 rounded-2xl bg-surface-container-low border border-outline-variant/20 space-y-2"
                >
                  <div class="flex items-center justify-between">
                    <h4 class="text-sm font-bold text-on-surface">{{ proj.name }}</h4>
                    <span v-if="proj.role" class="text-xs text-outline font-medium">Role: {{ proj.role }}</span>
                  </div>

                  <p class="text-xs text-on-surface-variant leading-relaxed">{{ proj.description }}</p>

                  <div v-if="proj.claimed_impact" class="text-xs text-emerald-400/90 font-medium">
                    ★ Impact: {{ proj.claimed_impact }}
                  </div>

                  <!-- Tech stack chips -->
                  <div v-if="proj.tech_stack?.length" class="flex flex-wrap gap-1.5 pt-1">
                    <span
                      v-for="(tech, tIdx) in proj.tech_stack"
                      :key="tIdx"
                      class="px-2 py-0.5 rounded-lg bg-primary/10 text-primary border border-primary/20 text-[10px] font-mono font-medium"
                    >
                      {{ tech }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Right Column (4 cols): Skills & Education -->
          <div class="lg:col-span-4 space-y-6">
            <!-- Skills Taxonomy -->
            <div class="bg-surface-container border border-outline-variant/30 rounded-3xl p-6 shadow-xl space-y-4">
              <div class="flex items-center gap-2 text-primary font-semibold text-xs uppercase tracking-wider">
                <span class="material-symbols-outlined text-[18px]">code</span>
                <span>Parsed Skills Taxonomy</span>
              </div>

              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="(skill, sIdx) in candidateStore.detectedSkills"
                  :key="sIdx"
                  class="px-2.5 py-1 rounded-xl bg-surface-container-high border border-outline-variant/30 text-xs font-semibold text-on-surface hover:border-primary/50 transition-colors"
                >
                  {{ skill }}
                </span>
              </div>
            </div>

            <!-- Frameworks and Tools -->
            <div
              v-if="candidateStore.storedProfile.frameworks_and_tools?.length"
              class="bg-surface-container border border-outline-variant/30 rounded-3xl p-6 shadow-xl space-y-4"
            >
              <div class="flex items-center gap-2 text-primary font-semibold text-xs uppercase tracking-wider">
                <span class="material-symbols-outlined text-[18px]">build</span>
                <span>Frameworks & Tools</span>
              </div>

              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="(tool, tIdx) in candidateStore.storedProfile.frameworks_and_tools"
                  :key="tIdx"
                  class="px-2.5 py-1 rounded-xl bg-primary/10 text-primary border border-primary/20 text-xs font-mono"
                >
                  {{ tool }}
                </span>
              </div>
            </div>

            <!-- Education -->
            <div
              v-if="candidateStore.storedProfile.education?.length"
              class="bg-surface-container border border-outline-variant/30 rounded-3xl p-6 shadow-xl space-y-4"
            >
              <div class="flex items-center gap-2 text-primary font-semibold text-xs uppercase tracking-wider">
                <span class="material-symbols-outlined text-[18px]">school</span>
                <span>Education</span>
              </div>

              <div class="space-y-3 text-xs">
                <div
                  v-for="(edu, eIdx) in candidateStore.storedProfile.education"
                  :key="eIdx"
                  class="p-3 rounded-xl bg-surface-container-low border border-outline-variant/20 space-y-0.5"
                >
                  <span class="font-bold text-on-surface block">{{ edu.degree }}</span>
                  <span class="text-on-surface-variant block">{{ edu.institution }}</span>
                  <span v-if="edu.year" class="text-[11px] text-outline font-mono">{{ edu.year }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
