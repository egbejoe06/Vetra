<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/services/api'
import type {
  InterviewEvaluationResponse,
  InterviewResponse,
  InterviewSessionResponse,
  TranscriptTurnResponse,
} from '@/types'
import Badge from '@/components/common/Badge.vue'
import ScorecardOverview from '@/components/scorecard/ScorecardOverview.vue'
import RubricScoreList from '@/components/scorecard/RubricScoreList.vue'
import QuestionScoreList from '@/components/scorecard/QuestionScoreList.vue'
import AuditTranscript from '@/components/scorecard/AuditTranscript.vue'
import AuditTrailView from '@/components/scorecard/AuditTrailView.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isCandidate = computed(() => authStore.userRole === 'candidate')
const isRecruiter = computed(() => !isCandidate.value)

const sessionId = computed(() => String(route.params.sessionId || ''))
const isLoading = ref(true)
const isSynthesizing = ref(false)
const synthesisError = ref<string | null>(null)
const highlightedTurnId = ref<string | undefined>(undefined)

const session = ref<InterviewSessionResponse | null>(null)
const interview = ref<InterviewResponse | null>(null)
const evaluation = ref<InterviewEvaluationResponse | null>(null)
const transcriptTurns = ref<TranscriptTurnResponse[]>([])

async function loadData() {
  if (!sessionId.value) return
  try {
    isLoading.value = true
    synthesisError.value = null

    // 1. Fetch active/completed session
    session.value = await api.getSession(sessionId.value)

    // 2. Fetch interview template details
    if (session.value?.interview_id) {
      try {
        interview.value = await api.getInterview(session.value.interview_id)
      } catch (e) {
        console.warn('Could not load interview details:', e)
      }
    }

    // 3. Fetch chronological dialogue transcript
    try {
      transcriptTurns.value = await api.getTranscript(sessionId.value)
    } catch (e) {
      console.warn('Could not load transcript turns:', e)
    }

    // 4. Fetch evaluation scorecard — poll with retries to handle the background
    //    synthesis race condition (session just completed, DB write still in flight)
    if (session.value?.status === 'COMPLETED') {
      const MAX_POLLS = 5
      const POLL_INTERVAL_MS = 2000
      for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
        evaluation.value = await api.getSessionEvaluation(sessionId.value)
        if (evaluation.value) break
        if (attempt < MAX_POLLS - 1) {
          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
        }
      }
    } else {
      evaluation.value = await api.getSessionEvaluation(sessionId.value)
    }

    // If still not found after polling, trigger an explicit synthesis
    if (!evaluation.value && session.value?.status === 'COMPLETED' && transcriptTurns.value.length > 0) {
      await handleSynthesizeReport(false)
    }
  } catch (err: any) {
    console.error('Error loading scorecard data:', err)
  } finally {
    isLoading.value = false
  }
}

async function handleSynthesizeReport(showLoadingOverlay = true) {
  if (!sessionId.value) return
  try {
    if (showLoadingOverlay) {
      isSynthesizing.value = true
    }
    synthesisError.value = null
    await api.synthesizeReport(sessionId.value)
    // Re-fetch from DB so recruiter dashboard sees the same persisted record
    evaluation.value = await api.getSessionEvaluation(sessionId.value)
  } catch (err: any) {
    console.error('Failed to synthesize report:', err)
    synthesisError.value = err.message || 'Failed to synthesize candidate evaluation report.'
  } finally {
    isSynthesizing.value = false
  }
}

