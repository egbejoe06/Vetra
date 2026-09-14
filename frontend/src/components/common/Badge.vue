<script setup lang="ts">
interface Props {
  variant?: 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'outline'
  size?: 'sm' | 'md'
}

withDefaults(defineProps<Props>(), {
  variant: 'secondary',
  size: 'md',
})
</script>

<template>
  <span
    class="inline-flex items-center gap-1 font-medium rounded-full border transition-colors"
    :class="[
      size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs',
      {
        'bg-primary/15 text-primary border-primary/30': variant === 'primary',
        'bg-surface-container-high text-on-surface-variant border-outline-variant/30': variant === 'secondary',
        'bg-emerald-500/15 text-emerald-400 border-emerald-500/30': variant === 'success',
        'bg-amber-500/15 text-amber-300 border-amber-500/30': variant === 'warning',
        'bg-error/15 text-error border-error/30': variant === 'error',
        'bg-transparent text-on-surface-variant border-outline-variant': variant === 'outline',
      }
    ]"
  >
    <slot />
  </span>
</template>
