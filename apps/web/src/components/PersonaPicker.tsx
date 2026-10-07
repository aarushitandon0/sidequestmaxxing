import { PERSONA_INFO } from '../lib/labels'
import { PERSONAS, type Persona } from '../lib/types'
import { PORTRAIT } from './art'
import { CheckIcon } from './Icons'

/** "Choose your Dungeon Master" 2×2 grid (design template). Radio-group semantics. */
export function PersonaPicker({ value, onChange }: { value: Persona; onChange: (p: Persona) => void }) {
  return (
    <div role="radiogroup" aria-label="Dungeon Master" className="grid grid-cols-2 gap-3">
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
            <img src={PORTRAIT[p]} alt="" width={96} height={96} className="h-20 w-20 rounded-full object-cover sm:h-24 sm:w-24" />
            <span className="mt-2 text-xl">{PERSONA_INFO[p].name}</span>
            <span className="text-[0.95rem] leading-snug text-ink-soft">{PERSONA_INFO[p].blurb}</span>
          </button>
        )
      })}
    </div>
  )
}
