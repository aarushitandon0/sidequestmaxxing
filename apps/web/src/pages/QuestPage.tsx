import { lazy, Suspense, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { CATEGORY_ART } from '../components/art'
import { QuestCard } from '../components/QuestCard'
import { Thinking } from '../components/Thinking'
import { api, ApiError, friendlyError } from '../lib/api'
import { lastRequest, rememberRequest } from '../lib/questRequest'
import { consumeReroll, rerollsLeft } from '../lib/reroll'
import { speak } from '../lib/speech'
import { localTimeIso } from '../lib/time'
import { usePrefs } from '../state/hooks'
import { useQuest } from '../state/QuestProvider'

const QuestMap = lazy(() => import('../components/QuestMap'))

export function QuestPage() {
  const [prefs] = usePrefs()
  const { run, offer, accept, reset } = useQuest()
  const navigate = useNavigate()
  const [busy, setBusy] = useState<null | 'accept' | 'reroll' | 'skip'>(null)
  const [error, setError] = useState<string | null>(null)
  const [left, setLeft] = useState(rerollsLeft)

  if (run.phase === 'accepted') return <Navigate to="/walk" replace />
  if (run.phase === 'verifying') return <Navigate to="/verify" replace />
  if (run.phase !== 'offered' || !run.quest) return <Navigate to="/home" replace />
  const quest = run.quest

  const onAccept = async () => {
    setBusy('accept')
    setError(null)
    try {
      const state = await api.acceptQuest(quest.id)
      accept(state.accepted_at ?? new Date().toISOString())
      if (prefs.voice) speak(quest.briefing) // the briefing is spoken; the phone can go away
      navigate('/walk')
    } catch (err) {
      if (err instanceof ApiError && err.code === 'quest_expired') {
        reset()
        setError('That quest expired. Grab a fresh one from the quest board.')
      } else setError(friendlyError(err))
    } finally {
      setBusy(null)
    }
  }

  const onReroll = async () => {
    const prev = lastRequest()
    if (!prev || left === 0) return
    setBusy('reroll')
    setError(null)
    try {
      await api.skipQuest(quest.id).catch(() => undefined) // memory hint only; never blocks
      const req = { ...prev, minutes_available: prefs.minutes, mood: prefs.mood, local_time_iso: localTimeIso() }
      const next = await api.generateQuest(req)
      rememberRequest(req)
      setLeft(consumeReroll())
      offer(next)
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setBusy(null)
    }
  }

  const onSkip = async () => {
    setBusy('skip')
    await api.skipQuest(quest.id).catch(() => undefined)
    reset()
    navigate('/home')
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-6">
      <div className="flex flex-col gap-4">
        {busy === 'reroll' ? <Thinking persona={prefs.persona} label="Rerolling the dice…" /> : null}
        <QuestCard
          quest={quest}
          persona={prefs.persona}
          voice={prefs.voice}
          busy={busy !== null}
          rerollsLeft={left}
          onAccept={onAccept}
          onReroll={onReroll}
          onSkip={onSkip}
        />
        {error ? (
          <p role="alert" className="rounded-xl border-2 border-berry/40 bg-parchment-light p-3 text-berry">
            {error}
          </p>
        ) : null}
      </div>
      {quest.place ? (
        <Suspense fallback={<div className="parchment h-72 lg:h-full" aria-hidden="true" />}>
          <QuestMap place={quest.place} className="h-72 border-4 border-wood shadow-xl lg:sticky lg:top-28 lg:h-[calc(100dvh-10rem)]" />
        </Suspense>
      ) : (
        <aside className="parchment hidden flex-col items-center justify-center gap-3 p-6 text-center lg:flex" aria-label="Where">
          <img src={CATEGORY_ART[quest.category]} alt="" className="h-64 w-full rounded-xl object-cover" />
          <p className="hand-title text-2xl">Right around you</p>
          <p className="text-ink-soft">No destination needed — this one happens wherever you are.</p>
        </aside>
      )}
    </div>
  )
}
