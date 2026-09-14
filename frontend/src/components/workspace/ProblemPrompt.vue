<script setup lang="ts">
import { useWorkspaceStore } from '@/stores/workspace'

const workspaceStore = useWorkspaceStore()
</script>

<template>
  <div class="flex flex-col h-full bg-surface-container border border-outline-variant/30 rounded-2xl overflow-hidden shadow-lg">
    <!-- Header -->
    <div class="px-4 py-3 border-b border-surface-container-highest flex items-center justify-between bg-surface-container-low">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-tertiary text-[18px]">terminal</span>
        <h3 class="text-xs font-semibold text-on-surface uppercase tracking-wider">Exercise Brief</h3>
      </div>
      <span
        v-if="workspaceStore.problemTitle"
        class="text-[11px] font-mono text-tertiary bg-tertiary/10 border border-tertiary/20 px-2 py-0.5 rounded"
      >
        Live Codebase
      </span>
    </div>

    <!-- Active Problem Content -->
    <div v-if="workspaceStore.hasProblem" class="flex-1 p-4 overflow-y-auto space-y-4 text-xs">
      <div>
        <h4 class="text-sm font-semibold text-on-surface mb-1">
          {{ workspaceStore.problemTitle }}
        </h4>
        <p class="text-on-surface-variant leading-relaxed">
          {{ workspaceStore.promptQuestion }}
        </p>
      </div>

      <div v-if="workspaceStore.instructions" class="p-3 bg-surface-container-low rounded-xl border border-outline-variant/20">
        <span class="font-semibold text-primary block mb-1">Scenario & Context:</span>
        <p class="text-on-surface-variant leading-relaxed whitespace-pre-line">
          {{ workspaceStore.instructions }}
        </p>
      </div>

      <div class="p-3 bg-surface-container-low rounded-xl border border-outline-variant/20 space-y-2">
        <span class="font-semibold text-on-surface block">Verbal Code Walkthrough:</span>
        <ul class="list-disc list-inside text-on-surface-variant space-y-1">
          <li>Inspect the files on screen and trace data flows out loud with the interviewer.</li>
          <li>Identify potential bugs, edge cases, bottlenecks, or architectural flaws.</li>
          <li>Talk through your proposed solution, trade-offs, and verification approach verbally—no code writing required.</li>
        </ul>
      </div>
    </div>

    <!-- Empty / Waiting State -->
    <div v-else class="flex-1 flex flex-col items-center justify-center p-6 text-center space-y-3 text-on-surface-variant">
      <span class="material-symbols-outlined text-[32px] text-outline">assignment_late</span>
      <div class="space-y-1">
        <h4 class="text-xs font-semibold text-on-surface">No Active Challenge Yet</h4>
        <p class="text-[11px] text-on-surface-variant leading-relaxed">
          The problem prompt will appear here automatically when the interviewer presents the technical review exercise.
        </p>
      </div>
    </div>
  </div>
</template>
