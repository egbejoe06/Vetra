<script setup lang="ts">
import { useRoute } from 'vue-router'
import Navbar from '@/components/common/Navbar.vue'
import ToastContainer from '@/components/common/ToastContainer.vue'

const route = useRoute()
</script>

<template>
  <div class="h-screen w-screen flex flex-col bg-background text-on-surface overflow-hidden">
    <!-- Main Top Navigation -->
    <Navbar v-if="!route.meta?.hideNavbar" />

    <!-- Global Toast & Error Notifications -->
    <ToastContainer />

    <!-- Route Content Area -->
    <main class="flex-1 min-h-0 h-full overflow-hidden relative flex flex-col">
      <router-view />
    </main>
  </div>
</template>

<style>
/* Smooth transitions */
.animate-fade-in {
  animation: fadeIn 0.25s ease-out forwards;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: scale(0.98);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
