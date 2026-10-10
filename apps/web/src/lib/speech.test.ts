/** Each Dungeon Master gets its own system voice and delivery (not one flat default voice). */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PERSONA_VOICE, assignVoices, speak } from './speech'
import type { Persona } from './types'

const voice = (name: string, lang = 'en-US') => ({ name, lang }) as SpeechSynthesisVoice

// A typical Windows + Chrome list, plus a couple of macOS/iOS names.
const VOICES = [
  voice('Microsoft David - English (United States)'),
  voice('Microsoft Zira - English (United States)'),
  voice('Google UK English Male', 'en-GB'),
  voice('Microsoft Sonia Online (Natural) - English (United Kingdom)', 'en-GB'),
  voice('Daniel', 'en-GB'),
  voice('Samantha'),
  voice('Microsoft Haruka - Japanese', 'ja-JP'),
]

const PERSONAS: Persona[] = ['chill', 'dramatic', 'nature_nerd', 'sarcastic']

interface Spoken {
  text: string
  rate: number
  pitch: number
  voice: SpeechSynthesisVoice | null
}

function stubSynth(voices: SpeechSynthesisVoice[]): Spoken[] {
  const spoken: Spoken[] = []
  vi.stubGlobal('speechSynthesis', {
    cancel: vi.fn(),
    getVoices: () => voices,
    speak: (u: Spoken) => spoken.push(u),
  })
  vi.stubGlobal('SpeechSynthesisUtterance', class {
    onend: (() => void) | null = null
    onerror: (() => void) | null = null
    rate = 1
    pitch = 1
    lang = ''
    voice: SpeechSynthesisVoice | null = null
    constructor(public text: string) {}
  })
  return spoken
}

afterEach(() => vi.unstubAllGlobals())

describe('persona voices', () => {
  it('gives each persona a different voice', () => {
    const picked = assignVoices(VOICES)
    const names = PERSONAS.map((p) => picked[p]?.name)
    expect(names.every(Boolean)).toBe(true)
    expect(new Set(names).size).toBe(PERSONAS.length)
  })

  it('never picks a non-English voice when English ones exist', () => {
    const picked = assignVoices(VOICES)
    for (const p of PERSONAS) expect(picked[p]?.lang.startsWith('en')).toBe(true)
  })

  it('matches names by preference: dramatic takes Daniel, nature nerd takes Sonia', () => {
    const picked = assignVoices(VOICES)
    expect(picked.dramatic?.name).toBe('Daniel')
    expect(picked.nature_nerd?.name).toContain('Sonia')
    expect(picked.chill?.name).toBe('Samantha')
  })

  it('still differs with a one-voice system (pitch and rate carry the persona)', () => {
    const only = [voice('Microsoft David - English (United States)')]
    const spoken = stubSynth(only)
    for (const p of PERSONAS) speak('Go outside.', p)
    const rates = new Set(spoken.map((s) => s.rate))
    const pitches = new Set(spoken.map((s) => s.pitch))
    expect(rates.size).toBeGreaterThan(1)
    expect(pitches.size).toBeGreaterThan(1)
  })

  it('speaks with the persona voice, rate and pitch', () => {
    const spoken = stubSynth(VOICES)
    expect(speak('Hark, traveller.', 'dramatic')).toBe(true)
    expect(spoken).toHaveLength(1)
    const [first] = spoken
    expect(first?.text).toBe('Hark, traveller.')
    expect(first?.rate).toBe(PERSONA_VOICE.dramatic.rate)
    expect(first?.pitch).toBe(PERSONA_VOICE.dramatic.pitch)
    expect(first?.voice?.name).toBe('Daniel')
  })

  it('works when the browser has no voice list yet', () => {
    const spoken = stubSynth([])
    expect(speak('Still speaks.', 'chill')).toBe(true)
    expect(spoken[0]?.voice).toBeNull()
    expect(spoken[0]?.rate).toBe(PERSONA_VOICE.chill.rate)
  })
})
