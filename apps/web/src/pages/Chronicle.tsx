import { useState } from 'react'

import { CATEGORY_ART } from '../components/art'
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

  return (
    <div className="mx-auto max-w-lg">
      <div className="parchment-frame">
        <section aria-labelledby="chron-title" className="parchment p-5">
          <h1 id="chron-title" className="hand-title text-center text-3xl">
            This Week's Chronicle
          </h1>
          <p className="text-center text-ink-soft">
            {fmt(new Date(now - 6 * DAY))} – {fmt(new Date(now))}
          </p>
          {week.length === 0 ? (
            <p className="mt-6 text-center text-lg">No quests yet this week. Still a lot of world left to see…</p>
          ) : (
            <ol className="mt-4 divide-y divide-edge/50">
              {week.map((r) => (
                <li key={r.quest_id} className="flex items-center gap-3 py-3">
                  <img src={CATEGORY_ART[r.category]} alt="" className="h-14 w-14 rounded-lg object-cover" />
                  <div>
                    <p className="text-lg leading-tight">{r.title ?? 'A side quest'}</p>
                    <p className="text-ink-soft">
                      +{r.xp_awarded} XP · {r.minutes_outside} min{r.place_name ? ` · ${r.place_name}` : ''}
                    </p>
                    <p className="text-sm text-moss">{SKILL_LABEL[r.category]}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-4 text-center">
            {week.length} quests · {minutes} min outside
          </p>
          <button type="button" className="btn btn-ghost mt-3 w-full" onClick={() => void share()} disabled={!week.length}>
            Share as text
          </button>
          {copied ? <p role="status" className="mt-1 text-center text-sm">Copied to your clipboard.</p> : null}
          <p className="mt-4 text-center italic text-ink-soft">Still a lot of world left to see…</p>
        </section>
      </div>
    </div>
  )
}
