import { useEffect, useState } from 'react'

import { speak, stopSpeaking, canSpeak } from '../lib/speech'
import type { Persona } from '../lib/types'
import { PERSONA_INFO } from '../lib/labels'
import { PORTRAIT } from './art'
import { PlayIcon, StopIcon } from './Icons'
import { Waveform } from './Waveform'

interface Props {
  persona: Persona
  text: string
  /** Text read aloud by Listen (defaults to `text`). The text is always shown too. */
  speech?: string
  listenable?: boolean
  dark?: boolean
  size?: 'md' | 'lg'
}

/** The Dungeon Master speaking: portrait + parchment speech bubble + Listen + waveform. */
export function DmBubble({ persona, text, speech, listenable = true, dark = false, size = 'md' }: Props) {
  const [playing, setPlaying] = useState(false)
  useEffect(() => () => stopSpeaking(), [])
  const portrait = size === 'lg' ? 'h-24 w-24' : 'h-16 w-16'

  const toggle = () => {
    if (playing) {
      stopSpeaking()
      setPlaying(false)
      return
    }
    if (speak(speech ?? text, () => setPlaying(false))) setPlaying(true)
  }

  return (
    <div className="flex items-end gap-3">
      <img
        src={PORTRAIT[persona]}
        alt={`${PERSONA_INFO[persona].name} Dungeon Master`}
        className={`${portrait} shrink-0 rounded-full border-[3px] border-parchment-light object-cover shadow-md`}
        width={96}
        height={96}
      />
      <div className={`bubble ${dark ? 'bubble-dark' : ''} flex-1`}>
        <p className="text-[1.05rem] leading-snug">{text}</p>
        {listenable && canSpeak() ? (
          <div className="mt-1 flex items-center gap-3 text-moss">
            <button
              type="button"
              onClick={toggle}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-moss text-parchment-light"
              aria-label={playing ? 'Stop the Dungeon Master' : 'Listen to the Dungeon Master'}
              aria-pressed={playing}
            >
              {playing ? <StopIcon /> : <PlayIcon />}
            </button>
            <Waveform active={playing} />
          </div>
        ) : null}
      </div>
    </div>
  )
}
