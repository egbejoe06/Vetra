<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { useInterviewStore } from '@/stores/interview'
import Badge from '@/components/common/Badge.vue'
import type { CandidateProfile, DiagnosticError, GeneratePlanResponse } from '@/types'

const router = useRouter()
const authStore = useAuthStore()
const interviewStore = useInterviewStore()

const inputMode = ref<'upload' | 'text'>('text')
const isParsing = ref(false)
const isGenerating = ref(false)
const selectedFile = ref<File | null>(null)
const resumeText = ref<string>('')

const jobTitle = ref('Senior Backend Engineer')
const yearsOfExp = ref(5)
const jobDescription = ref('Designing and scaling high-throughput distributed architectures, event-driven pipelines, and low-latency APIs.')
const selectedProblemCategory = ref<string>('BUG_INVESTIGATION')

const isBugCategorySelected = computed(() => {
  const cat = selectedProblemCategory.value?.toUpperCase() || ''
  return cat.includes('BUG') || cat.includes('DEBUG')
})

const parsedProfile = ref<CandidateProfile | null>(null)
const generatedPlan = ref<GeneratePlanResponse | null>(null)

// Freeze Cache Tracking
const lastParsedSignature = ref<string>('')
const isResumeModified = computed(() => {
  if (!parsedProfile.value) return false
  if (inputMode.value === 'text') {
    return resumeText.value.trim() !== lastParsedSignature.value
  } else {
    return (selectedFile.value?.name || '') !== lastParsedSignature.value
  }
})

// Pipeline Checkpoint & Diagnostic Error State
const activeCheckpointId = ref<string | null>(null)
const currentStep = ref<number>(1) // 1: Draft, 2: Exercises, 3: Final Plan
const showDebugDetails = ref(false)

const errorMessage = ref<string | null>(null)
const errorStep = ref<string | null>(null)
const errorCheckpointId = ref<string | null>(null)
const diagnosticErrors = ref<DiagnosticError[]>([])
const canResumeFromCheckpoint = ref<boolean>(false)
const isPollingCheckpoint = ref<boolean>(false)
const pollingMessage = ref<string | null>(null)
const deferCodingExercise = ref<boolean>(true)

// Safe display accessors
const candidateName = computed(() => parsedProfile.value?.candidate_name || parsedProfile.value?.name || 'Candidate')
const candidateSkills = computed(() => parsedProfile.value?.skills || parsedProfile.value?.primary_skills || [])

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files && target.files[0]) {
    selectedFile.value = target.files[0]
  }
}

async function handleParseResume(forceRefresh: boolean = false) {
  isParsing.value = true
  clearErrors()
  try {
    if (inputMode.value === 'upload') {
      if (!selectedFile.value) {
        throw new Error('Please select a PDF resume file to upload.')
      }
      parsedProfile.value = await api.parseResumeFile(selectedFile.value, forceRefresh)
      lastParsedSignature.value = selectedFile.value.name
    } else {
      if (!resumeText.value.trim()) {
        throw new Error('Please paste candidate resume text.')
      }
      parsedProfile.value = await api.parseResumeText(resumeText.value, forceRefresh)
      lastParsedSignature.value = resumeText.value.trim()
    }

    if (parsedProfile.value?.years_of_experience) {
      yearsOfExp.value = parsedProfile.value.years_of_experience
    }
  } catch (err: any) {
    handleError(err)
  } finally {
    isParsing.value = false
  }
}

async function pollForCompletedCheckpoint(cpId: string, maxAttempts = 30, intervalMs = 3000): Promise<GeneratePlanResponse | null> {
  isPollingCheckpoint.value = true
  pollingMessage.value = 'Generation is still processing on the backend service. Polling checkpoint status...'
  for (let i = 0; i < maxAttempts; i++) {
    try {
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
      const cp = await api.getPlannerCheckpoint(cpId)
      if (cp) {
        if (cp.status === 'COMPLETED' && cp.completed_plan) {
          return {
            plan: cp.completed_plan,
            checkpoint_id: cp.checkpoint_id,
            reused_from_checkpoint: true,
            step: 'COMPLETED',
          }
        }
        if (cp.status === 'FAILED') {
          throw new ApiError(cp.last_error || 'Plan generation failed on backend service.', {
            checkpoint_id: cp.checkpoint_id,
            step: cp.failed_step,
            diagnostic_errors: cp.diagnostic_errors,
            can_retry_with_checkpoint: Boolean(cp.coding_exercise),
          })
        }
      }
    } catch (e: any) {
      if (e instanceof ApiError && e.step) throw e
      // If transient network glitch or checkpoint not indexed yet, continue polling
    }
  }
  return null
}

