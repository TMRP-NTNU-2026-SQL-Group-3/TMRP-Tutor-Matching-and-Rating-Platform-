// Shared date/time formatters used across views.

export function formatLocalDate(dt) {
  if (!dt) return ''
  // FE-20: validate the parsed components before constructing a Date to avoid
  // "Invalid Date" appearing in the UI when the server returns a bad string.
  const parts = String(dt).slice(0, 10).split('-').map(Number)
  if (parts.length !== 3 || parts.some(isNaN)) return ''
  const [y, m, d] = parts
  // Parse YYYY-MM-DD strings as local (not UTC) to avoid off-by-one TZ shifts.
  const date = new Date(y, m - 1, d)
  if (isNaN(date.getTime())) return ''
  return date.toLocaleDateString('zh-TW')
}

export function formatTimeOnly(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

export function formatDateTimeShort(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

export function formatDateTimeFull(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString('zh-TW', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    timeZoneName: 'short',
  })
}
