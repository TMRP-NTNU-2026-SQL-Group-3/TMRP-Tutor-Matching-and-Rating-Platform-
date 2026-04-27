import { createHash } from 'crypto'

// Computes SHA-384 integrity hashes for every emitted JS/CSS chunk and injects
// `integrity="sha384-..."` attributes into the HTML assets in the Rollup bundle.
//
// Uses a single `generateBundle` hook with two passes so the hashing and HTML
// patching share the same bundle snapshot without any cross-hook timing issues.
// (Splitting across generateBundle + transformIndexHtml is unreliable: Vite
// calls transformIndexHtml from inside its own core generateBundle phase, which
// runs before post-enforce plugins' generateBundle — the map would be empty.)
//
// `enforce: 'post'` guarantees that by the time this hook runs, Vite's core
// pipeline has already emitted every chunk and generated the HTML assets.
export default function sriPlugin() {
  return {
    name: 'vite-plugin-inline-sri',
    apply: 'build',
    enforce: 'post',
    generateBundle(_, bundle) {
      // Pass 1: hash every JS / CSS chunk (skip HTML assets themselves).
      const integrityMap = new Map()
      for (const [fileName, chunk] of Object.entries(bundle)) {
        if (chunk.type === 'asset' && fileName.endsWith('.html')) continue
        const source = chunk.type === 'chunk' ? chunk.code : chunk.source
        if (!source) continue
        const buf = typeof source === 'string' ? Buffer.from(source) : source
        integrityMap.set(fileName, `sha384-${createHash('sha384').update(buf).digest('base64')}`)
      }

      // Pass 2: patch `src` and `href` attributes in every HTML asset.
      for (const [fileName, chunk] of Object.entries(bundle)) {
        if (chunk.type !== 'asset' || !fileName.endsWith('.html')) continue
        let html = typeof chunk.source === 'string'
          ? chunk.source
          : Buffer.from(chunk.source).toString('utf-8')

        // Match absolute-path src="/assets/..." and href="/assets/..." produced
        // by Vite's default base "/". Only injects integrity when the file is in
        // the bundle map (skips external links, anchor href, etc.).
        html = html.replace(/\bsrc="(\/[^"?#]+)"/g, (match, path) => {
          const integrity = integrityMap.get(path.slice(1))
          return integrity ? `src="${path}" integrity="${integrity}"` : match
        })
        html = html.replace(/\bhref="(\/[^"?#]+)"/g, (match, path) => {
          const integrity = integrityMap.get(path.slice(1))
          return integrity ? `href="${path}" integrity="${integrity}"` : match
        })

        chunk.source = html
      }
    },
  }
}