async function handleGeneratePlan(resumeFromCheckpoint: boolean = false) {
  if (!parsedProfile.value) return
  isGenerating.value = true
  clearErrors()

  const cpToUse = resumeFromCheckpoint
    ? (errorCheckpointId.value || activeCheckpointId.value || undefined)
    : (activeCheckpointId.value || `cp_${Math.random().toString(36).substring(2, 10)}`)
  activeCheckpointId.value = cpToUse || null

  try {
    currentStep.value = resumeFromCheckpoint ? 3 : 1
    const res = await api.generateInterviewPlan({
      candidate_profile: parsedProfile.value,
      job_spec: {
        job_title: jobTitle.value,
        years_of_experience: yearsOfExp.value,
        technical_focus: candidateSkills.value.slice(0, 5),
        behavioral_focus: ['System Ownership', 'Incident Post-Mortems', 'Design Tradeoffs'],
        duration_minutes: 45,
        questions_count: 6,
        description: jobDescription.value,
        problem_type: selectedProblemCategory.value || undefined,
      },
      checkpoint_id: cpToUse,
      defer_coding_exercise: deferCodingExercise.value,
    })
    generatedPlan.value = res
    if (res.checkpoint_id) {
      activeCheckpointId.value = res.checkpoint_id
    }
    currentStep.value = 3
  } catch (err: any) {
    const isTimeout = err?.message?.toLowerCase().includes('timeout') || err?.code === 'ECONNABORTED'
    if (isTimeout && cpToUse) {
      errorCheckpointId.value = cpToUse
      try {
        const recoveredPlan = await pollForCompletedCheckpoint(cpToUse)
        if (recoveredPlan) {
          generatedPlan.value = recoveredPlan
          currentStep.value = 3
          clearErrors()
          return
        }
      } catch (pollErr: any) {
        handleError(pollErr)
        return
      } finally {
        isPollingCheckpoint.value = false
        pollingMessage.value = null
      }
    }

    handleError(err)
    if (cpToUse && !errorCheckpointId.value) {
      errorCheckpointId.value = cpToUse
      canResumeFromCheckpoint.value = true
    }
  } finally {
    isGenerating.value = false
    isPollingCheckpoint.value = false
    pollingMessage.value = null
  }
}

function handleError(err: any) {
  console.error('[Planner Error Handler]:', err)
  if (err instanceof ApiError) {
    errorMessage.value = err.message
    errorStep.value = err.step || null
    errorCheckpointId.value = err.checkpointId || null
    diagnosticErrors.value = err.diagnosticErrors || []
    canResumeFromCheckpoint.value = err.canRetryWithCheckpoint || Boolean(err.checkpointId)
  } else {
    errorMessage.value = err.message || 'An unexpected error occurred.'
    errorStep.value = null
    errorCheckpointId.value = null
    diagnosticErrors.value = []
    canResumeFromCheckpoint.value = false
  }
  showDebugDetails.value = diagnosticErrors.value.length > 0
}

function clearErrors() {
  errorMessage.value = null
  errorStep.value = null
  errorCheckpointId.value = null
  diagnosticErrors.value = []
  canResumeFromCheckpoint.value = false
  showDebugDetails.value = false
}

async function handleCreateInterviewFromPlan() {
  if (!generatedPlan.value || !parsedProfile.value) return
  const recruiterId = authStore.recruiterId || '00000000-0000-0000-0000-000000000001'
  try {
    await interviewStore.createInterview(
      {
        job_title: jobTitle.value,
        years_of_experience: yearsOfExp.value,
        questions_count: generatedPlan.value.plan.questions.length,
        duration_minutes: 45,
        technical_focus: generatedPlan.value.plan.primary_focus_areas || candidateSkills.value.slice(0, 5),
        behavioral_focus: ['Leadership', 'System Reliability'],
        description: jobDescription.value,
        instructions: `Candidate: ${candidateName.value}. Tailored plan generated with coding challenge: ${generatedPlan.value.plan.coding_exercise?.title || 'System Problem'}`,
      },
      recruiterId,
    )
    router.push(`/recruiter`)
  } catch (err: any) {
    handleError(err)
  }
}
</script>

