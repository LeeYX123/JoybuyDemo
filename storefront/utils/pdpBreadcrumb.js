// PDP 面包屑节点解析（2026-11-23 批次 A）。
//
// 后端 ``category_breadcrumb`` 每级给 ``{id, name, depth, local_slug}``。
// 链接优先用 ``local_slug``（来源是 ProductCategory.local_category 的回填
// 映射），按 slug 在本地类目树里取到带 ``channel_code`` 的节点再走
// ``categoryHref``：L1 → /minihome/<code>，L2 → /c/<slug>。
//
// 没有 ``local_slug`` 时按「父级 + 名称」匹配：一级只在根里找；二级只在
// 已解析出的父级的 children 里找同名节点。**禁止全树按名字找第一个**——
// 「配件」在服装与配饰（fashion-accessories，0 商品）和电子产品
// （electronics-accessories）下同名，全树取首个会落到错误的一级。
import { categoryHref } from './categoryLinks'

export function normalizeCategoryName(value) {
  // 只去掉空白与标点，保留字母/数字/汉字：源站面包屑有 English 也有中文
  // 名称（「配件」「电子产品」），两级都要能按名称比较。
  return String(value || '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '')
}

function matchesName(category, target) {
  return [category?.name, category?.name_en, category?.name_zh].some(
    (name) => normalizeCategoryName(name) === target,
  )
}

// 本地类目树里的同 slug 节点（一级先在根里找，再在各根的 children 里找）。
function findCategoryBySlug(categories, slug) {
  if (!slug) return null
  for (const root of categories) {
    if (root.slug === slug) return root
    const child = (root.children || []).find((candidate) => candidate.slug === slug)
    if (child) return child
  }
  return null
}

function findCategoryByName(nodes, name) {
  const target = normalizeCategoryName(name)
  if (!target) return null
  return (nodes || []).find((candidate) => matchesName(candidate, target)) || null
}

/**
 * 把接口的 ``category_breadcrumb`` 解析成可渲染节点。
 *
 * @param {Array<{id: string, name: string, depth: number, local_slug?: string|null}>} crumbs
 * @param {Array<object>} categories 本地类目树（roots + children）
 * @param {(category: object) => string} [labelFor] 本地化名称（命中树节点时用）
 * @returns {Array<{key: string, label: string, to: string}>}
 */
export function resolveProductCategoryCrumbs(crumbs, categories, labelFor) {
  const roots = Array.isArray(categories) ? categories : []
  const rows = Array.isArray(crumbs) ? crumbs : []
  const localizedName = (category) => (labelFor ? labelFor(category) : category?.name || '')

  const resolved = []
  let parentNode = null
  for (const crumb of rows) {
    let treeNode = null
    if (crumb?.local_slug) {
      treeNode = findCategoryBySlug(roots, crumb.local_slug)
    }
    if (!treeNode) {
      const pool = crumb?.depth === 0 ? roots : parentNode?.children || []
      treeNode = findCategoryByName(pool, crumb?.name)
    }
    parentNode = treeNode

    // 命中树节点走 categoryHref（一级可带 channel_code 跳 /minihome/）；
    // 树里没有该 slug（隐藏类目/树未加载）时至少按 slug 降级到 /c/<slug>。
    let to = treeNode ? categoryHref(treeNode) : ''
    if (!to && crumb?.local_slug) to = categoryHref({ slug: crumb.local_slug })
    const node = {
      key: `crumb-${crumb?.id}`,
      label: treeNode ? localizedName(treeNode) : crumb?.name || '',
      to,
    }
    // 归父级的 139 条映射会让两级指向同一个本地类目：去掉重复的相邻级，
    // 避免出现「家居生活 / 家居生活 / 商品名」。
    const previous = resolved[resolved.length - 1]
    if (previous && node.to && previous.to === node.to && previous.label === node.label) {
      continue
    }
    resolved.push(node)
  }
  return resolved
}
