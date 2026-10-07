import { PERSONA_INFO } from '../lib/labels'
import { PERSONAS, type Persona } from '../lib/types'
import { PORTRAIT } from './art'
import { CheckIcon } from './Icons'

/** "Choose your Dungeon Master" 2×2 grid (design template). Radio-group semantics. */
export function PersonaPicker({
  value,
  onChange,
  wide = false,
  compact = false,
}: {
  value: Persona
  onChange: (p: Persona) => void
  /** Four across on large screens (onboarding). */
  wide?: boolean
  /** Smaller portraits (settings). */
  compact?: boolean
}) {
  return (
    <div role="radiogroup" aria-label="Dungeon Master" className={`grid grid-cols-2 gap-3 ${wide ? 'lg:grid-cols-4 lg:gap-4' : ''}`}>
      {PERSONAS.map((p) => {
        const selected = p === value
        return (
          <button
            key={p}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(p)}
            className={`parchment relative flex flex-col items-center px-2 pt-3 pb-3 text-center ${
              selected ? 'outline-3 outline-moss' : ''
            }`}
          >
            {selected ? (
              <span className="absolute top-2 right-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-moss text-parchment-light">
                <CheckIcon />
              </span>
            ) : null}
            <img src={PORTRAIT[p]} alt="" width={96} height={96} className={`rounded-full object-cover ${compact ? 'h-16 w-16 sm:h-20 sm:w-20' : 'h-20 w-20 sm:h-24 sm:w-24'} ${wide ? 'lg:h-32 lg:w-32' : ''}`} />
            <span className="mt-2 text-xl">{PERSONA_INFO[p].name}</span>
            <span className="text-[0.95rem] leading-snug text-ink-soft">{PERSONA_INFO[p].blurb}</span>
          </button>
        )
      })}
    </div>
  )
}
