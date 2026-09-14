<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useInterviewStore } from '@/stores/interview'
import { useRealtimeStore } from '@/stores/realtime'
import { useWorkspaceStore } from '@/stores/workspace'
import { useCandidateStore } from '@/stores/candidate'
import { realtimeWebSocket } from '@/services/websocket'
import { audioCaptureService } from '@/services/audioCapture'
import { audioPlayerService } from '@/services/audioPlayer'
import { api } from '@/services/api'
import type { CandidateProfile } from '@/types'
import ControlsBar from '@/components/interview/ControlsBar.vue'
import StageProgressBar from '@/components/interview/StageProgressBar.vue'
import TranscriptView from '@/components/interview/TranscriptView.vue'
import InterviewerTile from '@/components/media/InterviewerTile.vue'
import VideoTile from '@/components/media/VideoTile.vue'
import Modal from '@/components/common/Modal.vue'
import MonacoEditor from '@/components/workspace/MonacoEditor.vue'
import ProblemPrompt from '@/components/workspace/ProblemPrompt.vue'
import { InterviewStage } from '@/types'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const interviewStore = useInterviewStore()
const realtimeStore = useRealtimeStore()
const workspaceStore = useWorkspaceStore()
const candidateStore = useCandidateStore()

const isTranscriptOpen = ref(false)
const isProblemOpen = ref(false)
const isEndModalOpen = ref(false)

const sessionId = computed(() => String(route.params.sessionId || ''))
const isCodingMode = computed(() => workspaceStore.layoutMode === 'coding')

// ---------------------------------------------------------------------------
// Resume Upload Overlay State (PDF Only, No Pasting)
// ---------------------------------------------------------------------------
type UploadStep = 'upload' | 'parsing' | 'planning' | 'ready'

const setupStep = ref<UploadStep>('upload')
const isSetupVisible = ref(true) // overlay is shown until the interview starts
const selectedFile = ref<File | null>(null)
const setupError = ref<string | null>(null)
const parsedProfile = ref<CandidateProfile | null>(null)
const isOverridingResume = ref(false)

const hasStoredResume = computed(() => {
  return candidateStore.hasStoredResume && Boolean(parsedProfile.value || candidateStore.storedProfile)
})

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files && target.files[0]) {
    const file = target.files[0]
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      setupError.value = 'Only PDF resume files (.pdf) are supported. Text pasting is not allowed.'
      return
    }
    selectedFile.value = file
    setupError.value = null
  }
}

/**
 * Full resume → plan → start pipeline.
 * 1. If stored profile exists and no new file selected, use it immediately (skips parsing).
 * 2. If new PDF selected, parse it and persist to profile.
 * 3. Generate tailored interview plan.
 * 4. Send enriched context to backend via WS session_start.
 * 5. Hide overlay → interview begins.
 */
