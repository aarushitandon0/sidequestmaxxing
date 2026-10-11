import { Link, Navigate } from 'react-router-dom'

import { ART, CATEGORY_ART, PORTRAIT } from '../components/art'
import { DmBubble } from '../components/DmBubble'
import { ArrowRightIcon, ClockIcon, FlameIcon, LeafIcon, StarIcon } from '../components/Icons'
import { LocationConsent } from '../components/LocationConsent'
import { Medallion } from '../components/Medallion'
import { Thinking } from '../components/Thinking'
import { XpBar } from '../components/XpBar'
import { greeting, formatMinutes, MOOD_LABEL, PERSONA_INFO, SKILL_LABEL } from '../lib/labels'
import { MINUTE_OPTIONS } from '../lib/prefs'
import { CATEGORIES, MOODS } from '../lib/types'
import { usePrefs, useProfile } from '../state/hooks'
import { useQuest } from '../state/QuestProvider'
import { useStartQuest } from '../state/useStartQuest'

const STEPS = [
  { title: 'Get a quest', text: 'One short briefing for a real place near you.' },
  { title: 'Head out', text: 'The screen goes dark. Phone in pocket.' },
  { title: 'Explore', text: 'Look up. Notice things. Take your time.' },
  { title: 'Verify', text: 'One photo, checked on your device.' },
  { title: 'Level up', text: 'XP for the skill you just used.' },
] as const

/** Explorer card: level, XP, streak and quest count from the server profile. */
function ExplorerCard() {
  const [prefs] = usePrefs()
  const profile = useProfile()
  const p = profile.data
  const prev = p ? 120 * p.level * p.level : 0
  return (
    <section aria-labelledby="explorer-title" className="dark-panel p-4">
      <div className="flex items-center gap-3">
        <img src={PORTRAIT[prefs.persona]} alt="" className="h-16 w-16 rounded-full border-2 border-gold-light object-cover" />
        <div className="flex-1">
          <h2 id="explorer-title" className="text-2xl leading-none">
            {p ? `Lv. ${p.level} Explorer` : 'Explorer'}
          </h2>
          <p className="text-parchment-deep">Guided by {PERSONA_INFO[prefs.persona].name}</p>
        </div>
      </div>
      {p ? (
        <>
          <div className="mt-3">
            <XpBar value={p.total_xp - prev} max={p.next_level_xp - prev} label="Overall level progress" />
            <p className="mt-0.5 text-right text-sm text-parchment-deep">
              {p.total_xp} / {p.next_level_xp} XP
            </p>
          </div>
          <dl className="mt-2 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-xl bg-forest-soft p-2">
              <dt className="text-sm text-parchment-deep">Quests</dt>
              <dd className="text-2xl">{p.quests_completed}</dd>
            </div>
            <div className="rounded-xl bg-forest-soft p-2">
              <dt className="text-sm text-parchment-deep">Streak</dt>
              <dd className="flex items-center justify-center gap-1 text-2xl">
                {p.streak_days > 0 ? <FlameIcon className="text-gold-light" /> : null}
                {p.streak_days}d
              </dd>
            </div>
            <div className="rounded-xl bg-forest-soft p-2">
              <dt className="text-sm text-parchment-deep">Free time</dt>
              <dd className="text-2xl">{formatMinutes(prefs.minutes)}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="mt-3 text-parchment-deep">{profile.isError ? 'Your stats will appear when we can reach the realm.' : 'Loading your stats…'}</p>
      )}
    </section>
  )
}

