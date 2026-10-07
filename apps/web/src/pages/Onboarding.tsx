import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ART } from '../components/art'

import { ArrowRightIcon, HeadphonesIcon, PeopleIcon } from '../components/Icons'
import { PersonaPicker } from '../components/PersonaPicker'
import { World } from '../components/World'
import { INTEREST_OPTIONS, RADIUS_OPTIONS } from '../lib/prefs'
import { usePrefs } from '../state/hooks'

/** Onboarding in ≤ 3 taps (MASTERSPEC §11.1): persona → interests/radius/voice → safety. */
export function Onboarding() {
  const [prefs, update] = usePrefs()
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const navigate = useNavigate()

  const toggleInterest = (i: string) => {
    const has = prefs.interests.includes(i)
    const next = has ? prefs.interests.filter((x) => x !== i) : [...prefs.interests, i].slice(0, 6)
    update({ interests: next })
  }

  return (
    <div className="relative min-h-dvh">
    <World className="fixed inset-0 z-0 h-full w-full" />
    <main className="relative z-10 mx-auto flex min-h-dvh max-w-5xl flex-col px-4 py-6 lg:justify-center lg:py-10">
      <div className="flex flex-col items-center gap-3 text-center">
        <Link to="/" className="logo-text text-4xl no-underline sm:text-5xl" aria-label="Sidequestmaxxing story">
          Sidequestmaxxing
        </Link>
        <ol className="flex items-center gap-2" aria-hidden="true">
          {[1, 2, 3].map((n) => (
            <li key={n} className="flex items-center gap-2">
              <span
                className={`inline-flex h-9 w-9 items-center justify-center rounded-full border-2 text-lg ${
                  n <= step ? 'border-moss-dark bg-moss text-parchment-light' : 'border-edge bg-parchment-light text-ink-soft'
                }`}
              >
                {n}
              </span>
              {n < 3 ? <span className={`h-1 w-10 rounded ${n < step ? 'bg-moss' : 'bg-edge/60'}`} /> : null}
            </li>
          ))}
        </ol>
        <p className="sign-title text-base" aria-live="polite">
          Step {step} of 3
        </p>
      </div>

      {step === 1 && (
        <section aria-labelledby="dm-title" className="parchment-frame mt-5">
          <div className="parchment p-4 sm:p-8">
            <h1 id="dm-title" className="hand-title text-3xl lg:text-4xl">
              Choose your Dungeon Master
            </h1>
            <p className="mb-4 text-ink-soft">Each one sees the world differently. Pick the vibe that feels right today.</p>
            <PersonaPicker
              wide
              value={prefs.persona}
              onChange={(p) => {
                update({ persona: p })
                setStep(2)
              }}
            />
          </div>
        </section>
      )}

      {step === 2 && (
        <section aria-labelledby="interest-title" className="parchment mx-auto mt-5 w-full max-w-3xl p-4 sm:p-8">
          <h1 id="interest-title" className="hand-title text-3xl">
            What makes you curious?
          </h1>
          <p className="text-ink-soft">Optional. Pick up to 6 — the Dungeon Master leans into them.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {INTEREST_OPTIONS.map((i) => (
              <button
                key={i}
                type="button"
                className="toggle-chip"
                aria-pressed={prefs.interests.includes(i)}
                onClick={() => toggleInterest(i)}
              >
                {i}
              </button>
            ))}
          </div>

          <h2 className="mt-6 text-2xl">How far will you roam?</h2>
          <div role="radiogroup" aria-label="Quest radius" className="mt-2 flex gap-2">
            {RADIUS_OPTIONS.map((r) => (
              <button
                key={r.value}
                type="button"
                role="radio"
                aria-checked={prefs.radiusM === r.value}
                className="toggle-chip"
                onClick={() => update({ radiusM: r.value })}
              >
                {r.label}
              </button>
            ))}
          </div>

          <label className="mt-6 flex min-h-11 cursor-pointer items-center gap-3 text-xl">
            <input
              type="checkbox"
              className="h-6 w-6 accent-moss"
              checked={prefs.voice}
              onChange={(e) => update({ voice: e.target.checked })}
            />
            <HeadphonesIcon /> Let the Dungeon Master speak the briefing
          </label>
          <p className="ml-9 text-sm text-ink-soft">The words are always on screen too.</p>

          <button type="button" className="btn btn-wood mt-6 w-full" onClick={() => setStep(3)}>
            Continue <ArrowRightIcon />
          </button>
        </section>
      )}

      {step === 3 && (
        <section aria-labelledby="safety-title" className="parchment mx-auto mt-5 grid w-full max-w-4xl gap-6 p-4 sm:p-8 md:grid-cols-[1fr_1.4fr]">
          <img src={ART.sceneVerify} alt="" className="hidden h-full min-h-56 w-full rounded-xl object-cover md:block" />
          <div>
          <h1 id="safety-title" className="hand-title text-3xl">
            One promise before you go
          </h1>
          <div className="mt-3 flex items-start gap-3">
            <span className="mt-1 text-2xl text-moss">
              <PeopleIcon />
            </span>
            <p className="text-xl">
              <strong>Tell someone where you're going.</strong> Quests are only in public places and in daylight, and you can
              stop any quest at any time.
            </p>
          </div>
          <ul className="mt-4 list-disc space-y-1 pl-6 text-ink-soft">
            <li>Sidequestmaxxing is a game — not an emergency or navigation tool.</li>
            <li>Photos are checked on your device and never uploaded.</li>
            <li>The server sees only an approximate area (about 100 m) to find nearby places.</li>
          </ul>
          <button
            type="button"
            className="btn btn-moss mt-6 w-full"
            onClick={() => {
              update({ safetyAck: true, onboarded: true })
              navigate('/home')
            }}
          >
            I'll tell someone — let's go! <ArrowRightIcon />
          </button>
          <p className="mt-3 text-center text-sm text-ink-soft">
            Want on-device photo checks? You can install the verifier later in Settings.
          </p>
          </div>
        </section>
      )}
    </main>
    </div>
  )
}
