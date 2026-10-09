/**
 * Verifies the Content-Security-Policy in render.yaml against the real built bundle.
 *
 * A CSP is the one header that can white-screen a static deploy, and it cannot be checked by
 * eye: what matters is what the bundle actually loads at runtime. So this serves `dist/` with
 * the exact policy from render.yaml (the only substitution is the API host, which points at
 * the deployed API there and at localhost here) and drives Chromium through every route,
 * failing on any `securitypolicyviolation` event.
 *
 *   npm run build && node scripts/check_csp.mjs
 *
 * Needs the network: /map loads real OpenStreetMap tiles.
 */
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { extname, join, normalize, resolve } from 'node:path'

import { chromium } from '@playwright/test'

const WEB_ROOT = resolve(import.meta.dirname, '..')
const DIST = join(WEB_ROOT, 'dist')
const RENDER_YAML = resolve(WEB_ROOT, '../../render.yaml')
const PORT = 4183
const ORIGIN = `http://localhost:${PORT}`
/** render.yaml allow-lists the deployed API; locally the bundle's default base URL is this. */
const API_IN_YAML = 'https://sqm-api.onrender.com'
const API_LOCAL = 'http://localhost:8000'

const ROUTES = ['/', '/onboarding', '/home', '/quest', '/walk', '/verify', '/reward', '/profile', '/chronicle', '/settings', '/settings/export', '/map']

/**
 * An accepted quest, seeded into localStorage before the first paint. Without it /quest,
 * /walk, /verify and /map render empty states and Leaflet never mounts — which would leave
 * the two most CSP-sensitive things in the app (tile images from a third-party origin and
 * Leaflet's runtime inline styles) completely untested.
 */
const SEED_QUEST = {
  phase: 'accepted',
  quest: {
    id: '6f1c2c1e-0000-4000-8000-000000000001',
    title: 'The Riverbank Riddle',
    category: 'naturalist',
    briefing: 'Find the old stone marker by the river and look for a leaf growing in the cracks.',
    objective: 'Find the stone marker by the river.',
    place_id: 'way/1',
    est_minutes: 15,
    verification: { method: 'photo', photo_prompt: 'an old stone marker' },
    safety_note: 'Stay on the path and away from the water edge.',
    off_screen_tip: 'Phone in pocket.',
    rarity: 'common',
    xp: 30,
    distance_m: 1200,
    place: { id: 'way/1', name: 'Riverside Park', lat: 18.521, lng: 73.857 },
  },
  acceptedAt: new Date().toISOString(),
  screen: { visibleMs: 0, visibleSince: Date.now(), lastBeat: Date.now() },
  pending: null,
  result: null,
  finishedAt: null,
}

/** One field-log row, so /settings/export renders its table and offers the blob download. */
const SEED_FIELD = [{
  quest_id: '6f1c2c1e-0000-4000-8000-000000000001',
  date: new Date().toISOString().slice(0, 10),
  category: 'naturalist',
  rarity: 'common',
  est_minutes: 15,
  elapsed_seconds: 1200,
  screen_seconds: 60,
  screen_share: 0.05,
  verification_method: 'photo',
  source: 'llm',
  voice: true,
}]

const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.webp': 'image/webp', '.png': 'image/png',
  '.wasm': 'application/wasm', '.json': 'application/json', '.webmanifest': 'application/manifest+json',
  '.mp3': 'audio/mpeg', '.txt': 'text/plain', '.ico': 'image/x-icon',
}

/** Pulls the folded `value: >-` block out of the Content-Security-Policy header entry. */
async function cspFromRenderYaml() {
  const lines = (await readFile(RENDER_YAML, 'utf8')).split(/\r?\n/)
  const nameAt = lines.findIndex((l) => /^\s*name:\s*Content-Security-Policy\s*$/.test(l))
  if (nameAt === -1) throw new Error('render.yaml has no Content-Security-Policy header')
  const valueAt = lines.findIndex((l, i) => i > nameAt && /^\s*value:\s*>-\s*$/.test(l))
  if (valueAt !== nameAt + 1) throw new Error('expected `value: >-` right after the CSP header name')
  const indent = lines[valueAt].search(/\S/)
  const body = []
  for (const line of lines.slice(valueAt + 1)) {
    if (line.trim() === '') break
    if (line.search(/\S/) <= indent) break
    body.push(line.trim())
  }
  return body.join(' ').replace(API_IN_YAML, API_LOCAL)
}

