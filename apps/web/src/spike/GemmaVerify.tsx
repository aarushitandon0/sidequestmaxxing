import { useEffect, useState } from 'react'

import { VerifierInstall } from '../pages/VerifierInstall'
import { useVerifier } from '../verifier/context'
import type { Support } from '../verifier/gemma'

/**
 * P11 SPIKE (dev builds only, route /spike/gemma): batch-run the on-device verifier over a
 * labelled photo set and download per-image results for spike/score.ts. Photos stay local.
 * File naming: <label>__<photo prompt with dashes>__<anything>.jpg, label = pos | neg.
 */
interface Row {
  file: string
  label: 'pos' | 'neg'
  prompt: string
  match: boolean
  confidence: number
  seen: string
  latency_ms: number
}

export function parseFixtureName(name: string): { label: 'pos' | 'neg'; prompt: string } | null {
  const m = /^(pos|neg)__([^_]+(?:_[^_]+)*?)__/.exec(name)
  return m ? { label: m[1] as 'pos' | 'neg', prompt: m[2]!.replace(/-/g, ' ') } : null
}

export default function GemmaVerify() {
  const verifier = useVerifier()
  const [support, setSupport] = useState<Support | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [status, setStatus] = useState('')
  const [loadMs, setLoadMs] = useState<number | null>(null)

  useEffect(() => {
    void verifier.detectSupport().then(setSupport)
  }, [verifier])

  const run = async (files: FileList | null) => {
    if (!files) return
    const out: Row[] = []
    const t0 = performance.now()
    for (const [i, file] of [...files].entries()) {
      const meta = parseFixtureName(file.name)
      if (!meta) continue
      setStatus(`Checking ${i + 1}/${files.length}: ${file.name}`)
      const r = await verifier.verify(file, meta.prompt)
      if (i === 0) setLoadMs(Math.round(performance.now() - t0 - r.latencyMs))
      out.push({ file: file.name, ...meta, match: r.match, confidence: r.confidence, seen: r.seen, latency_ms: r.latencyMs })
      setRows([...out])
    }
    setStatus('Done. Download the results and run spike/score.ts.')
  }

  const download = () => {
    const meta = { user_agent: navigator.userAgent, model_load_ms: loadMs, created_at: new Date().toISOString() }
    const blob = new Blob([JSON.stringify({ meta, rows }, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'gemma_spike_results.json' // saved locally; nothing is uploaded
    a.click()
  }

  return (
    <main className="mx-auto max-w-2xl p-5">
      <h1 className="hand-title text-3xl">Gemma verifier spike (P11)</h1>
      <p>WebGPU: {support === null ? 'checking…' : support.ok ? 'available' : `not available (${support.reason})`}</p>
      <div className="mt-3"><VerifierInstall /></div>
      <label className="btn btn-ghost mt-3">
        Pick labelled photos
        <input type="file" multiple accept="image/*" className="sr-only" onChange={(e) => void run(e.target.files)} />
      </label>
      <p role="status" className="mt-2">{status}</p>
      {loadMs != null ? <p>First call incl. model load: ~{loadMs} ms before inference</p> : null}
      <table className="mt-3 w-full text-sm">
        <thead><tr><th>file</th><th>label</th><th>match</th><th>conf</th><th>ms</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.file}><td>{r.file}</td><td>{r.label}</td><td>{String(r.match)}</td><td>{r.confidence}</td><td>{r.latency_ms}</td></tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="btn btn-moss mt-3" onClick={download} disabled={!rows.length}>Download results JSON</button>
    </main>
  )
}
