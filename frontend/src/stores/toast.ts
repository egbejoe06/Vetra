import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastType = 'error' | 'success' | 'warning' | 'info'

export interface ToastItem {
  id: string
  type: ToastType
  title?: string
  message: string
  details?: string
  duration?: number
  timestamp: number
}

export interface ToastOptions {
  title?: string
  details?: string
  duration?: number
}

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<ToastItem[]>([])

  function addToast(type: ToastType, message: string, options: ToastOptions = {}) {
    // Avoid spamming duplicate error messages within 3 seconds
    const existing = toasts.value.find(
      (t) => t.type === type && t.message === message && Date.now() - t.timestamp < 3000,
    )
    if (existing) return existing.id

    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const duration = options.duration ?? (type === 'error' ? 7000 : 4500)

    const newToast: ToastItem = {
      id,
      type,
      title: options.title || (type === 'error' ? 'Error' : type === 'success' ? 'Success' : undefined),
      message,
      details: options.details,
      duration,
      timestamp: Date.now(),
    }

    toasts.value.push(newToast)

    if (duration > 0) {
      setTimeout(() => {
        dismiss(id)
      }, duration)
    }

    return id
  }

  function error(message: string, options?: ToastOptions) {
    return addToast('error', message, options)
  }

  function success(message: string, options?: ToastOptions) {
    return addToast('success', message, options)
  }

  function warning(message: string, options?: ToastOptions) {
    return addToast('warning', message, options)
  }

  function info(message: string, options?: ToastOptions) {
    return addToast('info', message, options)
  }

  function dismiss(id: string) {
    const idx = toasts.value.findIndex((t) => t.id === id)
    if (idx !== -1) {
      toasts.value.splice(idx, 1)
    }
  }

  function clear() {
    toasts.value = []
  }

  return {
    toasts,
    error,
    success,
    warning,
    info,
    dismiss,
    clear,
  }
})
