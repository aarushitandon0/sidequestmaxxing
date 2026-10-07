import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'

import { ART } from '../components/art'
import { CountUp } from '../components/CountUp'
import { ClockIcon, LeafIcon, PhoneIcon, SunIcon } from '../components/Icons'
import { XpBar } from '../components/XpBar'
import { SKILL_LABEL } from '../lib/labels'
import { elapsedSeconds } from '../lib/questMachine'
import { useProfile } from '../state/hooks'
import { useQuest } from '../state/QuestProvider'

/** Quest Complete (MASTERSPEC §11.1 #6): XP, level-ups, minutes outside, real screen share. */
export function Reward() {
  const { run, reset } = useQuest()
  const profile = useProfile(run.phase === 'completed')
  const [openedAt] = useState(() => Date.now())
  if (run.phase !== 'completed' || !run.quest || !run.result) return <Navigate to="/home" replace />
  const { quest, result } = run
  const minutes = Math.max(1, Math.round(elapsedSeconds(run, run.finishedAt ?? openedAt) / 60))
  const share = result.screen_share
  const prevLevelXp = 120 * result.level * result.level
  const nextLevelXp = 120 * (result.level + 1) * (result.level + 1)

  return (
    <div className="mx-auto max-w-5xl">
      <div className="parchment-frame">
        <article aria-labelledby="done-title" className="parchment grid gap-6 p-5 text-center sm:p-8 lg:grid-cols-2 lg:gap-10">
          <div className="flex flex-col">
          <LeafIcon className="mx-auto text-5xl text-moss" />
          <h1 id="done-title" className="hand-title text-4xl lg:text-5xl">
            Quest Complete!
          </h1>
          <p className="text-lg text-ink-soft">{quest.title}</p>
          <img src={ART.sceneReward} alt="" className="mt-3 h-40 w-full flex-1 rounded-xl object-cover lg:min-h-64" />

          </div>
          <div className="flex flex-col justify-center">
          <p className="flex items-center justify-center gap-2 text-4xl lg:justify-start">
            <SunIcon className="text-gold" /> +<CountUp value={result.xp_awarded} /> XP
            <span className="sr-only">{result.xp_awarded} XP earned</span>
          </p>
          <ul className="mt-3 space-y-2 text-left text-lg">
            <li className="flex items-center gap-2">
              <LeafIcon className="text-moss" /> +{result.xp_awarded} {SKILL_LABEL[quest.category]}
            </li>
            <li className="flex items-center gap-2">
              <ClockIcon className="text-moss" /> +{minutes} min outside
            </li>
            {share != null ? (
              <li className="flex items-center gap-2">
                <PhoneIcon className="text-moss" /> Your screen was on for {Math.round(share * 100)}% of this quest
                {share < 0.1 ? ' — bonus XP for staying present!' : ''}
              </li>
            ) : null}
            {result.within_radius === false ? <li className="text-ink-soft">Check-in was a bit far from the place, so XP was halved.</li> : null}
            {result.daily_cap_reached ? <li className="text-ink-soft">You hit today's XP cap — rest is part of the adventure.</li> : null}
          </ul>

          {result.level_ups.length ? (
            <div className="mt-4 rounded-xl border-2 border-gold bg-parchment-light p-3" role="status">
              {result.level_ups.map((u) => (
                <p key={`${u.kind}-${u.category ?? 'all'}`} className="text-xl">
                  {u.kind === 'overall'
                    ? `Level up! You're now level ${u.to_level}.`
                    : `${SKILL_LABEL[u.category!]} reached level ${u.to_level}${u.title ? ` — “${u.title}”` : ''}!`}
                </p>
              ))}
            </div>
          ) : null}

          <div className="mt-4 text-left">
            <p className="flex justify-between">
              <span>Your XP</span>
              <span>Lv. {result.level}</span>
            </p>
            <XpBar value={result.total_xp - prevLevelXp} max={nextLevelXp - prevLevelXp} label="Overall level progress" />
            <p className="text-right text-sm text-ink-soft">
              {result.total_xp} / {nextLevelXp}
            </p>
          </div>
          {result.streak > 1 ? <p className="mt-2">{result.streak}-day streak. Small steps, big adventures.</p> : <p className="mt-2 text-ink-soft">Small steps. Big adventures.</p>}

          <div className="mt-4 flex flex-col gap-2">
            <Link to="/profile" className="btn btn-moss" onClick={() => { reset(); void profile.refetch() }}>
              View your skills
            </Link>
            <Link to="/home" className="btn btn-ghost" onClick={() => reset()}>
              Back to the quest board
            </Link>
          </div>
          </div>
        </article>
      </div>
    </div>
  )
}
