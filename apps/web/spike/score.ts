/**
 * Scores a Gemma spike run (gemma_spike_results.json from /spike/gemma) and writes
 * evals/gemma_spike_<ts>.json. Accepted = match && confidence >= 0.6 (MASTERSPEC §7.6).
 *   node --experimental-strip-types spike/score.ts path/to/gemma_spike_results.json
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

interface Row { file: string; label: 'pos' | 'neg'; match: boolean; confidence: number; latency_ms: number }

export function score(rows: Row[]) {
  let tp = 0, fp = 0, tn = 0, fn = 0
  for (const r of rows) {
    const yes = r.match && r.confidence >= 0.6
    if (r.label === 'pos') {
      if (yes) tp++
      else fn++
    } else if (yes) fp++
    else tn++
  }
  const lat = rows.map((r) => r.latency_ms).sort((a, b) => a - b)
  const pct = (p: number) => (lat.length ? lat[Math.min(lat.length - 1, Math.floor(p * (lat.length - 1)))] : null)
  const div = (a: number, b: number) => (b ? Math.round((a / b) * 1000) / 1000 : null)
  return {
    n: rows.length, tp, fp, tn, fn,
    precision: div(tp, tp + fp), recall: div(tp, tp + fn), accuracy: div(tp + tn, rows.length),
    latency_ms_p50: pct(0.5), latency_ms_p95: pct(0.95),
  }
}

if (process.argv[2]) {
  const input = JSON.parse(readFileSync(process.argv[2], 'utf8')) as { meta: unknown; rows: Row[] }
  const out = { kind: 'gemma_spike', meta: input.meta, summary: score(input.rows), rows: input.rows }
  const file = resolve(import.meta.dirname, '../../../evals', `gemma_spike_${new Date().toISOString().replace(/[:.]/g, '')}.json`)
  writeFileSync(file, JSON.stringify(out, null, 2) + '\n')
  console.log(out.summary, `→ ${file}`)
}
