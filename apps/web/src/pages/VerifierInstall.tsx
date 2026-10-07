import { useEffect, useRef, useState } from 'react'

import { useVerifier } from '../verifier/context'
import type { Support } from '../verifier/gemma'

const REASON: Record<Exclude<Support, { ok: true }>['reason'], string> = {
  'no-webgpu': "This browser doesn't support WebGPU, which the on-device checker needs.",
  'no-adapter': "WebGPU is present but this device's graphics chip isn't available to it.",
  'no-opfs': "This browser can't store large files for offline use.",
}

const gb = (b: number) => `${(b / 1e9).toFixed(2)} GB`

/**
 * Opt-in install of the on-device verifier (MASTERSPEC §7.6): size warning, progress,
 * resumable download (or use a file you already have), cached for offline. Never blocks the app.
 */
export function VerifierInstall({ onInstalled }: { onInstalled?: () => void }) {
  const verifier = useVerifier()
  const [support, setSupport] = useState<Support | null>(null)
  const [progress, setProgress] = useState<{ loaded: number; total: number | null } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [installed, setInstalled] = useState(verifier.installed)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => {
    let live = true
    verifier.detectSupport().then(
      (s) => live && setSupport(s),
      () => live && setSupport({ ok: false, reason: 'no-webgpu' }),
    )
    return () => {
      live = false
      abort.current?.abort()
    }
  }, [verifier])

  const done = () => {
    setProgress(null)
    setInstalled(true)
    onInstalled?.()
  }
  const fail = (err: unknown) => {
    setProgress(null)
    if (err instanceof DOMException && err.name === 'AbortError') return
    setError('The download stopped. Tap again to resume where it left off.')
  }

  const download = () => {
    setError(null)
    abort.current = new AbortController()
    setProgress({ loaded: 0, total: null })
    verifier.download((loaded, total) => setProgress({ loaded, total }), abort.current.signal).then(done, fail)
  }
  const fromFile = (file: File | undefined) => {
    if (!file) return
    setError(null)
    setProgress({ loaded: 0, total: file.size })
    verifier.importFile(file, (loaded, total) => setProgress({ loaded, total })).then(done, fail)
  }

  if (installed) {
    return (
      <div className="rounded-xl bg-moss-pale p-3" role="status">
        <p>The on-device photo checker is installed. It works offline.</p>
        <button type="button" className="mt-2 min-h-11 text-ink-soft underline"
          onClick={() => void verifier.remove().then(() => setInstalled(false))}>
          Remove it to free space
        </button>
      </div>
    )
  }

  return (
    <section aria-labelledby="verifier-title" className="rounded-xl border-2 border-edge bg-parchment-light p-3">
      <h3 id="verifier-title" className="text-xl">On-device photo checker (optional)</h3>
      <p className="text-ink-soft">
        Gemma 3n runs in your browser so photos never leave your phone. It's a large download (about 3 GB) — use Wi‑Fi.
        Without it you can still check in or use honor mode.
      </p>
      {support === null ? <p role="status">Checking your device…</p> : null}
      {support && !support.ok ? <p className="mt-2 text-berry">{REASON[support.reason]} Check-in and honor mode still work.</p> : null}
      {support?.ok ? (
        progress ? (
          <div className="mt-2" role="status" aria-live="polite">
            <progress className="w-full" value={progress.loaded} max={progress.total ?? undefined} aria-label="Download progress" />
            <p className="text-sm">
              {gb(progress.loaded)}
              {progress.total ? ` of ${gb(progress.total)}` : ''}
            </p>
            <button type="button" className="min-h-11 underline" onClick={() => abort.current?.abort()}>
              Pause
            </button>
          </div>
        ) : (
          <div className="mt-2 flex flex-col gap-2">
            {verifier.modelUrl ? (
              <button type="button" className="btn btn-moss" onClick={download}>
                Download the checker (about 3 GB)
              </button>
            ) : null}
            <label className="btn btn-ghost">
              Use a model file I already have
              <input type="file" accept=".litertlm,.task,.bin" className="sr-only" onChange={(e) => fromFile(e.target.files?.[0])} />
            </label>
            {!verifier.modelUrl ? (
              <p className="text-sm text-ink-soft">
                The Gemma 3n web model is gated behind Google's Gemma terms on Hugging Face. Accept them there, download the
                “-Web .litertlm” file, then pick it here.
              </p>
            ) : null}
          </div>
        )
      ) : null}
      {error ? <p role="alert" className="mt-2 text-berry">{error}</p> : null}
    </section>
  )
}
