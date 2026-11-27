// Remembers the horizontal offset of a category tile strip across remounts.
//
// 2026-11-27: on /c/<slug> picking another L2 of the same parent re-creates the
// listing subtree (the carousel track element identity changes), so the strip
// used to jump back to its left edge. The offset is keyed by the parent
// category slug and only used by the listing strip (the channel page passes no
// key, so its behaviour is unchanged).
const memory = new Map()
const LIMIT = 32

export function rememberStripScroll(key, snapshot) {
  if (!key || !snapshot) return
  if (!memory.has(key) && memory.size >= LIMIT) {
    memory.delete(memory.keys().next().value)
  }
  memory.set(key, snapshot)
}

export function recallStripScroll(key) {
  return key ? memory.get(key) : undefined
}

export function forgetStripScroll(key) {
  if (key) memory.delete(key)
}
