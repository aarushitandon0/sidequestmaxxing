import { Link } from 'react-router-dom'

import { PORTRAIT } from '../components/art'
import { Medallion } from '../components/Medallion'
import { XpBar } from '../components/XpBar'
import { friendlyError } from '../lib/api'
import { CATEGORY_LABEL, SKILL_LABEL } from '../lib/labels'
import { CATEGORIES } from '../lib/types'
import { usePrefs, useProfile } from '../state/hooks'

/** Explorer profile + 7-branch skill tree (MASTERSPEC §11.1 #7). Levels come from the server. */
export function Profile() {
  const [prefs] = usePrefs()
  const profile = useProfile()

  if (profile.isPending) return <p role="status">Unrolling your skill tree…</p>
  if (profile.isError) {
    return (
      <div role="alert" className="parchment p-5">
        <p>{friendlyError(profile.error)}</p>
        <button type="button" className="btn btn-ghost mt-3" onClick={() => void profile.refetch()}>
          Try again
        </button>
      </div>
    )
  }
  const p = profile.data
  const prev = 120 * p.level * p.level

  return (
    <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
      <aside className="dark-panel flex flex-col gap-3 p-4" aria-label="Explorer">
        <div className="flex items-center gap-3">
          <img src={PORTRAIT[prefs.persona]} alt="" className="h-16 w-16 rounded-full border-2 border-parchment-deep object-cover" />
          <div>
            <h1 className="text-2xl">Explorer</h1>
            <p>Lv. {p.level}</p>
          </div>
        </div>
        <XpBar value={p.total_xp - prev} max={p.next_level_xp - prev} label="Overall level progress" />
        <p className="text-right text-sm text-parchment-deep">
          {p.total_xp} / {p.next_level_xp}
        </p>
        <dl className="grid grid-cols-2 gap-2 text-center">
          <div className="rounded-xl bg-forest-soft p-2">
            <dt className="text-sm text-parchment-deep">Quests</dt>
            <dd className="text-2xl">{p.quests_completed}</dd>
          </div>
          <div className="rounded-xl bg-forest-soft p-2">
            <dt className="text-sm text-parchment-deep">Streak</dt>
            <dd className="text-2xl">{p.streak_days}d</dd>
          </div>
        </dl>
        <Link to="/settings" className="btn btn-ghost-dark">
          Settings &amp; delete my data
        </Link>
      </aside>

      <section aria-labelledby="tree-title" className="parchment p-4 sm:p-6">
        <h2 id="tree-title" className="hand-title text-center text-3xl">
          Skill Tree
        </h2>
        <p className="text-center text-ink-soft">Grow your skills. Unlock new quests.</p>
        <div className="relative mt-4">
          <svg aria-hidden="true" viewBox="0 0 400 300" className="pointer-events-none absolute inset-0 h-full w-full opacity-30">
            <path d="M200 300 C200 230 200 200 200 150 M200 200 C160 170 110 160 80 120 M200 200 C240 170 290 160 320 120 M200 150 C180 110 160 80 140 40 M200 150 C220 110 240 80 260 40"
              stroke="#8a6a3c" strokeWidth="14" fill="none" strokeLinecap="round" />
          </svg>
          <ul className="relative grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-4">
            {CATEGORIES.map((c) => {
              const s = p.skills[c]
              const floor = 40 * s.level * s.level
              return (
                <li key={c} className="flex flex-col items-center text-center">
                  <Medallion category={c} size={68} dim={s.xp === 0} />
                  <p className="mt-1 text-lg leading-tight">{SKILL_LABEL[c]}</p>
                  <p className="text-ink-soft">Lv. {s.level}</p>
                  {s.title ? <p className="text-sm text-moss">“{s.title}”</p> : null}
                  <div className="mt-1 w-24">
                    <XpBar value={s.xp - floor} max={s.next_level_xp - floor} label={`${SKILL_LABEL[c]} progress`} />
                  </div>
                  <p className="text-xs text-ink-soft">({CATEGORY_LABEL[c]})</p>
                </li>
              )
            })}
          </ul>
        </div>
      </section>
    </div>
  )
}
