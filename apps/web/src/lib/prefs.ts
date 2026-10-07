import { readJson, writeJson } from './storage'
import type { Mood, Persona } from './types'

/** Player preferences set during onboarding. Stored locally; mirrored to the API best-effort. */
export interface Prefs {
  onboarded: boolean
  persona: Persona
  interests: string[]
  radiusM: number
  voice: boolean
  safetyAck: boolean
  minutes: number
  mood: Mood
}

const KEY = 'sqm.prefs.v1'

export const DEFAULT_PREFS: Prefs = {
  onboarded: false,
  persona: 'chill',
  interests: [],
  radiusM: 2500,
  voice: true,
  safetyAck: false,
  minutes: 45,
  mood: 'curious',
}

export function loadPrefs(): Prefs {
  return { ...DEFAULT_PREFS, ...(readJson<Partial<Prefs>>(KEY) ?? {}) }
}

export function savePrefs(update: Partial<Prefs>): Prefs {
  const next = { ...loadPrefs(), ...update }
  writeJson(KEY, next)
  return next
}

export const INTEREST_OPTIONS = [
  'birds',
  'trees',
  'history',
  'street food',
  'architecture',
  'art',
  'sketching',
  'coffee',
  'markets',
  'running',
  'quiet spots',
  'geology',
] as const

export const RADIUS_OPTIONS = [
  { value: 1000, label: '1 km' },
  { value: 2500, label: '2.5 km' },
  { value: 5000, label: '5 km' },
] as const

export const MINUTE_OPTIONS = [20, 45, 90] as const
