// ==============================================================================
// Vetra Frontend Type Definitions
// ==============================================================================

export interface UserCreatePayload {
  first_name: string
  last_name: string
  email: string
  password: string
  role: 'candidate' | 'recruiter'
}

export interface UserLoginPayload {
  email: string
  password: string
}

export interface AuthUser {
  id: string
  email: string
  first_name?: string
  last_name?: string
  role?: 'candidate' | 'recruiter'
  user_metadata?: {
    first_name?: string
    last_name?: string
    full_name?: string
    role?: 'candidate' | 'recruiter'
  }
}

export interface AuthResponse {
  user: AuthUser
  session?: any
  access_token?: string
  refresh_token?: string
  token_type?: string
  message?: string
}

export enum InterviewStage {
  INTRO = 'INTRO',
  RESUME_DEEP_DIVE = 'RESUME_DEEP_DIVE',
  TECHNICAL_QA = 'TECHNICAL_QA',
  TECHNICAL_EXERCISE = 'TECHNICAL_EXERCISE',
  BEHAVIORAL = 'BEHAVIORAL',
  WRAP_UP = 'WRAP_UP',
  COMPLETED = 'COMPLETED',
  CANCELLED = 'CANCELLED',
}

export enum TranscriptSpeaker {
  INTERVIEWER = 'INTERVIEWER',
  CANDIDATE = 'CANDIDATE',
  SYSTEM = 'SYSTEM',
}

export enum InterviewStatus {
  SCHEDULED = 'SCHEDULED',
  ACTIVE = 'ACTIVE',
  COMPLETED = 'COMPLETED',
  CANCELLED = 'CANCELLED',
}

export enum CandidateRecommendation {
  STRONG_HIRE = 'STRONG_HIRE',
  HIRE = 'HIRE',
  LEAN_HIRE = 'LEAN_HIRE',
  LEAN_REJECT = 'LEAN_REJECT',
  REJECT = 'REJECT',
  INCONCLUSIVE = 'INCONCLUSIVE',
}

export enum QuestionDifficulty {
  JUNIOR = 'JUNIOR',
  MID = 'MID',
  SENIOR = 'SENIOR',
  LEAD = 'LEAD',
  PRINCIPAL = 'PRINCIPAL',
}

export enum QuestionType {
  RESUME_DEEP_DIVE = 'RESUME_DEEP_DIVE',
  PROJECT_DEEP_DIVE = 'PROJECT_DEEP_DIVE',
  TECHNICAL_CONCEPT = 'TECHNICAL_CONCEPT',
  IMPLEMENTATION = 'IMPLEMENTATION',
  TRADEOFF = 'TRADEOFF',
  DEBUGGING = 'DEBUGGING',
  SYSTEM_DESIGN = 'SYSTEM_DESIGN',
  BEHAVIORAL = 'BEHAVIORAL',
  EXPERIENCE = 'EXPERIENCE',
  SCENARIO = 'SCENARIO',
  CODING_DISCUSSION = 'CODING_DISCUSSION',
}

export enum TechnicalProblemType {
  CODE_REVIEW = 'CODE_REVIEW',
  BUG_INVESTIGATION = 'BUG_INVESTIGATION',
  DEBUGGING = 'DEBUGGING',
  IMPLEMENTATION = 'IMPLEMENTATION',
  PERFORMANCE = 'PERFORMANCE',
  REFACTORING = 'REFACTORING',
  SYSTEM_DESIGN = 'SYSTEM_DESIGN',
  ARCHITECTURE_REVIEW = 'ARCHITECTURE_REVIEW',
  API_DESIGN = 'API_DESIGN',
  CODEBASE_DISCUSSION = 'CODEBASE_DISCUSSION',
  SECURITY_REVIEW = 'SECURITY_REVIEW',
  DATA_STRUCTURES_AND_ALGORITHMS = 'DATA_STRUCTURES_AND_ALGORITHMS',
  ALTERNATIVE_IMPLEMENTATION = 'ALTERNATIVE_IMPLEMENTATION',
}

export enum ArtifactType {
  CODEBASE = 'CODEBASE',
  CODE_SNIPPET = 'CODE_SNIPPET',
  SYSTEM_DIAGRAM = 'SYSTEM_DIAGRAM',
  ARCHITECTURE = 'ARCHITECTURE',
  DATA_MODEL = 'DATA_MODEL',
  EVALUATION_BLUEPRINT = 'EVALUATION_BLUEPRINT',
}

// ------------------------------------------------------------------------------
// Interview Template & Session
// ------------------------------------------------------------------------------

export interface InterviewCreate {
  job_title: string
  job_id?: string
  years_of_experience: number
  seniority?: QuestionDifficulty
  questions_count?: number
  duration_minutes?: number
  technical_focus?: string[]
  behavioral_focus?: string[]
  instructions?: string
  description?: string
  evaluation_criteria?: string
}

export interface InterviewUpdate {
  job_title?: string
  years_of_experience?: number
  seniority?: QuestionDifficulty
  questions_count?: number
  duration_minutes?: number
  technical_focus?: string[]
  behavioral_focus?: string[]
  instructions?: string
  description?: string
  evaluation_criteria?: string
}

