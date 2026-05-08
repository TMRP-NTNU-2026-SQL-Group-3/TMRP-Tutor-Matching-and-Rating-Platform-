import { createHash } from 'crypto'
import { readdirSync, readFileSync, writeFileSync, statSync } from 'fs'
import path from 'path'

// Computes SHA-384 integrity hashes for every emitted JS/CSS chunk and injects
// `integrity="sha384-..."` attributes into the HTML files in the build output.
//
// Why we read from disk in `writeBundle` instead of hashing `chunk.code` in
// `generateBundle`: Vite's `vite:build-import-analysis` plugin rewrites the
// entry chunk's code to replace `__VITE_PRELOAD__` placeholders with the real
// preload URL list. That mutation happens during the chunk-rendering pipeline
// after post-enforce `generateBundle` hooks run, so a hash computed there is
// stale for any chunk containing dynamic imports — the browser then silently
// blocks the script for SRI mismatch and the SPA fails to mount (white screen).
// `writeBundle` runs after all chunks are finalised and written to disk, so
// hashing the on-disk bytes is guaranteed to match what the browser fetches.
export default function sriPlugin() {
  let outDir = 'dist'
  return {
    name: 'vite-plugin-inline-sri',
    apply: 'build',
    enforce: 'post',
    configResolved(config) {
      outDir = config.build?.outDir || 'dist'
    },
    writeBundle(options) {
      const root = path.resolve(options.dir || outDir)

      // Pass 1: walk the output dir and hash every .js / .css file.
      const integrityMap = new Map()
      const walk = (dir) => {
        for (const entry of readdirSync(dir)) {
          const full = path.join(dir, entry)
          if (statSync(full).isDirectory()) {
            walk(full)
            continue
          }
          if (!/\.(js|css)$/.test(entry)) continue
          const buf = readFileSync(full)
          const rel = path.relative(root, full).split(path.sep).join('/')
          integrityMap.set(rel, `sha384-${createHash('sha384').update(buf).digest('base64')}`)
        }
      }
      walk(root)

      // Pass 2: patch every HTML file at the output root.
      for (const entry of readdirSync(root)) {
        if (!entry.endsWith('.html')) continue
        const htmlPath = path.join(root, entry)
        let html = readFileSync(htmlPath, 'utf-8')

        // Vite 6 already emits crossorigin on module scripts and modulepreload
        // links; SEC-04 requires it for SRI-validated CORS fetches. Only add
        // when missing so we don't produce duplicate attributes.
        html = html.replace(/(<script\b[^>]*?)src="(\/[^"?#]+)"([^>]*>)/g, (match, before, p, after) => {
          const integrity = integrityMap.get(p.slice(1))
          if (!integrity) return match
          const hasCrossorigin = /\bcrossorigin\b/.test(before + after)
          const corsAttr = hasCrossorigin ? '' : ' crossorigin="anonymous"'
          return `${before}src="${p}" integrity="${integrity}"${corsAttr}${after}`
        })
        html = html.replace(/(<link\b[^>]*?)href="(\/[^"?#]+)"([^>]*>)/g, (match, before, p, after) => {
          const integrity = integrityMap.get(p.slice(1))
          if (!integrity) return match
          const hasCrossorigin = /\bcrossorigin\b/.test(before + after)
          const corsAttr = hasCrossorigin ? '' : ' crossorigin="anonymous"'
          return `${before}href="${p}" integrity="${integrity}"${corsAttr}${after}`
        })

        writeFileSync(htmlPath, html)
      }
    },
  }
}
