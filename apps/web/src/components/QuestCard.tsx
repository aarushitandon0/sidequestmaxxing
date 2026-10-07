import { CATEGORY_ART } from './art'
import { DmBubble } from './DmBubble'
import { ArrowRightIcon, ClockIcon, PinIcon, StarIcon } from './Icons'
import { CATEGORY_LABEL, formatDistance, METHOD_LABEL, RARITY_LABEL, SKILL_LABEL } from '../lib/labels'
import type { Persona, Quest } from '../lib/types'

interface Props {
  quest: Quest
  persona: Persona
  voice: boolean
  busy?: boolean
  rerollsLeft: number
  onAccept: () => void
  onReroll: () => void
  onSkip: () => void
}

/** The quest offer card (MASTERSPEC §11.1 #3) in the template's parchment style. */
export function QuestCard({ quest, persona, voice, busy = false, rerollsLeft, onAccept, onReroll, onSkip }: Props) {
  const distance = formatDistance(quest.distance_m)
  return (
    <article aria-labelledby="quest-title" className="parchment overflow-hidden">
      <div className="grid gap-4 p-4 sm:grid-cols-[180px_1fr] sm:p-5">
        <img src={CATEGORY_ART[quest.category]} alt="" className="h-44 w-full rounded-xl object-cover sm:h-full" />
        <div>
          <h1 id="quest-title" className="hand-title flex items-start gap-2 text-3xl">
            <PinIcon className="mt-1 shrink-0 text-gold" />
            {quest.title}
          </h1>
          {quest.place ? (
            <p className="mt-1 flex items-center gap-1 text-ink-soft">
              <PinIcon /> {quest.place.name}
              {distance ? <span> · {distance}</span> : null}
            </p>
          ) : (
            <p className="mt-1 text-ink-soft">Right around you — no destination needed.</p>
          )}
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Quest details">
            <li className="chip">{CATEGORY_LABEL[quest.category]}</li>
            <li className="chip">{RARITY_LABEL[quest.rarity]}</li>
            <li className="chip">
              <ClockIcon /> {quest.est_minutes} min
            </li>
            <li className="chip">
              <StarIcon /> +{quest.xp} XP · {SKILL_LABEL[quest.category]}
            </li>
          </ul>
          <p className="mt-3 text-lg">
            <strong>Objective:</strong> {quest.objective}
          </p>
          <p className="mt-1 text-ink-soft">Proof: {METHOD_LABEL[quest.verification.method]}</p>
        </div>
      </div>

      <div className="px-4 sm:px-5">
        <DmBubble persona={persona} text={quest.briefing} listenable={voice} questId={quest.id} kind="briefing" />
      </div>

      <div className="mx-4 mt-4 rounded-xl border-2 border-gold/60 bg-parchment-light p-3 sm:mx-5" role="note">
        <p>
          <strong>Safety:</strong> {quest.safety_note}
        </p>
        <p className="mt-1 text-ink-soft">{quest.off_screen_tip}</p>
      </div>

      <div className="flex flex-col gap-2 p-4 sm:flex-row sm:p-5">
        <button type="button" className="btn btn-moss flex-1 text-xl" onClick={onAccept} disabled={busy}>
          Accept Quest <ArrowRightIcon />
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={onReroll}
          disabled={busy || rerollsLeft === 0}
          aria-describedby="reroll-left"
        >
          Reroll
          <span id="reroll-left" className="text-sm text-ink-soft">
            ({rerollsLeft} left today)
          </span>
        </button>
        <button type="button" className="btn btn-ghost" onClick={onSkip} disabled={busy}>
          Skip
        </button>
      </div>
    </article>
  )
}