export interface InterviewResponse {
  id: string
  recruiter_id: string
  job_id?: string
  job_title: string
  years_of_experience: number
  seniority?: QuestionDifficulty
  room_code: string
  status: InterviewStatus
  current_stage: InterviewStage
  duration_minutes: number
  questions_count: number
  technical_focus: string[]
  behavioral_focus: string[]
  instructions?: string
  description?: string
  evaluation_criteria?: string
  created_at: string
  updated_at: string
}

export interface InterviewJoin {
  room_code: string
  candidate_name: string
  candidate_email: string
  email?: string
  redo?: boolean
}

export interface InterviewSessionResponse {
  id: string
  interview_id: string
  candidate_id?: string
  candidate_name: string
  candidate_email?: string
  room_code?: string
  status: InterviewStatus
  current_stage: InterviewStage
  started_at?: string
  completed_at?: string
  created_at: string
  updated_at: string
}

export interface InterviewJoinResponse {
  session: InterviewSessionResponse
  interview: InterviewResponse
  candidate_profile?: any
  resumed: boolean
  message: string
}

// ------------------------------------------------------------------------------
// Code Files & Problems
// ------------------------------------------------------------------------------

export interface CodeFile {
  file_path: string
  content: string
  language?: string
  is_read_only?: boolean
}

export interface TechnicalProblemResponse {
  id: string
  session_id: string
  title: string
  problem_type: TechnicalProblemType | string
  prompt_question: string
  instructions?: string
  starter_code?: string
  language: string
  code_files: CodeFile[]
  created_at: string
}

export interface InterviewArtifactResponse {
  id: string
  session_id: string
  artifact_type: ArtifactType | string
  title: string
  content: Record<string, any> | string
  created_at: string
}

// ------------------------------------------------------------------------------
// Transcripts & Dialogue Turns
// ------------------------------------------------------------------------------

export interface TranscriptTurnResponse {
  id?: string
  turn_id?: string
  turn_index?: number
  session_id: string
  speaker: TranscriptSpeaker
  stage: InterviewStage
  content: string
  audio_url?: string
  created_at: string
}

export interface DialogueTurn {
  id?: string
  turn_id?: string
  speaker: TranscriptSpeaker
  stage: InterviewStage
  content: string
  timestamp: string
  is_final?: boolean
}

// ------------------------------------------------------------------------------
// Planner & Resume Parsing
// ------------------------------------------------------------------------------

export interface WorkExperience {
  company: string
  title: string
  duration?: string
  highlights: string[]
  technologies: string[]
}

export interface CandidateProject {
  name: string
  description: string
  role?: string
  technologies: string[]
  architecture_highlights?: string[]
  claimed_impact?: string
  tech_stack?: string[]
}

export interface DetectedGap {
  area: string
  description: string
  suggested_probe?: string
  gap_type?: string
  probe_angle?: string
}

export interface EducationItem {
  institution: string
  degree: string
  field?: string
  year?: string
}

export interface CandidateProfile {
  name: string
  candidate_name?: string
  candidate_email?: string
  email?: string
  phone?: string
  primary_skills: string[]
  skills?: string[]
  secondary_skills?: string[]
  frameworks_and_tools?: string[]
  years_of_experience: number
  current_role?: string
  work_experiences?: WorkExperience[]
  work_experience?: WorkExperience[]
  projects: CandidateProject[]
  detected_gaps: DetectedGap[]
  education: EducationItem[]
  summary?: string
  freeze_hash?: string
}

export interface CandidateResumeMetadata {
  filename: string
  uploaded_at: string
  file_size_bytes?: number
  resume_hash: string
  experience_years?: number
}

export interface CandidateProfileRecord {
  id?: string
  user_id?: string
  email: string
  full_name?: string
  experience_years?: number
  resume_url?: string
  resume_filename?: string
  resume_hash?: string
  has_resume: boolean
  parsed_profile?: CandidateProfile
  metadata?: CandidateResumeMetadata
  updated_at?: string
  created_at?: string
}

export interface CandidateResumeUploadResponse {
  status: string
  message: string
  reused_cache: boolean
  candidate_profile: CandidateProfileRecord
}

export interface RubricCriterion {
  category: string
  weight: number
  description: string
  scoring_guidelines: Record<string, string>
}

export interface InterviewQuestion {
  id?: string
  question_text: string
  question_type: QuestionType | string
  difficulty: QuestionDifficulty | string
  competency: string
  target_answer_points: string[]
  probing_follow_ups: string[]
  context?: string
}

export interface CodingExerciseAsset {
  title: string
  problem_type: TechnicalProblemType | string
  scenario_description: string
  task_instructions: string
  language: string
  code_files: CodeFile[]
  evaluation_criteria: string[]
  test_cases?: Record<string, any>[]
  context?: string
  objective?: string
}

export interface InterviewPlan {
  role_title: string
  target_seniority: string
  primary_focus_areas: string[]
  questions: InterviewQuestion[]
  coding_exercise?: CodingExerciseAsset
  system_design_exercise?: any
  rubrics: RubricCriterion[]
  stage_allocations: Record<string, number>
}

