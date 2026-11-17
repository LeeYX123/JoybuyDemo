// Resolves a listing slug against the category tree so the results page can
// render the right trail, sibling tiles and sidebar state.
//
// L2 view  (/c/<child slug>): root = the parent L1, child = the matched L2.
// L1 view  (/c/<root> or /s?category=<root>): root = that L1, child = null —
//          the trail stops at the L1, nothing is selected in the tiles and the
//          sidebar must NOT expand the children.
export function resolveCategoryContext(categories, slug) {
  const empty = { root: null, child: null }
  if (!slug || !Array.isArray(categories)) return empty

  const byChild = categories.find((root) =>
    (root.children || []).some((child) => child.slug === slug),
  )
  if (byChild) {
    return {
      root: byChild,
      child: (byChild.children || []).find((child) => child.slug === slug) || null,
    }
  }

  const root = categories.find((candidate) => candidate.slug === slug) || null
  return { root, child: null }
}
