import { ref } from 'vue'

// Tiny global toast queue for account interactions (wishlist feedback, address
// save errors). Messages are already translated by the caller; the component
// only renders text, so no remote assets or third-party dependencies.
const toasts = ref([])
let nextId = 1

export function useUiToast() {
  function dismiss(id) {
    toasts.value = toasts.value.filter((toast) => toast.id !== id)
  }

  function show(message, { type = 'info', timeout = 3200 } = {}) {
    if (!message) return
    const id = nextId
    nextId += 1
    toasts.value = [...toasts.value, { id, message, type }]
    if (timeout > 0 && typeof window !== 'undefined') {
      window.setTimeout(() => dismiss(id), timeout)
    }
    return id
  }

  return { toasts, show, dismiss }
}
