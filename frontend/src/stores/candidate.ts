import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type {
  CandidateProfile,
  CandidateProfileRecord,
  CandidateResumeMetadata,
} from '@/types'

const LOCAL_STORAGE_KEY_RECORD = 'vetra_candidate_profile_record'
const LOCAL_STORAGE_KEY_PROFILE = 'vetra_parsed_resume_profile'

export const useCandidateStore = defineStore('candidate', () => {
  const authStore = useAuthStore()

  // 1. Initial State from localStorage for instant zero-latency loading
  const rawRecord = localStorage.getItem(LOCAL_STORAGE_KEY_RECORD)
  const rawProfile = localStorage.getItem(LOCAL_STORAGE_KEY_PROFILE)

  const profileRecord = ref<CandidateProfileRecord | null>(
    rawRecord ? JSON.parse(rawRecord) : null,
  )
  const storedProfile = ref<CandidateProfile | null>(
    rawProfile ? JSON.parse(rawProfile) : (profileRecord.value?.parsed_profile || null),
  )
  const resumeMetadata = ref<CandidateResumeMetadata | null>(
    profileRecord.value?.metadata || null,
  )

  const isLoading = ref(false)
  const isUploading = ref(false)
  const error = ref<string | null>(null)
  const lastSuccessMessage = ref<string | null>(null)

  // 2. Computed Properties
  const hasStoredResume = computed<boolean>(() => {
    return Boolean(storedProfile.value || (profileRecord.value && profileRecord.value.has_resume))
  })

  const candidateFullName = computed<string>(() => {
    return (
      profileRecord.value?.full_name ||
      storedProfile.value?.candidate_name ||
      (storedProfile.value as any)?.name ||
      authStore.candidateName ||
      'Candidate'
    )
  })

  const candidateEmailAddress = computed<string>(() => {
    return (
      profileRecord.value?.email ||
      storedProfile.value?.candidate_email ||
      authStore.candidateEmail ||
      'candidate@vetra.ai'
    )
  })

  const detectedSkills = computed<string[]>(() => {
    if (!storedProfile.value) return []
    const skills = (storedProfile.value as any).skills || (storedProfile.value as any).primary_skills || []
    return Array.isArray(skills) ? skills : []
  })

  const detectedExperienceYears = computed<number>(() => {
    return storedProfile.value?.years_of_experience ?? profileRecord.value?.experience_years ?? 0
  })

  // 3. Actions
  function _saveToLocalStorage() {
    try {
      if (profileRecord.value) {
        localStorage.setItem(LOCAL_STORAGE_KEY_RECORD, JSON.stringify(profileRecord.value))
      } else {
        localStorage.removeItem(LOCAL_STORAGE_KEY_RECORD)
      }

      if (storedProfile.value) {
        localStorage.setItem(LOCAL_STORAGE_KEY_PROFILE, JSON.stringify(storedProfile.value))
      } else {
        localStorage.removeItem(LOCAL_STORAGE_KEY_PROFILE)
      }
    } catch (e) {
      console.warn('[CandidateStore] Failed to write to localStorage:', e)
    }
  }

  async function loadProfile(candidateId?: string, email?: string) {
    const idToUse = candidateId || authStore.currentUser?.id
    const emailToUse = email || authStore.candidateEmail

    if (!idToUse && !emailToUse) {
      return null
    }

    isLoading.value = true
    error.value = null

    try {
      const record = await api.getCandidateProfile({
        candidate_id: idToUse,
        email: emailToUse,
      })

      profileRecord.value = record
      if (record.parsed_profile) {
        storedProfile.value = record.parsed_profile
      }
      if (record.metadata) {
        resumeMetadata.value = record.metadata
      }

      _saveToLocalStorage()
      return record
    } catch (err: any) {
      console.warn('[CandidateStore] loadProfile note:', err.message)
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function uploadResumeFile(file: File, forceRefresh: boolean = false) {
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      error.value = 'Only PDF resume files (.pdf) are accepted.'
      throw new Error(error.value)
    }

    isUploading.value = true
    error.value = null
    lastSuccessMessage.value = null

    try {
      const res = await api.uploadCandidateResumeFile(file, {
        candidate_id: authStore.currentUser?.id,
        email: authStore.candidateEmail,
        full_name: authStore.candidateName,
        force_refresh: forceRefresh,
      })

      profileRecord.value = res.candidate_profile
      if (res.candidate_profile.parsed_profile) {
        storedProfile.value = res.candidate_profile.parsed_profile
      }
      if (res.candidate_profile.metadata) {
        resumeMetadata.value = res.candidate_profile.metadata
      }

      lastSuccessMessage.value = res.message
      _saveToLocalStorage()
      return res
    } catch (err: any) {
      error.value = err.message || 'Failed to upload and parse resume PDF.'
      throw err
    } finally {
      isUploading.value = false
    }
  }

  async function clearResume() {
    isLoading.value = true
    error.value = null
    lastSuccessMessage.value = null

    try {
      const idToUse = authStore.currentUser?.id
      const emailToUse = authStore.candidateEmail
      if (idToUse || emailToUse) {
        await api.deleteCandidateResume({
          candidate_id: idToUse,
          email: emailToUse,
        })
      }

      storedProfile.value = null
      resumeMetadata.value = null
      if (profileRecord.value) {
        profileRecord.value.has_resume = false
        profileRecord.value.parsed_profile = undefined
        profileRecord.value.metadata = undefined
        profileRecord.value.resume_filename = undefined
        profileRecord.value.resume_hash = undefined
      }

      _saveToLocalStorage()
      lastSuccessMessage.value = 'Resume cleared successfully.'
    } catch (err: any) {
      error.value = err.message || 'Failed to remove resume.'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  function hydrateFromJoin(candidateProfilePayload: any) {
    if (!candidateProfilePayload) return
    try {
      if (candidateProfilePayload.parsed_profile) {
        storedProfile.value = candidateProfilePayload.parsed_profile
      }
      if (candidateProfilePayload.metadata) {
        resumeMetadata.value = candidateProfilePayload.metadata
      }
      profileRecord.value = candidateProfilePayload
      _saveToLocalStorage()
    } catch (e) {
      console.warn('[CandidateStore] hydrateFromJoin error:', e)
    }
  }

  return {
    profileRecord,
    storedProfile,
    resumeMetadata,
    hasStoredResume,
    candidateFullName,
    candidateEmailAddress,
    detectedSkills,
    detectedExperienceYears,
    isLoading,
    isUploading,
    error,
    lastSuccessMessage,
    loadProfile,
    uploadResumeFile,
    clearResume,
    hydrateFromJoin,
  }
})
