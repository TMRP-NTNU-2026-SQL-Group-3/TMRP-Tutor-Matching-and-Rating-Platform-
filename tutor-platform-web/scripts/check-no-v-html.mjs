// F-17: lightweight guard-rail that fails the build if any template binds
// user-sourced content through `v-html`. Vue's text interpolation escapes by
// default, so our current code is XSS-safe — this script exists to keep that
// invariant from regressing without pulling in a full ESLint tool-chain.
//
// Run manually:    npm run lint
// Runs on CI via:  npm run build  (prebuild hook)
//
// If you have a legitimate reason to render trusted HTML in a template, add
// `// eslint-disable-line no-v-html` on the offending line to opt-out.
import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('../src', import.meta.url))
const V_HTML_RE = /\bv-html\b/
const INNER_HTML_RE = /\.(innerHTML|outerHTML)\s*[+]?=/
const OPT_OUT_RE = /eslint-disable-line\s+no-v-html/

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      files.push(...await walk(full))
    } else if (entry.isFile() && /\.(vue|js|ts)$/.test(entry.name)) {
      files.push(full)
    }
  }
  return files
}

const violations = []
for (const file of await walk(ROOT)) {
  const lines = (await readFile(file, 'utf8')).split('\n')
  lines.forEach((line, idx) => {
    if ((V_HTML_RE.test(line) || INNER_HTML_RE.test(line)) && !OPT_OUT_RE.test(line)) {
      violations.push(`${relative(process.cwd(), file)}:${idx + 1}  ${line.trim()}`)
    }
  })
}

if (violations.length) {
  console.error('[lint] v-html / innerHTML is forbidden on user-sourced bindings (F-17):')
  for (const v of violations) console.error('  ' + v)
  console.error('\nUse text interpolation ({{ ... }}) instead, or add `// eslint-disable-line no-v-html` if the content is proven-safe.')
  process.exit(1)
}
console.log('[lint] no v-html / innerHTML violations')