/** Seven skills at a glance (links to the full tree). */
function SkillSnapshot() {
  const profile = useProfile()
  const p = profile.data
  return (
    <section aria-labelledby="snap-title" className="parchment p-4">
      <div className="flex items-baseline justify-between">
        <h2 id="snap-title" className="hand-title text-2xl">
          Your skills
        </h2>
        <Link to="/profile" className="text-moss underline">
          Skill tree
        </Link>
      </div>
      <ul className="mt-3 grid grid-cols-4 gap-x-2 gap-y-3 sm:grid-cols-7 lg:grid-cols-4">
        {CATEGORIES.map((c) => {
          const s = p?.skills[c]
          return (
            <li key={c} className="flex flex-col items-center text-center">
              <Medallion category={c} size={46} dim={!s || s.xp === 0} />
              <span className="mt-1 text-sm leading-tight">{SKILL_LABEL[c]}</span>
              <span className="text-xs text-ink-soft">Lv. {s?.level ?? 0}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/** Quest Board: one big "Get a quest", the current quest, the explorer's stats and skills. */
export function Home() {
  const [prefs, update] = usePrefs()
  const { run } = useQuest()
  const start = useStartQuest(prefs)

  if (!prefs.onboarded) return <Navigate to="/onboarding" replace />

  const live = run.phase === 'accepted' || run.phase === 'verifying'
  const busy = start.status === 'locating' || start.status === 'thinking'

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 lg:gap-6">
      <h1 className="sr-only">Quest board</h1>

      {live && run.quest ? (
        <section aria-labelledby="live-title" className="dark-panel flex flex-wrap items-center gap-4 p-4 lg:col-span-12">
          <img src={CATEGORY_ART[run.quest.category]} alt="" className="h-20 w-20 rounded-xl object-cover" />
          <div className="min-w-48 flex-1">
            <h2 id="live-title" className="text-2xl">
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
        <Link to="/quest" className="parchment flex items-center gap-3 p-4 no-underline lg:col-span-12">
          <LeafIcon className="text-2xl text-moss" />
          <span className="flex-1 text-xl">A quest is waiting: {run.quest.title}</span>
          <ArrowRightIcon />
        </Link>
      ) : null}

      <div className="flex flex-col gap-5 lg:col-span-8 lg:gap-6">
        <div className="parchment-frame">
          <section aria-labelledby="new-title" className="parchment grid grid-cols-1 gap-5 p-4 sm:p-6 md:grid-cols-[minmax(0,200px)_1fr] md:gap-8">
            <div className="hidden flex-col items-center text-center md:flex">
              <img
                src={PORTRAIT[prefs.persona]}
                alt=""
                width={200}
                height={200}
                className="aspect-square w-full rounded-full border-4 border-parchment-light object-cover shadow-lg"
              />
              <p className="sign-title mt-3 text-lg">{PERSONA_INFO[prefs.persona].name}</p>
              <p className="mt-1 text-sm text-ink-soft">your Dungeon Master</p>
            </div>

            <div className="flex min-w-0 flex-col">
              <div className="md:hidden">
                <DmBubble persona={prefs.persona} text={greeting(prefs.persona, new Date().getHours())} size="lg" listenable={prefs.voice} />
              </div>
              <div className="hidden md:block">
                <DmBubble persona={prefs.persona} text={greeting(prefs.persona, new Date().getHours())} listenable={prefs.voice} hidePortrait />
              </div>

              {!live ? (
                <>
                  <h2 id="new-title" className="hand-title mt-5 text-3xl lg:text-4xl">
                    Ready for a side quest?
                  </h2>

                  <div className="mt-3 flex flex-col gap-4">
                    <fieldset className="min-w-0">
                      <legend className="flex items-center gap-1.5 text-lg">
                        <ClockIcon className="text-gold" /> How much time do you have?
                      </legend>
                      <div className="mt-1 flex flex-wrap gap-2">
                        {MINUTE_OPTIONS.map((m) => (
                          <button key={m} type="button" className="toggle-chip" aria-pressed={prefs.minutes === m}
                            onClick={() => update({ minutes: m })}>
                            {formatMinutes(m)}
                          </button>
                        ))}
                      </div>
                    </fieldset>

                    <fieldset className="min-w-0">
                      <legend className="flex items-center gap-1.5 text-lg">
                        <StarIcon className="text-gold" /> How are you feeling?
                      </legend>
                      <div className="mt-1 flex flex-wrap gap-2">
                        {MOODS.map((m) => (
                          <button key={m} type="button" className="toggle-chip" aria-pressed={prefs.mood === m}
                            onClick={() => update({ mood: m })}>
                            {MOOD_LABEL[m]}
                          </button>
                        ))}
                      </div>
                    </fieldset>
                  </div>

                  <div className="mt-6">
                    {start.status === 'consent' ? (
                      <LocationConsent
                        onDevice={() => void start.withChoice('device')}
                        onCity={(slug) => void start.withChoice(`city:${slug}`)}
                        onCancel={start.cancel}
                      />
                    ) : busy ? (
                      <Thinking persona={prefs.persona} label={start.status === 'locating' ? 'Finding your corner of the map…' : undefined} />
                    ) : (
                      <>
                        <button type="button" className="btn btn-wood w-full py-4 text-2xl" onClick={start.start}
                          disabled={run.phase === 'offered'}>
                          Get a quest <ArrowRightIcon />
                        </button>
                        {start.where ? (
                          <div className="mt-2 flex flex-wrap items-center justify-center gap-x-2 text-ink-soft">
                            <span>{`Playing ${start.where} ·`}</span>
                            <button type="button" className="min-h-11 underline" onClick={start.pickAgain}>
                              Change
                            </button>
                          </div>
                        ) : null}
                      </>
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
                          <button type="button" className="btn btn-ghost" onClick={start.pickAgain}>
                            Pick a city instead
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </>
              ) : (
                <p id="new-title" className="mt-5 text-xl">
                  Finish your live quest first — the next one will be waiting.
                </p>
              )}
            </div>
          </section>
        </div>

        <section aria-labelledby="how-title" className="parchment p-4 sm:p-5">
          <h2 id="how-title" className="hand-title text-2xl">
            How a quest unfolds
          </h2>
          <ol className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {STEPS.map((s, i) => (
              <li key={s.title} className="overflow-hidden rounded-xl border-2 border-edge bg-parchment-light">
                <img src={ART.story[i]} alt="" className="h-24 w-full object-cover" />
                <div className="p-2">
                  <p className="text-lg leading-tight">
                    {i + 1}. {s.title}
                  </p>
                  <p className="text-sm leading-snug text-ink-soft">{s.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <aside className="flex flex-col gap-5 lg:col-span-4 lg:gap-6" aria-label="Your stats">
        <ExplorerCard />
        <SkillSnapshot />
        <div className="parchment flex items-start gap-3 p-4 text-ink-soft">
          <LeafIcon className="mt-1 shrink-0 text-2xl text-moss" />
          <p>Quests are only in public places and in daylight. Tell someone where you're going — and stop any time.</p>
        </div>
      </aside>
    </div>
  )
}
