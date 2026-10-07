import type { Persona } from '../lib/types'
import { PORTRAIT } from './art'
import { Waveform } from './Waveform'

export function Thinking({ persona, label = 'The Dungeon Master is thinking…' }: { persona: Persona; label?: string }) {
  return (
    <div role="status" aria-live="polite" className="parchment flex items-center gap-4 p-4">
      <img src={PORTRAIT[persona]} alt="" className="h-16 w-16 rounded-full border-2 border-edge object-cover" />
      <div>
        <p className="text-xl">{label}</p>
        <span className="text-moss">
          <Waveform />
        </span>
      </div>
    </div>
  )
}
