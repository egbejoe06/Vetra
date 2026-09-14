import axios from 'axios'
import type {
  AuthResponse,
  CandidateProfile,
  CandidateProfileRecord,
  CandidateResumeUploadResponse,
  GeneratePlanRequest,
  GeneratePlanResponse,
  InterviewArtifactResponse,
  InterviewCreate,
  InterviewEvaluationResponse,
  InterviewJoin,
  InterviewJoinResponse,
  InterviewPlanCreate,
  InterviewResponse,
  InterviewSessionResponse,
  InterviewStage,
  InterviewStatus,
  InterviewUpdate,
  TechnicalProblemResponse,
  TranscriptTurnResponse,
  UserCreatePayload,
  UserLoginPayload,
} from '@/types'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('vetra_access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

export class ApiError extends Error {
  detail?: any
  checkpointId?: string
  step?: string
  diagnosticErrors?: any[]
  canRetryWithCheckpoint?: boolean

  constructor(message: string, detail?: any) {
    super(message)
    this.name = 'ApiError'
    this.detail = detail
    if (detail && typeof detail === 'object') {
      this.checkpointId = detail.checkpoint_id
      this.step = detail.step
      this.diagnosticErrors = detail.diagnostic_errors
      this.canRetryWithCheckpoint = Boolean(detail.can_retry_with_checkpoint)
    }
  }
}

import { useToastStore } from '@/stores/toast'

// Response interceptor
apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    let message = 'An unexpected error occurred'
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = detail
        .map((d: any) => (d && typeof d === 'object' && d.msg ? `${d.loc ? d.loc.slice(1).join('.') + ': ' : ''}${d.msg}` : JSON.stringify(d)))
        .join(', ')
    } else if (detail && typeof detail === 'object') {
      message = detail.message || JSON.stringify(detail)
    } else if (error.message) {
      message = error.message
    }
    console.error('[API Error]:', message, error)

    // Notify user via toast unless caller specifically requested silent mode
    if (!error.config?.skipGlobalToast) {
      try {
        const toastStore = useToastStore()
        let detailsString: string | undefined
        if (detail && typeof detail === 'object') {
          detailsString = JSON.stringify(detail, null, 2)
        }
        toastStore.error(message, {
          title: error.response?.status ? `Error (${error.response.status})` : 'Network Error',
          details: detailsString,
        })
      } catch {
        // Fallback if Pinia is not yet initialized
      }
    }

    return Promise.reject(new ApiError(message, detail))
  },
)

