import { createRouter, createWebHistory } from 'vue-router'
import RecruiterDashboard from '@/views/RecruiterDashboard.vue'
import CandidateDashboard from '@/views/CandidateDashboard.vue'
import CandidateLobby from '@/views/CandidateLobby.vue'
import InterviewRoom from '@/views/InterviewRoom.vue'
import ScorecardView from '@/views/ScorecardView.vue'
import AuthView from '@/views/AuthView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: () => {
        const userJson = localStorage.getItem('vetra_auth_user')
        if (userJson) {
          try {
            const user = JSON.parse(userJson)
            if (user?.role === 'candidate' || user?.user_metadata?.role === 'candidate') {
              return '/candidate'
            }
          } catch {}
        }
        return '/recruiter'
      },
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
    },
    {
      path: '/evaluations/:sessionId',
      name: 'scorecard-view',
      component: ScorecardView,
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/recruiter',
    },
  ],
})

export default router
