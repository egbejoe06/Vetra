<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const mode = ref<'signin' | 'signup'>('signin')
const showPassword = ref(false)
const errorMessage = ref<string | null>(null)

const form = reactive({
  first_name: '',
  last_name: '',
  email: '',
  password: '',
  role: 'recruiter' as 'recruiter' | 'candidate',
})

async function handleSubmit() {
  errorMessage.value = null

  if (!form.email || !form.password) {
    errorMessage.value = 'Please fill in all required fields.'
    return
  }

  try {
    if (mode.value === 'signin') {
      await authStore.login({
        email: form.email.trim(),
        password: form.password,
      })
    } else {
      if (!form.first_name.trim() || !form.last_name.trim()) {
        errorMessage.value = 'Please provide both your first and last name.'
        return
      }
      await authStore.signup({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
      })
    }

    // Redirect based on role or intended redirect query
    const redirectPath = (route.query.redirect as string) || (authStore.userRole === 'candidate' ? '/candidate' : '/recruiter')
    router.push(redirectPath)
  } catch (err: any) {
    errorMessage.value = err.message || 'Authentication failed. Please check your credentials.'
  }
}
</script>

<template>
  <div class="bg-background text-on-surface font-sans h-full w-full overflow-hidden antialiased">
    <main class="flex h-full w-full">
      <!-- Left Panel: Visualizer & Tagline (Hidden on Mobile) -->
      <div
        class="hidden lg:flex w-1/2 relative bg-surface-container overflow-hidden items-center justify-center p-8 lg:p-12 select-none"
      >
        <!-- High-Fidelity AI Visual Background -->
        <div
          class="absolute inset-0 bg-cover bg-center opacity-30 mix-blend-screen"
          style="background-image: url('https://lh3.googleusercontent.com/aida-public/AB6AXuAZSEojJG6bw2WPKT0w6FAugN33dxYqQznYNmLQH_GOBH9D_ScUDfm4YQoSwPD8pdTbMonSrODnrbwXQUZxbyBWiR3bVk2_XjjDErgcfWTGniKX9QZKOV9JbEiG_KyapfyTf93fPKPmheg1Tbvi61TXe3BqDqUDq_pKVxRE_O4yulT2R0FMdd9vil4GG5UpayBoKJmjGxYYUdvqCWE8sO4vPYon4BW2clfvCwilJiHCZ3y5zvOUuYJ4');"
        ></div>

        <!-- Vignette / Soft Shadow overlay -->
        <div class="absolute inset-0 bg-gradient-to-tr from-surface via-surface/50 to-transparent"></div>
        <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-transparent via-background/20 to-background/80"></div>

        <!-- Content Container -->
        <div class="relative z-10 flex flex-col gap-8 max-w-[540px]">
          <!-- Brand / Logo -->
          <div class="flex items-center gap-3 text-primary text-xl">
            <span class="material-symbols-outlined text-[28px]" style="font-variation-settings: 'FILL' 1;">psychology</span>
            <span class="font-bold tracking-tight text-on-surface">Vetra <span class="text-primary font-bold">AI</span></span>
          </div>

          <!-- Tagline -->
          <div class="flex flex-col gap-4">
            <h1 class="text-4xl lg:text-5xl font-bold leading-tight text-on-surface">
              Hire smarter,<br />
              <span class="text-primary">not harder.</span>
            </h1>
            <p class="text-sm lg:text-base text-on-surface-variant max-w-md leading-relaxed">
              Experience the future of technical interviewing with our intelligent assessment platform. Uncover true engineering potential with deep architectural and live coding analysis.
            </p>
          </div>

          <!-- Decorative Elements -->
          <div class="flex gap-3 mt-4 opacity-80">
            <div class="w-12 h-1 rounded-full bg-primary/40"></div>
            <div class="w-2 h-1 rounded-full bg-primary/40"></div>
            <div class="w-2 h-1 rounded-full bg-primary/40"></div>
          </div>
        </div>

        <!-- Subtle edge highlight for depth -->
        <div class="absolute right-0 top-0 bottom-0 w-[1px] bg-gradient-to-b from-transparent via-outline-variant/30 to-transparent"></div>
      </div>

      <!-- Right Panel: Authentication Form -->
      <div class="w-full lg:w-1/2 flex items-center justify-center p-6 sm:p-10 relative bg-surface overflow-y-auto">
        <!-- Subtle AI ambient glow behind form -->
        <div class="absolute top-1/4 -right-20 w-96 h-96 bg-primary/5 rounded-full blur-[100px] pointer-events-none"></div>

        <div class="w-full max-w-[420px] flex flex-col gap-6 z-10 my-auto">
          <!-- Mobile Logo (Visible only on small screens) -->
          <div class="flex lg:hidden items-center justify-center gap-2 text-primary text-xl mb-1">
            <span class="material-symbols-outlined text-[26px]" style="font-variation-settings: 'FILL' 1;">psychology</span>
            <span class="font-bold tracking-tight text-on-surface">Vetra <span class="text-primary font-bold">AI</span></span>
          </div>

          <!-- Segmented Control (Sign In / Sign Up) -->
          <div class="flex bg-surface-container-high rounded-full p-1 relative shadow-sm h-11 items-center border border-outline-variant/20">
            <button
              type="button"
              class="flex-1 h-full flex items-center justify-center text-xs font-semibold rounded-full transition-all"
              :class="mode === 'signin' ? 'bg-surface-container text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'"
              @click="mode = 'signin'"
            >
              Sign In
            </button>
            <button
              type="button"
              class="flex-1 h-full flex items-center justify-center text-xs font-semibold rounded-full transition-all"
              :class="mode === 'signup' ? 'bg-surface-container text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'"
              @click="mode = 'signup'"
            >
              Sign Up
            </button>
          </div>

          <!-- Header -->
          <div class="flex flex-col gap-1 text-center">
            <h2 class="text-2xl font-bold text-on-surface">
              {{ mode === 'signin' ? 'Welcome back' : 'Create your account' }}
            </h2>
            <p class="text-xs text-on-surface-variant">
              {{ mode === 'signin' ? 'Enter your details to access your dashboard.' : 'Start evaluating candidates with Vetra AI.' }}
            </p>
          </div>

          <!-- Error Alert Banner -->
          <div
            v-if="errorMessage"
            class="p-3 bg-error/15 border border-error/30 rounded-xl text-error text-xs flex items-center gap-2 animate-fade-in"
          >
            <span class="material-symbols-outlined text-[18px] shrink-0">error</span>
            <span>{{ errorMessage }}</span>
          </div>

          <!-- Form -->
          <form class="flex flex-col gap-4" @submit.prevent="handleSubmit">
            <!-- First and Last Name (Sign Up only) -->
            <div v-if="mode === 'signup'" class="grid grid-cols-2 gap-3 animate-fade-in">
              <div class="flex flex-col gap-1.5">
                <label class="text-xs font-medium text-on-surface-variant">First Name</label>
                <input
                  v-model="form.first_name"
                  type="text"
                  required
                  placeholder="e.g. Jane"
                  class="w-full bg-surface-container-low text-on-surface placeholder:text-outline border border-transparent rounded-xl py-3 px-3.5 focus:bg-surface-container focus:border-primary/50 focus:outline-none transition-all text-xs"
                />
              </div>
              <div class="flex flex-col gap-1.5">
                <label class="text-xs font-medium text-on-surface-variant">Last Name</label>
                <input
                  v-model="form.last_name"
                  type="text"
                  required
                  placeholder="e.g. Doe"
                  class="w-full bg-surface-container-low text-on-surface placeholder:text-outline border border-transparent rounded-xl py-3 px-3.5 focus:bg-surface-container focus:border-primary/50 focus:outline-none transition-all text-xs"
                />
              </div>
            </div>

            <!-- Role Selector (Sign Up only) -->
            <div v-if="mode === 'signup'" class="flex flex-col gap-1.5 animate-fade-in">
              <label class="text-xs font-medium text-on-surface-variant">Account Type</label>
              <div class="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  class="p-2.5 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
                  :class="form.role === 'recruiter' ? 'bg-primary/15 text-primary border-primary/40' : 'bg-surface-container-low text-on-surface-variant border-transparent'"
                  @click="form.role = 'recruiter'"
                >
                  <span class="material-symbols-outlined text-[16px]">business_center</span>
                  <span>Recruiter / Lead</span>
                </button>
                <button
                  type="button"
                  class="p-2.5 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
                  :class="form.role === 'candidate' ? 'bg-primary/15 text-primary border-primary/40' : 'bg-surface-container-low text-on-surface-variant border-transparent'"
                  @click="form.role = 'candidate'"
                >
                  <span class="material-symbols-outlined text-[16px]">school</span>
                  <span>Candidate</span>
                </button>
              </div>
            </div>

            <!-- Email Field -->
            <div class="flex flex-col gap-1.5 relative">
              <label class="text-xs font-medium text-on-surface-variant">Email</label>
              <div class="relative flex items-center">
                <span class="material-symbols-outlined absolute left-3.5 text-outline text-[18px]">mail</span>
                <input
                  v-model="form.email"
                  required
                  type="email"
                  placeholder="name@company.com"
                  class="w-full bg-surface-container-low text-on-surface placeholder:text-outline border border-transparent rounded-xl py-3 pl-11 pr-4 focus:bg-surface-container focus:border-primary/50 focus:outline-none transition-all text-xs"
                />
              </div>
            </div>

            <!-- Password Field -->
            <div class="flex flex-col gap-1.5">
              <div class="flex justify-between items-center">
                <label class="text-xs font-medium text-on-surface-variant">Password</label>
                <a v-if="mode === 'signin'" class="text-[11px] text-primary hover:underline" href="#">Forgot password?</a>
              </div>
              <div class="relative flex items-center">
                <span class="material-symbols-outlined absolute left-3.5 text-outline text-[18px]">lock</span>
                <input
                  v-model="form.password"
                  required
                  :type="showPassword ? 'text' : 'password'"
                  placeholder="••••••••"
                  class="w-full bg-surface-container-low text-on-surface placeholder:text-outline border border-transparent rounded-xl py-3 pl-11 pr-11 focus:bg-surface-container focus:border-primary/50 focus:outline-none transition-all text-xs"
                />
                <button
                  type="button"
                  class="absolute right-3.5 text-outline hover:text-on-surface transition-colors"
                  @click="showPassword = !showPassword"
                >
                  <span class="material-symbols-outlined text-[18px]">
                    {{ showPassword ? 'visibility_off' : 'visibility' }}
                  </span>
                </button>
              </div>
            </div>

            <!-- Submit Button -->
            <button
              type="submit"
              class="group w-full bg-primary text-on-primary font-semibold text-xs py-3.5 rounded-full mt-2 hover:bg-primary-fixed transition-all duration-300 flex items-center justify-center gap-2 relative overflow-hidden shadow-lg"
              :disabled="authStore.isLoading"
            >
              <span>{{ authStore.isLoading ? 'Authenticating...' : mode === 'signin' ? 'Sign In' : 'Create Account' }}</span>
              <span class="material-symbols-outlined text-[18px] group-hover:translate-x-1 transition-transform duration-300">
                {{ authStore.isLoading ? 'sync' : 'arrow_forward' }}
              </span>
            </button>
          </form>

          <!-- Divider -->
          <div class="flex items-center gap-4 py-1">
            <div class="flex-1 h-[1px] bg-surface-container-highest"></div>
            <span class="text-[10px] uppercase font-semibold text-outline tracking-wider">OR CONTINUE WITH</span>
            <div class="flex-1 h-[1px] bg-surface-container-highest"></div>
          </div>

          <!-- Social Login -->
          <button
            type="button"
            class="w-full flex items-center justify-center gap-3 bg-surface-container-low border border-outline-variant/30 text-on-surface text-xs font-medium py-3 rounded-full hover:bg-surface-container transition-colors shadow-sm"
            @click="form.email = 'recruiter@vetra.ai'; form.password = 'password123'; handleSubmit();"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"></path>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"></path>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"></path>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"></path>
              <path d="M1 1h22v22H1z" fill="none"></path>
            </svg>
            <span>Continue with Google</span>
          </button>

          <!-- Footer / Legal -->
          <p class="text-center text-[11px] text-on-surface-variant leading-relaxed">
            By continuing, you agree to Vetra AI's <br />
            <a class="text-primary hover:underline" href="#">Terms of Service</a> and <a class="text-primary hover:underline" href="#">Privacy Policy</a>.
          </p>
        </div>
      </div>
    </main>
  </div>
</template>
