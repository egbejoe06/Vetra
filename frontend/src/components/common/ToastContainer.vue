<script setup lang="ts">
import { ref } from 'vue'
import { useToastStore, type ToastItem } from '@/stores/toast'

const toastStore = useToastStore()
const expandedDetails = ref<Record<string, boolean>>({})

function toggleDetails(id: string) {
  expandedDetails.value[id] = !expandedDetails.value[id]
}
</script>

<template>
  <div
    class="fixed top-4 right-4 z-50 flex flex-col gap-2.5 max-w-sm sm:max-w-md w-full pointer-events-none px-3 sm:px-0"
    aria-live="polite"
  >
    <TransitionGroup name="toast">
      <div
        v-for="toast in toastStore.toasts"
        :key="toast.id"
        class="pointer-events-auto w-full rounded-xl border shadow-xl p-3.5 backdrop-blur-md transition-all text-xs relative overflow-hidden"
        :class="{
          'bg-surface-container-highest/95 border-error/50 text-on-surface shadow-error/10': toast.type === 'error',
          'bg-surface-container-highest/95 border-emerald-500/40 text-on-surface shadow-emerald-500/10': toast.type === 'success',
          'bg-surface-container-highest/95 border-amber-500/40 text-on-surface shadow-amber-500/10': toast.type === 'warning',
          'bg-surface-container-highest/95 border-primary/40 text-on-surface shadow-primary/10': toast.type === 'info',
        }"
      >
        <!-- Accent bar -->
        <div
          class="absolute left-0 top-0 bottom-0 w-1"
          :class="{
            'bg-error': toast.type === 'error',
            'bg-emerald-400': toast.type === 'success',
            'bg-amber-400': toast.type === 'warning',
            'bg-primary': toast.type === 'info',
          }"
        ></div>

        <div class="flex items-start gap-3 pl-1">
          <!-- Type Icon -->
          <div class="shrink-0 mt-0.5">
            <span
              v-if="toast.type === 'error'"
              class="material-symbols-outlined text-error text-[20px]"
            >
              error
            </span>
            <span
              v-else-if="toast.type === 'success'"
              class="material-symbols-outlined text-emerald-400 text-[20px]"
            >
              check_circle
            </span>
            <span
              v-else-if="toast.type === 'warning'"
              class="material-symbols-outlined text-amber-400 text-[20px]"
            >
              warning
            </span>
            <span
              v-else
              class="material-symbols-outlined text-primary text-[20px]"
            >
              info
            </span>
          </div>

          <!-- Message Body -->
          <div class="flex-1 min-w-0 pr-1">
            <div v-if="toast.title" class="font-semibold text-on-surface text-xs tracking-tight mb-0.5">
              {{ toast.title }}
            </div>
            <p class="text-on-surface-variant text-xs leading-relaxed break-words">
              {{ toast.message }}
            </p>

            <!-- Optional Details Accordion -->
            <div v-if="toast.details" class="mt-2">
              <button
                type="button"
                class="text-[11px] font-mono text-outline hover:text-on-surface flex items-center gap-1 transition-colors"
                @click="toggleDetails(toast.id)"
              >
                <span>{{ expandedDetails[toast.id] ? 'Hide technical details' : 'Show technical details' }}</span>
                <span class="material-symbols-outlined text-[14px]">
                  {{ expandedDetails[toast.id] ? 'expand_less' : 'expand_more' }}
                </span>
              </button>
              <pre
                v-if="expandedDetails[toast.id]"
                class="mt-1.5 p-2 rounded-lg bg-surface-container-lowest/80 border border-outline-variant/30 text-[10px] font-mono text-on-surface-variant overflow-x-auto max-h-36 whitespace-pre-wrap select-text"
              >{{ toast.details }}</pre>
            </div>
          </div>

          <!-- Dismiss Button -->
          <button
            type="button"
            class="shrink-0 p-1 rounded-md text-outline hover:text-on-surface hover:bg-surface-container transition-colors"
            title="Dismiss notification"
            @click="toastStore.dismiss(toast.id)"
          >
            <span class="material-symbols-outlined text-[16px]">close</span>
          </button>
        </div>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.25s ease-out;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(30px) scale(0.95);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(30px) scale(0.95);
}
</style>
