<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useInterviewStore } from '@/stores/interview'
import { api } from '@/services/api'
import Badge from '@/components/common/Badge.vue'
import Modal from '@/components/common/Modal.vue'
import AuditTranscript from '@/components/scorecard/AuditTranscript.vue'
import { useToastStore } from '@/stores/toast'
import type { InterviewCreate, InterviewResponse, TranscriptTurnResponse } from '@/types'
import { QuestionDifficulty } from '@/types'

const router = useRouter()
const authStore = useAuthStore()
const interviewStore = useInterviewStore()
const toastStore = useToastStore()

const dashboardError = ref<string | null>(null)
const isCreateModalOpen = ref(false)
const createError = ref<string | null>(null)
const isCreating = ref(false)

// Delete confirmation modal state
const isDeleteModalOpen = ref(false)
const interviewToDelete = ref<InterviewResponse | null>(null)
const isDeleting = ref(false)
const deleteError = ref<string | null>(null)

const isEvaluationsModalOpen = ref(false)
const selectedInterviewForEvals = ref<InterviewResponse | null>(null)
const evaluationsLoading = ref(false)
const copiedCode = ref<string | null>(null)
const techFocusInput = ref('')
const behavioralFocusInput = ref('')

const form = reactive<InterviewCreate>({
  job_title: '',
  years_of_experience: 3,
  seniority: undefined,
  questions_count: 8,
  duration_minutes: 45,
  technical_focus: [],
  behavioral_focus: [],
  instructions: '',
  description: '',
  evaluation_criteria: '',
})

function resetForm() {
  form.job_title = ''
  form.years_of_experience = 3
  form.seniority = undefined
  form.questions_count = 8
  form.duration_minutes = 45
  form.technical_focus = []
  form.behavioral_focus = []
  form.instructions = ''
  form.description = ''
  form.evaluation_criteria = ''
  techFocusInput.value = ''
  behavioralFocusInput.value = ''
  createError.value = null
}

function openCreateModal() {
  resetForm()
  isCreateModalOpen.value = true
}

function openDeleteModal(interview: InterviewResponse) {
  interviewToDelete.value = interview
  deleteError.value = null
  isDeleteModalOpen.value = true
}

function closeDeleteModal() {
  if (isDeleting.value) return
  isDeleteModalOpen.value = false
  interviewToDelete.value = null
  deleteError.value = null
}

async function confirmDeleteInterview() {
  if (!interviewToDelete.value) return
  isDeleting.value = true
  deleteError.value = null
  const target = interviewToDelete.value
  try {
    await interviewStore.deleteInterview(target.id, authStore.recruiterId)
    toastStore.success(`Interview "${target.job_title}" was successfully deleted.`)
    closeDeleteModal()
  } catch (err: any) {
    deleteError.value = err.message || 'Failed to delete interview template.'
  } finally {
    isDeleting.value = false
  }
}

async function loadInterviews() {
  dashboardError.value = null
  try {
    await interviewStore.fetchInterviews(authStore.recruiterId)
  } catch (err: any) {
    dashboardError.value = err.message || 'Failed to load interview templates.'
  }
}

onMounted(() => {
  loadInterviews()
})

function addTechFocus() {
  const raw = techFocusInput.value.trim()
  if (!raw) return
  form.technical_focus = form.technical_focus || []
  const items = raw.split(/[\s,;]+/).map(s => s.trim()).filter(Boolean)
  for (const item of items) {
    if (!form.technical_focus.includes(item)) {
      form.technical_focus.push(item)
    }
  }
  techFocusInput.value = ''
}

function removeTechFocus(idx: number) {
  form.technical_focus?.splice(idx, 1)
}

function addBehavioralFocus() {
  const raw = behavioralFocusInput.value.trim()
  if (!raw) return
  form.behavioral_focus = form.behavioral_focus || []
  const items = (raw.includes(',') || raw.includes(';'))
    ? raw.split(/[,;]+/).map(s => s.trim()).filter(Boolean)
    : [raw]
  for (const item of items) {
    if (!form.behavioral_focus.includes(item)) {
      form.behavioral_focus.push(item)
    }
  }
  behavioralFocusInput.value = ''
}

function removeBehavioralFocus(idx: number) {
  form.behavioral_focus?.splice(idx, 1)
}

async function handleCreateInterview() {
  createError.value = null
  if (!form.job_title.trim()) {
    createError.value = 'Please provide a job title / target role.'
    return
  }

  isCreating.value = true
  const recruiterId = authStore.recruiterId || '00000000-0000-0000-0000-000000000001'
  try {
    const created = await interviewStore.createInterview(form, recruiterId)
    toastStore.success(`Interview "${created.job_title}" created with Room Code ${created.room_code}!`)
    isCreateModalOpen.value = false
    resetForm()
    // Show success and copy code
    copyCandidateLink(created.room_code)
  } catch (err: any) {
    createError.value = err.message || 'Failed to create interview template.'
    console.error('Failed to create interview:', err)
  } finally {
    isCreating.value = false
  }
}

function copyCandidateLink(roomCode: string) {
  const link = `${window.location.origin}/join?code=${roomCode}`
  navigator.clipboard.writeText(link)
  copiedCode.value = roomCode
  toastStore.info(`Candidate link copied: ${link}`, { title: `Room Code ${roomCode}` })
  setTimeout(() => {
    copiedCode.value = null
  }, 3000)
}


const isCriteriaModalOpen = ref(false)
const selectedInterviewForCriteria = ref<InterviewResponse | null>(null)

