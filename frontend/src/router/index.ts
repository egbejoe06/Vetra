import { createRouter, createWebHistory } from 'vue-router'
import RecruiterDashboard from '@/views/RecruiterDashboard.vue'
import CandidateDashboard from '@/views/CandidateDashboard.vue'
import CandidateLobby from '@/views/CandidateLobby.vue'
import InterviewRoom from '@/views/InterviewRoom.vue'
import ScorecardView from '@/views/ScorecardView.vue'
import AuthView from '@/views/AuthView.vue'
import LandingView from '@/views/LandingView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'landing',
      component: LandingView,
      meta: { hideNavbar: true },
    },
    {
      path: '/auth',
      name: 'auth',
      component: AuthView,
    },
    {
      path: '/login',
      redirect: '/auth',
    },
    {
      path: '/recruiter',
      name: 'recruiter-dashboard',
      component: RecruiterDashboard,
      meta: { requiresAuth: true },
    },
    {
      path: '/candidate',
      name: 'candidate-dashboard',
      component: CandidateDashboard,
    },
    {
      path: '/planner',
      redirect: '/recruiter',
    },
    {
      path: '/join',
      name: 'candidate-join',
      component: CandidateLobby,
    },
    {
      path: '/lobby/:code',
      name: 'candidate-lobby',
      component: CandidateLobby,
    },
    {
      path: '/session/:sessionId',
      name: 'interview-room',
      component: InterviewRoom,
      meta: { requiresAuth: true },
    },
    {
      path: '/evaluations/:sessionId',
      name: 'scorecard-view',
      component: ScorecardView,
      meta: { requiresAuth: true },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/recruiter',
    },
  ],
})

// Protect recruiter routes — redirect to /auth if no token is present
router.beforeEach((to) => {
  if (to.meta.requiresAuth) {
    const token = localStorage.getItem('vetra_access_token')
    if (!token) {
      return { path: '/auth', query: { redirect: to.fullPath } }
    }
  }
})

export default router
