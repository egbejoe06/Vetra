import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/services/api'
import {
  type InterviewCreate,
  type InterviewEvaluationResponse,
  type InterviewResponse,
  type InterviewSessionResponse,
  InterviewStage,
  InterviewStatus,
} from '@/types'

export const useInterviewStore = defineStore('interview', () => {
  const currentInterview = ref<InterviewResponse | null>(null)
  const currentSession = ref<InterviewSessionResponse | null>(null)
  const interviewsList = ref<InterviewResponse[]>([])
  const evaluationsList = ref<InterviewEvaluationResponse[]>([])
  const isLoading = ref<boolean>(false)
  const errorMessage = ref<string | null>(null)

  // Stage sequence for progression
  const stageSequence: InterviewStage[] = [
    InterviewStage.INTRO,
    InterviewStage.RESUME_DEEP_DIVE,
    InterviewStage.TECHNICAL_QA,
    InterviewStage.TECHNICAL_EXERCISE,
    InterviewStage.BEHAVIORAL,
    InterviewStage.WRAP_UP,
  ]

  const currentStage = computed<InterviewStage>(() => {
    return currentSession.value?.current_stage || currentInterview.value?.current_stage || InterviewStage.INTRO
  })

  const currentStageIndex = computed<number>(() => {
    return stageSequence.indexOf(currentStage.value)
  })

  // Timer state
  const sessionStartTime = ref<Date | null>(null)
  const elapsedSeconds = ref<number>(0)
  let timerInterval: number | null = null

  function startSessionTimer() {
    sessionStartTime.value = new Date()
    elapsedSeconds.value = 0
    if (timerInterval) clearInterval(timerInterval)
    timerInterval = window.setInterval(() => {
      elapsedSeconds.value++
    }, 1000)
  }

  function stopSessionTimer() {
    if (timerInterval) {
      clearInterval(timerInterval)
      timerInterval = null
    }
  }

  const formattedTimer = computed<string>(() => {
    const mins = Math.floor(elapsedSeconds.value / 60)
    const secs = elapsedSeconds.value % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  })

  // Actions
  async function fetchInterviews(recruiterId?: string) {
    isLoading.value = true
    errorMessage.value = null
    try {
      const params = recruiterId && recruiterId.trim() ? { recruiter_id: recruiterId.trim() } : undefined
      const res = await api.listInterviews(params)
      // If filtering by specific recruiter_id returned nothing, fallback to fetching all available templates
      if ((!res || res.length === 0) && params) {
        const all = await api.listInterviews()
        interviewsList.value = all || []
      } else {
        interviewsList.value = res || []
      }
    } catch (err: any) {
      errorMessage.value = err.message
    } finally {
      isLoading.value = false
    }
  }

  async function createInterview(data: InterviewCreate, recruiterId: string) {
    isLoading.value = true
    errorMessage.value = null
    try {
      const created = await api.createInterview(data, recruiterId)
      currentInterview.value = created
      interviewsList.value.unshift(created)
      return created
    } catch (err: any) {
      errorMessage.value = err.message
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function joinInterviewByCode(roomCode: string, name: string, email: string, redo: boolean = false) {
    isLoading.value = true
    errorMessage.value = null
    try {
      const cleanEmail = email.trim()
      const res = await api.joinInterview({
        room_code: roomCode.trim(),
        candidate_name: name.trim(),
        candidate_email: cleanEmail,
        email: cleanEmail,
        redo,
      })
      currentSession.value = res.session
      currentInterview.value = res.interview
      startSessionTimer()
      return res
    } catch (err: any) {
      errorMessage.value = err.message
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function fetchSession(sessionId: string) {
    isLoading.value = true
    errorMessage.value = null
    try {
      currentSession.value = await api.getSession(sessionId)
      if (currentSession.value.interview_id) {
        currentInterview.value = await api.getInterview(currentSession.value.interview_id)
      }
    } catch (err: any) {
      errorMessage.value = err.message
    } finally {
      isLoading.value = false
    }
  }

  async function setSessionStage(stage: InterviewStage) {
    if (!currentSession.value) return
    try {
      const updated = await api.updateSessionStage(currentSession.value.id, stage)
      currentSession.value.current_stage = updated.current_stage
    } catch (err: any) {
      console.error('Failed to update stage:', err)
    }
  }

  async function endSession() {
    if (!currentSession.value) return
    stopSessionTimer()
    try {
      const completed = await api.completeSession(currentSession.value.id)
      currentSession.value = completed
    } catch (err: any) {
      console.error('Failed to complete session:', err)
    }
  }

  async function fetchEvaluations(interviewId: string) {
    isLoading.value = true
    errorMessage.value = null
    try {
      evaluationsList.value = await api.listInterviewEvaluations(interviewId)
      return evaluationsList.value
    } catch (err: any) {
      errorMessage.value = err.message
      return []
    } finally {
      isLoading.value = false
    }
  }

  async function deleteInterview(interviewId: string, recruiterId?: string) {
    isLoading.value = true
    errorMessage.value = null
    try {
      const res = await api.deleteInterview(interviewId, recruiterId)
      interviewsList.value = interviewsList.value.filter((i) => i.id !== interviewId)
      if (currentInterview.value?.id === interviewId) {
        currentInterview.value = null
      }
      return res
    } catch (err: any) {
      errorMessage.value = err.message
      throw err
    } finally {
      isLoading.value = false
    }
  }

  return {
    currentInterview,
    currentSession,
    interviewsList,
    evaluationsList,
    isLoading,
    errorMessage,
    stageSequence,
    currentStage,
    currentStageIndex,
    elapsedSeconds,
    formattedTimer,
    startSessionTimer,
    stopSessionTimer,
    fetchInterviews,
    createInterview,
    deleteInterview,
    joinInterviewByCode,
    fetchSession,
    setSessionStage,
    endSession,
    fetchEvaluations,
  }
})