async function handleStartInterview() {
  setupError.value = null

  try {
    // Ensure both AudioContexts are unlocked by this user click gesture
    try {
      await audioCaptureService.resumeAudioContext()
      await audioPlayerService.resume()
      realtimeStore.isAudioSuspended = false
    } catch (audioErr) {
      console.warn('[InterviewRoom] AudioContext unlock warning:', audioErr)
    }

    // --- Step 1: Resolve / Parse Resume ---
    if (!parsedProfile.value || selectedFile.value) {
      setupStep.value = 'parsing'
      try {
        if (!selectedFile.value) {
          setupError.value = 'Please select a PDF resume file to continue.'
          setupStep.value = 'upload'
          return
        }
        parsedProfile.value = await api.parseResumeFile(selectedFile.value)
        // Persist newly parsed resume to candidate profile for future sessions
        candidateStore.uploadResumeFile(selectedFile.value).catch((e) => {
          console.warn('[InterviewRoom] Background profile sync note:', e)
        })
      } catch (err: any) {
        setupError.value = `Resume parsing failed: ${err.message || 'Unknown parsing error'}`
        setupStep.value = 'upload'
        return
      }
    }

    // --- Step 2: Generate Interview Plan (Required for Interview) ---
    setupStep.value = 'planning'
    const interview = interviewStore.currentInterview
    const profile = parsedProfile.value || ({} as any)

    const candidateName = (profile as any).candidate_name || (profile as any).name || authStore.candidateName || 'Candidate'
    const skills: string[] = (profile as any).skills || (profile as any).primary_skills || []
    const gaps: any[] = (profile as any).detected_gaps || []

    const targetRoleSeniority = interview?.years_of_experience ?? profile.years_of_experience ?? 3
    const targetJobTitle = interview?.job_title || 'Software Engineer'
    const jobDescriptionText = interview?.description || 'High-scale engineering role focusing on robust distributed architecture.'

    let plan: any
    try {
      const planRes = await api.generateInterviewPlan({
        candidate_profile: profile,
        job_spec: {
          job_title: targetJobTitle,
          years_of_experience: targetRoleSeniority,
          technical_focus: interview?.technical_focus?.length ? interview.technical_focus : skills.slice(0, 5),
          behavioral_focus: interview?.behavioral_focus?.length ? interview.behavioral_focus : ['System Ownership', 'Communication', 'Design Tradeoffs'],
          duration_minutes: interview?.duration_minutes ?? 45,
          questions_count: interview?.questions_count ?? 6,
          description: jobDescriptionText,
          instructions: interview?.instructions || '',
          ...(interview?.id ? { interview_id: interview.id } : {}),
        },
        defer_coding_exercise: true,
        session_id: sessionId.value,
        force_refresh: true,
      })
      plan = planRes.plan

      // Trigger in-interview background exercise generation immediately so it is ready for Stage 4
      const targetIntId = planRes.interview_id || interview?.id
      if (targetIntId) {
        api.triggerGenerateExercises(targetIntId, sessionId.value, planRes.checkpoint_id, true).catch((e) => {
          console.warn('[InterviewRoom] Background exercise trigger note:', e)
        })
      }
    } catch (err: any) {
      console.error('[InterviewRoom] Plan generation failed:', err)
      setupError.value = `Interview plan generation failed: ${err.message || 'Request timed out'}. Please try again.`
      setupStep.value = 'upload'
      return
    }

    // Preload coding exercise into workspace store if already present
    if (plan.coding_exercise) {
      workspaceStore.loadTechnicalProblem(plan.coding_exercise, false)
    }

    const introSummary = (plan.intro_questions || [])
      .map((q: any, i: number) => `Intro Q${i + 1}: ${q.question_text}`)
      .join('\n')

    const resumeQuestionsSummary = (plan.questions || [])
      .filter((q: any) => q.stage === 'RESUME_DEEP_DIVE' || q.question_type === 'RESUME_DEEP_DIVE' || q.question_type === 'PROJECT_DEEP_DIVE')
      .map((q: any, i: number) => `Resume Q${i + 1} [${q.competency}]: ${q.question_text}`)
      .join('\n')

    const technicalQuestionsSummary = (plan.questions || [])
      .filter((q: any) => q.stage !== 'RESUME_DEEP_DIVE' && q.stage !== 'INTRO' && q.stage !== 'BEHAVIORAL' && q.question_type !== 'RESUME_DEEP_DIVE' && q.question_type !== 'PROJECT_DEEP_DIVE' && q.question_type !== 'BEHAVIORAL')
      .slice(0, 4)
      .map((q: any, i: number) => `Tech Q${i + 1} [${q.competency}]: ${q.question_text}`)
      .join('\n')

    const behavioralQuestionsSummary = (
      plan.behavioral_questions ||
      (plan.questions || []).filter((q: any) => q.stage === 'BEHAVIORAL' || q.question_type === 'BEHAVIORAL')
    )
      .slice(0, 2)
      .map((q: any, i: number) => `Behavioral Q${i + 1} [${q.competency || 'Ownership & Leadership'}]: ${q.question_text}`)
      .join('\n')

    const projectsSummary = (profile.projects || [])
      .map((p: any) => `* Project "${p.name}": ${p.description} (Role: ${p.role || 'Contributor'}, Tech: ${(p.tech_stack || []).join(', ')})`)
      .join('\n')

    const experienceSummary = (profile.work_experience || [])
      .map((w: any) => `* ${w.role} at ${w.company} (${(w.tech_stack || []).join(', ')}): ${(w.responsibilities || []).slice(0, 3).join('; ')}`)
      .join('\n')

    const codingEx = plan.coding_exercise
    let codingSummary = ''
    if (codingEx) {
      const fileList = (codingEx.code_files || []).map((f: any) => f.path || f.file_path).join(', ')
      codingSummary =
        `\n[TECHNICAL CODE REVIEW & ARCHITECTURAL WALKTHROUGH]\n` +
        `Title: ${codingEx.title}\n` +
        `Type: ${codingEx.problem_type || 'CODE_REVIEW'}\n` +
        (codingEx.objective ? `Objective: ${codingEx.objective}\n` : '') +
        `Scenario Prompt: ${codingEx.prompt_question}\n` +
        (codingEx.context ? `Instructions / Context: ${codingEx.context}\n` : '') +
        `Files in Review Workspace: ${fileList || 'Codebase files provided'}\n` +
        (codingEx.discussion_questions?.length ? `Key Discussion Points: ${codingEx.discussion_questions.join('; ')}\n` : '') +
        `CRITICAL DIRECTIVE: Vetra is a 100% voice-driven technical interview. There is ZERO code writing or typing in this interview! Do NOT ask the candidate to write, type, or edit code in the editor. Ask them to inspect the code on screen, trace data flows out loud, explain the root cause and flaws, and verbally talk through how they would architect a fix or refactor. Keep the conversation dynamic, probing, and interactive purely through speech.`
    } else {
      codingSummary = `\n[TECHNICAL CODE REVIEW]: To be determined during the interview.`
    }

    const contextSummary =
      `[TARGET ROLE SPECIFICATION]\n` +
      `Role: ${targetJobTitle}\n` +
      `Required Seniority: ${targetRoleSeniority}+ years of experience\n` +
      `Job Description: ${jobDescriptionText}\n` +
      (interview?.instructions ? `Recruiter Notes: ${interview.instructions}\n` : '') +
      `\n[CANDIDATE PROFILE, WORK HISTORY & PROJECTS]\n` +
      `Name: ${candidateName}\n` +
      `Experience: ${profile.years_of_experience ?? targetRoleSeniority} years\n` +
      `Primary Skills: ${skills.join(', ')}\n` +
      (experienceSummary ? `Work History & Past Employers:\n${experienceSummary}\n` : '') +
      (projectsSummary ? `Claimed Projects:\n${projectsSummary}\n` : '') +
      (gaps.length
        ? `Skill Gaps: ${gaps.map((g: any) => g.area || g.gap_type).filter(Boolean).join(', ')}\n`
        : '') +
      `\n[TAILORED INTERVIEW PLAN]\n` +
      (introSummary ? `[STAGE: INTRO - 2 QUESTIONS REQUIRED]\n${introSummary}\n` : '') +
      (resumeQuestionsSummary ? `\n[STAGE: RESUME DEEP DIVE - WORK EXPERIENCE & PROJECT PROBING]\n${resumeQuestionsSummary}\n` : '') +
      (technicalQuestionsSummary ? `\n[STAGE: TECHNICAL QA]\n${technicalQuestionsSummary}\n` : '') +
      `${codingSummary}\n` +
      (behavioralQuestionsSummary ? `\n[STAGE: BEHAVIORAL - 2 QUESTIONS REQUIRED - NEVER SKIP]\n${behavioralQuestionsSummary}\n` : '') +
      `\n[STAGE: WRAP_UP - CANDIDATE QUESTIONS & POLITE CLOSING - NEVER SKIP]\nInvite candidate to ask questions, answer concisely, and thank them warmly.\n` +
      `\n[CRITICAL INTERVIEWER DIRECTIVES]:\n` +
      `1. INTRO STAGE (EXACTLY 2 QUESTIONS):\n` +
      `   - Q1: Warm welcome, brief intro of Vetra and the interview agenda, ask how they are doing.\n` +
      `   - Q2: Deep tailored introductory question connecting candidate's seniority and background to the job description challenges.\n` +
      `2. RESUME DEEP DIVE: Probe candidate's professional work experience at previous companies (engineering responsibilities, production systems, day-to-day ownership, scale, and team collaboration) as well as specific project architectures. You MUST check their work history, not only side/independent projects. STRICTLY NEVER ask basic textbook questions like 'how do you do REST API' or generic definitions.\n` +
      `3. TECHNICAL QA: 2-3 focused technical questions on core architecture and tradeoffs.\n` +
      `4. TECHNICAL EXERCISE: Interactive codebase walkthrough & verbal code review. CRITICAL: ZERO code writing or typing! Prompt the candidate to inspect the code on screen and talk through data flow, flaws, and solutions out loud. Once the discussion is complete, you MUST call request_stage_transition('BEHAVIORAL')!\n` +
      `5. BEHAVIORAL STAGE (MANDATORY - DO NOT SKIP): Ask the 2 tailored behavioral questions above evaluating ownership, teamwork, and handling project tradeoffs. Once complete, call request_stage_transition('WRAP_UP')!\n` +
      `6. WRAP UP STAGE (MANDATORY - DO NOT SKIP): Ask if candidate has questions for you, answer them supportively, and close warmly.\n` +
      `7. PACING: 2-3 questions per stage maximum. When satisfied, call request_stage_transition to progress.\n` +
      `\nPlease greet ${candidateName} warmly by name and begin with Question 1 of the Introduction.`

    // --- Step 3: Prime AI + Start Interview ---
    setupStep.value = 'ready'
    try {
      if (typeof (realtimeStore as any).sendSessionStart === 'function') {
        realtimeStore.sendSessionStart(contextSummary)
      } else {
        realtimeWebSocket.sendSessionStart(contextSummary)
      }
    } catch (sendErr) {
      console.warn('[InterviewRoom] Send session start warning:', sendErr)
    }

    // Hide the overlay after a brief moment so the candidate sees the room
    setTimeout(() => {
      isSetupVisible.value = false
      interviewStore.startSessionTimer()
    }, 600)
  } catch (fatalErr: any) {
    console.error('[InterviewRoom] Unexpected error starting interview:', fatalErr)
    setupError.value = `Unable to start interview: ${fatalErr.message || 'An unexpected error occurred.'}`
    setupStep.value = 'upload'
  }
}

