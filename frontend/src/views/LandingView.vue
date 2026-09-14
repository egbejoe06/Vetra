<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

function scrollToSection(id: string) {
  const el = document.getElementById(id)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth' })
  }
}
</script>

<template>
  <div
    class="landing-page h-full w-full overflow-y-auto overflow-x-hidden bg-background text-on-surface font-body-md antialiased selection:bg-primary selection:text-on-primary relative"
  >
    <!-- Ambient Glow Elements -->
    <div class="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <div
        class="absolute -top-32 left-1/2 -translate-x-1/2 w-[850px] h-[500px] bg-gradient-to-b from-primary-container/20 via-secondary/10 to-transparent blur-3xl opacity-50"
      ></div>
      <div
        class="absolute top-[45%] -right-48 w-[500px] h-[500px] bg-secondary-container/10 rounded-full blur-[140px] opacity-40"
      ></div>
    </div>

    <!-- ==================== TOP NAVIGATION ==================== -->
    <header class="sticky top-0 z-50 bg-surface/85 backdrop-blur-md border-b border-outline-variant/30">
      <div class="flex justify-between items-center w-full px-6 md:px-12 max-w-7xl mx-auto h-20">
        <!-- Brand -->
        <router-link class="flex items-center gap-2.5 group" to="/">
          <div
            class="w-9 h-9 rounded-lg bg-surface-container-high border border-outline-variant/40 flex items-center justify-center shadow-md shadow-indigo-500/10"
          >
            <span class="material-symbols-outlined text-secondary text-xl" style="font-variation-settings: 'FILL' 1;">terminal</span>
          </div>
          <span class="text-headline-md font-headline-md font-bold tracking-tight text-on-surface text-xl">Vetra</span>
          <span class="w-2 h-2 rounded-full bg-tertiary inline-block"></span>
        </router-link>

        <!-- Focused Navigation Links -->
        <nav class="hidden md:flex items-center gap-8 text-sm font-medium">
          <button
            class="text-on-surface font-semibold hover:text-primary transition-colors duration-150"
            @click="scrollToSection('features')"
          >
            Features
          </button>
          <button
            class="text-on-surface-variant hover:text-on-surface transition-colors duration-150"
            @click="scrollToSection('how-it-works')"
          >
            How It Works
          </button>
          <button
            class="text-on-surface-variant hover:text-on-surface transition-colors duration-150"
            @click="scrollToSection('interactive-preview')"
          >
            Sandbox
          </button>
          <router-link
            to="/join"
            class="text-on-surface-variant hover:text-on-surface transition-colors duration-150"
          >
            Candidate Lobby
          </router-link>
        </nav>

        <!-- Header CTA -->
        <div class="flex items-center gap-3">
          <router-link
            v-if="authStore.isAuthenticated"
            :to="authStore.userRole === 'candidate' ? '/candidate' : '/recruiter'"
            class="px-5 py-2.5 rounded-lg bg-gradient-to-r from-primary-container to-inverse-primary text-on-primary-fixed font-headline-sm text-sm font-semibold tracking-wide shadow-md shadow-primary-container/20 hover:scale-[1.02] active:scale-[0.98] transition-all"
          >
            Go to Dashboard
          </router-link>
          <template v-else>
            <router-link
              to="/auth"
              class="hidden sm:inline-flex px-4 py-2 text-sm font-medium text-on-surface-variant hover:text-on-surface transition-colors"
            >
              Sign In
            </router-link>
            <router-link
              to="/auth"
              class="px-5 py-2.5 rounded-lg bg-gradient-to-r from-primary-container to-inverse-primary text-on-primary-fixed font-headline-sm text-sm font-semibold tracking-wide shadow-md shadow-primary-container/20 hover:scale-[1.02] active:scale-[0.98] transition-all"
            >
              Schedule Demo
            </router-link>
          </template>
        </div>
      </div>
    </header>

    <main class="relative z-10">
      <!-- ==================== HERO SECTION ==================== -->
      <section class="pt-20 pb-16 px-6 md:px-12 max-w-7xl mx-auto flex flex-col items-center text-center">
        <!-- Minimalist Eyebrow Pill -->
        <div
          class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-surface-container-high/80 border border-secondary/30 text-secondary text-xs font-mono mb-8 backdrop-blur-sm"
        >
          <span class="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
          <span>Gemini Live API • Speech-to-Speech Realtime Audio</span>
        </div>

        <!-- Hero Title -->
        <h1
          class="text-4xl sm:text-5xl lg:text-6xl font-extrabold font-headline-xl tracking-tight text-on-surface max-w-4xl mb-6 leading-[1.15]"
        >
          The Voice-Native
          <span class="bg-gradient-to-r from-primary via-secondary to-tertiary-fixed-dim bg-clip-text text-transparent">
            AI Interviewer
          </span>
        </h1>

        <!-- Concise Value Subhead -->
        <p class="text-lg sm:text-xl text-on-surface-variant max-w-2xl mb-10 leading-relaxed font-body-lg">
          Vetra conducts conversational, zero-latency technical interviews. It probes candidate experience dynamically, facilitates live code execution, and generates objective hiring scorecards.
        </p>

        <!-- Streamlined CTAs -->
        <div class="flex flex-col sm:flex-row items-center gap-4 mb-16 w-full justify-center">
          <router-link
            to="/auth"
            class="w-full sm:w-auto px-7 py-3.5 rounded-xl bg-gradient-to-r from-primary-container to-inverse-primary text-on-primary-fixed font-headline-sm text-base font-semibold shadow-xl shadow-primary-container/25 hover:shadow-cyan-400/20 hover:scale-[1.02] transition-all flex items-center justify-center gap-2"
          >
            <span>Book Demo</span>
            <span class="material-symbols-outlined text-lg">arrow_forward</span>
          </router-link>
          <button
            class="w-full sm:w-auto px-7 py-3.5 rounded-xl bg-surface-container-high/70 border border-outline-variant/50 text-on-surface font-body-md text-base hover:bg-surface-container-highest/80 hover:border-secondary/50 backdrop-blur-md transition-all flex items-center justify-center gap-2"
            @click="scrollToSection('interactive-preview')"
          >
            <span class="material-symbols-outlined text-secondary text-xl">play_circle</span>
            <span>Try Interactive Sandbox</span>
          </button>
        </div>

        <!-- ==================== REFINED HERO PREVIEW MOCKUP ==================== -->
        <div
          class="w-full rounded-2xl bg-surface-container-lowest border border-outline-variant/40 p-3 sm:p-4 backdrop-blur-xl shadow-2xl shadow-black/60 relative text-left"
          id="interactive-preview"
        >
          <!-- Window Title Bar -->
          <div class="flex items-center justify-between px-3 py-2 border-b border-outline-variant/20 mb-3 text-xs">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-error/70"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-secondary-container/70"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-tertiary/70"></span>
              <span class="text-outline font-mono ml-2">Vetra Session • Staff Distributed Systems Lead</span>
            </div>
            <div class="flex items-center gap-2">
              <span
                class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-tertiary/10 text-tertiary text-[11px] font-mono border border-tertiary/20"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-tertiary animate-ping"></span> Live Audio Active
              </span>
              <span class="text-outline font-mono text-[11px]">280ms RTT</span>
            </div>
          </div>

          <!-- Split Layout: Voice Agent + Live IDE -->
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-3">
            <!-- Left Pane: AI Voice Node & Conversational Turn (5 cols) -->
            <div
              class="lg:col-span-5 rounded-xl bg-surface-container-low/90 border border-outline-variant/30 p-5 flex flex-col justify-between space-y-6"
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="w-2 h-2 rounded-full bg-secondary animate-ping"></div>
                  <span class="text-xs font-mono font-semibold text-on-surface">Vetra Voice Node</span>
                </div>
                <span
                  class="text-[11px] font-mono px-2 py-0.5 rounded bg-surface-container-high text-secondary border border-secondary/20"
                >
                  48kHz Raw PCM
                </span>
              </div>

              <!-- Waveform Visualizer -->
              <div class="flex flex-col items-center justify-center py-6">
                <div
                  class="w-20 h-20 rounded-full bg-surface-container-highest/80 border border-primary/30 flex items-center justify-center shadow-lg shadow-indigo-500/20 mb-5 relative"
                >
                  <div class="absolute inset-0 rounded-full bg-primary/20 blur-md"></div>
                  <span class="material-symbols-outlined text-primary text-3xl relative z-10 animate-pulse">graphic_eq</span>
                </div>

                <!-- Waveform bars -->
                <div class="flex items-end gap-1.5 h-10">
                  <div class="w-1.5 bg-secondary/80 rounded-full wave-1"></div>
                  <div class="w-1.5 bg-primary rounded-full wave-2"></div>
                  <div class="w-1.5 bg-tertiary rounded-full wave-3"></div>
                  <div class="w-1.5 bg-primary-container rounded-full wave-4"></div>
                  <div class="w-1.5 bg-secondary rounded-full wave-2"></div>
                  <div class="w-1.5 bg-primary rounded-full wave-1"></div>
                </div>
                <span class="text-xs text-outline mt-3 font-mono">Barge-in detection active</span>
              </div>

              <!-- Live Transcript Quote -->
              <div class="p-3.5 rounded-xl bg-surface-container-high/70 border border-outline-variant/30">
                <div class="flex items-center justify-between text-xs font-mono text-primary mb-1.5">
                  <span class="font-bold flex items-center gap-1.5">
                    <span class="material-symbols-outlined text-sm">smart_toy</span> Vetra AI
                  </span>
                  <span class="text-outline text-[11px]">Just now</span>
                </div>
                <p class="text-sm text-on-surface italic leading-relaxed">
                  "How did you prevent consumer rebalance storms when repartitioning Kafka streams under peak load at Stripe?"
                </p>
              </div>
            </div>

            <!-- Right Pane: Live Monaco Coding Environment (7 cols) -->
            <div
              class="lg:col-span-7 rounded-xl bg-surface-container-lowest border border-outline-variant/30 flex flex-col font-mono text-xs"
            >
              <!-- Editor Tabs -->
              <div
                class="flex items-center justify-between bg-surface-container-low px-4 py-2 border-b border-outline-variant/30"
              >
                <div class="flex items-center gap-2">
                  <span
                    class="px-3 py-1 rounded bg-surface-container-lowest border border-outline-variant/30 text-on-surface text-xs font-medium flex items-center gap-1.5"
                  >
                    <span class="text-secondary">py</span> partition_manager.py
                  </span>
                  <span class="px-2 py-1 text-on-surface-variant text-xs">tests.py</span>
                </div>
                <span class="text-[11px] text-tertiary flex items-center gap-1">
                  <span class="material-symbols-outlined text-sm">check_circle</span> 8/8 Tests Passed
                </span>
              </div>

              <!-- Code Buffer -->
              <div class="p-4 space-y-1.5 leading-relaxed text-on-surface-variant overflow-x-auto text-xs">
                <div><span class="text-outline">01</span> <span class="text-secondary">class</span> <span class="text-tertiary font-bold">PartitionRebalanceOrchestrator</span>:</div>
                <div><span class="text-outline">02</span> &nbsp;&nbsp;<span class="text-outline-variant">"""Cooperative sticky rebalancing without consumer stalls"""</span></div>
                <div><span class="text-outline">03</span> &nbsp;&nbsp;<span class="text-secondary">async def</span> <span class="text-primary font-bold">reassign_partition_cooperative</span>(self, revoked, target):</div>
                <div class="bg-primary/10 border-l-2 border-primary -mx-4 px-4 py-0.5"><span class="text-primary font-bold">04</span> &nbsp;&nbsp;&nbsp;&nbsp;batch_lock = <span class="text-secondary">await</span> self._acquire_claim(target)</div>
                <div><span class="text-outline">05</span> &nbsp;&nbsp;&nbsp;&nbsp;<span class="text-secondary">if not</span> batch_lock: <span class="text-secondary">raise</span> EpochRevokedError()</div>
                <div><span class="text-outline">06</span> &nbsp;&nbsp;&nbsp;&nbsp;<span class="text-secondary">return await</span> self._commit_offset_fence(batch_lock, revoked)</div>
              </div>

              <!-- Live Evaluation Summary -->
              <div
                class="mt-auto bg-surface-container/60 p-3 border-t border-outline-variant/30 flex items-center justify-between text-xs"
              >
                <div class="flex items-center gap-2">
                  <span class="material-symbols-outlined text-primary text-base">auto_awesome</span>
                  <span class="text-on-surface">Candidate chose cooperative protocol to eliminate eager eviction.</span>
                </div>
                <span class="text-tertiary font-semibold font-mono">Complexity: O(N log K)</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== KEY METRICS BAR ==================== -->
      <section class="py-12 border-y border-outline-variant/20 bg-surface-container-lowest/50 backdrop-blur-sm">
        <div class="max-w-7xl mx-auto px-6 md:px-12">
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8 text-center sm:text-left">
            <div class="p-4">
              <div class="text-4xl font-extrabold text-primary font-headline-xl mb-1">78%</div>
              <div class="text-sm font-semibold text-on-surface mb-1">Engineer Screening Time Saved</div>
              <p class="text-xs text-on-surface-variant">Replaces preliminary technical phone screens with standardized evaluations.</p>
            </div>
            <div class="p-4">
              <div class="text-4xl font-extrabold text-secondary font-headline-xl mb-1">&lt;300ms</div>
              <div class="text-sm font-semibold text-on-surface mb-1">Speech-to-Speech Latency</div>
              <p class="text-xs text-on-surface-variant">Native bidirectional audio streaming ensures zero unnatural conversational pauses.</p>
            </div>
            <div class="p-4">
              <div class="text-4xl font-extrabold text-tertiary font-headline-xl mb-1">99.4%</div>
              <div class="text-sm font-semibold text-on-surface mb-1">Technical Comprehension</div>
              <p class="text-xs text-on-surface-variant">Accurate handling of complex engineering jargon, acronyms, and accents.</p>
            </div>
            <div class="p-4">
              <div class="text-4xl font-extrabold text-primary-container font-headline-xl mb-1">4.9 / 5</div>
              <div class="text-sm font-semibold text-on-surface mb-1">Candidate CSAT Score</div>
              <p class="text-xs text-on-surface-variant">Candidates report higher fairness, deep probing, and an unbiased environment.</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== CORE PILLARS / FEATURES ==================== -->
      <section class="py-24 px-6 md:px-12 max-w-7xl mx-auto" id="features">
        <div class="text-center max-w-2xl mx-auto mb-16 space-y-3">
          <h2 class="text-3xl sm:text-4xl font-bold font-headline-xl text-on-surface">Core Architecture Pillars</h2>
          <p class="text-base text-on-surface-variant">Engineered for deterministic precision, conversational naturalism, and objective scoring.</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <!-- Card 1 -->
          <div
            class="p-6 rounded-2xl bg-surface-container/60 border border-outline-variant/30 hover:border-primary/40 transition-all flex flex-col justify-between group"
          >
            <div class="space-y-4">
              <div
                class="w-12 h-12 rounded-xl bg-surface-container-high border border-outline-variant/30 flex items-center justify-center text-secondary group-hover:scale-105 transition-transform"
              >
                <span class="material-symbols-outlined text-2xl">mic</span>
              </div>
              <h3 class="text-lg font-bold font-headline-sm text-on-surface">Realtime Gemini Live Voice</h3>
              <p class="text-sm text-on-surface-variant leading-relaxed">
                Bidirectional audio with natural barge-in detection. Candidates can clarify assumptions or pivot mid-sentence without awkward robotic lag.
              </p>
            </div>
          </div>
          <!-- Card 2 -->
          <div
            class="p-6 rounded-2xl bg-surface-container/60 border border-outline-variant/30 hover:border-secondary/40 transition-all flex flex-col justify-between group"
          >
            <div class="space-y-4">
              <div
                class="w-12 h-12 rounded-xl bg-surface-container-high border border-outline-variant/30 flex items-center justify-center text-primary group-hover:scale-105 transition-transform"
              >
                <span class="material-symbols-outlined text-2xl">psychology</span>
              </div>
              <h3 class="text-lg font-bold font-headline-sm text-on-surface">Dynamic Resume Grounding</h3>
              <p class="text-sm text-on-surface-variant leading-relaxed">
                Vetra cross-references candidates' actual repos and past projects against your rubric to ask targeted, high-signal architecture questions.
              </p>
            </div>
          </div>
          <!-- Card 3 -->
          <div
            class="p-6 rounded-2xl bg-surface-container/60 border border-outline-variant/30 hover:border-tertiary/40 transition-all flex flex-col justify-between group"
          >
            <div class="space-y-4">
              <div
                class="w-12 h-12 rounded-xl bg-surface-container-high border border-outline-variant/30 flex items-center justify-center text-tertiary group-hover:scale-105 transition-transform"
              >
                <span class="material-symbols-outlined text-2xl">code</span>
              </div>
              <h3 class="text-lg font-bold font-headline-sm text-on-surface">Live Monaco IDE</h3>
              <p class="text-sm text-on-surface-variant leading-relaxed">
                Candidates execute multi-language code in an isolated kernel with real-time test runners, automated feedback, and complexity heuristics.
              </p>
            </div>
          </div>
          <!-- Card 4 -->
          <div
            class="p-6 rounded-2xl bg-surface-container/60 border border-outline-variant/30 hover:border-primary-container/40 transition-all flex flex-col justify-between group"
          >
            <div class="space-y-4">
              <div
                class="w-12 h-12 rounded-xl bg-surface-container-high border border-outline-variant/30 flex items-center justify-center text-secondary group-hover:scale-105 transition-transform"
              >
                <span class="material-symbols-outlined text-2xl">assessment</span>
              </div>
              <h3 class="text-lg font-bold font-headline-sm text-on-surface">Audit-Grade Scorecards</h3>
              <p class="text-sm text-on-surface-variant leading-relaxed">
                Eliminate subjective bias with immutable reports, verified timestamp citations, code quality metrics, and seamless ATS sync into Greenhouse or Lever.
              </p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== HOW IT WORKS (3-STEP TIMELINE) ==================== -->
      <section class="py-20 px-6 md:px-12 max-w-7xl mx-auto border-t border-outline-variant/20" id="how-it-works">
        <div class="text-center max-w-2xl mx-auto mb-16 space-y-3">
          <div
            class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-secondary/10 border border-secondary/30 text-secondary text-xs font-mono"
          >
            HOW IT WORKS
          </div>
          <h2 class="text-3xl sm:text-4xl font-bold font-headline-xl text-on-surface">Three Steps to Objective Hiring</h2>
          <p class="text-base text-on-surface-variant">Seamless candidate onboarding with zero app installations required.</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8 relative">
          <!-- Step 1 -->
          <div class="p-6 rounded-2xl bg-surface-container/50 border border-outline-variant/30 space-y-4 text-left relative">
            <div class="flex items-center justify-between">
              <span class="text-xs font-mono text-secondary font-bold px-2.5 py-1 rounded bg-secondary/10 border border-secondary/30">STEP 01</span>
              <span class="material-symbols-outlined text-outline">key</span>
            </div>
            <h3 class="text-xl font-bold text-on-surface font-headline-sm">Share 6-Digit Room Code</h3>
            <p class="text-sm text-on-surface-variant leading-relaxed">
              Invite candidates to their personalized, calibrated interview room with a single click or automatic ATS invite. Candidates join instantly via browser.
            </p>
          </div>
          <!-- Step 2 -->
          <div class="p-6 rounded-2xl bg-surface-container/50 border border-outline-variant/30 space-y-4 text-left relative">
            <div class="flex items-center justify-between">
              <span class="text-xs font-mono text-primary font-bold px-2.5 py-1 rounded bg-primary/10 border border-primary/30">STEP 02</span>
              <span class="material-symbols-outlined text-outline">graphic_eq</span>
            </div>
            <h3 class="text-xl font-bold text-on-surface font-headline-sm">Voice-Native Realtime Interview</h3>
            <p class="text-sm text-on-surface-variant leading-relaxed">
              Vetra guides the candidate through resume validation, system architecture tradeoffs, and live Monaco coding exercises in a fluid audio dialogue.
            </p>
          </div>
          <!-- Step 3 -->
          <div class="p-6 rounded-2xl bg-surface-container/50 border border-outline-variant/30 space-y-4 text-left relative">
            <div class="flex items-center justify-between">
              <span class="text-xs font-mono text-tertiary font-bold px-2.5 py-1 rounded bg-tertiary/10 border border-tertiary/30">STEP 03</span>
              <span class="material-symbols-outlined text-outline">verified</span>
            </div>
            <h3 class="text-xl font-bold text-on-surface font-headline-sm">Objective Evidence Scorecard</h3>
            <p class="text-sm text-on-surface-variant leading-relaxed">
              Recruiters and hiring managers receive audit-grade evaluation summaries with exact transcript audio bookmarks, code benchmarks, and rubric alignment.
            </p>
          </div>
        </div>
      </section>

      <!-- ==================== BOTTOM CTA BANNER ==================== -->
      <section class="py-20 px-6 md:px-12 max-w-7xl mx-auto" id="demo">
        <div
          class="rounded-3xl bg-gradient-to-r from-surface-container-high via-surface-container to-surface-container-high border border-primary/30 p-10 md:p-14 text-center shadow-2xl relative overflow-hidden"
        >
          <div class="max-w-2xl mx-auto space-y-6">
            <h2 class="text-3xl sm:text-4xl font-bold font-headline-xl text-on-surface">
              Ready to revolutionize your hiring pipeline?
            </h2>
            <p class="text-base text-on-surface-variant leading-relaxed">
              Integrate Vetra in under an afternoon. Connect your ATS, customize your rubrics, and deliver fair, consistent technical interviews at any scale.
            </p>
            <div class="flex flex-col sm:flex-row items-center justify-center gap-4 pt-2">
              <router-link
                to="/auth"
                class="w-full sm:w-auto px-8 py-3.5 rounded-xl bg-gradient-to-r from-primary-container to-inverse-primary text-on-primary-fixed font-headline-sm text-base font-semibold shadow-lg shadow-primary-container/30 hover:scale-[1.02] transition-all text-center"
              >
                Schedule 15-Min Live Demo
              </router-link>
              <router-link
                to="/auth"
                class="w-full sm:w-auto px-7 py-3.5 rounded-xl bg-surface-container-high border border-outline-variant/50 text-on-surface font-body-md text-base hover:bg-surface-bright transition-all text-center"
              >
                Start Free Trial
              </router-link>
            </div>
          </div>
        </div>
      </section>
    </main>

    <!-- ==================== MINIMALIST FOOTER ==================== -->
    <footer class="border-t border-outline-variant/20 bg-surface-container-lowest py-10 px-6 md:px-12 text-xs">
      <div class="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-6">
        <div class="flex items-center gap-3">
          <span class="text-base font-bold text-on-surface font-headline-sm">Vetra</span>
          <span class="text-outline">|</span>
          <span class="text-on-surface-variant">© 2025 Vetra Intelligence Inc. All rights reserved.</span>
        </div>
        <div class="flex items-center gap-6 text-on-surface-variant">
          <button class="hover:text-secondary transition-colors" @click="scrollToSection('features')">Platform</button>
          <button class="hover:text-secondary transition-colors" @click="scrollToSection('features')">Features</button>
          <router-link class="hover:text-secondary transition-colors" to="/auth">Security &amp; SOC-2</router-link>
          <router-link class="hover:text-secondary transition-colors" to="/auth">Privacy</router-link>
          <router-link class="hover:text-secondary transition-colors" to="/auth">Status</router-link>
        </div>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.landing-page {
  --color-primary: #c0c1ff;
  --color-primary-container: #8083ff;
  --color-inverse-primary: #494bd6;
  --color-on-primary-fixed: #07006c;
  --color-secondary: #4cd7f6;
  --color-secondary-container: #03b5d3;
  --color-tertiary: #4edea3;
  --color-tertiary-fixed-dim: #4edea3;
  --color-background: #0f131d;
  --color-surface: #0f131d;
  --color-surface-container-lowest: #0a0e18;
  --color-surface-container-low: #171b26;
  --color-surface-container: #1c1f2a;
  --color-surface-container-high: #262a35;
  --color-surface-container-highest: #313540;
  --color-on-surface: #dfe2f1;
  --color-on-surface-variant: #c7c4d7;
  --color-outline: #908fa0;
  --color-outline-variant: #464554;
}

.font-headline-xl {
  font-family: 'Plus Jakarta Sans', sans-serif;
}
.font-headline-md {
  font-family: 'Plus Jakarta Sans', sans-serif;
}
.font-headline-sm {
  font-family: 'Plus Jakarta Sans', sans-serif;
}
.font-body-md {
  font-family: 'Inter', sans-serif;
}
.font-body-lg {
  font-family: 'Inter', sans-serif;
}

.text-on-primary-fixed {
  color: #07006c;
}
.text-tertiary-fixed-dim {
  color: #4edea3;
}

@keyframes wavePulse {
  0%, 100% { height: 8px; }
  50% { height: 32px; }
}
@keyframes wavePulseHigh {
  0%, 100% { height: 12px; }
  50% { height: 44px; }
}
.wave-1 { animation: wavePulse 1.2s ease-in-out infinite 0.1s; }
.wave-2 { animation: wavePulseHigh 0.95s ease-in-out infinite 0.25s; }
.wave-3 { animation: wavePulse 1.4s ease-in-out infinite 0.4s; }
.wave-4 { animation: wavePulseHigh 1.05s ease-in-out infinite 0.15s; }
</style>
