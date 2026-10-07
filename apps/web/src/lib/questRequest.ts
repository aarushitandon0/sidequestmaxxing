import type { Coarse } from './location'
import type { Prefs } from './prefs'
import { readJson, writeJson } from './storage'
import { localTimeIso } from './time'
import type { QuestRequest } from './types'

const LAST = 'sqm.last_request.v1'

/** Only sanitizable keywords and enums go to the API; the server re-sanitizes anyway. */
export function buildQuestRequest(where: Coarse, prefs: Prefs, now: Date = new Date()): QuestRequest {
  return {
    lat: where.lat,
    lng: where.lng,
    minutes_available: prefs.minutes,
    radius_m: prefs.radiusM,
    mood: prefs.mood,
    interests: prefs.interests.slice(0, 6),
    persona: prefs.persona,
    mode: 'walk',
    local_time_iso: localTimeIso(now),
  }
}

/** Kept on this device only, so Reroll can ask again without re-reading location. */
export function rememberRequest(req: QuestRequest): void {
  writeJson(LAST, req)
}

export function lastRequest(): QuestRequest | null {
  return readJson<QuestRequest>(LAST)
}
