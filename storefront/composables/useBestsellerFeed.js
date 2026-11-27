// Shared data loader for the desktop and mobile 【畅销榜单 / Bestsellers】
// floors (2026-11-27).
//
// - Tabs listed in `utils/bestsellerCurations.js` are curated: one search
//   request per configured sub-category (in parallel), then composed into the
//   3:2 row by `composeCuratedItems`.
// - Every other tab keeps the original single request unchanged.
// - If the curated composition cannot fill the row (a sub-category is too
//   small, requests fail, ...) we fall back to the tab's original
//   single-request list and log a warning instead of showing a broken row.
//
// 2026-11-27: every request carries `market` + `locale` (same shape as
// `useSearchApi`), so the search API localises card titles at read time. Every
// call site must also put `localeKey` into its useAsyncData key, otherwise the
// cached English row survives a language switch.
import { computed } from 'vue'
import { useRuntimeConfig } from '#imports'

import { useMarketLocale } from './useMarketLocale'
import {
  bestsellerSegments,
  composeCuratedItems,
  curationTotal,
} from '../utils/bestsellerCurations'

export function useBestsellerFeed() {
  const config = useRuntimeConfig()
  const { apiQuery } = useMarketLocale()

  // Reactive cache-key fragment: the floors key their useAsyncData on it so a
  // locale/market switch refetches instead of reusing the previous payload.
  const localeKey = computed(() => `${apiQuery.value.market}-${apiQuery.value.locale}`)

  // Server-side calls use the internal API base, the browser uses the public
  // `/api/v1` proxy prefix.
  function searchUrl(slug) {
    const search = new URLSearchParams({ category: slug, sort: 'newest', page: '1' })
    for (const [key, value] of Object.entries(apiQuery.value)) {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
    }
    const query = search.toString()
    return import.meta.server
      ? `${config.apiBaseInternal}/search?${query}`
      : `/api/v1/search?${query}`
  }

  async function fetchTabItems(slug) {
    const response = await $fetch(searchUrl(slug))
    return Array.isArray(response?.items) ? response.items : []
  }

  /**
   * Items for one tab, unsliced: curated tabs return exactly the configured
   * row (5 today), other tabs return the plain search page.
   */
  async function loadTabItems(slug) {
    const segments = bestsellerSegments(slug)
    if (!segments) return fetchTabItems(slug)

    const limit = curationTotal(segments)
    try {
      const responses = await Promise.all(
        segments.map((segment) => $fetch(searchUrl(segment.category))),
      )
      const candidateLists = responses.map((response) =>
        Array.isArray(response?.items) ? response.items : [],
      )
      const { items, complete } = composeCuratedItems(segments, candidateLists, limit)
      if (complete) return items
      console.warn(
        `[bestsellers] curation for "${slug}" only produced ${items.length}/${limit} cards; ` +
          'falling back to the tab list',
      )
    } catch (error) {
      console.warn(
        `[bestsellers] curation request for "${slug}" failed; falling back to the tab list`,
        error,
      )
    }

    return fetchTabItems(slug)
  }

  return { loadTabItems, searchUrl, localeKey }
}
