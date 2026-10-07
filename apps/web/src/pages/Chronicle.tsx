import { useState } from 'react'

import { Link } from 'react-router-dom'

import { ART, CATEGORY_ART } from '../components/art'
import { friendlyError } from '../lib/api'
import { SKILL_LABEL } from '../lib/labels'
import type { RecentCompletion } from '../lib/types'
import { useProfile } from '../state/hooks'

const DAY = 86_400_000

function weekOf(items: RecentCompletion[], now = Date.now()) {
  return items.filter((r) => now - Date.parse(r.completed_at) < 7 * DAY)
}

const fmt = (d: Date) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

/** This week's adventures from real completions (the written weekly story arrives with P18). */
export function Chronicle() {
  const profile = useProfile()
  const [copied, setCopied] = useState(false)
  const [now] = useState(() => Date.now())

  if (profile.isPending) return <p role="status">Opening the chronicle…</p>
  if (profile.isError) return <p role="alert" className="parchment p-5">{friendlyError(profile.error)}</p>

  const week = weekOf(profile.data.recent, now)
  const minutes = week.reduce((s, r) => s + r.minutes_outside, 0)
  const text = [
    `My week of side quests (${fmt(new Date(now - 6 * DAY))} – ${fmt(new Date(now))}):`,
    ...week.map((r) => `• ${r.title ?? SKILL_LABEL[r.category]}${r.place_name ? ` at ${r.place_name}` : ''} — +${r.xp_awarded} XP, ${r.minutes_outside} min outside`),
    `${week.length} quests, ${minutes} minutes outside. #sidequestmaxxing`,
  ].join('\n')

  const share = async () => {
    try {
      if (navigator.share) await navigator.share({ text })
      else {
        await navigator.clipboard.writeText(text)
        setCopied(true)
      }
    } catch {
      // share sheet dismissed
    }
  }

  const xp = week.reduce((s, r) => s + r.xp_awarded, 0)
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now - (6 - i) * DAY)
    const key = d.toDateString()
    return { d, done: week.filter((r) => new Date(r.completed_at).toDateString() === key).length }
  })
  const counts = new Map<RecentCompletion['category'], number>()
  for (const r of week) counts.set(r.category, (counts.get(r.category) ?? 0) + 1)
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 lg:gap-6">
      <div className="parchment-frame lg:col-span-7">
        <section aria-labelledby="chron-title" className="parchment h-full p-5 sm:p-8">
          <h1 id="chron-title" className="hand-title text-center text-4xl">
            This Week's Chronicle
          </h1>
          <p className="text-center text-ink-soft">
            {fmt(new Date(now - 6 * DAY))} – {fmt(new Date(now))}
          </p>
          {week.length === 0 ? (
            <div className="mt-8 text-center">
              <img src={ART.sceneMountains} alt="" className="mx-auto h-40 w-full max-w-md rounded-xl object-cover opacity-90" />
              <p className="mt-4 text-xl">No quests yet this week. Still a lot of world left to see…</p>
              <Link to="/home" className="btn btn-wood mt-4">
                Start a quest
              </Link>
            </div>
          ) : (
            <ol className="mt-4 divide-y divide-edge/50">
              {week.map((r) => (
                <li key={r.quest_id} className="flex items-center gap-4 py-3">
                  <img src={CATEGORY_ART[r.category]} alt="" className="h-16 w-16 rounded-lg object-cover" />
                  <div>
                    <p className="text-xl leading-tight">{r.title ?? 'A side quest'}</p>
                    <p className="text-ink-soft">
                      +{r.xp_awarded} XP · {r.minutes_outside} min{r.place_name ? ` · ${r.place_name}` : ''}
                    </p>
                    <p className="text-sm text-moss">{SKILL_LABEL[r.category]}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-6 text-center italic text-ink-soft">Still a lot of world left to see…</p>
        </section>
      </div>

      <aside className="flex flex-col gap-5 lg:col-span-5 lg:gap-6" aria-label="Week at a glance">
        <section aria-labelledby="glance-title" className="dark-panel p-5">
          <h2 id="glance-title" className="text-2xl">Week at a glance</h2>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-center">
            <div className="rounded-xl bg-forest-soft p-3">
              <dt className="text-sm text-parchment-deep">Quests</dt>
              <dd className="text-3xl">{week.length}</dd>
            </div>
            <div className="rounded-xl bg-forest-soft p-3">
              <dt className="text-sm text-parchment-deep">Minutes outside</dt>
              <dd className="text-3xl">{minutes}</dd>
            </div>
            <div className="rounded-xl bg-forest-soft p-3">
              <dt className="text-sm text-parchment-deep">XP earned</dt>
              <dd className="text-3xl">{xp}</dd>
            </div>
            <div className="rounded-xl bg-forest-soft p-3">
              <dt className="text-sm text-parchment-deep">Top skill</dt>
              <dd className="text-2xl">{top ? SKILL_LABEL[top] : '—'}</dd>
            </div>
          </dl>
          <ol className="mt-4 grid grid-cols-7 gap-1 text-center" aria-label="Quests per day">
            {days.map(({ d, done }) => (
              <li key={d.toDateString()} className="flex flex-col items-center gap-1">
                <span className="text-sm text-parchment-deep">{d.toLocaleDateString(undefined, { weekday: 'narrow' })}</span>
                <span
                  className={`inline-flex h-9 w-9 items-center justify-center rounded-full border-2 ${
                    done ? 'border-gold-light bg-moss text-parchment-light' : 'border-forest-soft text-parchment-deep/60'
                  }`}
                >
                  {done || '·'}
                </span>
                <span className="sr-only">
                  {d.toLocaleDateString(undefined, { weekday: 'long' })}: {done} quests
                </span>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="share-title" className="parchment p-5">
          <h2 id="share-title" className="hand-title text-2xl">
            Share your week
          </h2>
          <p className="text-ink-soft">A plain-text recap — no photos, no places beyond the names you visited.</p>
          <button type="button" className="btn btn-ghost mt-3 w-full" onClick={() => void share()} disabled={!week.length}>
            Share as text
          </button>
          {copied ? <p role="status" className="mt-1 text-center text-sm">Copied to your clipboard.</p> : null}
        </section>
      </aside>
    </div>
  )
}
