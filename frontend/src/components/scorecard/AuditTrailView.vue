<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AuditTrailItem } from '@/types'

interface Props {
  auditTrail: AuditTrailItem[]
}

const props = defineProps<Props>()

const filter = ref<'ALL' | 'VERIFIED' | 'REJECTED'>('ALL')

const filteredItems = computed(() => {
  if (filter.value === 'ALL') return props.auditTrail
  return props.auditTrail.filter((item) => item.resolution === filter.value)
})

const verifiedCount = computed(() => {
  return props.auditTrail.filter((item) => item.resolution === 'VERIFIED').length
})

const rejectedCount = computed(() => {
  return props.auditTrail.filter((item) => item.resolution === 'REJECTED').length
})
</script>

<template>
  <div class="bg-surface-container border border-outline-variant/30 rounded-2xl p-6 shadow-xl space-y-4">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-surface-container-highest pb-4">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-primary text-[20px]">policy</span>
        <div>
          <h3 class="text-xs font-semibold text-on-surface uppercase tracking-wider">
            Deterministic Evidence & Citation Audit Trail
          </h3>
          <p class="text-[11px] text-on-surface-variant">
            Empirical verification of turn citations by the EvidenceResolver engine.
          </p>
        </div>
      </div>

      <!-- Filter Buttons -->
      <div class="flex items-center gap-1.5 bg-surface-container-low p-1 rounded-xl border border-outline-variant/20 text-xs">
        <button
          type="button"
          class="px-2.5 py-1 rounded-lg transition-all font-medium"
          :class="filter === 'ALL' ? 'bg-surface-container-highest text-on-surface' : 'text-on-surface-variant hover:text-on-surface'"
          @click="filter = 'ALL'"
        >
          All ({{ auditTrail.length }})
        </button>
        <button
          type="button"
          class="px-2.5 py-1 rounded-lg transition-all font-medium flex items-center gap-1"
          :class="filter === 'VERIFIED' ? 'bg-emerald-500/20 text-emerald-300 font-semibold' : 'text-emerald-400/70 hover:text-emerald-300'"
          @click="filter = 'VERIFIED'"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          Verified ({{ verifiedCount }})
        </button>
        <button
          type="button"
          class="px-2.5 py-1 rounded-lg transition-all font-medium flex items-center gap-1"
          :class="filter === 'REJECTED' ? 'bg-rose-500/20 text-rose-300 font-semibold' : 'text-rose-400/70 hover:text-rose-300'"
          @click="filter = 'REJECTED'"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
          Rejected / Filtered ({{ rejectedCount }})
        </button>
      </div>
    </div>

    <!-- Empty State -->
    <div
      v-if="filteredItems.length === 0"
      class="text-center py-8 text-on-surface-variant text-xs"
    >
      No audit records found matching the selected filter.
    </div>

    <!-- Audit Trail Cards -->
    <div class="space-y-2.5 max-h-[380px] overflow-y-auto pr-2">
      <div
        v-for="(item, idx) in filteredItems"
        :key="idx"
        class="p-3.5 rounded-xl border transition-all text-xs space-y-1.5"
        :class="[
          item.resolution === 'VERIFIED'
            ? 'bg-emerald-500/5 border-emerald-500/20'
            : item.resolution === 'REJECTED'
            ? 'bg-rose-500/5 border-rose-500/25'
            : 'bg-amber-500/5 border-amber-500/20'
        ]"
      >
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span
              class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
              :class="[
                item.resolution === 'VERIFIED'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                  : item.resolution === 'REJECTED'
                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                  : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
              ]"
            >
              {{ item.resolution }}
            </span>
            <span class="font-mono text-[11px] text-outline">
              Citation: <strong class="text-on-surface font-mono">{{ item.original_citation }}</strong>
            </span>
          </div>
          <span v-if="item.timestamp" class="text-[10px] text-outline font-mono">
            {{ new Date(item.timestamp).toLocaleTimeString() }}
          </span>
        </div>

        <p class="text-on-surface font-medium leading-relaxed">
          {{ item.claim }}
        </p>

        <p class="text-[11px] text-on-surface-variant flex items-start gap-1">
          <span class="material-symbols-outlined text-[14px] shrink-0 mt-0.5" :class="item.resolution === 'VERIFIED' ? 'text-emerald-400' : 'text-rose-400'">
            {{ item.resolution === 'VERIFIED' ? 'check_circle' : 'cancel' }}
          </span>
          <span>{{ item.reason }}</span>
        </p>
      </div>
    </div>
  </div>
</template>