function parseCriteriaList(val: any): string[] {
  if (!val) return []
  if (Array.isArray(val)) {
    return val.map((s) => String(s).trim()).filter(Boolean)
  }
  if (typeof val === 'string') {
    const trimmed = val.trim()
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      return trimmed
        .slice(1, -1)
        .split(',')
        .map((s) => s.replace(/^"|"$/g, '').trim())
        .filter(Boolean)
    }
    if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
      try {
        const parsed = JSON.parse(trimmed)
        if (Array.isArray(parsed)) return parsed.map((s) => String(s).trim()).filter(Boolean)
      } catch {}
    }
    return trimmed.split(',').map((s) => s.trim()).filter(Boolean)
  }
  return []
}

function getInterviewCriteria(interview: InterviewResponse): string[] {
  const tech = parseCriteriaList(interview.technical_focus)
  const beh = parseCriteriaList(interview.behavioral_focus)
  const combined = [...tech]
  for (const b of beh) {
    if (!combined.includes(b)) {
      combined.push(b)
    }
  }
  return combined
}

function openCriteriaModal(interview: InterviewResponse) {
  selectedInterviewForCriteria.value = interview
  isCriteriaModalOpen.value = true
}

const expandedEvalSessionId = ref<string | null>(null)
const evalTranscriptMap = ref<Record<string, TranscriptTurnResponse[]>>({})
const evalTranscriptLoading = ref<Record<string, boolean>>({})
const evalActiveTab = ref<Record<string, 'report' | 'transcript'>>({})

async function openEvaluationsModal(interview: InterviewResponse) {
  selectedInterviewForEvals.value = interview
  isEvaluationsModalOpen.value = true
  evaluationsLoading.value = true
  expandedEvalSessionId.value = null
  try {
    await interviewStore.fetchEvaluations(interview.id)
  } finally {
    evaluationsLoading.value = false
  }
}

async function toggleEvaluationDetail(sessionId: string) {
  if (expandedEvalSessionId.value === sessionId) {
    expandedEvalSessionId.value = null
    return
  }
  expandedEvalSessionId.value = sessionId
  if (!evalActiveTab.value[sessionId]) {
    evalActiveTab.value[sessionId] = 'report'
  }
  if (!evalTranscriptMap.value[sessionId]) {
    evalTranscriptLoading.value[sessionId] = true
    try {
      evalTranscriptMap.value[sessionId] = await api.getTranscript(sessionId)
    } catch (err) {
      console.warn('Could not fetch candidate transcript:', err)
      evalTranscriptMap.value[sessionId] = []
    } finally {
      evalTranscriptLoading.value[sessionId] = false
    }
  }
}

function navigateToScorecard(sessionId: string) {
  isEvaluationsModalOpen.value = false
  router.push(`/evaluations/${sessionId}`)
}
</script>

