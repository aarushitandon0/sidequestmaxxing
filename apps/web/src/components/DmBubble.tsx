import { useEffect, useRef, useState } from 'react'

import { canSpeak } from '../lib/speech'
import { canUseVoice, speakQuest, speakText, stopVoice, useVoiceState, type VoiceKind } from '../lib/voice'
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
  /** When set, Listen plays this quest's ElevenLabs audio (browser voice as fallback). */
  questId?: string
  kind?: VoiceKind
  /** Hide the small portrait when a big one is shown next to the bubble. */
  hidePortrait?: boolean
}

/** The Dungeon Master speaking: portrait + parchment speech bubble + Listen + waveform. */
export function DmBubble({ persona, text, speech, listenable = true, dark = false, size = 'md', hidePortrait = false, questId, kind = 'briefing' }: Props) {
  const voice = useVoiceState()
  const [mine, setMine] = useState(false)
  const [loading, setLoading] = useState(false)
  const mineRef = useRef(false)
  // Stop only what this bubble started (Accept starts the briefing and then leaves this page).
  useEffect(() => () => {
    if (mineRef.current) stopVoice()
  }, [])
  const playing = mine && (loading || voice.playing !== null)
  const finish = () => {
    mineRef.current = false
    setMine(false)
  }
  const portrait = size === 'lg' ? 'h-20 w-20 sm:h-24 sm:w-24' : 'h-16 w-16'

  const toggle = () => {
    if (playing) {
      stopVoice()
      setLoading(false)
      finish()
      return
    }
    mineRef.current = true
    setMine(true)
    setLoading(true)
    const words = speech ?? text
    const started = questId ? speakQuest({ questId, kind, text: words, onEnd: finish }) : speakText(words, finish)
    void started.then((source) => {
      setLoading(false)
      if (source === 'none') finish()
    })
  }

  return (
    <div className="flex items-end gap-3">
      {hidePortrait ? null : (
      <img
        src={PORTRAIT[persona]}
        alt={`${PERSONA_INFO[persona].name} Dungeon Master`}
        className={`${portrait} shrink-0 rounded-full border-[3px] border-parchment-light object-cover shadow-md`}
        width={96}
        height={96}
      />
      )}
      <div className={`bubble ${dark ? 'bubble-dark' : ''} min-w-0 flex-1`}>
        <p className="text-[1.05rem] leading-snug">{text}</p>
        {listenable && (questId ? canUseVoice() : canSpeak()) ? (
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
            <Waveform active={playing && !loading} className="min-w-0 overflow-hidden" />
            {loading ? <span className="sr-only" role="status">Getting the voice ready…</span> : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
