import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { ART, PORTRAIT } from '../components/art'
import { HeadphonesIcon, XIcon } from '../components/Icons'
import { Waveform } from '../components/Waveform'
import { api } from '../lib/api'
import { formatClock } from '../lib/labels'
import { elapsedSeconds } from '../lib/questMachine'
import { speak } from '../lib/speech'
import { usePrefs, useNow } from '../state/hooks'
import { useQuest } from '../state/QuestProvider'

/**
 * Walk Mode (MASTERSPEC §11.1 #4): near-black, minimal, no wake lock. The timer is computed
 * from the server's accepted_at, so it is right after backgrounding, reloads and lock screens.
 */
export function Walk() {
  const [prefs] = usePrefs()
  const { run, startVerify, reset } = useQuest()
  const navigate = useNavigate()
  const now = useNow(1000)
  const [confirmStop, setConfirmStop] = useState(false)
  const [speaking, setSpeaking] = useState(false)

  if (run.phase === 'verifying') return <Navigate to="/verify" replace />
  if (run.phase === 'completed') return <Navigate to="/reward" replace />
  if (run.phase !== 'accepted' || !run.quest) return <Navigate to="/home" replace />
  const quest = run.quest
  const elapsed = elapsedSeconds(run, now)

  const repeat = () => {
    if (speak(quest.briefing, () => setSpeaking(false))) setSpeaking(true)
  }

  const stop = async () => {
    await api.skipQuest(quest.id).catch(() => undefined)
    reset()
    navigate('/home')
  }

  return (
    <main className="relative flex min-h-dvh flex-col overflow-hidden bg-forest-deep text-parchment-light">
      <img src={ART.sceneForest} alt="" className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-25" />
      <div className="absolute inset-0 bg-gradient-to-b from-forest-deep/70 via-forest-deep/40 to-forest-deep/95" aria-hidden="true" />

      <header className="relative flex items-start justify-between gap-3 p-5">
        <div>
          <h1 className="text-3xl">Walk Mode</h1>
          <p className="max-w-xs text-parchment-deep">Your quest is live. Keep your phone in your pocket and explore.</p>
        </div>
        <button
          type="button"
          onClick={repeat}
          className="inline-flex h-12 w-12 items-center justify-center rounded-full border-2 border-parchment-deep/50 text-2xl"
          aria-label="Repeat the briefing out loud"
        >
          <HeadphonesIcon />
        </button>
      </header>

      <section className="relative flex flex-1 flex-col items-center justify-center px-6 text-center" aria-label="Quest timer">
        <p className="text-parchment-deep">{quest.title}</p>
        <p className="mt-2 font-[family-name:var(--font-logo)] text-7xl tabular-nums" aria-live="off">
          <span className="sr-only">Time outside: </span>
          {formatClock(elapsed)}
        </p>
        <p className="mt-3 max-w-sm text-lg text-parchment-deep">{quest.objective}</p>
      </section>

      <section className="relative p-5">
        <div className="flex items-end gap-3">
          <img src={PORTRAIT[prefs.persona]} alt="" className="h-14 w-14 rounded-full border-2 border-parchment-deep object-cover" />
          <p className="bubble bubble-dark flex-1">{quest.off_screen_tip}</p>
        </div>
        <div className="mt-3 flex flex-col items-center text-moss-light">
          <Waveform active={speaking} bars={24} />
          <p className="mt-1 text-parchment-deep">Stay present. You got this.</p>
        </div>

        <button
          type="button"
          className="btn btn-moss mt-5 w-full py-5 text-2xl"
          onClick={() => {
            startVerify()
            navigate('/verify')
          }}
        >
          I'm back
        </button>

        {confirmStop ? (
          <div role="alertdialog" aria-labelledby="stop-q" className="mt-3 rounded-xl bg-forest-soft p-3 text-center">
            <p id="stop-q">Stop this quest? No penalty — you can grab another any time.</p>
            <div className="mt-2 flex justify-center gap-2">
              <button type="button" className="btn btn-ghost-dark" onClick={() => void stop()}>
                Yes, stop
              </button>
              <button type="button" className="btn btn-ghost-dark" onClick={() => setConfirmStop(false)}>
                Keep going
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="mx-auto mt-3 flex min-h-11 items-center gap-1 text-parchment-deep underline"
            onClick={() => setConfirmStop(true)}
          >
            <XIcon /> Stop quest
          </button>
        )}
        <p className="mt-2 text-center text-sm text-parchment-deep/80">Safety: {quest.safety_note}</p>
      </section>
    </main>
  )
}