// ---------------------------------------------------------------------------
// Room Lifecycle
// ---------------------------------------------------------------------------
const unlockAudio = async () => {
  try {
    await audioPlayerService.resume()
    await audioCaptureService.resumeAudioContext()
    realtimeStore.isAudioSuspended = false
  } catch (e) {
    // Ignore
  }
}

onMounted(async () => {
  window.addEventListener('click', unlockAudio, { passive: true })
  window.addEventListener('pointerdown', unlockAudio, { passive: true })
  window.addEventListener('keydown', unlockAudio, { passive: true })

  if (sessionId.value) {
    // 0. Preload candidate profile for instant resume reuse
    await candidateStore.loadProfile()
    if (candidateStore.hasStoredResume && candidateStore.storedProfile) {
      parsedProfile.value = candidateStore.storedProfile
    }

    // 1. Fetch Session & Interview metadata
    await interviewStore.fetchSession(sessionId.value)

    // 2. Preload any existing technical problem for this session in background
    try {
      const problems = await api.getTechnicalProblems(sessionId.value)
      if (problems && problems.length > 0) {
        workspaceStore.loadTechnicalProblem(problems[0], false)
      }
    } catch (err) {
      console.warn('[InterviewRoom] Could not preload technical problem:', err)
    }

    // 3. Connect WebSocket + mic NOW (but AI won't speak until session_start is sent)
    await realtimeStore.connectSession(sessionId.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('click', unlockAudio)
  window.removeEventListener('pointerdown', unlockAudio)
  window.removeEventListener('keydown', unlockAudio)
  realtimeStore.disconnect()
})

function handleSelectStage(stage: InterviewStage) {
  interviewStore.setSessionStage(stage)
  if (stage === InterviewStage.TECHNICAL_EXERCISE) {
    workspaceStore.setLayoutMode('coding')
    if (!workspaceStore.hasProblem && sessionId.value) {
      api.getTechnicalProblems(sessionId.value).then((probs) => {
        if (probs && probs.length > 0) {
          workspaceStore.loadTechnicalProblem(probs[0], true)
        }
      }).catch(console.error)
    }
  } else {
    workspaceStore.setLayoutMode('discussion')
  }
}

function handleSendMessage(text: string) {
  realtimeStore.sendChatMessage(text)
}

async function handleConfirmEndInterview() {
  isEndModalOpen.value = false
  await interviewStore.endSession()
  realtimeStore.disconnect()
  router.push(`/evaluations/${sessionId.value}`)
}
</script>

<template>
  <div class="h-full w-full flex flex-col bg-[#0d0e11] overflow-hidden select-none relative">

    <!-- ======================================================================
         Resume Upload Overlay (shown before interview starts)
         ====================================================================== -->
    <Transition name="overlay-fade">
      <div
        v-if="isSetupVisible"
        class="absolute inset-0 z-50 flex items-center justify-center bg-[#0d0e11]/95 backdrop-blur-sm p-4"
      >
        <div class="w-full max-w-lg bg-surface-container border border-outline-variant/30 rounded-3xl p-8 shadow-2xl space-y-6">

          <!-- Header -->
          <div class="space-y-1">
            <div class="flex items-center gap-2 text-primary">
              <span class="material-symbols-outlined text-[22px]" style="font-variation-settings: 'FILL' 1;">psychology</span>
              <span class="text-sm font-semibold">Vetra AI Interview</span>
            </div>
            <h2 class="text-xl font-bold text-on-surface">
              {{ setupStep === 'parsing' ? 'Reading your resume...' :
                 setupStep === 'planning' ? 'Generating your interview plan...' :
                 setupStep === 'ready'    ? 'Ready! Starting now...' :
                 hasStoredResume && !isOverridingResume ? 'Profile Resume Ready' :
                 'Upload Resume (PDF)' }}
            </h2>
            <p class="text-xs text-on-surface-variant leading-relaxed">
              {{ setupStep === 'upload'
                  ? (hasStoredResume && !isOverridingResume
                      ? 'Your profile resume is verified and loaded. Your interview will be tailored to your background immediately without waiting.'
                      : 'Upload your resume PDF. Vetra AI will parse your technical background and generate a personalized interview.')
                  : setupStep === 'parsing'
                  ? 'Extracting your skills, experience, and background...'
                  : setupStep === 'planning'
                  ? 'Crafting tailored questions and a coding challenge just for you...'
                  : 'Your interviewer is ready. Starting the session...' }}
            </p>
          </div>

          <!-- Progress States -->
          <div v-if="setupStep !== 'upload'" class="space-y-3">
            <!-- Parsing step -->
            <div class="flex items-center gap-3 p-3 rounded-xl"
                 :class="setupStep === 'parsing' ? 'bg-primary/10 border border-primary/20' : 'bg-surface-container-low'">
              <span class="material-symbols-outlined text-[18px]"
                    :class="setupStep === 'parsing' ? 'text-primary animate-spin' : 'text-emerald-400'"
                    style="font-variation-settings: 'FILL' 1;">
                {{ setupStep === 'parsing' ? 'sync' : 'check_circle' }}
              </span>
              <span class="text-xs font-medium"
                    :class="setupStep === 'parsing' ? 'text-primary' : 'text-on-surface-variant'">
                Resume parsed
              </span>
            </div>

            <!-- Planning step -->
            <div class="flex items-center gap-3 p-3 rounded-xl"
                 :class="setupStep === 'planning' ? 'bg-primary/10 border border-primary/20' :
                         setupStep === 'ready'    ? 'bg-surface-container-low' : 'opacity-40 bg-surface-container-low'">
              <span class="material-symbols-outlined text-[18px]"
                    :class="setupStep === 'planning' ? 'text-primary animate-spin' :
                            setupStep === 'ready'    ? 'text-emerald-400' : 'text-outline'"
                    style="font-variation-settings: 'FILL' 1;">
                {{ setupStep === 'planning' ? 'sync' : setupStep === 'ready' ? 'check_circle' : 'radio_button_unchecked' }}
              </span>
              <span class="text-xs font-medium"
                    :class="setupStep === 'planning' ? 'text-primary' : 'text-on-surface-variant'">
                Interview plan generated
              </span>
            </div>


            <!-- Ready step -->
            <div class="flex items-center gap-3 p-3 rounded-xl"
                 :class="setupStep === 'ready' ? 'bg-emerald-500/10 border border-emerald-500/20' : 'opacity-40 bg-surface-container-low'">
              <span class="material-symbols-outlined text-[18px]"
                    :class="setupStep === 'ready' ? 'text-emerald-400' : 'text-outline'"
                    style="font-variation-settings: 'FILL' 1;">
                {{ setupStep === 'ready' ? 'check_circle' : 'radio_button_unchecked' }}
              </span>
              <span class="text-xs font-medium"
                    :class="setupStep === 'ready' ? 'text-emerald-300' : 'text-on-surface-variant'">
                AI interviewer briefed
              </span>
            </div>
          </div>

          <!-- Upload / Resume Selection Form (only shown on 'upload' step) -->
          <template v-if="setupStep === 'upload'">
            <!-- Error -->
            <div v-if="setupError" class="p-3 bg-error/15 border border-error/30 rounded-xl text-error text-xs flex items-center gap-2">
              <span class="material-symbols-outlined text-[16px]">error</span>
              {{ setupError }}
            </div>

            <!-- Scenario A: Stored Profile Resume Available (Instant Start) -->
            <div v-if="hasStoredResume && !isOverridingResume" class="space-y-4">
              <div class="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 space-y-3">
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2 text-emerald-400 text-xs font-bold">
                    <span class="material-symbols-outlined text-[18px]">verified</span>
                    <span>Using Saved Candidate Resume</span>
                  </div>
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/20 text-emerald-300 font-bold">
                    INSTANT
                  </span>
                </div>

                <div class="space-y-1">
                  <div class="text-sm font-bold text-on-surface flex items-center gap-2">
                    <span class="material-symbols-outlined text-primary text-[18px]">picture_as_pdf</span>
                    <span>{{ candidateStore.resumeMetadata?.filename || 'Stored Resume PDF' }}</span>
                  </div>
                  <p class="text-xs text-on-surface-variant">
                    {{ candidateStore.candidateFullName }}
                    <span v-if="candidateStore.detectedExperienceYears">• {{ candidateStore.detectedExperienceYears }} YOE</span>
                    <span v-if="candidateStore.detectedSkills.length">• {{ candidateStore.detectedSkills.length }} Skills</span>
                  </p>
                </div>

                <!-- Detected Skills Snippet -->
                <div v-if="candidateStore.detectedSkills.length" class="flex flex-wrap gap-1 pt-1">
                  <span
                    v-for="(skill, sIdx) in candidateStore.detectedSkills.slice(0, 6)"
                    :key="sIdx"
                    class="px-2 py-0.5 rounded-md bg-surface-container-high text-[10px] font-mono text-on-surface-variant"
                  >
                    {{ skill }}
                  </span>
                  <span v-if="candidateStore.detectedSkills.length > 6" class="text-[10px] text-outline font-mono self-center">
                    +{{ candidateStore.detectedSkills.length - 6 }} more
                  </span>
                </div>
              </div>

              <!-- Instant Start Button -->
              <button
                class="w-full py-3.5 rounded-2xl bg-primary text-on-primary text-sm font-bold hover:bg-primary-fixed transition-all flex items-center justify-center gap-2 shadow-lg cursor-pointer"
                @click="handleStartInterview"
              >
                <span class="material-symbols-outlined text-[20px]" style="font-variation-settings: 'FILL' 1;">rocket_launch</span>
                <span>Start Tailored Interview (Instant)</span>
              </button>

              <!-- Option to upload a different PDF -->
              <div class="text-center pt-1">
                <button
                  type="button"
                  class="text-xs text-on-surface-variant hover:text-primary transition-colors cursor-pointer underline"
                  @click="isOverridingResume = true"
                >
                  Upload a different PDF resume for this session
                </button>
              </div>
            </div>

            <!-- Scenario B: No Stored Resume or User Wants to Override (PDF Only) -->
            <div v-else class="space-y-4">
              <label
                class="border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center gap-3 cursor-pointer transition-colors"
                :class="selectedFile
                  ? 'border-primary/60 bg-primary/5'
                  : 'border-outline-variant/40 hover:border-primary/50 bg-surface-container-low'"
              >
                <span class="material-symbols-outlined text-[36px]"
                      :class="selectedFile ? 'text-primary' : 'text-outline'"
                      style="font-variation-settings: 'FILL' 1;">
                  {{ selectedFile ? 'task' : 'picture_as_pdf' }}
                </span>
                <div class="text-center">
                  <span class="text-xs font-semibold text-on-surface">
                    {{ selectedFile ? selectedFile.name : 'Click to select your resume PDF' }}
                  </span>
                  <p class="text-[11px] text-on-surface-variant mt-0.5">PDF format only (up to 15 MB). Text pasting is disabled.</p>
                </div>
                <input type="file" accept=".pdf,application/pdf" class="hidden" @change="handleFileChange" />
              </label>

              <!-- Start Button -->
              <button
                class="w-full py-3.5 rounded-2xl bg-primary text-on-primary text-sm font-bold hover:bg-primary-fixed transition-all flex items-center justify-center gap-2 shadow-lg cursor-pointer"
                :disabled="!selectedFile"
                :class="{ 'opacity-50 cursor-not-allowed': !selectedFile }"
                @click="handleStartInterview"
              >
                <span class="material-symbols-outlined text-[20px]" style="font-variation-settings: 'FILL' 1;">rocket_launch</span>
                <span>{{ selectedFile ? 'Upload & Start Interview' : 'Select PDF Resume to Continue' }}</span>
              </button>

              <!-- Return to Stored Resume Option if Overriding -->
              <div v-if="hasStoredResume" class="text-center pt-1">
                <button
                  type="button"
                  class="text-xs text-primary hover:underline transition-colors cursor-pointer"
                  @click="isOverridingResume = false; selectedFile = null"
                >
                  ← Back to saved profile resume
                </button>
              </div>

              <p class="text-center text-[11px] text-on-surface-variant">
                Uploaded resumes are stored in your candidate profile for instant reuse in future interviews.
              </p>
            </div>
          </template>
        </div>
      </div>
    </Transition>

    <!-- ======================================================================
         Interview Room — Top Stage Header
         ====================================================================== -->
    <div class="h-14 px-4 bg-surface-container/80 backdrop-blur-md border-b border-surface-container-highest flex items-center justify-between z-20 shrink-0">
      <!-- Session & Role Title -->
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
          <span class="material-symbols-outlined fill text-[18px]">psychology</span>
        </div>
        <div class="hidden sm:flex flex-col">
          <span class="text-xs font-semibold text-on-surface">
            {{ interviewStore.currentInterview?.job_title || 'Technical Interview Session' }}
          </span>
          <span class="text-[10px] text-on-surface-variant font-mono">
            Candidate: {{ authStore.candidateName }}
          </span>
        </div>
      </div>

      <!-- Stage Progression Bar -->
      <StageProgressBar
        :current-stage="interviewStore.currentStage"
        @select-stage="handleSelectStage"
      />

      <!-- Right Area: Header View Mode Switcher + Timer -->
      <div class="flex items-center gap-3">
        <!-- View Mode Switcher (Discussion vs Coding Challenge) -->
        <div class="flex items-center bg-surface-container-low rounded-xl p-1 border border-outline-variant/30 text-xs">
          <button
            type="button"
            class="flex items-center gap-1.5 px-3 py-1 rounded-lg font-medium transition-all cursor-pointer"
            :class="[
              !isCodingMode
                ? 'bg-surface-container-highest text-primary shadow-sm font-semibold'
                : 'text-on-surface-variant hover:text-on-surface'
            ]"
            title="Switch to Face-to-Face Video Discussion"
            @click="workspaceStore.setLayoutMode('discussion')"
          >
            <span class="material-symbols-outlined text-[16px]">co_present</span>
            <span class="hidden md:inline">Discussion</span>
          </button>

          <button
            type="button"
            class="flex items-center gap-1.5 px-3 py-1 rounded-lg font-medium transition-all cursor-pointer relative"
            :class="[
              isCodingMode
                ? 'bg-primary/20 text-primary border border-primary/40 shadow-sm font-semibold'
                : 'text-on-surface-variant hover:text-on-surface'
            ]"
            title="Switch to Code Review Surface (Verbal Walkthrough)"
            @click="workspaceStore.setLayoutMode('coding')"
          >
            <span class="material-symbols-outlined text-[16px]">code</span>
            <span class="hidden md:inline">Code Review</span>
            <span
              v-if="workspaceStore.hasProblem"
              class="w-2 h-2 rounded-full"
              :class="isCodingMode ? 'bg-primary animate-pulse' : 'bg-emerald-400'"
              :title="workspaceStore.hasProblem ? 'Codebase Loaded for Review' : ''"
            ></span>
          </button>
        </div>

        <!-- Timer & Live Indicator -->
        <div class="flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-lowest border border-outline-variant/30 text-xs font-mono">
          <span class="w-2 h-2 rounded-full animate-pulse"
                :class="isSetupVisible ? 'bg-amber-400' : 'bg-emerald-400'"></span>
          <span class="text-primary font-bold">{{ interviewStore.formattedTimer }}</span>
        </div>
      </div>
    </div>

    <!-- Audio Autoplay Unlock Prompt if browser restricted audio -->
    <Transition name="overlay-fade">
      <button
        v-if="realtimeStore.isAudioSuspended && !isSetupVisible"
        type="button"
        class="absolute top-16 left-1/2 -translate-x-1/2 z-40 bg-amber-500 hover:bg-amber-400 text-black font-bold text-xs px-4 py-2 rounded-full shadow-2xl flex items-center gap-2 cursor-pointer transition-all animate-bounce"
        @click="realtimeStore.unlockAudio()"
      >
        <span class="material-symbols-outlined text-[18px]">volume_up</span>
        <span>Click to enable AI interviewer voice</span>
      </button>
    </Transition>

    <!-- ======================================================================
         Main Dynamic Stage Canvas
         ====================================================================== -->
    <div class="flex-1 relative flex overflow-hidden p-3 gap-3">
      <!-- 1. DISCUSSION MODE LAYOUT -->
      <div
        v-if="!isCodingMode"
        class="flex-1 grid grid-cols-1 md:grid-cols-2 gap-3 h-full max-h-full"
      >
        <!-- AI Interviewer Tile -->
        <div class="h-full w-full min-h-[220px]">
          <InterviewerTile
            :is-speaking="realtimeStore.isInterviewerSpeaking"
            :audio-level="realtimeStore.interviewerAudioLevel"
          />
        </div>

        <!-- Candidate Video Tile -->
        <div class="h-full w-full min-h-[220px]">
          <VideoTile
            :candidate-name="authStore.candidateName"
            :is-enabled="realtimeStore.isCameraEnabled"
            :is-muted="realtimeStore.isMicMuted"
            :audio-level="realtimeStore.candidateAudioLevel"
          />
        </div>
      </div>

      <!-- 2. CODING MODE LAYOUT -->
      <div
        v-else
        class="flex-1 relative flex h-full max-h-full gap-3 overflow-hidden"
      >
        <!-- Left 75%: Multi-File Monaco Code Editor Workspace -->
        <div class="flex-1 h-full min-h-0 min-w-0">
          <MonacoEditor />
        </div>

        <!-- Right Side: PiP Floating / Stacked Video Containers -->
        <div class="w-56 flex flex-col gap-3 shrink-0 hidden md:flex">
          <InterviewerTile
            :is-speaking="realtimeStore.isInterviewerSpeaking"
            :audio-level="realtimeStore.interviewerAudioLevel"
            is-pi-p
          />
          <VideoTile
            :candidate-name="authStore.candidateName"
            :is-enabled="realtimeStore.isCameraEnabled"
            :is-muted="realtimeStore.isMicMuted"
            :audio-level="realtimeStore.candidateAudioLevel"
            is-pi-p
          />
        </div>
      </div>

      <!-- Live Transcript Drawer -->
      <div
        v-if="isTranscriptOpen"
        class="w-80 md:w-96 h-full shrink-0 animate-fade-in z-30"
      >
        <TranscriptView
          :turns="realtimeStore.turns"
          :interim-candidate-text="realtimeStore.interimCandidateText"
          :interim-interviewer-text="realtimeStore.interimInterviewerText"
          @send-message="handleSendMessage"
        />
      </div>

      <!-- Problem Prompt Drawer -->
      <div
        v-if="isProblemOpen"
        class="w-80 md:w-96 h-full shrink-0 animate-fade-in z-30"
      >
        <ProblemPrompt />
      </div>
    </div>

    <!-- ======================================================================
         Bottom Call Controls Bar
         ====================================================================== -->
    <ControlsBar
      :is-transcript-open="isTranscriptOpen"
      :is-problem-open="isProblemOpen"
      @toggle-transcript="isTranscriptOpen = !isTranscriptOpen"
      @toggle-problem="isProblemOpen = !isProblemOpen"
      @end-interview="isEndModalOpen = true"
    />

    <!-- ======================================================================
         End Interview Confirmation Modal
         ====================================================================== -->
    <Modal
      :is-open="isEndModalOpen"
      title="End Technical Interview Session?"
      max-width="max-w-md"
      @close="isEndModalOpen = false"
    >
      <div class="space-y-3">
        <p class="text-xs text-on-surface-variant leading-relaxed">
          Are you sure you want to end this interview session? Your dialogue transcript and technical review evaluation will be finalized and submitted for scoring.
        </p>
      </div>

      <template #footer>
        <button
          class="px-4 py-2 rounded-xl text-xs font-medium text-on-surface-variant hover:text-on-surface"
          @click="isEndModalOpen = false"
        >
          Cancel
        </button>
        <button
          class="px-4 py-2 rounded-xl bg-error text-white text-xs font-semibold hover:bg-error/90"
          @click="handleConfirmEndInterview"
        >
          End & View Scorecard
        </button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}
.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
  transform: scale(0.98);
}
</style>