function handleNavigateTurn(turnId: string) {
  highlightedTurnId.value = turnId
  const el = document.getElementById(turnId)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="flex-1 min-h-0 h-full w-full flex flex-col overflow-y-auto bg-surface p-6 lg:p-8 space-y-8 select-none">
    <!-- Header Navigation -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <h1 class="text-2xl font-bold text-on-surface">
            {{ isCandidate ? 'Interview Performance Report' : 'Candidate Evaluation & Audit Scorecard' }}
          </h1>
          <Badge :variant="isCandidate ? 'success' : 'primary'" size="sm">
            {{ isCandidate ? 'Interview Completed' : 'Phase 6 Grounded Report' }}
          </Badge>
        </div>
        <p class="text-sm text-on-surface-variant mt-1">
          {{ isCandidate
            ? 'Comprehensive performance review, verified demonstrated strengths, and category feedback.'
            : 'Calibrated scoring rubric, deterministic mathematical weighting, and grounded dialogue audit trail.' }}
        </p>
      </div>

      <div class="flex items-center gap-3">
        <!-- Re-synthesize Button (Recruiter Only) -->
        <button
          v-if="isRecruiter"
          type="button"
          class="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-surface-container-high border border-outline-variant/30 text-xs font-semibold text-on-surface hover:bg-surface-container-highest transition-all disabled:opacity-50"
          :disabled="isSynthesizing"
          @click="() => handleSynthesizeReport(true)"
        >
          <span
            class="material-symbols-outlined text-[16px]"
            :class="{ 'animate-spin': isSynthesizing }"
          >
            {{ isSynthesizing ? 'sync' : 'auto_awesome' }}
          </span>
          <span>{{ isSynthesizing ? 'Synthesizing...' : 'Re-synthesize Scorecard' }}</span>
        </button>

        <!-- Navigation Button -->
        <router-link
          v-if="isRecruiter"
          to="/recruiter"
          class="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-surface-container-high border border-outline-variant/30 text-xs font-semibold text-on-surface hover:bg-surface-container-highest transition-all"
        >
          <span class="material-symbols-outlined text-[16px]">dashboard</span>
          <span>Recruiter Dashboard</span>
        </router-link>
        <template v-else>
          <router-link
            v-if="session?.room_code"
            :to="`/join?code=${session.room_code}&redo=true`"
            class="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:opacity-90 transition-all shadow-md"
          >
            <span class="material-symbols-outlined text-[16px]">replay</span>
            <span>Redo Interview</span>
          </router-link>
          <router-link
            to="/candidate"
            class="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-surface-container-high border border-outline-variant/30 text-xs font-semibold text-on-surface hover:bg-surface-container-highest transition-all"
          >
            <span class="material-symbols-outlined text-[16px]">home</span>
            <span>Candidate Dashboard</span>
          </router-link>
        </template>
      </div>
    </div>

    <!-- Synthesis Error Banner (if any) -->
    <div
      v-if="synthesisError"
      class="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300 flex items-start justify-between gap-3 animate-fade-in"
    >
      <div class="flex items-start gap-2">
        <span class="material-symbols-outlined text-rose-400 text-[18px] shrink-0 mt-0.5">error</span>
        <div>
          <span class="font-semibold">Synthesis Error:</span> {{ synthesisError }}
        </div>
      </div>
      <button class="underline hover:text-white" @click="synthesisError = null">Dismiss</button>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="flex flex-col items-center justify-center py-24 space-y-4">
      <div class="w-10 h-10 border-2 border-primary/20 border-t-primary rounded-full animate-spin"></div>
      <p class="text-xs text-on-surface-variant font-mono">Loading session evaluation & transcript turns...</p>
    </div>

    <!-- Main Content when loaded -->
    <div v-else class="space-y-8">
      <!-- 1. Evaluation Available State -->
      <div v-if="evaluation" class="space-y-8">
        <!-- Executive Overview Card -->
        <ScorecardOverview
          :evaluation="evaluation"
          :job-title="interview?.job_title"
          :show-hiring-signal="isRecruiter"
        />

        <!-- Rubric Breakdown Cards -->
        <RubricScoreList
          :rubric-scores="evaluation.rubric_scores"
          @navigate-turn="handleNavigateTurn"
        />

        <!-- Question-by-Question Breakdown -->
        <QuestionScoreList
          v-if="evaluation.question_scores && evaluation.question_scores.length > 0"
          :question-scores="evaluation.question_scores"
        />

        <!-- Evidence & Citation Audit Trail (Recruiter Only) -->
        <AuditTrailView
          v-if="isRecruiter && evaluation.audit_trail && evaluation.audit_trail.length > 0"
          :audit-trail="evaluation.audit_trail"
        />
      </div>

      <!-- 2. Evaluation Pending / Not Generated State -->
      <div
        v-else
        class="bg-surface-container border border-outline-variant/30 rounded-2xl p-8 shadow-xl text-center space-y-4"
      >
        <div class="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto text-primary">
          <span class="material-symbols-outlined text-[32px]" :class="{ 'animate-spin': isSynthesizing }">
            {{ isSynthesizing ? 'sync' : 'insights' }}
          </span>
        </div>
        <div class="space-y-1 max-w-md mx-auto">
          <h3 class="text-base font-bold text-on-surface">
            {{ isSynthesizing ? 'Generating Calibrated Report...' : 'Scorecard Evaluation Pending' }}
          </h3>
          <p class="text-xs text-on-surface-variant leading-relaxed">
            {{ isSynthesizing
              ? 'Evaluating transcript responses against interview rubrics and compiling verified feedback...'
              : `This interview session contains ${transcriptTurns.length} dialogue turns. The final calibrated scorecard report is being prepared.` }}
          </p>
        </div>
        <div v-if="isRecruiter">
          <button
            type="button"
            class="px-5 py-2.5 rounded-xl bg-primary text-on-primary text-xs font-semibold hover:bg-primary-fixed transition-all inline-flex items-center gap-2"
            :disabled="isSynthesizing"
            @click="() => handleSynthesizeReport(true)"
          >
            <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isSynthesizing }">
              {{ isSynthesizing ? 'sync' : 'auto_awesome' }}
            </span>
            <span>{{ isSynthesizing ? 'Generating Report...' : 'Generate Scorecard with Phase 6 AI Synthesizer' }}</span>
          </button>
        </div>
      </div>

      <!-- 3. Chronological Dialogue Audit Transcript (Always Real Data) -->
      <AuditTranscript
        :transcript-turns="transcriptTurns"
        :highlighted-turn-id="highlightedTurnId"
      />
    </div>
  </div>
</template>