function serve(csp) {
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent((req.url ?? '/').split('?')[0])
    // Mirrors the render.yaml rewrite: anything that isn't a file falls back to index.html.
    const candidate = resolve(DIST, '.' + normalize(path))
    const file = candidate.startsWith(DIST) && existsSync(candidate) && extname(candidate) ? candidate : join(DIST, 'index.html')
    res.setHeader('Content-Security-Policy', csp)
    res.setHeader('Content-Type', TYPES[extname(file)] ?? 'application/octet-stream')
    res.end(await readFile(file))
  })
  return new Promise((ok) => server.listen(PORT, () => ok(server)))
}

const csp = await cspFromRenderYaml()
if (!existsSync(join(DIST, 'index.html'))) {
  console.error('No dist/index.html — run `npm run build` first.')
  process.exit(1)
}
console.log(`CSP under test:\n  ${csp}\n`)

const server = await serve(csp)
const browser = await chromium.launch()
const violations = []
try {
  for (const route of ROUTES) {
    const page = await browser.newPage()
    page.on('console', (m) => {
      if (/Content Security Policy|Refused to/i.test(m.text())) violations.push({ route, from: 'console', detail: m.text() })
    })
    await page.addInitScript(({ seed, field }) => {
      try {
        window.localStorage.setItem('sqm.quest.v1', JSON.stringify(seed))
        window.localStorage.setItem('sqm.field.v1', JSON.stringify(field))
        window.localStorage.setItem('sqm.device_id', JSON.stringify('6f1c2c1e-0000-4000-8000-0000000000de'))
      } catch {
        // Private-mode storage; the empty states still exercise the app shell.
      }
      window.__csp = []
      document.addEventListener('securitypolicyviolation', (e) => {
        window.__csp.push(`${e.violatedDirective} blocked ${e.blockedURI} (${e.sourceFile ?? 'inline'})`)
      })
    }, { seed: SEED_QUEST, field: SEED_FIELD })
    await page.goto(`${ORIGIN}${route}`, { waitUntil: 'load' })
    // Let lazy chunks, the SW registration, fonts and map tiles settle.
    await page.waitForTimeout(2500)
    for (const detail of await page.evaluate(() => window.__csp ?? [])) violations.push({ route, from: 'event', detail })
    // A blank page raises no violations either, so a silent white-screen must not read as a
    // pass: every route has to have rendered real content, and /map has to have booted Leaflet.
    const rendered = await page.evaluate(() => (document.getElementById('root')?.innerText ?? '').trim().length)
    if (rendered < 40) violations.push({ route, from: 'render', detail: `rendered only ${rendered} chars of text` })
    // A blob: CSV download is the one thing this page does that a CSP can break.
    if (route === '/settings/export') {
      await page.getByRole('button', { name: /Download CSV/ }).click()
      await page.waitForTimeout(500)
      for (const detail of await page.evaluate(() => window.__csp ?? [])) violations.push({ route, from: 'event', detail })
    }
    if (route === '/map') {
      if ((await page.locator('.leaflet-container').count()) === 0) {
        violations.push({ route, from: 'render', detail: 'no .leaflet-container — the map never mounted' })
      }
      // Tiles come from a third-party origin, so this is the one directive a typo silently
      // breaks: no <img.leaflet-tile> means img-src is wrong, violation event or not.
      const tiles = await page.locator('img.leaflet-tile').count()
      if (tiles === 0) violations.push({ route, from: 'render', detail: 'no map tiles loaded — check img-src' })
      else console.log(`${''.padEnd(17)} ${tiles} OSM tiles loaded under the policy`)
    }
    await page.close()
    console.log(`${route.padEnd(17)} ${violations.some((v) => v.route === route) ? 'FAIL' : `ok (${rendered} chars)`}`)
  }
} finally {
  await browser.close()
  server.close()
}

const unique = [...new Set(violations.map((v) => `${v.route}  ${v.detail}`))]
if (unique.length) {
  console.error(`\n${unique.length} CSP violation(s):`)
  for (const v of unique) console.error(`  - ${v}`)
  process.exit(1)
}
console.log(`\nNo CSP violations across ${ROUTES.length} routes.`)
