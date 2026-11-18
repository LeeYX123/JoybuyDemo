// crypto.randomUUID 是 secure-context-only API：纯 http（非 localhost）访问时
// 该方法不存在，直接调用会抛 TypeError。降级实现基于 crypto.getRandomValues，
// 该 API 在非安全上下文同样可用。
export function uuidv4() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16),
  )
}
