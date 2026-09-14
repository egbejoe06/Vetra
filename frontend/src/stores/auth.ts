import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/services/api'
import type { AuthUser, UserCreatePayload, UserLoginPayload } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  // Restore persisted state from localStorage
  const token = ref<string | null>(localStorage.getItem('vetra_access_token'))
  const userJson = localStorage.getItem('vetra_auth_user')
  const currentUser = ref<AuthUser | null>(userJson ? JSON.parse(userJson) : null)

  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value && !!currentUser.value)

  const userRole = computed<'recruiter' | 'candidate'>(() => {
    return (
      currentUser.value?.role ||
      currentUser.value?.user_metadata?.role ||
      'recruiter'
    )
  })

  const recruiterId = computed<string>(() => {
    if (currentUser.value?.id) {
      return currentUser.value.id
    }
    return ''
  })

  const candidateName = computed<string>(() => {
    if (currentUser.value) {
      const first = currentUser.value.first_name || currentUser.value.user_metadata?.first_name || ''
      const last = currentUser.value.last_name || currentUser.value.user_metadata?.last_name || ''
      const full = `${first} ${last}`.trim()
      return full || currentUser.value.email.split('@')[0] || 'Candidate'
    }
    return ''
  })

  const candidateEmail = computed<string>(() => {
    return currentUser.value?.email || ''
  })

  async function login(payload: UserLoginPayload) {
    isLoading.value = true
    error.value = null
    try {
      const res = await api.login(payload)
      if (res.access_token) {
        token.value = res.access_token
        localStorage.setItem('vetra_access_token', res.access_token)
      }
      if (res.user) {
        currentUser.value = res.user
        localStorage.setItem('vetra_auth_user', JSON.stringify(res.user))
        if (res.user.id) {
          localStorage.setItem('vetra_user_id', res.user.id)
        }
      }
      return res
    } catch (err: any) {
      error.value = err.message
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function signup(payload: UserCreatePayload) {
    isLoading.value = true
    error.value = null
    try {
      const res = await api.signup(payload)
      if (res.access_token) {
        token.value = res.access_token
        localStorage.setItem('vetra_access_token', res.access_token)
      }
      if (res.user) {
        currentUser.value = res.user
        localStorage.setItem('vetra_auth_user', JSON.stringify(res.user))
        if (res.user.id) {
          localStorage.setItem('vetra_user_id', res.user.id)
        }
      }
      return res
    } catch (err: any) {
      error.value = err.message
      throw err
    } finally {
      isLoading.value = false
    }
  }

  function setCandidate(name: string, email?: string) {
    setGuestCandidate(name, email)
  }

  function setGuestCandidate(name: string, email?: string) {
    const guestUser: AuthUser = {
      id: crypto.randomUUID(),
      email: email || `${name.toLowerCase().replace(/\s+/g, '')}@candidate.vetra`,
      first_name: name.split(' ')[0] || name,
      last_name: name.split(' ').slice(1).join(' ') || '',
      role: 'candidate',
    }
    currentUser.value = guestUser
    localStorage.setItem('vetra_auth_user', JSON.stringify(guestUser))
  }

  function logout() {
    token.value = null
    currentUser.value = null
    localStorage.removeItem('vetra_access_token')
    localStorage.removeItem('vetra_auth_user')
    localStorage.removeItem('vetra_user_id')
  }

  return {
    token,
    currentUser,
    isAuthenticated,
    userRole,
    recruiterId,
    candidateName,
    candidateEmail,
    isLoading,
    error,
    login,
    signup,
    setCandidate,
    setGuestCandidate,
    logout,
  }
})
