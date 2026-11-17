// 一级类目的落地页链接。有频道 code（/api/v1/categories depth=0 行的
// channel_code，由 CategoryMapping 的 minihome:<code> 反查）的一级跳独立
// 频道落地页 /minihome/<code>（joybuy.co.uk/minihome/<pagecode> 同构）；
// 没有频道 code 的一级（computers-accessories、outdoor-sports 等）保持
// 跳 /c/<slug> 结果页。二级始终走 /c/<slug>。
export function categoryHref(category) {
  if (!category || !category.slug) return ''
  const code = typeof category.channel_code === 'string' ? category.channel_code : ''
  return code ? `/minihome/${code}` : `/c/${category.slug}`
}
