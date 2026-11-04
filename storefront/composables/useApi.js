export function useApi(path, options = {}) {
  const config = useRuntimeConfig()

  return useFetch(path, {
    baseURL: import.meta.server ? config.apiBaseInternal : config.public.apiBase,
    credentials: 'include',
    retry: 0,
    ...options,
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
  })
}
