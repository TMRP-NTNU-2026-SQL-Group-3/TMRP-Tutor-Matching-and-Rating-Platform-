// Shared date/time formatters used across views.

export function formatLocalDate(dt) {
  if (!dt) return ''
  // Parse YYYY-MM-DD strings as local (not UTC) to avoid off-by-one TZ shifts.
  const [y, m, d] = String(dt).slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('zh-TW')
}

export function formatTimeOnly(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

export function formatDateTimeShort(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

export function formatDateTimeFull(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-TW', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    timeZoneName: 'short',
  })
}
