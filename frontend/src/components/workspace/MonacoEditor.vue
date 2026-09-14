<script setup lang="ts">
import { computed } from 'vue'
import { CodeEditor } from 'monaco-editor-vue3'
import { useWorkspaceStore } from '@/stores/workspace'
import FileTabs from './FileTabs.vue'

const workspaceStore = useWorkspaceStore()

const editorOptions = {
  fontSize: 13,
  fontFamily: "'JetBrains Mono', monospace",
  minimap: { enabled: false },
  automaticLayout: true,
  scrollBeyondLastLine: false,
  lineNumbers: 'on' as const,
  roundedSelection: false,
  renderLineHighlight: 'all' as const,
  tabSize: 4,
  wordWrap: 'on' as const,
  cursorBlinking: 'smooth' as const,
  smoothScrolling: true,
  readOnly: true,
  domReadOnly: true,
}

const currentLanguage = computed(() => workspaceStore.activeFileLanguage)
</script>

<template>
  <div class="flex flex-col h-full w-full bg-[#1e1e1e] border border-outline-variant/30 rounded-2xl overflow-hidden shadow-2xl">
    <!-- 1. Code Review Viewer with File Tabs (When files exist) -->
    <template v-if="workspaceStore.fileNames.length > 0">
      <!-- Top File Tabs Bar & Verbal Review Indicator -->
      <div class="flex items-center justify-between bg-[#252526] border-b border-[#2d2d2d] pr-3">
        <div class="flex-1 min-w-0">
          <FileTabs />
        </div>
        <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/25 text-[11px] text-primary font-medium shrink-0 ml-2">
          <span class="material-symbols-outlined text-[14px]">record_voice_over</span>
          <span>Verbal Code Review</span>
        </div>
      </div>

      <!-- Monaco Code Editor Instance (Read-Only Code Viewer) -->
      <div class="flex-1 relative w-full h-full min-h-[300px]">
        <CodeEditor
          v-model:value="workspaceStore.activeFileContent"
          :language="currentLanguage"
          theme="vs-dark"
          :options="editorOptions"
          class="w-full h-full absolute inset-0"
        />
      </div>

      <!-- Status Bar -->
      <div class="h-6 bg-[#181818] border-t border-[#2d2d2d] px-3 flex items-center justify-between text-[11px] text-[#858585] font-mono select-none">
        <div class="flex items-center gap-3">
          <span class="text-primary font-semibold">{{ workspaceStore.activeFile }}</span>
          <span>UTF-8</span>
        </div>
        <div class="flex items-center gap-3">
          <span>Language: {{ currentLanguage.toUpperCase() }}</span>
          <span class="flex items-center gap-1.5 text-emerald-400">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            Read-Only Review Surface
          </span>
        </div>
      </div>
    </template>

    <!-- 2. Elegant Waiting / Loading Screen (When no challenge is active yet) -->
    <template v-else>
      <div class="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4 select-none bg-surface-container-lowest">
        <!-- High-tech pulsating icon -->
        <div class="relative flex items-center justify-center">
          <div class="absolute w-24 h-24 rounded-full bg-primary/10 animate-ping opacity-50"></div>
          <div class="w-16 h-16 rounded-2xl bg-surface-container border border-outline-variant/40 flex items-center justify-center text-primary shadow-xl">
            <span class="material-symbols-outlined text-[32px] animate-pulse">terminal</span>
          </div>
        </div>

        <div class="max-w-md space-y-2">
          <h3 class="text-base font-semibold text-on-surface">
            Code Review Surface Ready
          </h3>
          <p class="text-xs text-on-surface-variant leading-relaxed">
            When you enter the Technical Exercise stage, the multi-file codebase will appear here. You will inspect the code on screen and talk through your analysis and solutions out loud with Vetra.
          </p>
        </div>

        <div class="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-surface-container-high border border-outline-variant/30 text-[11px] font-mono text-outline">
          <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
          <span>Awaiting Technical Stage...</span>
        </div>
      </div>
    </template>
  </div>
</template>
