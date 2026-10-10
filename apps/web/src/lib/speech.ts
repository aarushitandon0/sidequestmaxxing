/**
 * Browser speech (MASTERSPEC §2.4 fallback voice). The ElevenLabs voice (P13) tries the
 * server first and falls back here. The text is always also shown on screen.
 *
 * Each Dungeon Master gets a different system voice and its own pitch/rate, so the four
 * personas don't all read in the same flat default voice. Which voices exist depends on the
 * OS and browser, so we rank by name fragments and then hand out distinct voices.
 */

import type { Persona } from './types'

export interface PersonaVoice {
  /** Name fragments, best first: the names real systems ship (Windows/macOS/iOS/Android/Chrome). */
  prefer: readonly string[]
  rate: number
  pitch: number
}

/** Tuned to the PERSONA_INFO blurbs in lib/labels.ts. */
export const PERSONA_VOICE: Record<Persona, PersonaVoice> = {
  // Calm, friendly, a bit funny: warm and unhurried.
  chill: {
    prefer: ['samantha', 'aria', 'jenny', 'michelle', 'zira', 'nicky', 'karen', 'google us english'],
    rate: 0.95,
    pitch: 1.0,
  },
  // Over-the-top fantasy narrator: deep, slow, theatrical.
  dramatic: {
    prefer: ['daniel', 'george', 'arthur', 'guy', 'christopher', 'roger', 'alex', 'david', 'google uk english male'],
    rate: 0.82,
    pitch: 0.75,
  },
  // Delighted by trees and birds: bright and quick.
  nature_nerd: {
    prefer: ['sonia', 'libby', 'natasha', 'tessa', 'moira', 'emma', 'serena', 'ana', 'google uk english female'],
    rate: 1.08,
    pitch: 1.25,
  },
  // Dry humour: brisk, a little flat, slightly lower.
  sarcastic: {
    prefer: ['oliver', 'ryan', 'eric', 'steffan', 'rishi', 'thomas', 'mark', 'fred', 'google uk english male'],
    rate: 1.04,
    pitch: 0.9,
  },
}

const ORDER: readonly Persona[] = ['dramatic', 'nature_nerd', 'chill', 'sarcastic']

export function canSpeak(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

function englishVoices(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice[] {
  const en = voices.filter((v) => v.lang?.toLowerCase().startsWith('en'))
  return en.length ? en : voices
}

/**
 * One voice per persona, all different where the system has enough of them.
 * Deterministic: same voice list in, same assignment out.
 */
export function assignVoices(voices: SpeechSynthesisVoice[]): Partial<Record<Persona, SpeechSynthesisVoice>> {
  const pool = englishVoices(voices)
  const taken = new Set<SpeechSynthesisVoice>()
  const picked: Partial<Record<Persona, SpeechSynthesisVoice>> = {}
  // Most distinctive personas choose first, so a short voice list still sounds varied.
  for (const persona of ORDER) {
    const { prefer } = PERSONA_VOICE[persona]
    let best: SpeechSynthesisVoice | undefined
    let bestRank = Number.POSITIVE_INFINITY
    for (const voice of pool) {
      if (taken.has(voice)) continue
      const name = voice.name.toLowerCase()
      const rank = prefer.findIndex((fragment) => name.includes(fragment))
      if (rank >= 0 && rank < bestRank) {
        best = voice
        bestRank = rank
      }
    }
    // Nothing matched by name: take the next unused voice so two personas still differ.
    best ??= pool.find((v) => !taken.has(v))
    if (best) {
      taken.add(best)
      picked[persona] = best
    }
  }
  return picked
}

let cache: { voices: SpeechSynthesisVoice[]; picked: Partial<Record<Persona, SpeechSynthesisVoice>> } | null = null

function voiceFor(persona: Persona): SpeechSynthesisVoice | undefined {
  // getVoices() is empty until the list loads, so re-pick whenever it changes.
  const synth = window.speechSynthesis
  const voices = typeof synth.getVoices === 'function' ? synth.getVoices() : []
  if (!voices.length) return undefined
  if (!cache || cache.voices.length !== voices.length || cache.voices[0] !== voices[0]) {
    cache = { voices, picked: assignVoices(voices) }
  }
  return cache.picked[persona]
}

export function speak(text: string, persona: Persona = 'chill', onEnd?: () => void): boolean {
  if (!canSpeak()) return false
  const synth = window.speechSynthesis
  synth.cancel()
  const style = PERSONA_VOICE[persona] ?? PERSONA_VOICE.chill
  const u = new SpeechSynthesisUtterance(text)
  u.rate = style.rate
  u.pitch = style.pitch
  const voice = voiceFor(persona)
  if (voice) {
    u.voice = voice
    u.lang = voice.lang
  }
  u.onend = () => onEnd?.()
  u.onerror = () => onEnd?.()
  synth.speak(u)
  return true
}

export function stopSpeaking(): void {
  if (canSpeak()) window.speechSynthesis.cancel()
}
