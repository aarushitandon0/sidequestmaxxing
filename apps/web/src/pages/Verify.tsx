import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { CameraIcon, CheckIcon, LockIcon, PinIcon, XIcon } from '../components/Icons'
import { api, ApiError, friendlyError } from '../lib/api'
import { getCoarseLocation, type LocationError } from '../lib/location'
import { elapsedSeconds } from '../lib/questMachine'
import { visibleSeconds } from '../lib/screenTime'
import type { CompletionRequest, VerificationResult } from '../lib/types'
import { useOnline } from '../state/hooks'
import { useQuest } from '../state/QuestProvider'
import { useVerifier } from '../verifier/context'
import { accepted, type VerifyOutcome } from '../verifier/parse'
import { VerifierInstall } from './VerifierInstall'

type Step =
  | { kind: 'choose' }
  | { kind: 'checking'; preview: string }
  | { kind: 'result'; preview: string; outcome: VerifyOutcome }
  | { kind: 'locating' }
  | { kind: 'claiming' }

/**
 * Verify (MASTERSPEC §7.6, §2.4): on-device Gemma photo check → check-in (≈300 m) → honor
 * mode (50% XP). The photo stays in this tab's memory; only the {match, confidence, seen}
 * result is sent (there is no upload endpoint and the API client has no method for it).
 */
