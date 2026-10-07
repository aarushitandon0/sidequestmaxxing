import { useSyncExternalStore } from 'react'

import { API_BASE_URL } from './api'
import { getDeviceId } from './device'
import { canSpeak, speak, stopSpeaking } from './speech'

/**
 * The Dungeon Master's voice (MASTERSPEC §2.4, P13). Order of preference:
 *   1. a pre-generated demo clip (public/demo-audio, matched by the text's SHA-256),
 *   2. ElevenLabs audio cached on this device (Cache Storage, per quest/recap id + kind),
 *   3. POST /v1/tts (server picks the text from the quest or recap — we never send text),
 *   4. the browser's speechSynthesis with the same text.
 * The text is always on screen too. Any failure silently falls through to the next step.
 */

export type VoiceKind = 'briefing' | 'hint' | 'recap'
export type VoiceSource = 'demo' | 'cache' | 'elevenlabs' | 'browser' | 'none'

export interface SpeakQuestOptions {
  /** The quest id, or the recap id when kind is 'recap'. */
  questId: string
  kind?: VoiceKind
  text: string
  onEnd?: () => void
}

const CACHE_NAME = 'sqm-voice-v1'
const TTS_TIMEOUT_MS = 8000

// ---------------------------------------------------------------- playing state (one voice at a time)

interface VoiceState {
  playing: string | null // `${questId}:${kind}` or 'browser'
}

let state: VoiceState = { playing: null }
let current: { audio: HTMLAudioElement; url: string | null } | null = null
let token = 0
const listeners = new Set<() => void>()

function setState(next: VoiceState) {
  state = next
  for (const l of listeners) l()
}

export function useVoiceState(): VoiceState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => state,
    () => state,
  )
}

export function stopVoice(): void {
  token++
  if (current) {
    current.audio.pause()
    if (current.url) URL.revokeObjectURL(current.url)
    current = null
  }
  stopSpeaking()
  if (state.playing) setState({ playing: null })
}

// ---------------------------------------------------------------- sources

let manifest: Promise<Record<string, string>> | null = null

async function sha256Hex(text: string): Promise<string | null> {
  try {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
    return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
  } catch {
    return null
  }
}

async function demoClip(text: string): Promise<string | null> {
  manifest ??= fetch('/demo-audio/manifest.json')
    .then(async (r): Promise<Record<string, string>> => {
      if (!r.ok) return {}
      const m = (await r.json()) as { clips?: Record<string, string> }
      return m.clips ?? {}
    })
    .catch((): Record<string, string> => ({}))
  const clips = await manifest
  if (!Object.keys(clips).length) return null
  const hash = await sha256Hex(text)
  const file = hash ? clips[hash] : undefined
  return file && /^[\w.-]+\.mp3$/.test(file) ? `/demo-audio/${file}` : null
}

const cacheKey = (questId: string, kind: VoiceKind) =>
  `/__voice/${encodeURIComponent(questId)}/${kind}`

async function openCache(): Promise<Cache | null> {
  try {
    return typeof caches === 'undefined' ? null : await caches.open(CACHE_NAME)
  } catch {
    return null
  }
}

async function cachedAudio(questId: string, kind: VoiceKind): Promise<ArrayBuffer | null> {
  const cache = await openCache()
  const hit = await cache?.match(cacheKey(questId, kind)).catch(() => undefined)
  return hit ? hit.arrayBuffer() : null
}

/** Asks the server for this quest's (or recap's) audio. Only ids + kind are sent — never text. */
async function fetchAudio(questId: string, kind: VoiceKind): Promise<ArrayBuffer | null> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TTS_TIMEOUT_MS)
  try {
    const res = await fetch(`${API_BASE_URL}/v1/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device-Id': getDeviceId() },
      body: JSON.stringify(kind === 'recap' ? { recap_id: questId, kind } : { quest_id: questId, kind }),
      signal: ctrl.signal,
    })
    if (!res.ok || !(res.headers.get('Content-Type') ?? '').startsWith('audio/')) return null
    const buf = await res.arrayBuffer()
    if (!buf.byteLength) return null
    const cache = await openCache()
    await cache
      ?.put(cacheKey(questId, kind), new Response(buf.slice(0), { headers: { 'Content-Type': 'audio/mpeg' } }))
      .catch(() => undefined)
    return buf
  } catch {
    return null // offline, timeout, CORS — browser voice takes over
  } finally {
    clearTimeout(timer)
  }
}

// ---------------------------------------------------------------- playback

async function playUrl(url: string, revoke: boolean, key: string, my: number, onEnd?: () => void): Promise<boolean> {
  if (my !== token) return true // superseded by a newer request: nothing to do
  const audio = new Audio(url)
  current = { audio, url: revoke ? url : null }
  const done = () => {
    if (current?.audio !== audio) return
    if (revoke) URL.revokeObjectURL(url)
    current = null
    setState({ playing: null })
    onEnd?.()
  }
  audio.onended = done
  try {
    await audio.play()
    setState({ playing: key })
    return true
  } catch {
    // Autoplay blocked or undecodable: clean up and let the browser voice speak instead.
    if (current?.audio === audio) current = null
    if (revoke) URL.revokeObjectURL(url)
    return false
  }
}

function browserVoice(text: string, onEnd?: () => void): VoiceSource {
  const ok = speak(text, () => {
    setState({ playing: null })
    onEnd?.()
  })
  if (ok) setState({ playing: 'browser' })
  return ok ? 'browser' : 'none'
}

export async function speakQuest({ questId, kind = 'briefing', text, onEnd }: SpeakQuestOptions): Promise<VoiceSource> {
  stopVoice()
  const my = token
  const key = `${questId}:${kind}`

  const demo = await demoClip(text)
  if (demo && (await playUrl(demo, false, key, my, onEnd))) return 'demo'

  const cached = await cachedAudio(questId, kind)
  const buf = cached ?? (await fetchAudio(questId, kind))
  if (my !== token) return 'none' // stopped while we were fetching
  if (buf) {
    const url = URL.createObjectURL(new Blob([buf], { type: 'audio/mpeg' }))
    if (await playUrl(url, true, key, my, onEnd)) return cached ? 'cache' : 'elevenlabs'
  }
  if (my !== token) return 'none'
  return browserVoice(text, onEnd)
}

/** Lines with no quest behind them (greetings, the story demo): demo clip, else browser voice. */
export async function speakText(text: string, onEnd?: () => void): Promise<VoiceSource> {
  stopVoice()
  const my = token
  const demo = await demoClip(text)
  if (demo && (await playUrl(demo, false, 'text', my, onEnd))) return 'demo'
  if (my !== token) return 'none'
  return browserVoice(text, onEnd)
}

export function canUseVoice(): boolean {
  return canSpeak() || typeof Audio !== 'undefined'
}

/** "Delete my data": drop cached voice audio too. */
export async function clearVoiceCache(): Promise<void> {
  stopVoice()
  try {
    if (typeof caches !== 'undefined') await caches.delete(CACHE_NAME)
  } catch {
    // storage blocked: nothing cached
  }
}
