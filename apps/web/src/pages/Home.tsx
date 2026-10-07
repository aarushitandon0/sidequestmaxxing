import { Link, Navigate } from 'react-router-dom'

import { CATEGORY_ART } from '../components/art'
import { DmBubble } from '../components/DmBubble'
import { ArrowRightIcon, ClockIcon, FlameIcon, LeafIcon } from '../components/Icons'
import { LocationConsent } from '../components/LocationConsent'
import { LevelCard } from '../components/Shell'
import { Thinking } from '../components/Thinking'
import { greeting, formatMinutes, MOOD_LABEL } from '../lib/labels'
import { MINUTE_OPTIONS } from '../lib/prefs'
import { MOODS } from '../lib/types'
import { usePrefs, useProfile } from '../state/hooks'
import { useQuest } from '../state/QuestProvider'
import { useStartQuest } from '../state/useStartQuest'

/** Quest Board: one big "Get a quest", the current quest, streak and level. */
export function Home() {
  const [prefs, update] = usePrefs()
  const { run } = useQuest()
  const profile = useProfile()
  const start = useStartQuest(prefs)

  if (!prefs.onboarded) return <Navigate to="/onboarding" replace />

  const live = run.phase === 'accepted' || run.phase === 'verifying'
  const busy = start.status === 'locating' || start.status === 'thinking'

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
      <div className="flex flex-col gap-5">
        <h1 className="sr-only">Quest board</h1>
        <DmBubble persona={prefs.persona} text={greeting(prefs.persona, new Date().getHours())} size="lg" listenable={prefs.voice} />

        {live && run.quest ? (
          <section aria-labelledby="live-title" className="dark-panel flex items-center gap-4 p-4">
            <img src={CATEGORY_ART[run.quest.category]} alt="" className="h-20 w-20 rounded-xl object-cover" />
            <div className="flex-1">
              <h2 id="live-title" className="text-xl">
                Your quest is live: {run.quest.title}
              </h2>
              <p className="text-parchment-deep">Phone in pocket. Come back when you're done.</p>
            </div>
            <Link to={run.phase === 'verifying' ? '/verify' : '/walk'} className="btn btn-moss">
              Resume <ArrowRightIcon />
            </Link>
          </section>
        ) : null}

        {run.phase === 'offered' && run.quest ? (
          <Link to="/quest" className="parchment flex items-center gap-3 p-4 no-underline">
            <LeafIcon className="text-2xl text-moss" />
            <span className="flex-1 text-xl">A quest is waiting: {run.quest.title}</span>
            <ArrowRightIcon />
          </Link>
        ) : null}

        {!live ? (
          <section aria-labelledby="new-title" className="parchment p-4 sm:p-5">
            <h2 id="new-title" className="hand-title text-2xl">
              Ready for a side quest?
            </h2>

            <fieldset className="mt-3">
              <legend className="text-lg">How much time do you have?</legend>
              <div className="mt-1 flex flex-wrap gap-2">
                {MINUTE_OPTIONS.map((m) => (
                  <button key={m} type="button" className="toggle-chip" aria-pressed={prefs.minutes === m}
                    onClick={() => update({ minutes: m })}>
                    {formatMinutes(m)}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset className="mt-3">
              <legend className="text-lg">How are you feeling?</legend>
              <div className="mt-1 flex flex-wrap gap-2">
                {MOODS.map((m) => (
                  <button key={m} type="button" className="toggle-chip" aria-pressed={prefs.mood === m}
                    onClick={() => update({ mood: m })}>
                    {MOOD_LABEL[m]}
                  </button>
                ))}
              </div>
            </fieldset>

            <div className="mt-5">
              {start.status === 'consent' ? (
                <LocationConsent
                  onDevice={() => void start.withChoice('device')}
                  onDemo={() => void start.withChoice('demo')}
                  onCancel={start.cancel}
                />
              ) : busy ? (
                <Thinking persona={prefs.persona} label={start.status === 'locating' ? 'Finding your corner of the map…' : undefined} />
              ) : (
                <button type="button" className="btn btn-wood w-full text-xl" onClick={start.start}
                  disabled={run.phase === 'offered'}>
                  Get a quest <ArrowRightIcon />
                </button>
              )}
              {start.status === 'error' && start.error ? (
                <div role="alert" className="mt-3 rounded-xl border-2 border-berry/40 bg-parchment-light p-3 text-berry">
                  <p>{start.error}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {!start.rateLimited ? (
                      <button type="button" className="btn btn-ghost" onClick={start.start}>
                        Try again
                      </button>
                    ) : null}
                    <button type="button" className="btn btn-ghost" onClick={() => void start.withChoice('demo')}>
                      Use the demo area
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        ) : null}
      </div>

      <aside className="flex flex-col gap-3 lg:w-72" aria-label="Your stats">
        <LevelCard />
        <div className="parchment flex items-center gap-3 p-3">
          <ClockIcon className="text-3xl text-gold" />
          <p className="text-lg">{formatMinutes(prefs.minutes)} free</p>
        </div>
        {profile.data && profile.data.streak_days > 0 ? (
          <div className="parchment flex items-center gap-3 p-3">
            <FlameIcon className="text-3xl text-berry" />
            <p className="text-lg">{profile.data.streak_days}-day streak</p>
          </div>
        ) : null}
        <div className="parchment flex items-start gap-3 p-3 text-ink-soft">
          <LeafIcon className="mt-1 shrink-0 text-2xl text-moss" />
          <p>You'll get a short briefing, then head out. The screen goes dark so you can be in the moment.</p>
        </div>
      </aside>
    </div>
  )
}
