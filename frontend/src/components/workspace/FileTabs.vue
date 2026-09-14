<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'

const workspaceStore = useWorkspaceStore()

function getFileIcon(fileName: string): string {
  if (fileName.endsWith('.py')) return 'code'
  if (fileName.endsWith('.ts') || fileName.endsWith('.js')) return 'javascript'
  if (fileName.endsWith('.json')) return 'data_object'
  if (fileName.endsWith('.md')) return 'description'
  return 'draft'
}
</script>

<template>
  <div class="flex items-center bg-surface-container-low border-b border-surface-container-highest px-2 overflow-x-auto select-none">
    <div class="flex items-center gap-1">
      <button
        v-for="fileName in workspaceStore.fileNames"
        :key="fileName"
        class="flex items-center gap-2 px-3 py-2 text-xs font-mono border-b-2 transition-all"
        :class="[
          workspaceStore.activeFile === fileName
            ? 'border-primary text-primary bg-surface-container font-semibold'
            : 'border-transparent text-on-surface-variant hover:text-on-surface hover:bg-surface-container/50'
        ]"
        @click="workspaceStore.setActiveFile(fileName)"
      >
        <span class="material-symbols-outlined text-[16px]">
          {{ getFileIcon(fileName) }}
        </span>
        <span>{{ fileName }}</span>
      </button>
    </div>
  </div>
</template>
