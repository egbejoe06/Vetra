<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRealtimeStore } from '@/stores/realtime'
import { useInterviewStore } from '@/stores/interview'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const realtimeStore = useRealtimeStore()
const interviewStore = useInterviewStore()
const authStore = useAuthStore()

const isLiveRoom = computed(() => route.name === 'interview-room')
const isAuthPage = computed(() => route.name === 'auth')

const navLinks = [
  { name: 'recruiter-dashboard', label: 'Recruiter Portal', icon: 'business_center', path: '/recruiter' },
  { name: 'candidate-dashboard', label: 'Candidate Portal', icon: 'school', path: '/candidate' },
]

function handleLogout() {
  authStore.logout()
  router.push('/auth')
}
</script>

<template>
  <header
    class="h-14 border-b border-surface-container-highest bg-surface-container/90 backdrop-blur-md px-4 flex items-center justify-between z-30 select-none"
  >
    <!-- Brand -->
    <div class="flex items-center gap-6">
      <router-link :to="authStore.userRole === 'candidate' ? '/candidate' : '/recruiter'" class="flex items-center gap-2.5 group">
        <div
          class="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary group-hover:bg-primary/20 transition-all"
        >
          <span class="material-symbols-outlined fill text-[20px]">psychology</span>
        </div>
        <div class="flex items-center">
          <span class="text-sm font-semibold tracking-tight text-on-surface">Vetra <span class="text-primary font-bold">AI</span></span>
        </div>
      </router-link>

      <!-- Main Navigation (Hidden inside live room or auth page) -->
      <nav v-if="!isLiveRoom && !isAuthPage" class="hidden md:flex items-center gap-1 bg-surface-container-low rounded-full p-1 border border-outline-variant/20">
        <router-link
          v-for="link in navLinks"
          :key="link.path"
          :to="link.path"
          class="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all"
          :class="[
            route.path === link.path || (link.path !== '/' && route.path.startsWith(link.path))
              ? 'bg-surface-container-highest text-primary shadow-sm'
              : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container'
          ]"
        >
          <span class="material-symbols-outlined text-[16px]">{{ link.icon }}</span>
          <span>{{ link.label }}</span>
        </router-link>
      </nav>
    </div>

    <!-- Right Side Status & Actions -->
    <div class="flex items-center gap-3">
      <!-- Live Status Pill when in active call -->
      <div
        v-if="isLiveRoom"
        class="flex items-center gap-2 px-3 py-1 rounded-full bg-surface-container-lowest border border-outline-variant/30 text-xs"
      >
        <div class="relative flex h-2 w-2">
          <span
            v-if="realtimeStore.connectionStatus === 'connected'"
            class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"
          ></span>
          <span
            class="relative inline-flex rounded-full h-2 w-2"
            :class="{
              'bg-emerald-500': realtimeStore.connectionStatus === 'connected',
              'bg-amber-500': realtimeStore.connectionStatus === 'connecting',
              'bg-red-500': realtimeStore.connectionStatus === 'error' || realtimeStore.connectionStatus === 'disconnected'
            }"
          ></span>
        </div>
        <span class="text-on-surface font-mono font-medium">
          {{ realtimeStore.connectionStatus === 'connected' ? 'LIVE' : realtimeStore.connectionStatus.toUpperCase() }}
        </span>
        <span class="text-outline">|</span>
        <span class="text-on-surface-variant font-mono">{{ interviewStore.formattedTimer }}</span>
      </div>

      <!-- Quick Room Code Badge if set -->
      <div
        v-if="!isAuthPage && interviewStore.currentInterview?.room_code"
        class="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-surface-container-high border border-outline-variant/30 text-xs font-mono"
      >
        <span class="text-on-surface-variant">Code:</span>
        <span class="text-primary font-bold tracking-wider">{{ interviewStore.currentInterview.room_code }}</span>
      </div>

      <!-- Auth Action / User Profile Pill -->
      <div v-if="!isLiveRoom" class="flex items-center gap-2">
        <div v-if="authStore.isAuthenticated" class="flex items-center gap-2">
          <div class="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-high border border-outline-variant/30 text-xs">
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span class="text-on-surface font-medium truncate max-w-[120px]">{{ authStore.candidateName || authStore.currentUser?.email }}</span>
          </div>
          <button
            class="p-1.5 rounded-lg text-outline hover:text-error hover:bg-surface-container-high transition-colors"
            title="Sign Out"
            @click="handleLogout"
          >
            <span class="material-symbols-outlined text-[18px]">logout</span>
          </button>
        </div>
        <router-link
          v-else-if="!isAuthPage"
          to="/auth"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-container-high border border-outline-variant/30 text-xs font-medium text-on-surface hover:bg-surface-container-highest transition-all"
        >
          <span class="material-symbols-outlined text-[16px]">account_circle</span>
          <span>Sign In</span>
        </router-link>
      </div>
    </div>
  </header>
</template>