<template>
  <div class="flex-1 min-h-0 h-full w-full flex flex-col overflow-y-auto bg-surface p-6 lg:p-8 space-y-8">
    <!-- Header with Actions -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <h1 class="text-2xl font-bold text-on-surface">Recruiter Dashboard</h1>
          <Badge variant="primary" size="sm">Recruiter Portal</Badge>
        </div>
        <p class="text-sm text-on-surface-variant mt-1">
          Configure interview blueprints, issue 6-digit candidate access codes, and monitor candidate evaluations.
        </p>
      </div>

      <div class="flex items-center gap-3">
        <button
          class="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed transition-all shadow-md"
          @click="openCreateModal"
        >
          <span class="material-symbols-outlined text-[18px]">add_circle</span>
          <span>Create Interview</span>
        </button>
      </div>
    </div>

    <!-- Global Dashboard Error Banner -->
    <div
      v-if="dashboardError || interviewStore.errorMessage"
      class="p-4 rounded-2xl bg-error/15 border border-error/30 text-error text-xs flex items-center justify-between animate-fade-in"
    >
      <div class="flex items-center gap-2.5">
        <span class="material-symbols-outlined text-[20px] shrink-0">error</span>
        <span>{{ dashboardError || interviewStore.errorMessage }}</span>
      </div>
      <button
        type="button"
        class="text-xs underline hover:text-white ml-4 shrink-0"
        @click="dashboardError = null; interviewStore.errorMessage = null"
      >
        Dismiss
      </button>
    </div>

    <!-- Quick Stats Grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <div class="p-5 rounded-2xl bg-surface-container border border-outline-variant/20 shadow-md">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-on-surface-variant">Active Interview Templates</span>
          <span class="material-symbols-outlined text-primary text-[20px]">assignment</span>
        </div>
        <p class="text-2xl font-bold text-on-surface mt-2">{{ interviewStore.interviewsList.length }}</p>
      </div>

      <div class="p-5 rounded-2xl bg-surface-container border border-outline-variant/20 shadow-md">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-on-surface-variant">Candidate Evaluations</span>
          <span class="material-symbols-outlined text-tertiary text-[20px]">assessment</span>
        </div>
        <p class="text-2xl font-bold text-on-surface mt-2">{{ interviewStore.evaluationsList.length }}</p>
      </div>

      <div class="p-5 rounded-2xl bg-surface-container border border-outline-variant/20 shadow-md">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-on-surface-variant">Access Codes Generated</span>
          <span class="material-symbols-outlined text-emerald-400 text-[20px]">key</span>
        </div>
        <p class="text-2xl font-bold text-on-surface mt-2 font-mono">{{ interviewStore.interviewsList.filter(i => !!i.room_code).length }}</p>
      </div>
    </div>

    <!-- Copied Alert Banner -->
    <div
      v-if="copiedCode"
      class="p-4 rounded-2xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between animate-fade-in"
    >
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-[18px]">check_circle</span>
        <span>Candidate invite link copied to clipboard! Access Code: <strong>{{ copiedCode }}</strong></span>
      </div>
      <button class="underline hover:text-white" @click="copiedCode = null">Dismiss</button>
    </div>

    <!-- Interview Templates Table -->
    <div class="bg-surface-container border border-outline-variant/30 rounded-2xl overflow-hidden shadow-xl flex flex-col">
      <div class="px-6 py-4 border-b border-surface-container-highest flex items-center justify-between bg-surface-container-low shrink-0">
        <h2 class="text-sm font-semibold text-on-surface uppercase tracking-wider">
          Configured Interview Templates
        </h2>
        <button
          class="text-xs text-primary hover:underline flex items-center gap-1"
          @click="interviewStore.fetchInterviews(authStore.recruiterId)"
        >
          <span class="material-symbols-outlined text-[16px]">refresh</span>
          <span>Refresh</span>
        </button>
      </div>

      <div class="overflow-x-auto overflow-y-auto max-h-[600px]">
        <table class="w-full text-left text-xs">
          <thead class="bg-surface-container-high text-on-surface-variant uppercase tracking-wider font-semibold border-b border-surface-container-highest sticky top-0 z-10 shadow-sm">
            <tr>
              <th class="px-6 py-3.5">Role & Job Title</th>
              <th class="px-6 py-3.5">Experience</th>
              <th class="px-6 py-3.5">Room Code</th>
              <th class="px-6 py-3.5">Criteria & Competencies</th>
              <th class="px-6 py-3.5">Status</th>
              <th class="px-6 py-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-surface-container-highest text-on-surface">
            <tr
              v-for="interview in interviewStore.interviewsList"
              :key="interview.id"
              class="hover:bg-surface-container-high/50 transition-colors"
            >
              <!-- Role -->
              <td class="px-6 py-4 font-semibold text-sm">
                {{ interview.job_title }}
              </td>

              <!-- Experience -->
              <td class="px-6 py-4">
                <div class="flex flex-col gap-1">
                  <span class="font-mono text-on-surface-variant">{{ interview.years_of_experience }} yrs</span>
                  <span
                    v-if="interview.seniority"
                    class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold tracking-wider uppercase bg-secondary/15 text-secondary border border-secondary/20 w-fit"
                  >
                    {{ interview.seniority }}
                  </span>
                </div>
              </td>

              <!-- 6-digit room code -->
              <td class="px-6 py-4">
                <div class="flex items-center gap-2">
                  <span class="px-2.5 py-1 rounded-lg bg-primary/10 border border-primary/30 text-primary font-mono font-bold tracking-widest text-sm">
                    {{ interview.room_code }}
                  </span>
                  <button
                    class="p-1 rounded text-outline hover:text-primary transition-colors"
                    title="Copy candidate join link"
                    @click="copyCandidateLink(interview.room_code)"
                  >
                    <span class="material-symbols-outlined text-[18px]">content_copy</span>
                  </button>
                </div>
              </td>

              <!-- Criteria Tags -->
              <td class="px-6 py-4">
                <div v-if="getInterviewCriteria(interview).length > 0 || interview.evaluation_criteria || interview.instructions" class="flex flex-wrap gap-1 max-w-xs items-center">
                  <span
                    v-for="tag in getInterviewCriteria(interview).slice(0, 3)"
                    :key="tag"
                    class="px-2 py-0.5 rounded-full bg-primary/10 border border-primary/20 text-[10px] text-primary font-medium cursor-pointer hover:bg-primary/20 transition-all"
                    :title="tag"
                    @click="openCriteriaModal(interview)"
                  >
                    {{ tag }}
                  </span>
                  <button
                    v-if="getInterviewCriteria(interview).length > 3"
                    type="button"
                    class="text-[10px] px-1.5 py-0.5 rounded-full bg-surface-container-highest text-outline hover:text-primary transition-colors cursor-pointer self-center"
                    title="View all criteria"
                    @click="openCriteriaModal(interview)"
                  >
                    +{{ getInterviewCriteria(interview).length - 3 }} more
                  </button>
                  <span
                    v-if="interview.evaluation_criteria"
                    class="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400 font-medium cursor-pointer hover:bg-emerald-500/20 transition-all flex items-center gap-0.5"
                    title="Recruiter evaluation criteria configured"
                    @click="openCriteriaModal(interview)"
                  >
                    <span class="material-symbols-outlined text-[12px]">gavel</span>
                    <span>Eval Criteria</span>
                  </span>
                </div>
                <div v-else class="text-[11px] text-on-surface-variant/50 italic flex items-center gap-1">
                  <span class="material-symbols-outlined text-[13px]">info</span>
                  <span>No criteria configured</span>
                </div>
              </td>

              <!-- Status -->
              <td class="px-6 py-4">
                <Badge :variant="interview.status === 'ACTIVE' ? 'success' : interview.status === 'COMPLETED' ? 'secondary' : 'primary'" size="sm">
                  {{ interview.status }}
                </Badge>
              </td>

              <!-- Actions -->
              <td class="px-6 py-4 text-right">
                <div class="flex items-center justify-end gap-2">
                  <button
                    class="px-2.5 py-1.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/30 text-xs text-on-surface hover:text-primary font-medium transition-all flex items-center gap-1"
                    title="View interview criteria"
                    @click="openCriteriaModal(interview)"
                  >
                    <span class="material-symbols-outlined text-[15px]">checklist</span>
                    <span>Criteria</span>
                  </button>
                  <button
                    class="px-2.5 py-1.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/30 text-xs text-on-surface hover:text-primary font-medium transition-all flex items-center gap-1"
                    title="View candidate evaluations"
                    @click="openEvaluationsModal(interview)"
                  >
                    <span class="material-symbols-outlined text-[15px]">assessment</span>
                    <span>Scorecards</span>
                  </button>
                  <button
                    class="px-2.5 py-1.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/30 text-xs text-on-surface-variant hover:text-primary font-medium transition-all flex items-center gap-1"
                    title="Copy candidate invite link"
                    @click="copyCandidateLink(interview.room_code)"
                  >
                    <span class="material-symbols-outlined text-[15px]">content_copy</span>
                    <span>Copy Link</span>
                  </button>
                  <button
                    class="px-2.5 py-1.5 rounded-lg bg-surface-container-high hover:bg-error/15 border border-outline-variant/30 hover:border-error/40 text-xs text-on-surface-variant hover:text-error font-medium transition-all flex items-center gap-1 group"
                    title="Delete interview template"
                    @click="openDeleteModal(interview)"
                  >
                    <span class="material-symbols-outlined text-[15px] group-hover:text-error">delete</span>
                    <span>Delete</span>
                  </button>
                </div>
              </td>
            </tr>

            <!-- Empty State -->
            <tr v-if="interviewStore.interviewsList.length === 0 && !interviewStore.isLoading">
              <td colspan="6" class="px-6 py-12 text-center text-on-surface-variant space-y-3">
                <span class="material-symbols-outlined text-[36px] text-outline">description</span>
                <p class="text-sm">No interview templates created yet.</p>
                <button
                  class="px-4 py-2 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed"
                  @click="openCreateModal"
                >
                  Create First Interview
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create Interview Modal -->
    <Modal
      :is-open="isCreateModalOpen"
      title="Create New AI Interview Template"
      max-width="max-w-2xl"
      @close="isCreateModalOpen = false"
    >
      <form class="space-y-4" @submit.prevent="handleCreateInterview">
        <!-- Error Banner inside Create Modal -->
        <div
          v-if="createError"
          class="p-3.5 rounded-xl bg-error/10 border border-error/30 text-error text-xs flex items-start gap-2.5 animate-fade-in"
        >
          <span class="material-symbols-outlined text-[18px] shrink-0 mt-0.5">error</span>
          <div class="flex-1">
            <span class="font-semibold block text-on-surface">Failed to create interview</span>
            <span class="text-on-surface-variant text-[11px]">{{ createError }}</span>
          </div>
          <button type="button" class="text-outline hover:text-on-surface" @click="createError = null">
            <span class="material-symbols-outlined text-[16px]">close</span>
          </button>
        </div>

        <!-- Job Title -->
        <div class="space-y-1">
          <label class="text-xs font-medium text-on-surface-variant">Job Title / Target Role *</label>
          <input
            v-model="form.job_title"
            required
            type="text"
            placeholder="e.g. Senior Backend Engineer"
            class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-primary"
          />
        </div>

        <!-- Full Description -->
        <div class="space-y-1">
          <label class="text-xs font-medium text-on-surface-variant flex items-center justify-between">
            <span>Full Role & Interview Description</span>
            <span class="text-[11px] text-outline font-normal">What you want the interview to focus on</span>
          </label>
          <textarea
            v-model="form.description"
            rows="3"
            placeholder="Detailed description of the role, team context, key engineering challenges, mission, and core focus of this interview..."
            class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl p-3 text-xs text-on-surface focus:outline-none focus:border-primary resize-none leading-relaxed"
          ></textarea>
        </div>

        <!-- Experience, Seniority & Duration Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <div class="space-y-1">
            <label class="text-xs font-medium text-on-surface-variant">Years of Exp</label>
            <input
              v-model.number="form.years_of_experience"
              type="number"
              min="0"
              max="25"
              class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl px-3 py-2 text-xs text-on-surface focus:outline-none focus:border-primary"
            />
          </div>

          <div class="space-y-1">
            <label class="text-xs font-medium text-on-surface-variant">Seniority Tier</label>
            <select
              v-model="form.seniority"
              class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl px-3 py-2 text-xs text-on-surface focus:outline-none focus:border-primary"
            >
              <option :value="undefined">Auto-detect (from YOE / Title)</option>
              <option :value="QuestionDifficulty.JUNIOR">Junior (0–2 YOE)</option>
              <option :value="QuestionDifficulty.MID">Mid-Level (2–5 YOE)</option>
              <option :value="QuestionDifficulty.SENIOR">Senior (5–8 YOE)</option>
              <option :value="QuestionDifficulty.LEAD">Lead / Staff (>8 YOE)</option>
              <option :value="QuestionDifficulty.PRINCIPAL">Principal / Architect</option>
            </select>
          </div>

          <div class="space-y-1">
            <label class="text-xs font-medium text-on-surface-variant">Questions Count</label>
            <input
              v-model.number="form.questions_count"
              type="number"
              min="3"
              max="20"
              class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl px-3 py-2 text-xs text-on-surface focus:outline-none focus:border-primary"
            />
          </div>

          <div class="space-y-1">
            <label class="text-xs font-medium text-on-surface-variant">Duration (Mins)</label>
            <input
              v-model.number="form.duration_minutes"
              type="number"
              min="15"
              max="120"
              class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl px-3 py-2 text-xs text-on-surface focus:outline-none focus:border-primary"
            />
          </div>
        </div>

        <!-- Technical Focus Tags -->
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-on-surface-variant">Technical Competencies & Focus (Skills)</label>
          <div class="flex gap-2">
            <input
              v-model="techFocusInput"
              type="text"
              placeholder="Add skill (e.g. Python, Redis, Kafka) and press Enter"
              class="flex-1 bg-surface-container-low border border-outline-variant/30 rounded-xl px-4 py-2 text-xs text-on-surface focus:outline-none focus:border-primary"
              @keydown.enter.prevent="addTechFocus"
            />
            <button
              type="button"
              class="px-3 py-2 bg-surface-container-high border border-outline-variant/30 rounded-xl text-xs text-on-surface hover:bg-surface-container-highest"
              @click="addTechFocus"
            >
              Add
            </button>
          </div>
          <div v-if="form.technical_focus && form.technical_focus.length > 0" class="flex flex-wrap gap-1.5 pt-1">
            <span
              v-for="(tag, idx) in form.technical_focus"
              :key="idx"
              class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs"
            >
              <span>{{ tag }}</span>
              <button type="button" class="hover:text-error" @click="removeTechFocus(idx)">
                <span class="material-symbols-outlined text-[14px]">close</span>
              </button>
            </span>
          </div>
          <p v-else class="text-[11px] text-outline italic pt-0.5">No technical skills added yet.</p>
        </div>

        <!-- Behavioral Focus Tags -->
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-on-surface-variant">Behavioral & Cultural Dimensions</label>
          <div class="flex gap-2">
            <input
              v-model="behavioralFocusInput"
              type="text"
              placeholder="Add trait (e.g. Ownership, Incident Management) and press Enter"
              class="flex-1 bg-surface-container-low border border-outline-variant/30 rounded-xl px-4 py-2 text-xs text-on-surface focus:outline-none focus:border-primary"
              @keydown.enter.prevent="addBehavioralFocus"
            />
            <button
              type="button"
              class="px-3 py-2 bg-surface-container-high border border-outline-variant/30 rounded-xl text-xs text-on-surface hover:bg-surface-container-highest"
              @click="addBehavioralFocus"
            >
              Add
            </button>
          </div>
          <div v-if="form.behavioral_focus && form.behavioral_focus.length > 0" class="flex flex-wrap gap-1.5 pt-1">
            <span
              v-for="(tag, idx) in form.behavioral_focus"
              :key="idx"
              class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-tertiary/10 border border-tertiary/20 text-tertiary text-xs"
            >
              <span>{{ tag }}</span>
              <button type="button" class="hover:text-error" @click="removeBehavioralFocus(idx)">
                <span class="material-symbols-outlined text-[14px]">close</span>
              </button>
            </span>
          </div>
          <p v-else class="text-[11px] text-outline italic pt-0.5">No behavioral traits added yet.</p>
        </div>

        <!-- Questioning & Probing Focus -->
        <div class="space-y-1">
          <label class="text-xs font-medium text-on-surface-variant flex items-center justify-between">
            <span class="flex items-center gap-1.5 text-primary">
              <span class="material-symbols-outlined text-[16px]">help_outline</span>
              <span>Questioning & Probing Focus</span>
            </span>
            <span class="text-[11px] text-outline font-normal">What the AI interviewer should ask about</span>
          </label>
          <textarea
            v-model="form.instructions"
            rows="2"
            placeholder="Specific topics, edge cases, project depth, or technical scenarios you want the AI interviewer to probe (e.g. focus questions on concurrency, database locking tradeoffs, and microservice failure modes)..."
            class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl p-3 text-xs text-on-surface focus:outline-none focus:border-primary resize-none leading-relaxed"
          ></textarea>
        </div>

        <!-- Evaluation Criteria & Grading Priorities -->
        <div class="space-y-1">
          <label class="text-xs font-medium text-on-surface-variant flex items-center justify-between">
            <span class="flex items-center gap-1.5 text-emerald-400">
              <span class="material-symbols-outlined text-[16px]">gavel</span>
              <span>Evaluation Criteria & Grading Priorities</span>
            </span>
            <span class="text-[11px] text-outline font-normal">How the candidate answers will be evaluated</span>
          </label>
          <textarea
            v-model="form.evaluation_criteria"
            rows="2"
            placeholder="How you want candidate performance evaluated: key signals to look for, scoring priorities, pass/fail standards (e.g. look for deep trade-off analysis, architectural clarity, and ownership of production failures)..."
            class="w-full bg-surface-container-low border border-outline-variant/30 rounded-xl p-3 text-xs text-on-surface focus:outline-none focus:border-primary resize-none leading-relaxed"
          ></textarea>
        </div>
      </form>

      <template #footer>
        <button
          type="button"
          class="px-4 py-2 rounded-xl text-xs font-medium text-on-surface-variant hover:text-on-surface"
          @click="isCreateModalOpen = false"
        >
          Cancel
        </button>
        <button
          type="button"
          class="px-5 py-2 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed transition-all flex items-center gap-2"
          :disabled="isCreating || interviewStore.isLoading"
          @click="handleCreateInterview"
        >
          <span v-if="isCreating || interviewStore.isLoading" class="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>
          <span>{{ isCreating || interviewStore.isLoading ? 'Generating Template...' : 'Generate 6-Digit Room Code' }}</span>
        </button>
      </template>
    </Modal>

    <!-- Delete Confirmation Modal -->
    <Modal
      :is-open="isDeleteModalOpen"
      title="Delete Interview Template"
      max-width="max-w-md"
      @close="closeDeleteModal"
    >
      <div class="space-y-4">
        <!-- Error Banner inside Delete Modal -->
        <div
          v-if="deleteError"
          class="p-3.5 rounded-xl bg-error/10 border border-error/30 text-error text-xs flex items-start gap-2.5 animate-fade-in"
        >
          <span class="material-symbols-outlined text-[18px] shrink-0 mt-0.5">error</span>
          <div class="flex-1">
            <span class="font-semibold block text-on-surface">Failed to delete interview</span>
            <span class="text-on-surface-variant text-[11px]">{{ deleteError }}</span>
          </div>
          <button type="button" class="text-outline hover:text-on-surface" @click="deleteError = null">
            <span class="material-symbols-outlined text-[16px]">close</span>
          </button>
        </div>

        <div class="flex items-start gap-3 p-4 rounded-xl bg-error/10 border border-error/20 text-on-surface">
          <span class="material-symbols-outlined text-error text-[24px] shrink-0 mt-0.5">warning</span>
          <div class="text-xs space-y-1">
            <p class="font-semibold text-error text-sm">Permanent Deletion Warning</p>
            <p class="text-on-surface-variant leading-relaxed">
              Are you sure you want to delete this interview template? This action cannot be undone. All candidate sessions, transcripts, audio recordings, and evaluation scorecards associated with this room code will be permanently removed.
            </p>
          </div>
        </div>

        <div v-if="interviewToDelete" class="p-3.5 rounded-xl bg-surface-container-low border border-outline-variant/30 space-y-2">
          <div class="flex justify-between items-center text-xs">
            <span class="text-on-surface-variant">Role / Job Title:</span>
            <span class="font-semibold text-on-surface">{{ interviewToDelete.job_title }}</span>
          </div>
          <div class="flex justify-between items-center text-xs">
            <span class="text-on-surface-variant">Room Code:</span>
            <span class="font-mono font-bold text-primary px-2 py-0.5 rounded bg-primary/10 border border-primary/20">
              {{ interviewToDelete.room_code }}
            </span>
          </div>
          <div class="flex justify-between items-center text-xs">
            <span class="text-on-surface-variant">Experience / Duration:</span>
            <span class="text-on-surface">{{ interviewToDelete.years_of_experience }} yrs &bull; {{ interviewToDelete.duration_minutes }} mins</span>
          </div>
        </div>
      </div>

      <template #footer>
        <button
          type="button"
          class="px-4 py-2 rounded-xl text-xs font-medium text-on-surface-variant hover:text-on-surface"
          :disabled="isDeleting"
          @click="closeDeleteModal"
        >
          Cancel
        </button>
        <button
          type="button"
          class="px-4 py-2 rounded-xl bg-error text-on-error text-xs font-semibold hover:bg-error/90 transition-all flex items-center gap-1.5 shadow-md"
          :disabled="isDeleting"
          @click="confirmDeleteInterview"
        >
          <span v-if="isDeleting" class="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>
          <span v-else class="material-symbols-outlined text-[16px]">delete</span>
          <span>{{ isDeleting ? 'Deleting Interview...' : 'Delete Interview' }}</span>
        </button>
      </template>
    </Modal>

    <!-- Candidate Evaluations Modal -->
    <Modal
      :is-open="isEvaluationsModalOpen"
      :title="`Candidate Evaluations: ${selectedInterviewForEvals?.job_title || ''}`"
      max-width="max-w-5xl"
      @close="isEvaluationsModalOpen = false"
    >
      <div v-if="evaluationsLoading" class="py-12 text-center space-y-3">
        <div class="w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin mx-auto"></div>
        <p class="text-xs text-on-surface-variant font-mono">Loading candidate scorecards...</p>
      </div>

      <div v-else-if="interviewStore.evaluationsList.length === 0" class="py-12 text-center space-y-3">
        <span class="material-symbols-outlined text-[36px] text-outline">assignment_late</span>
        <p class="text-sm text-on-surface">No completed candidate evaluations yet.</p>
        <p class="text-xs text-on-surface-variant max-w-sm mx-auto">
          When candidates complete their interview session using room code
          <strong class="text-primary font-mono">{{ selectedInterviewForEvals?.room_code }}</strong>,
          their Phase 6 evaluation scorecard will automatically appear here.
        </p>
      </div>

      <div v-else class="space-y-4 max-h-[620px] overflow-y-auto pr-1">
        <div
          v-for="evaluation in interviewStore.evaluationsList"
          :key="evaluation.id"
          class="rounded-xl bg-surface-container-low border border-outline-variant/20 overflow-hidden transition-all"
          :class="{ 'border-primary/40 shadow-lg ring-1 ring-primary/20': expandedEvalSessionId === evaluation.session_id }"
        >
          <!-- Card Header Bar -->
          <div class="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <h4 class="text-sm font-semibold text-on-surface">{{ evaluation.candidate_name }}</h4>
                <Badge
                  :variant="evaluation.recommendation === 'STRONG_HIRE' || evaluation.recommendation === 'HIRE' ? 'success' : evaluation.recommendation === 'LEAN_HIRE' ? 'primary' : 'warning'"
                  size="sm"
                >
                  {{ evaluation.recommendation.replace('_', ' ') }}
                </Badge>
              </div>
              <p class="text-xs text-on-surface-variant line-clamp-2 max-w-2xl">
                {{ evaluation.summary }}
              </p>
              <div class="flex items-center gap-3 text-[11px] text-outline font-mono pt-0.5">
                <span>Completed: {{ new Date(evaluation.completed_at).toLocaleDateString() }}</span>
                <span>•</span>
                <span>Session: {{ evaluation.session_id.substring(0, 8) }}</span>
              </div>
            </div>

            <div class="flex items-center gap-4 shrink-0">
              <div class="text-right">
                <div class="text-xs text-outline font-medium">Overall Score</div>
                <div class="text-base font-bold text-primary">{{ evaluation.overall_score != null ? evaluation.overall_score.toFixed(1) : 'N/A' }} <span class="text-[10px] text-outline font-normal">/ 10</span></div>
              </div>

              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="px-3 py-1.5 rounded-lg border border-outline-variant/30 text-xs font-medium text-on-surface hover:bg-surface-container-high transition-all flex items-center gap-1"
                  @click="toggleEvaluationDetail(evaluation.session_id)"
                >
                  <span class="material-symbols-outlined text-[15px]">
                    {{ expandedEvalSessionId === evaluation.session_id ? 'expand_less' : 'expand_more' }}
                  </span>
                  <span>{{ expandedEvalSessionId === evaluation.session_id ? 'Hide Details' : 'Inspect' }}</span>
                </button>

                <button
                  type="button"
                  class="px-3 py-1.5 rounded-lg bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed transition-all flex items-center gap-1"
                  @click="navigateToScorecard(evaluation.session_id)"
                >
                  <span>Scorecard</span>
                  <span class="material-symbols-outlined text-[14px]">arrow_forward</span>
                </button>
              </div>
            </div>
          </div>

          <!-- Expanded Candidate Detail Panel -->
          <div
            v-if="expandedEvalSessionId === evaluation.session_id"
            class="border-t border-outline-variant/20 bg-surface-container/50 p-4 space-y-4"
          >
            <!-- Sub-tab Navigation -->
            <div class="flex items-center gap-2 border-b border-surface-container-highest pb-2">
              <button
                type="button"
                class="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5"
                :class="evalActiveTab[evaluation.session_id] === 'report' ? 'bg-primary/20 text-primary border border-primary/30' : 'text-on-surface-variant hover:text-on-surface'"
                @click="evalActiveTab[evaluation.session_id] = 'report'"
              >
                <span class="material-symbols-outlined text-[15px]">assessment</span>
                <span>Evaluation Details & Rubrics</span>
              </button>

              <button
                type="button"
                class="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5"
                :class="evalActiveTab[evaluation.session_id] === 'transcript' ? 'bg-primary/20 text-primary border border-primary/30' : 'text-on-surface-variant hover:text-on-surface'"
                @click="evalActiveTab[evaluation.session_id] = 'transcript'"
              >
                <span class="material-symbols-outlined text-[15px]">forum</span>
                <span>
                  Dialogue Transcript
                  <span v-if="evalTranscriptMap[evaluation.session_id]" class="font-mono text-[10px] ml-1 opacity-70">
                    ({{ evalTranscriptMap[evaluation.session_id]?.length }} turns)
                  </span>
                </span>
              </button>
            </div>

            <!-- Tab 1: Full Report Details & Rubrics -->
            <div v-if="evalActiveTab[evaluation.session_id] === 'report'" class="space-y-4">
              <!-- Full Assessment Summary -->
              <div class="space-y-1.5">
                <div class="text-[11px] font-semibold text-outline uppercase tracking-wider flex items-center gap-1">
                  <span class="material-symbols-outlined text-[16px] text-primary">summarize</span>
                  Executive Assessment Summary
                </div>
                <p class="text-xs text-on-surface leading-relaxed bg-surface-container-low p-3 rounded-lg border border-outline-variant/20">
                  {{ evaluation.summary }}
                </p>
              </div>

              <!-- Strengths & Weaknesses Grid -->
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div class="bg-surface-container-low p-3 rounded-lg border border-emerald-500/20 space-y-1.5">
                  <div class="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                    <span class="material-symbols-outlined text-[15px]">verified</span>
                    Demonstrated Strengths
                  </div>
                  <ul class="space-y-1 text-xs text-on-surface-variant">
                    <li v-for="(s, idx) in evaluation.key_strengths" :key="idx" class="flex items-start gap-1.5">
                      <span class="material-symbols-outlined text-emerald-400 text-[14px] shrink-0 mt-0.5">check</span>
                      <span>{{ s }}</span>
                    </li>
                  </ul>
                </div>

                <div class="bg-surface-container-low p-3 rounded-lg border border-amber-500/20 space-y-1.5">
                  <div class="text-[11px] font-semibold text-amber-300 uppercase tracking-wider flex items-center gap-1">
                    <span class="material-symbols-outlined text-[15px]">warning</span>
                    Areas for Growth
                  </div>
                  <ul class="space-y-1 text-xs text-on-surface-variant">
                    <li v-for="(w, idx) in evaluation.key_weaknesses" :key="idx" class="flex items-start gap-1.5">
                      <span class="material-symbols-outlined text-amber-300 text-[14px] shrink-0 mt-0.5">arrow_right</span>
                      <span>{{ w }}</span>
                    </li>
                  </ul>
                </div>
              </div>

              <!-- Category Rubrics Breakdown with Quotes -->
              <div class="space-y-2">
                <div class="text-[11px] font-semibold text-outline uppercase tracking-wider flex items-center gap-1">
                  <span class="material-symbols-outlined text-[16px] text-primary">rule</span>
                  Category Rubrics Breakdown
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  <div
                    v-for="(r, idx) in evaluation.rubric_scores"
                    :key="idx"
                    class="bg-surface-container-low p-3 rounded-lg border border-outline-variant/20 space-y-2"
                  >
                    <div class="flex items-center justify-between">
                      <span class="text-xs font-bold text-on-surface">{{ r.category }}</span>
                      <span class="text-xs font-bold text-primary">{{ r.score != null ? r.score.toFixed(1) : 'N/A' }} <span class="text-[10px] text-outline font-normal">/ 5.0</span></span>
                    </div>
                    <p class="text-xs text-on-surface-variant leading-relaxed">{{ r.feedback }}</p>
                    <!-- Evidence Quotes -->
                    <div v-if="r.evidence_quotes && r.evidence_quotes.length > 0" class="space-y-1 pt-1 border-t border-outline-variant/10">
                      <div class="text-[10px] text-outline font-medium">Candidate Quotes:</div>
                      <div
                        v-for="(quote, qIdx) in r.evidence_quotes"
                        :key="qIdx"
                        class="text-[11px] text-on-surface-variant italic bg-surface-container-highest/40 p-1.5 rounded border-l-2 border-primary/40"
                      >
                        "{{ quote }}"
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Question Scores (if available) -->
              <div v-if="evaluation.question_scores && evaluation.question_scores.length > 0" class="space-y-2">
                <div class="text-[11px] font-semibold text-outline uppercase tracking-wider flex items-center gap-1">
                  <span class="material-symbols-outlined text-[16px] text-primary">quiz</span>
                  Question-by-Question Scores
                </div>
                <div class="space-y-2">
                  <div
                    v-for="(q, idx) in evaluation.question_scores"
                    :key="idx"
                    class="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/20 flex items-start justify-between gap-3 text-xs"
                  >
                    <div class="space-y-0.5">
                      <div class="font-medium text-on-surface">{{ q.question_text }}</div>
                      <div class="text-on-surface-variant text-[11px]">{{ q.feedback }}</div>
                    </div>
                    <div class="text-xs font-bold text-primary shrink-0">
                      {{ q.score != null ? q.score.toFixed(1) : 'N/A' }} <span class="text-[10px] text-outline font-normal">/ 5.0</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Tab 2: Dialogue Transcript -->
            <div v-else-if="evalActiveTab[evaluation.session_id] === 'transcript'">
              <div v-if="evalTranscriptLoading[evaluation.session_id]" class="py-8 text-center space-y-2">
                <div class="w-6 h-6 border-2 border-primary/20 border-t-primary rounded-full animate-spin mx-auto"></div>
                <p class="text-xs text-on-surface-variant font-mono">Loading full dialogue transcript...</p>
              </div>
              <div v-else-if="!evalTranscriptMap[evaluation.session_id] || (evalTranscriptMap[evaluation.session_id]?.length ?? 0) === 0" class="py-8 text-center text-xs text-on-surface-variant">
                No dialogue turns recorded for this session.
              </div>
              <AuditTranscript
                v-else
                :transcript-turns="evalTranscriptMap[evaluation.session_id] || []"
              />
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <button
          type="button"
          class="px-4 py-2 rounded-xl text-xs font-medium text-on-surface-variant hover:text-on-surface"
          @click="isEvaluationsModalOpen = false"
        >
          Close
        </button>
      </template>
    </Modal>

    <!-- Criteria Breakdown Modal -->
    <Modal
      :is-open="isCriteriaModalOpen"
      :title="`Evaluation Criteria: ${selectedInterviewForCriteria?.job_title || ''}`"
      max-width="max-w-lg"
      @close="isCriteriaModalOpen = false"
    >
      <div v-if="selectedInterviewForCriteria" class="space-y-4 text-xs">
        <div class="p-3 bg-surface-container-low rounded-xl border border-outline-variant/20 flex items-center justify-between">
          <div>
            <div class="text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold">Configured Role</div>
            <div class="text-sm font-bold text-on-surface">{{ selectedInterviewForCriteria.job_title }}</div>
          </div>
          <span class="px-2.5 py-1 rounded-lg bg-primary/10 border border-primary/20 text-primary font-mono font-bold text-xs">
            Code: {{ selectedInterviewForCriteria.room_code }}
          </span>
        </div>

        <!-- Role Description -->
        <div v-if="selectedInterviewForCriteria.description" class="space-y-1.5">
          <div class="font-semibold text-on-surface flex items-center gap-1 text-xs uppercase tracking-wider">
            <span class="material-symbols-outlined text-[16px] text-primary">description</span>
            <span>Role & Interview Description</span>
          </div>
          <p class="p-3 rounded-xl bg-surface-container-low border border-outline-variant/20 text-on-surface leading-relaxed text-xs">
            {{ selectedInterviewForCriteria.description }}
          </p>
        </div>

        <!-- Technical Criteria -->
        <div class="space-y-2">
          <div class="font-semibold text-primary flex items-center gap-1 text-xs uppercase tracking-wider">
            <span class="material-symbols-outlined text-[16px]">code</span>
            <span>Technical Focus Skills</span>
          </div>
          <div v-if="parseCriteriaList(selectedInterviewForCriteria.technical_focus).length" class="flex flex-wrap gap-1.5">
            <span
              v-for="skill in parseCriteriaList(selectedInterviewForCriteria.technical_focus)"
              :key="skill"
              class="px-2.5 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-medium"
            >
              {{ skill }}
            </span>
          </div>
          <p v-else class="text-on-surface-variant/60 italic text-[11px]">No technical criteria configured.</p>
        </div>

        <!-- Behavioral Criteria -->
        <div class="space-y-2">
          <div class="font-semibold text-tertiary flex items-center gap-1 text-xs uppercase tracking-wider">
            <span class="material-symbols-outlined text-[16px]">psychology</span>
            <span>Behavioral & Cultural Dimensions</span>
          </div>
          <div v-if="parseCriteriaList(selectedInterviewForCriteria.behavioral_focus).length" class="flex flex-wrap gap-1.5">
            <span
              v-for="trait in parseCriteriaList(selectedInterviewForCriteria.behavioral_focus)"
              :key="trait"
              class="px-2.5 py-1 rounded-full bg-tertiary/10 border border-tertiary/20 text-tertiary text-xs font-medium"
            >
              {{ trait }}
            </span>
          </div>
          <p v-else class="text-on-surface-variant/60 italic text-[11px]">No behavioral criteria configured.</p>
        </div>

        <!-- Questioning & Probing Focus -->
        <div v-if="selectedInterviewForCriteria.instructions" class="space-y-1.5 pt-2 border-t border-surface-container-highest">
          <div class="font-semibold text-primary flex items-center gap-1 text-xs uppercase tracking-wider">
            <span class="material-symbols-outlined text-[16px]">help_outline</span>
            <span>Questioning & Probing Focus (AI Interviewer)</span>
          </div>
          <p class="p-3 rounded-xl bg-surface-container-low border border-outline-variant/20 text-on-surface leading-relaxed text-xs">
            {{ selectedInterviewForCriteria.instructions }}
          </p>
        </div>

        <!-- Evaluation Criteria & Grading Priorities -->
        <div v-if="selectedInterviewForCriteria.evaluation_criteria" class="space-y-1.5 pt-2 border-t border-surface-container-highest">
          <div class="font-semibold text-emerald-400 flex items-center gap-1 text-xs uppercase tracking-wider">
            <span class="material-symbols-outlined text-[16px]">gavel</span>
            <span>Evaluation Criteria & Grading Priorities (AI Evaluator)</span>
          </div>
          <p class="p-3 rounded-xl bg-surface-container-low border border-emerald-500/20 text-on-surface leading-relaxed text-xs">
            {{ selectedInterviewForCriteria.evaluation_criteria }}
          </p>
        </div>
      </div>

      <template #footer>
        <button
          type="button"
          class="px-4 py-2 rounded-xl text-xs font-medium text-on-surface-variant hover:text-on-surface"
          @click="isCriteriaModalOpen = false"
        >
          Close
        </button>
      </template>
    </Modal>
  </div>
</template>
