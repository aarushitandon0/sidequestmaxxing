/**
 * Builds src/story/data.json for the story page's "Receipts" scene from eval artifacts:
 *   evals/results.json  — written by the eval harness (P16)
 *   evals/field.md      — field-test summary (P21), first markdown table = rows
 * Missing/invalid files → null → the scene is hidden. Numbers are copied, never typed.
 * Runs inside the Vite config (dev, build, test); also `node --experimental-strip-types`.
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Metric, StoryData } from '../src/story/types.ts'

export type { Metric, StoryData }

const isCell = (v: unknown): v is number | string | null => v === null || typeof v === 'number' || typeof v === 'string'

export function parseResults(raw: string): StoryData['results'] {
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return null
  }
  if (!data || typeof data !== 'object') return null
  const d = data as { n?: unknown; metrics?: unknown }
  if (!Array.isArray(d.metrics)) return null
  const metrics: Metric[] = []
  for (const m of d.metrics) {
    if (!m || typeof m !== 'object') continue
    const r = m as Record<string, unknown>
    if (typeof r.label !== 'string' || !isCell(r.baseline) || !isCell(r.tuned)) continue
    metrics.push({ label: r.label, baseline: r.baseline, tuned: r.tuned, ...(typeof r.unit === 'string' ? { unit: r.unit } : {}) })
  }
  return metrics.length ? { source: 'evals/results.json', n: typeof d.n === 'number' ? d.n : null, metrics } : null
}

export function parseField(md: string): StoryData['field'] {
  const rows: { label: string; value: string }[] = []
  let inTable = false
  for (const line of md.split(/\r?\n/)) {
    const t = line.trim()
    if (!t.startsWith('|')) {
      if (inTable) break
      continue
    }
    const cells = t.replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
    if (cells.every((c) => /^:?-{3,}:?$/.test(c))) continue // separator row
    if (!inTable) {
      inTable = true // header row
      continue
    }
    if (cells.length >= 2 && cells[0] && cells[1]) rows.push({ label: cells[0], value: cells[1] })
  }
  return rows.length ? { source: 'evals/field.md', rows } : null
}

export function buildStoryData(repoRoot: string): StoryData {
  const read = (p: string) => {
    const f = resolve(repoRoot, p)
    return existsSync(f) ? readFileSync(f, 'utf8') : null
  }
  const results = read('evals/results.json')
  const field = read('evals/field.md')
  return { results: results ? parseResults(results) : null, field: field ? parseField(field) : null }
}

/** Writes the JSON only when it changed (keeps the committed file stable). */
export function writeStoryData(webRoot: string): StoryData {
  const data = buildStoryData(resolve(webRoot, '../..'))
  const out = resolve(webRoot, 'src/story/data.json')
  const text = JSON.stringify(data, null, 2) + '\n'
  if (!existsSync(out) || readFileSync(out, 'utf8') !== text) writeFileSync(out, text)
  return data
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const data = writeStoryData(resolve(dirname(fileURLToPath(import.meta.url)), '..'))
  console.log(`story data: results=${data.results ? 'yes' : 'none'} field=${data.field ? 'yes' : 'none'}`)
}
