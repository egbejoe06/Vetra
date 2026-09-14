<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  level: number // 0 - 100
  barCount?: number
  color?: 'primary' | 'ai' | 'emerald'
}

const props = withDefaults(defineProps<Props>(), {
  level: 0,
  barCount: 5,
  color: 'primary',
})

// Generate dynamic heights for bars based on level
const barHeights = computed(() => {
  const normalized = Math.min(100, Math.max(0, props.level))
  const heights: number[] = []

  for (let i = 0; i < props.barCount; i++) {
    if (normalized === 0) {
      heights.push(15) // baseline small height
    } else {
      // Deterministic pseudo-random variation per bar based on index
      const variation = Math.sin((i + 1) * 1.5) * 0.3 + 0.7
      const h = Math.min(100, Math.max(20, normalized * variation * 1.2))
      heights.push(Math.round(h))
    }
  }
  return heights
})
</script>

<template>
  <div class="flex items-center gap-1 h-8 px-2 justify-center">
    <div
      v-for="(h, idx) in barHeights"
      :key="idx"
      class="w-1 rounded-full transition-all duration-100 ease-out"
      :style="{ height: `${h}%` }"
      :class="{
        'bg-primary': color === 'primary',
        'ai-gradient-bg': color === 'ai',
        'bg-emerald-400': color === 'emerald',
      }"
    />
  </div>
</template>