export function Verify() {
  const { run, back, queue, complete } = useQuest()
  const verifier = useVerifier()
  const navigate = useNavigate()
  const online = useOnline()
  const fileInput = useRef<HTMLInputElement | null>(null)
  const [step, setStep] = useState<Step>({ kind: 'choose' })
  const [error, setError] = useState<string | null>(null)
  const [installed, setInstalled] = useState(verifier.installed)
  const [showInstall, setShowInstall] = useState(false)
  const preview = step.kind === 'checking' || step.kind === 'result' ? step.preview : null

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  if (run.phase === 'completed') return <Navigate to="/reward" replace />
  if (run.phase === 'accepted') return <Navigate to="/walk" replace />
  if (run.phase !== 'verifying' || !run.quest) return <Navigate to="/home" replace />
  const quest = run.quest
  const photoPrompt = quest.verification.photo_prompt

  const payload = (verification: VerificationResult, checkin?: { lat: number; lng: number }): CompletionRequest => {
    const now = Date.now()
    return {
      verification,
      elapsed_seconds: elapsedSeconds(run, run.finishedAt ?? now),
      screen_seconds: run.screen ? visibleSeconds(run.screen, now) : 0,
      ...(checkin ? { checkin } : {}),
    }
  }

  const claim = async (body: CompletionRequest) => {
    setStep({ kind: 'claiming' })
    setError(null)
    try {
      complete(await api.completeQuest(quest.id, body))
      navigate('/reward')
    } catch (err) {
      if (err instanceof ApiError && err.isNetwork) {
        queue(body) // verified offline; the provider claims it when the network is back
        setStep({ kind: 'choose' })
        return
      }
      setError(friendlyError(err))
      setStep({ kind: 'choose' })
    }
  }

  const onPhoto = async (file: File | undefined) => {
    if (!file || !photoPrompt) return
    const url = URL.createObjectURL(file)
    setError(null)
    setStep({ kind: 'checking', preview: url })
    try {
      const outcome = await verifier.verify(file, photoPrompt)
      setStep({ kind: 'result', preview: url, outcome })
    } catch {
      setError("The on-device check couldn't run on this phone. Use check-in or honor mode instead.")
      setStep({ kind: 'choose' })
    }
  }

  const onCheckin = async () => {
    setStep({ kind: 'locating' })
    setError(null)
    try {
      const here = await getCoarseLocation()
      await claim(payload({ method: 'checkin' }, here))
    } catch (code) {
      if (typeof code === 'string') {
        const msg: Record<LocationError, string> = {
          denied: 'Location is blocked, so check-in is unavailable. Honor mode still works.',
          unavailable: "Couldn't find your position. Try again or use honor mode.",
          timeout: 'Finding your position took too long. Try again or use honor mode.',
          unsupported: "This browser can't check in. Honor mode still works.",
        }
        setError(msg[code as LocationError] ?? msg.unavailable)
      }
      setStep({ kind: 'choose' })
    }
  }

  if (run.pending) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center p-5">
        <div className="parchment p-6 text-center" role="status">
          <h1 className="hand-title text-3xl">Verified — saved on your phone</h1>
          <p className="mt-2">
            {online ? 'Claiming your reward…' : "You're offline. We'll claim your reward as soon as you're back online."}
          </p>
        </div>
      </main>
    )
  }

  return (
    <main className="mx-auto min-h-dvh max-w-xl p-4">
      <div className="dark-panel overflow-hidden">
        <header className="flex items-start gap-3 p-4">
          <button type="button" onClick={() => { back(); navigate('/walk') }} aria-label="Back to Walk Mode"
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-2xl">
            <XIcon />
          </button>
          <div>
            <h1 className="text-3xl">Verify</h1>
            <p className="text-parchment-deep">
              {photoPrompt ? 'Take one photo. Our model checks it on your device.' : 'Show the realm you made it.'}
            </p>
          </div>
        </header>

        <div className="parchment m-3 mt-0 p-4 text-ink">
          <p className="text-lg">
            <strong>{quest.title}:</strong> {quest.objective}
          </p>
          {photoPrompt ? <p className="text-ink-soft">Photo of: {photoPrompt}</p> : null}

          {preview ? (
            <figure className="relative mt-3 overflow-hidden rounded-xl border-4 border-parchment-light">
              <img src={preview} alt="Your photo (stays on this device)" className="max-h-80 w-full object-cover" />
              {step.kind === 'checking' ? (
                <figcaption role="status" className="absolute inset-x-0 bottom-0 bg-forest/85 p-2 text-center text-parchment-light">
                  Checking on your device…
                </figcaption>
              ) : null}
            </figure>
          ) : null}

          {step.kind === 'result' ? (
            accepted(step.outcome) ? (
              <div className="mt-3 text-center" role="status">
                <p className="inline-flex items-center gap-2 rounded-full bg-moss px-4 py-1 text-xl text-parchment-light">
                  <CheckIcon /> Match found!
                </p>
                <p className="mt-1 text-ink-soft">That's the one. {step.outcome.seen ? `I see ${step.outcome.seen}.` : ''}</p>
                <button type="button" className="btn btn-moss mt-3 w-full text-xl"
                  onClick={() => void claim(payload({ method: 'photo', match: true, confidence: step.outcome.confidence, seen: step.outcome.seen || null }))}>
                  Claim reward
                </button>
              </div>
            ) : (
              <div className="mt-3 text-center" role="status">
                <p className="text-xl">Not quite.</p>
                <p className="text-ink-soft">
                  {step.outcome.seen ? `I see ${step.outcome.seen}. ` : ''}Retake the photo, or use another way below.
                </p>
              </div>
            )
          ) : null}

          {step.kind === 'claiming' || step.kind === 'locating' ? (
            <p role="status" className="mt-3 text-center text-lg">
              {step.kind === 'locating' ? 'Checking you in…' : 'Claiming your reward…'}
            </p>
          ) : null}

          {error ? (
            <p role="alert" className="mt-3 rounded-xl border-2 border-berry/40 bg-parchment-light p-3 text-berry">
              {error}
            </p>
          ) : null}

          {step.kind !== 'checking' && step.kind !== 'claiming' && step.kind !== 'locating' ? (
            <div className="mt-4 flex flex-col gap-2">
              {photoPrompt && installed ? (
                <>
                  <input ref={fileInput} type="file" accept="image/*" capture="environment" className="sr-only"
                    aria-label="Take a photo" onChange={(e) => void onPhoto(e.target.files?.[0])} />
                  <button type="button" className="btn btn-moss text-xl" onClick={() => fileInput.current?.click()}>
                    <CameraIcon /> {step.kind === 'result' ? 'Retake photo' : 'Take the photo'}
                  </button>
                </>
              ) : null}
              {photoPrompt && !installed ? (
                showInstall ? (
                  <VerifierInstall onInstalled={() => { setInstalled(true); setShowInstall(false) }} />
                ) : (
                  <button type="button" className="btn btn-ghost" onClick={() => setShowInstall(true)}>
                    <LockIcon /> Install the on-device photo checker
                  </button>
                )
              ) : null}
              {quest.place ? (
                <button type="button" className="btn btn-ghost" onClick={() => void onCheckin()}>
                  <PinIcon /> Check in at {quest.place.name} (within about 300 m)
                </button>
              ) : null}
              <button type="button" className="btn btn-ghost" onClick={() => void claim(payload({ method: 'honor' }))}>
                I did it — honor mode (half XP)
              </button>
            </div>
          ) : null}

          <p className="mt-4 rounded-xl bg-moss-pale p-3 text-ink-soft">
            <strong>Works in airplane mode.</strong> The photo check runs on your phone and the photo is never uploaded.
            If you're offline, your reward is claimed automatically when you're back online.
          </p>
        </div>
      </div>
      <p className="mt-3 text-center">
        <Link to="/walk" onClick={() => back()} className="text-ink-soft underline">
          Not done yet? Back to Walk Mode
        </Link>
      </p>
    </main>
  )
}
