// Vitest stand-in for Nuxt's #imports surface. Component tests only mount
// presentational trees, so each auto-import resolves to a safe stub that
// records its arguments and returns inert reactive-safe defaults.
import { computed, ref } from 'vue'

export const stubCalls = []

function recorder(name) {
  return (...args) => {
    stubCalls.push({ name, args })
    return ref(null)
  }
}

export const useCookie = recorder('useCookie')
export const useFetch = (...args) => {
  stubCalls.push({ name: 'useFetch', args })
  return { data: ref(null), error: ref(null), status: ref('idle'), refresh: async () => {} }
}
export const useRequestHeaders = () => ({})
export const useRuntimeConfig = () => ({
  apiBaseInternal: 'http://127.0.0.1:8000/api/v1',
  public: { apiBase: '/api/v1' },
})
export const useRoute = () => ({ params: {}, query: {} })
export const useRouter = () => ({ push: () => {} })
export const navigateTo = recorder('navigateTo')
export const useHead = recorder('useHead')
export const useState = (initializer) =>
  ref(typeof initializer === 'function' ? initializer() : null)
export const useAsyncData = (...args) => {
  stubCalls.push({ name: 'useAsyncData', args })
  return { data: computed(() => null), error: computed(() => null), status: ref('idle') }
}

export default {
  useCookie,
  useFetch,
  useRequestHeaders,
  useRuntimeConfig,
  useRoute,
  useRouter,
  navigateTo,
  useHead,
  useState,
  useAsyncData,
}
