/**
 * Splits `text` into an ordered array of {text, mark} segments where every
 * occurrence of `query` (case-insensitive) is flagged mark:true.  Callers
 * render each segment with v-text / {{ }} so no raw HTML is ever involved.
 *
 * Returns [{text: string, mark: boolean}]
 */
export function highlightParts(text, query) {
  if (!query || !text) return [{ text: text || '', mark: false }]
  const lower = text.toLowerCase()
  const lowerQ = query.toLowerCase()
  const parts = []
  let pos = 0
  let idx
  while ((idx = lower.indexOf(lowerQ, pos)) !== -1) {
    if (idx > pos) parts.push({ text: text.slice(pos, idx), mark: false })
    parts.push({ text: text.slice(idx, idx + query.length), mark: true })
    pos = idx + query.length
  }
  if (pos < text.length) parts.push({ text: text.slice(pos), mark: false })
  return parts
}
