import { reactive } from 'vue'
import { navigateTo, useRoute } from '#imports'

import { useBuyerAuth } from './useBuyerAuth'
import { useLocale } from './useLocale'
import { useUiToast } from './useUiToast'

// Shared wishlist state for the heart buttons on product cards and the detail
// page. The set is module-scoped so every mounted card agrees after one card
// toggles; the ids load once per signed-in session.
const favouriteIds = reactive(new Set())
const pendingIds = reactive(new Set())
let loaded = false
let loadedAccountId = ''
let inflight = null

async function fetchFavouriteIds(accountId) {
  if (typeof window === 'undefined') return null
  if (inflight) return inflight
  inflight = $fetch('/api/v1/buyer/favourites?ids_only=1', {
    credentials: 'include',
    ignoreResponseError: true,
  })
    .then((response) => {
      const ids = Array.isArray(response?.spu_public_ids) ? response.spu_public_ids : []
      favouriteIds.clear()
      for (const id of ids) favouriteIds.add(String(id))
      loaded = true
      loadedAccountId = accountId
      return response
    })
    .catch(() => null)
    .finally(() => {
      inflight = null
    })
  return inflight
}

export function useWishlist() {
  const { isAuthenticated, account } = useBuyerAuth()
  const { t } = useLocale()
  const { show } = useUiToast()
  const route = useRoute()

  function isFavourite(publicId) {
    return Boolean(publicId) && favouriteIds.has(String(publicId))
  }

  function isPending(publicId) {
    return pendingIds.has(String(publicId))
  }

  function ensureLoaded() {
    const accountId = isAuthenticated.value ? String(account.value?.id || '') : ''
    if (!accountId) {
      favouriteIds.clear()
      loaded = false
      loadedAccountId = ''
      return null
    }
    if (loaded && loadedAccountId === accountId) return null
    return fetchFavouriteIds(accountId)
  }

  function removeLocal(publicId) {
    favouriteIds.delete(String(publicId))
  }

  async function toggle(publicId) {
    const id = String(publicId || '')
    if (!id || pendingIds.has(id)) return false

    if (!isAuthenticated.value) {
      show(t('wishlist.signInToSave'))
      await navigateTo(`/auth/login?next=${encodeURIComponent(route.fullPath || '/')}`)
      return false
    }

    // Wait for the initial id load so a fast click cannot race the hydrate.
    await ensureLoaded()
    const wasFavourite = favouriteIds.has(id)
    // Optimistic: flip immediately, reconcile with the server below.
    if (wasFavourite) favouriteIds.delete(id)
    else favouriteIds.add(id)
    pendingIds.add(id)

    try {
      const session = await $fetch('/api/v1/auth/buyer/session', { credentials: 'include' })
      const response = await $fetch('/api/v1/buyer/favourites', {
        method: wasFavourite ? 'DELETE' : 'POST',
        body: { spu_public_id: id },
        headers: { 'X-CSRFToken': session?.csrf_token || '' },
        credentials: 'include',
        ignoreResponseError: true,
      })
      if (response?.error) throw new Error(response.error.message || 'wishlist')
      show(wasFavourite ? t('wishlist.removed') : t('wishlist.saved'), {
        type: 'success',
        timeout: 1800,
      })
      return !wasFavourite
    } catch {
      if (wasFavourite) favouriteIds.add(id)
      else favouriteIds.delete(id)
      show(t('wishlist.toggleFailed'), { type: 'error' })
      return wasFavourite
    } finally {
      pendingIds.delete(id)
    }
  }

  return {
    favouriteIds,
    isFavourite,
    isPending,
    ensureLoaded,
    removeLocal,
    toggle,
  }
}