export interface InterviewPlanCreate {
  interview_id?: string
  job_id?: string
  job_title: string
  years_of_experience?: number
  questions_count?: number
  duration_minutes?: number
  technical_focus?: string[]
  behavioral_focus?: string[]
  instructions?: string
  description?: string
  problem_type?: TechnicalProblemType | string
}

export interface GeneratePlanRequest {
  candidate_profile: CandidateProfile
  job_spec: InterviewPlanCreate
  checkpoint_id?: string
  coding_exercise?: CodingExerciseAsset
  system_design_exercise?: any
  defer_coding_exercise?: boolean
  session_id?: string
  force_refresh?: boolean
}

export interface GeneratePlanResponse {
  plan: InterviewPlan
  interview_id?: string
  checkpoint_id?: string
  reused_from_checkpoint?: boolean
  step?: string
  created_at?: string
}

export interface DiagnosticError {
  provider: string
  operation?: string
  error_type?: string
  status_code?: number
  message: string
  timestamp?: string
}

export interface PlannerErrorDetail {
  message: string
  step?: string
  checkpoint_id?: string
  diagnostic_errors?: DiagnosticError[]
  can_retry_with_checkpoint?: boolean
}

// ------------------------------------------------------------------------------
// Evaluations & Recruiter Reports
// ------------------------------------------------------------------------------

export interface RubricScoreItem {
  category: string
  score: number | null // 1.0 - 5.0 or null if NOT_ASSESSED
  weight?: number
  status?: string // 'ASSESSED' | 'NOT_ASSESSED'
  feedback: string
  cited_turn_ids?: string[]
  verified_turn_ids?: string[]
  evidence_quotes?: string[]
}

export interface QuestionScoreItem {
  question_id?: string
  question_text: string
  score: number | null
  status?: string // 'ASSESSED' | 'NOT_ASSESSED'
  feedback?: string
  verified_turn_ids?: string[]
}

export interface AuditTrailItem {
  claim: string
  original_citation: string
  resolution: 'VERIFIED' | 'REJECTED' | 'MODIFIED'
  reason: string
  timestamp?: string
}

export interface ScoreBreakdown {
  weights: Record<string, number>
  raw_category_scores: Record<string, number>
  weighted_composite: number
  calibrated_overall_score: number | null
  assessed_categories?: string[]
  unassessed_categories?: string[]
}

export interface InterviewEvaluationResponse {
  id: string
  session_id: string
  interview_id: string
  candidate_id?: string
  candidate_name: string
  overall_score: number | null // 0.0 - 10.0 or null
  recommendation: CandidateRecommendation
  summary: string
  key_strengths: string[]
  key_weaknesses: string[]
  rubric_scores: RubricScoreItem[]
  question_scores: QuestionScoreItem[]
  completion_status?: string // 'COMPLETED' | 'INCOMPLETE'
  stages_completed?: string[]
  stages_not_reached?: string[]
  snapshot_id?: string
  audit_trail?: AuditTrailItem[]
  score_breakdown?: ScoreBreakdown
  completed_at: string
}

// ------------------------------------------------------------------------------
// WebSocket Protocol Messages
// ------------------------------------------------------------------------------

export interface WsAudioMessage {
  type: 'audio'
  data: string // base64 PCM
  sample_rate?: number
}

export interface WsTextMessage {
  type: 'text'
  text: string
}

export interface WsPingMessage {
  type: 'ping'
}

export interface WsPongMessage {
  type: 'pong'
  timestamp: string
}

export interface WsInterruptedMessage {
  type: 'interrupted'
  timestamp: string
  reason?: string
}

export interface WsTranscriptMessage {
  type: 'transcript'
  speaker: TranscriptSpeaker
  text: string
  is_final: boolean
  turn_id?: string
  stage?: InterviewStage
  timestamp: string
}

export interface WsStageUpdateMessage {
  type: 'stage_update'
  stage: InterviewStage
  guidance?: Record<string, any>
  transition_reason?: string
  timestamp: string
}

export interface WsProblemPresentedMessage {
  type: 'problem_presented'
  problem_id: string
  title: string
  problem_type: string
  prompt_question: string
  instructions?: string
  code_files: (CodeFile | any)[]
  timestamp: string
}

export interface WsSessionStatusMessage {
  type: 'session_status'
  status: string
  session_id: string
  message?: string
  resumed?: boolean
  timestamp: string
}

export interface WsErrorMessage {
  type: 'error'
  message: string
  code?: string
  timestamp: string
}

export interface WsTurnCompleteMessage {
  type: 'turn_complete'
  speaker: TranscriptSpeaker
  timestamp: string
}

export type WsServerMessage =
  | WsAudioMessage
  | WsInterruptedMessage
  | WsTranscriptMessage
  | WsStageUpdateMessage
  | WsProblemPresentedMessage
  | WsSessionStatusMessage
  | WsPongMessage
  | WsErrorMessage
  | WsTurnCompleteMessage