<template>
  <div class="flex-1 min-h-0 h-full w-full flex flex-col overflow-y-auto bg-surface p-6 lg:p-8 space-y-8">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <h1 class="text-2xl font-bold text-on-surface">Interview Planner & Blueprint Playground</h1>
          <Badge variant="primary" size="sm">Gemini 2.5 Flash + Kimi Engine</Badge>
          <Badge v-if="activeCheckpointId" variant="secondary" size="sm">
            Checkpoint: {{ activeCheckpointId }}
          </Badge>
        </div>
        <p class="text-sm text-on-surface-variant mt-1">
          Drop candidate resumes to extract structured competency profiles and generate dynamic multi-file coding challenges with automatic checkpointing.
        </p>
      </div>

      <router-link
        to="/recruiter"
        class="flex items-center gap-1.5 text-xs text-on-surface-variant hover:text-on-surface self-start sm:self-center"
      >
        <span class="material-symbols-outlined text-[16px]">arrow_back</span>
        <span>Back to Dashboard</span>
      </router-link>
    </div>

    <!-- Diagnostic Error Banner with Checkpoint Resume -->
    <div
      v-if="errorMessage"
      class="p-5 rounded-2xl bg-error/10 border border-error/30 text-on-surface space-y-3 shadow-lg"
    >
      <div class="flex items-start justify-between gap-3">
        <div class="flex items-start gap-3">
          <span class="material-symbols-outlined text-error text-[22px] mt-0.5">error</span>
          <div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-bold text-error">Plan Generation Failed</span>
              <Badge v-if="errorStep" variant="warning" size="sm">{{ errorStep }}</Badge>
              <Badge v-if="errorCheckpointId" variant="secondary" size="sm">Checkpoint: {{ errorCheckpointId }}</Badge>
            </div>
            <p class="text-xs text-on-surface-variant mt-1 leading-relaxed whitespace-pre-wrap">{{ errorMessage }}</p>
          </div>
        </div>
        <button class="text-xs text-on-surface-variant hover:text-on-surface underline shrink-0" @click="clearErrors">Dismiss</button>
      </div>

      <!-- Checkpoint Resume Callout -->
      <div
        v-if="canResumeFromCheckpoint && errorCheckpointId"
        class="p-3.5 rounded-xl bg-surface-container-high border border-primary/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
      >
        <div class="flex items-center gap-2 text-xs">
          <span class="material-symbols-outlined text-primary text-[18px]">bookmark</span>
          <span class="text-on-surface">
            <strong>Exercises preserved in checkpoint:</strong> Step 2 coding and system design exercises are safely stored. You can resume without re-running exercises.
          </span>
        </div>
        <button
          type="button"
          class="px-4 py-1.5 rounded-lg bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed transition-all flex items-center gap-1.5 shrink-0 shadow"
          :disabled="isGenerating"
          @click="handleGeneratePlan(true)"
        >
          <span class="material-symbols-outlined text-[16px]">replay</span>
          <span>Resume & Retry from Checkpoint</span>
        </button>
      </div>

      <!-- Expandable Debugging Telemetry Details -->
      <div v-if="diagnosticErrors.length > 0" class="pt-1 border-t border-outline-variant/20">
        <button
          type="button"
          class="text-xs text-primary font-semibold flex items-center gap-1 hover:underline"
          @click="showDebugDetails = !showDebugDetails"
        >
          <span class="material-symbols-outlined text-[16px]">
            {{ showDebugDetails ? 'expand_less' : 'expand_more' }}
          </span>
          <span>{{ showDebugDetails ? 'Hide Provider Debugging Telemetry' : 'Show Provider Debugging Telemetry (' + diagnosticErrors.length + ' events)' }}</span>
        </button>

        <div v-if="showDebugDetails" class="mt-2 space-y-1.5 max-h-48 overflow-y-auto font-mono text-[11px]">
          <div
            v-for="(diag, idx) in diagnosticErrors"
            :key="idx"
            class="p-2 rounded-lg bg-surface-container-low border border-outline-variant/30 text-on-surface space-y-0.5"
          >
            <div class="flex items-center justify-between text-xs">
              <span class="font-bold text-amber-400">[{{ diag.provider.toUpperCase() }}] {{ diag.operation }}</span>
              <span v-if="diag.status_code" class="text-error font-bold">HTTP {{ diag.status_code }}</span>
            </div>
            <div class="text-on-surface-variant break-all">{{ diag.error_type }}: {{ diag.message }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 3-Stage Pipeline Progress Tracker -->
    <div v-if="isGenerating" class="p-4 rounded-2xl bg-surface-container border border-primary/30 shadow-lg space-y-3">
      <div class="flex items-center justify-between">
        <span class="text-xs font-bold text-primary uppercase tracking-wider flex items-center gap-1.5">
          <span class="material-symbols-outlined text-[18px] animate-spin">sync</span>
          {{ isPollingCheckpoint ? (pollingMessage || 'Backend is still generating... Polling checkpoint status') : (deferCodingExercise ? '⚡ Generating Fast Plan (Exercises generate during interview questions)' : 'Generating Tailored Interview Plan (with Codebase)') }}
        </span>
        <span class="text-xs text-on-surface-variant font-mono">
          {{ isPollingCheckpoint ? 'Awaiting Backend Completion' : (deferCodingExercise ? 'Fast Mode' : `Step ${currentStep} of 3`) }}
        </span>
      </div>

      <div class="grid grid-cols-3 gap-3 text-xs">
        <div class="p-2.5 rounded-xl border transition-all" :class="currentStep >= 1 ? 'bg-primary/10 border-primary text-primary' : 'bg-surface-container-low border-outline-variant/20 text-on-surface-variant'">
          <div class="font-bold">1. Plan Draft</div>
          <div class="text-[11px] opacity-80">Blueprint & Questions</div>
        </div>
        <div class="p-2.5 rounded-xl border transition-all" :class="deferCodingExercise ? 'bg-surface-container-low border-primary/40 text-primary' : (currentStep >= 2 ? 'bg-primary/10 border-primary text-primary' : 'bg-surface-container-low border-outline-variant/20 text-on-surface-variant')">
          <div class="font-bold">2. Exercises</div>
          <div class="text-[11px] opacity-80">{{ deferCodingExercise ? '⚡ Deferred to Live Questions' : (isBugCategorySelected ? 'Coding & Bug Fix' : 'Coding & System Design') }}</div>
        </div>
        <div class="p-2.5 rounded-xl border transition-all" :class="currentStep >= 3 ? 'bg-primary/10 border-primary text-primary' : 'bg-surface-container-low border-outline-variant/20 text-on-surface-variant'">
          <div class="font-bold">3. Final Plan</div>
          <div class="text-[11px] opacity-80">Rubrics & Ready</div>
        </div>
      </div>
    </div>

    <!-- Step 1: Resume Input -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <!-- Left: Resume Dropzone / Text Editor (5 cols) -->
      <div class="lg:col-span-5 bg-surface-container border border-outline-variant/30 rounded-2xl p-6 shadow-xl space-y-5">
        <div class="flex items-center justify-between border-b border-surface-container-highest pb-3">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary text-[20px]">upload_file</span>
            <h2 class="text-sm font-semibold text-on-surface uppercase tracking-wider">1. Candidate Resume</h2>
          </div>

          <!-- Input Switcher -->
          <div class="flex bg-surface-container-high rounded-lg p-0.5 text-[11px]">
            <button
              class="px-2.5 py-1 rounded-md transition-all"
              :class="inputMode === 'text' ? 'bg-primary text-on-primary font-semibold shadow-sm' : 'text-on-surface-variant'"
              @click="inputMode = 'text'"
            >
              Plain Text
            </button>
            <button
              class="px-2.5 py-1 rounded-md transition-all"
              :class="inputMode === 'upload' ? 'bg-primary text-on-primary font-semibold shadow-sm' : 'text-on-surface-variant'"
              @click="inputMode = 'upload'"
            >
              Upload PDF
            </button>
          </div>
        </div>

        <!-- Plain Text Input Area -->
        <div v-if="inputMode === 'text'" class="space-y-2">
          <textarea
            v-model="resumeText"
            rows="12"
            placeholder="Paste raw resume text here..."
            class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl p-3 text-xs text-on-surface font-mono focus:outline-none focus:border-primary resize-none leading-relaxed"
          ></textarea>
        </div>

        <!-- File Upload Area -->
        <div v-else class="space-y-4">
          <label
            class="border-2 border-dashed border-outline-variant/40 rounded-2xl p-8 flex flex-col items-center justify-center gap-3 cursor-pointer hover:border-primary/60 transition-colors bg-surface-container-low"
          >
            <span class="material-symbols-outlined text-[36px] text-primary">picture_as_pdf</span>
            <div class="text-center">
              <span class="text-xs font-semibold text-on-surface">Click to select candidate PDF resume</span>
              <p class="text-[11px] text-on-surface-variant mt-1">Supports PDF format up to 10MB</p>
            </div>
            <span v-if="selectedFile" class="text-xs font-mono text-primary font-semibold mt-2">
              Selected: {{ selectedFile.name }}
            </span>
            <input type="file" accept=".pdf" class="hidden" @change="handleFileChange" />
          </label>
        </div>

        <!-- Target Job Config -->
        <div class="grid grid-cols-2 gap-3 pt-2">
          <div class="space-y-1">
            <label class="text-[11px] font-medium text-on-surface-variant">Target Job Title</label>
            <input
              v-model="jobTitle"
              type="text"
              class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl px-3 py-1.5 text-xs text-on-surface focus:outline-none focus:border-primary"
            />
          </div>
          <div class="space-y-1">
            <label class="text-[11px] font-medium text-on-surface-variant">Min Experience (Yrs)</label>
            <input
              v-model.number="yearsOfExp"
              type="number"
              min="0"
              class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl px-3 py-1.5 text-xs text-on-surface focus:outline-none focus:border-primary"
            />
          </div>
        </div>

        <div class="space-y-1 pt-1">
          <label class="text-[11px] font-medium text-on-surface-variant">Job Description & Core Challenges</label>
          <textarea
            v-model="jobDescription"
            rows="2"
            placeholder="Paste role description and core technical challenges..."
            class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl px-3 py-1.5 text-xs text-on-surface focus:outline-none focus:border-primary resize-none"
          ></textarea>
        </div>

        <div class="space-y-1 pt-1">
          <label class="text-[11px] font-medium text-on-surface-variant flex items-center justify-between">
            <span>Technical Exercise Category</span>
            <span v-if="isBugCategorySelected" class="text-[10px] text-amber-400 font-normal">
              SysDesign bypassed for Bug exercises
            </span>
          </label>
          <select
            v-model="selectedProblemCategory"
            class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl px-3 py-1.5 text-xs text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="BUG_INVESTIGATION">Bug Investigation (Multi-file Codebase Fix)</option>
            <option value="DEBUGGING">Debugging & Invariant Failure</option>
            <option value="IMPLEMENTATION">Feature Implementation</option>
            <option value="SYSTEM_DESIGN">System Design & Distributed Architecture</option>
            <option value="CODE_REVIEW">Code Review & Quality</option>
            <option value="REFACTORING">Refactoring & Performance</option>
            <option value="">Auto-Detect (Evidence-Driven)</option>
          </select>
        </div>

        <!-- Freeze Cache State Indicator & Parse Actions -->
        <div class="space-y-2 pt-2">
          <div v-if="parsedProfile" class="flex items-center justify-between text-[11px] px-1">
            <div class="flex items-center gap-1.5">
              <span class="material-symbols-outlined text-[16px]" :class="isResumeModified ? 'text-amber-400' : 'text-emerald-400'">
                {{ isResumeModified ? 'edit_note' : 'lock' }}
              </span>
              <span :class="isResumeModified ? 'text-amber-400 font-semibold' : 'text-emerald-400 font-medium'">
                {{ isResumeModified ? 'Resume edited (Re-freeze needed)' : 'Resume Frozen in Cache' }}
              </span>
            </div>
            <button
              type="button"
              class="text-on-surface-variant hover:text-on-surface underline text-[11px]"
              @click="handleParseResume(true)"
            >
              Force Re-freeze
            </button>
          </div>

          <!-- Parse Button -->
          <button
            type="button"
            class="w-full py-3 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed transition-all flex items-center justify-center gap-2 shadow-md"
            :disabled="isParsing"
            @click="handleParseResume(false)"
          >
            <span class="material-symbols-outlined text-[18px]">
              {{ isParsing ? 'sync' : 'auto_fix_high' }}
            </span>
            <span>{{ isParsing ? 'Extracting Profile...' : (parsedProfile && !isResumeModified ? 'Profile Extracted (Cached)' : 'Extract Candidate Profile') }}</span>
          </button>
        </div>
      </div>

      <!-- Right: Extracted Profile & Blueprint Explorer (7 cols) -->
      <div class="lg:col-span-7 space-y-6">
        <!-- Extracted Profile Card -->
        <div class="bg-surface-container border border-outline-variant/30 rounded-2xl p-6 shadow-xl space-y-5">
          <div class="flex items-center justify-between border-b border-surface-container-highest pb-3">
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-primary text-[20px]">badge</span>
              <h2 class="text-sm font-semibold text-on-surface uppercase tracking-wider">2. Extracted Competency Profile</h2>
            </div>
            <Badge v-if="parsedProfile" variant="success" size="sm">Frozen Profile</Badge>
          </div>

          <!-- Empty State -->
          <div v-if="!parsedProfile" class="py-12 text-center text-on-surface-variant space-y-2">
            <span class="material-symbols-outlined text-[36px] text-outline">analytics</span>
            <p class="text-xs">Extract candidate resume on the left to review skills, career timeline, and detected gaps.</p>
          </div>

          <!-- Extracted Details -->
          <div v-else class="space-y-4">
            <div class="flex items-center justify-between bg-surface-container-low p-4 rounded-xl border border-outline-variant/20">
              <div>
                <h3 class="text-base font-bold text-on-surface">{{ candidateName }}</h3>
                <p class="text-xs text-on-surface-variant mt-0.5">
                  {{ parsedProfile.years_of_experience }} Years Experience • {{ parsedProfile.candidate_email || parsedProfile.email || 'Email not specified' }}
                </p>
              </div>
              <div class="flex flex-col items-end gap-2">
                <button
                  class="px-4 py-2 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed transition-all flex items-center gap-1.5 shadow-md"
                  :disabled="isGenerating"
                  @click="handleGeneratePlan(false)"
                >
                  <span class="material-symbols-outlined text-[16px]">
                    {{ isGenerating ? 'sync' : 'psychology' }}
                  </span>
                  <span>{{ isGenerating ? 'Generating Plan...' : 'Generate AI Interview Plan' }}</span>
                </button>
                <label class="flex items-center gap-1.5 text-[11px] text-on-surface-variant cursor-pointer select-none">
                  <input
                    type="checkbox"
                    v-model="deferCodingExercise"
                    class="rounded border-outline-variant text-primary focus:ring-primary h-3.5 w-3.5"
                  />
                  <span>Fast Setup (~4s) • Defer coding exercise to interview</span>
                </label>
              </div>
            </div>

            <!-- Primary Skills -->
            <div class="space-y-1.5">
              <span class="text-xs font-semibold text-on-surface uppercase tracking-wider">Primary Skills</span>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="skill in candidateSkills"
                  :key="skill"
                  class="px-2.5 py-1 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs font-medium"
                >
                  {{ skill }}
                </span>
              </div>
            </div>

            <!-- Detected Gaps & Probing Opportunities -->
            <div v-if="parsedProfile.detected_gaps && parsedProfile.detected_gaps.length > 0" class="space-y-2">
              <span class="text-xs font-semibold text-amber-300 uppercase tracking-wider flex items-center gap-1">
                <span class="material-symbols-outlined text-[16px]">troubleshoot</span>
                Identified Skill Gaps & Suggested Probes
              </span>
              <div class="space-y-2">
                <div
                  v-for="(gap, idx) in parsedProfile.detected_gaps"
                  :key="idx"
                  class="p-3 bg-surface-container-low rounded-xl border border-amber-500/20 text-xs text-on-surface space-y-1"
                >
                  <div class="font-semibold text-amber-300">{{ gap.gap_type || (gap as any).area }}: {{ gap.description }}</div>
                  <div v-if="gap.probe_angle || (gap as any).suggested_probe" class="text-on-surface-variant text-[11px] italic">
                    Probe: "{{ gap.probe_angle || (gap as any).suggested_probe }}"
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Generated Plan Preview -->
        <div v-if="generatedPlan" class="bg-surface-container border border-outline-variant/30 rounded-2xl p-6 shadow-xl space-y-5 animate-fade-in">
          <div class="flex items-center justify-between border-b border-surface-container-highest pb-3">
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-primary text-[20px]">psychology</span>
              <h2 class="text-sm font-semibold text-on-surface uppercase tracking-wider">3. AI Interview Blueprint</h2>
              <Badge v-if="generatedPlan.reused_from_checkpoint" variant="secondary" size="sm">Reused from Checkpoint</Badge>
            </div>
            <button
              class="px-4 py-1.5 rounded-xl bg-emerald-500 text-slate-950 font-bold text-xs hover:bg-emerald-400 transition-all flex items-center gap-1.5 shadow-md"
              @click="handleCreateInterviewFromPlan"
            >
              <span class="material-symbols-outlined text-[16px]">rocket_launch</span>
              <span>Launch Interview Room</span>
            </button>
          </div>

          <!-- Questions Bank -->
          <div class="space-y-3">
            <h4 class="text-xs font-semibold text-on-surface uppercase tracking-wider">
              Tailored Question Bank ({{ generatedPlan.plan.questions.length }})
            </h4>
            <div class="space-y-2 max-h-60 overflow-y-auto pr-1">
              <div
                v-for="(q, idx) in generatedPlan.plan.questions"
                :key="idx"
                class="p-3 rounded-xl bg-surface-container-low border border-outline-variant/20 text-xs space-y-1"
              >
                <div class="flex items-center justify-between">
                  <span class="font-semibold text-primary">Q{{ idx + 1 }}: {{ q.competency }}</span>
                  <Badge variant="secondary" size="sm">{{ q.difficulty }}</Badge>
                </div>
                <p class="text-on-surface">{{ q.question_text }}</p>
              </div>
            </div>
          </div>

          <!-- Coding Challenge Asset -->
          <div v-if="generatedPlan.plan.coding_exercise" class="p-4 rounded-xl bg-surface-container-low border border-outline-variant/20 space-y-2">
            <div class="flex items-center justify-between">
              <span class="font-semibold text-xs text-tertiary flex items-center gap-1.5">
                <span class="material-symbols-outlined text-[16px]">terminal</span>
                Coding Challenge: {{ generatedPlan.plan.coding_exercise.title }}
              </span>
              <Badge variant="warning" size="sm">{{ generatedPlan.plan.coding_exercise.language }}</Badge>
            </div>
            <p class="text-xs text-on-surface-variant">
              {{ generatedPlan.plan.coding_exercise.scenario_description || generatedPlan.plan.coding_exercise.context || generatedPlan.plan.coding_exercise.objective }}
            </p>
            <div class="flex items-center gap-2 pt-1 font-mono text-[11px] text-primary">
              <span>Files:</span>
              <span
                v-for="f in generatedPlan.plan.coding_exercise.code_files"
                :key="f.file_path"
                class="px-2 py-0.5 rounded bg-surface-container-high border border-outline-variant/30"
              >
                {{ f.file_path }}
              </span>
            </div>
          </div>
          <div v-else class="p-4 rounded-xl bg-surface-container-low/70 border border-primary/20 space-y-1.5">
            <div class="flex items-center justify-between">
              <span class="font-semibold text-xs text-primary flex items-center gap-1.5">
                <span class="material-symbols-outlined text-[16px]">bolt</span>
                Coding Challenge: Deferred to Live Interview (Fast Setup)
              </span>
              <Badge variant="primary" size="sm">JIT Background Task</Badge>
            </div>
            <p class="text-xs text-on-surface-variant">
              The coding exercise will be generated and AST-validated in the background as soon as the candidate enters the interview room, eliminating upfront waiting time.
            </p>
          </div>

          <!-- System Design Exercise Status / Preview -->
          <div v-if="generatedPlan.plan.system_design_exercise" class="p-4 rounded-xl bg-surface-container-low border border-outline-variant/20 space-y-2">
            <div class="flex items-center justify-between">
              <span class="font-semibold text-xs text-secondary flex items-center gap-1.5">
                <span class="material-symbols-outlined text-[16px]">account_tree</span>
                System Design Challenge: {{ generatedPlan.plan.system_design_exercise.title }}
              </span>
              <Badge variant="primary" size="sm">Architecture</Badge>
            </div>
            <p class="text-xs text-on-surface-variant">
              {{ generatedPlan.plan.system_design_exercise.scenario_prompt || generatedPlan.plan.system_design_exercise.objective }}
            </p>
          </div>
          <div v-else-if="generatedPlan.plan.coding_exercise" class="p-3 rounded-xl bg-surface-container-low/60 border border-outline-variant/20 text-xs text-on-surface-variant flex items-center gap-2">
            <span class="material-symbols-outlined text-[18px] text-amber-400">task_alt</span>
            <span>Technical assessment is focused on hands-on code investigation (System Design generation skipped).</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