export const api = {
  // --------------------------------------------------------------------------
  // 0. Authentication
  // --------------------------------------------------------------------------
  async signup(data: UserCreatePayload): Promise<AuthResponse> {
    return (await apiClient.post('/auth/signup', data)) as unknown as AuthResponse
  },

  async login(data: UserLoginPayload): Promise<AuthResponse> {
    return (await apiClient.post('/auth/login', data)) as unknown as AuthResponse
  },

  // --------------------------------------------------------------------------
  // 1. Interviews (Recruiter)
  // --------------------------------------------------------------------------
  async createInterview(
    data: InterviewCreate,
    recruiterId: string,
  ): Promise<InterviewResponse> {
    return (await apiClient.post('/interviews', data, {
      params: recruiterId && recruiterId.trim() ? { recruiter_id: recruiterId.trim() } : undefined,
    })) as unknown as InterviewResponse
  },

  async listInterviews(params?: {
    recruiter_id?: string
    status?: InterviewStatus
    limit?: number
    offset?: number
  }): Promise<InterviewResponse[]> {
    const cleanParams = params
      ? Object.fromEntries(
          Object.entries(params).filter(([_, v]) => v !== undefined && v !== null && v !== ''),
        )
      : undefined
    return (await apiClient.get('/interviews', {
      params: cleanParams,
    })) as unknown as InterviewResponse[]
  },

  async getInterviewByCode(roomCode: string, skipGlobalToast = true): Promise<InterviewResponse> {
    return (await apiClient.get(`/interviews/code/${roomCode}`, {
      skipGlobalToast,
    } as any)) as unknown as InterviewResponse
  },

  async getInterview(interviewId: string): Promise<InterviewResponse> {
    return (await apiClient.get(
      `/interviews/${interviewId}`,
    )) as unknown as InterviewResponse
  },

  async updateInterview(
    interviewId: string,
    data: InterviewUpdate,
    recruiterId?: string,
  ): Promise<InterviewResponse> {
    return (await apiClient.patch(`/interviews/${interviewId}`, data, {
      params: recruiterId && recruiterId.trim() ? { recruiter_id: recruiterId.trim() } : undefined,
    })) as unknown as InterviewResponse
  },

  async deleteInterview(
    interviewId: string,
    recruiterId?: string,
  ): Promise<{ message: string }> {
    return (await apiClient.delete(`/interviews/${interviewId}`, {
      params: recruiterId && recruiterId.trim() ? { recruiter_id: recruiterId.trim() } : undefined,
    })) as unknown as { message: string }
  },

  // --------------------------------------------------------------------------
  // 2. Candidate Join & Sessions
  // --------------------------------------------------------------------------
  async joinInterview(
    data: InterviewJoin,
    candidateId?: string,
  ): Promise<InterviewJoinResponse> {
    return (await apiClient.post('/interviews/join', data, {
      params: candidateId && candidateId.trim() ? { candidate_id: candidateId.trim() } : undefined,
    })) as unknown as InterviewJoinResponse
  },

  async getSession(sessionId: string): Promise<InterviewSessionResponse> {
    return (await apiClient.get(
      `/interviews/sessions/${sessionId}`,
    )) as unknown as InterviewSessionResponse
  },

  async updateSessionStage(
    sessionId: string,
    stage: InterviewStage,
  ): Promise<InterviewSessionResponse> {
    return (await apiClient.patch(`/interviews/sessions/${sessionId}/stage`, {
      current_stage: stage,
    })) as unknown as InterviewSessionResponse
  },

  async updateSessionStatus(
    sessionId: string,
    status: InterviewStatus,
  ): Promise<InterviewSessionResponse> {
    return (await apiClient.patch(`/interviews/sessions/${sessionId}/status`, {
      status,
    })) as unknown as InterviewSessionResponse
  },

  async completeSession(sessionId: string): Promise<InterviewSessionResponse> {
    return (await apiClient.post(
      `/interviews/sessions/${sessionId}/complete`,
    )) as unknown as InterviewSessionResponse
  },

  // --------------------------------------------------------------------------
  // 3. Problems, Artifacts & Transcripts
  // --------------------------------------------------------------------------
  async getTechnicalProblems(
    sessionId: string,
  ): Promise<TechnicalProblemResponse[]> {
    return (await apiClient.get(
      `/interviews/sessions/${sessionId}/technical-problems`,
    )) as unknown as TechnicalProblemResponse[]
  },

  async getArtifacts(sessionId: string): Promise<InterviewArtifactResponse[]> {
    return (await apiClient.get(
      `/interviews/sessions/${sessionId}/artifacts`,
    )) as unknown as InterviewArtifactResponse[]
  },

  async getTranscript(sessionId: string): Promise<TranscriptTurnResponse[]> {
    return (await apiClient.get(
      `/interviews/sessions/${sessionId}/transcript`,
    )) as unknown as TranscriptTurnResponse[]
  },

  // --------------------------------------------------------------------------
  // 4. Evaluations & Scorecards
  // --------------------------------------------------------------------------
  async getSessionEvaluation(
    sessionId: string,
  ): Promise<InterviewEvaluationResponse | null> {
    try {
      return (await apiClient.get(
        `/interviews/sessions/${sessionId}/evaluation`,
      )) as unknown as InterviewEvaluationResponse
    } catch (err: any) {
      // Return null if evaluation is not yet generated
      return null
    }
  },

  async synthesizeReport(
    sessionId: string,
  ): Promise<InterviewEvaluationResponse> {
    return (await apiClient.post(
      `/interviews/sessions/${sessionId}/synthesize-report`,
      {},
      { timeout: 120000 },
    )) as unknown as InterviewEvaluationResponse
  },

  async listInterviewEvaluations(
    interviewId: string,
  ): Promise<InterviewEvaluationResponse[]> {
    try {
      return (await apiClient.get(
        `/interviews/${interviewId}/evaluations`,
      )) as unknown as InterviewEvaluationResponse[]
    } catch (err) {
      return []
    }
  },

  // --------------------------------------------------------------------------
  // 5. Pre-Interview Generator & Resume Parsing (Freeze Caching + Checkpoints)
  // --------------------------------------------------------------------------
  async parseResumeText(resumeText: string, forceRefresh: boolean = false): Promise<CandidateProfile> {
    return (await apiClient.post(
      '/resume/parse-text',
      { resume_text: resumeText, force_refresh: forceRefresh },
      { timeout: 60000 },
    )) as unknown as CandidateProfile
  },

  async parseResumeFile(file: File, forceRefresh: boolean = false): Promise<CandidateProfile> {
    const formData = new FormData()
    formData.append('file', file)
    return (await apiClient.post(`/resume/parse-file?force_refresh=${forceRefresh}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })) as unknown as CandidateProfile
  },

  async generateInterviewPlan(
    request: GeneratePlanRequest,
  ): Promise<GeneratePlanResponse> {
    return (await apiClient.post(
      '/interviews/generate-plan',
      request,
      { timeout: 300000 },
    )) as unknown as GeneratePlanResponse
  },

  async getPlannerCheckpoint(checkpointId: string): Promise<any> {
    return (await apiClient.get(
      `/interviews/planner/checkpoints/${checkpointId}`,
    )) as unknown as any
  },

  async triggerGenerateExercises(
    interviewId: string,
    sessionId?: string,
    checkpointId?: string,
    forceRefresh?: boolean,
  ): Promise<any> {
    return (await apiClient.post('/interviews/generate-exercises', {
      interview_id: interviewId,
      session_id: sessionId,
      checkpoint_id: checkpointId,
      force_refresh: forceRefresh,
    })) as unknown as any
  },

  // --------------------------------------------------------------------------
  // 6. Candidate Profile & Resume Storage (PDF File Only)
  // --------------------------------------------------------------------------
  async getCandidateProfile(params: { candidate_id?: string; email?: string }): Promise<CandidateProfileRecord> {
    return (await apiClient.get('/candidate/profile', {
      params: Object.fromEntries(Object.entries(params).filter(([_, v]) => Boolean(v))),
    })) as unknown as CandidateProfileRecord
  },

  async uploadCandidateResumeFile(
    file: File,
    metadata?: { candidate_id?: string; email?: string; full_name?: string; force_refresh?: boolean },
  ): Promise<CandidateResumeUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)
    if (metadata?.candidate_id) formData.append('candidate_id', metadata.candidate_id)
    if (metadata?.email) formData.append('email', metadata.email)
    if (metadata?.full_name) formData.append('full_name', metadata.full_name)
    if (metadata?.force_refresh) formData.append('force_refresh', 'true')

    return (await apiClient.post('/candidate/profile/resume-file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })) as unknown as CandidateResumeUploadResponse
  },

  async deleteCandidateResume(params: { candidate_id?: string; email?: string }): Promise<{ message: string }> {
    return (await apiClient.delete('/candidate/profile/resume', {
      params: Object.fromEntries(Object.entries(params).filter(([_, v]) => Boolean(v))),
    })) as unknown as { message: string }
  },
}
