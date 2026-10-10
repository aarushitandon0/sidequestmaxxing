import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api, ApiError, friendlyError } from '../lib/api'
import { findCity } from '../lib/cities'
import { coarse, DEMO_AREA, getCoarseLocation, type Coarse, type LocationError } from '../lib/location'
import type { Prefs } from '../lib/prefs'
import { buildQuestRequest, rememberRequest } from '../lib/questRequest'
import { readJson, writeJson } from '../lib/storage'
import { useQuest } from './QuestProvider'

/**
 * How the player wants their position decided. `city:<slug>` picks a seeded city centre
 * (P24); `demo` is the old stored value for Pune and is still honoured so an existing
 * device does not get asked again after an update.
 */
export type LocationChoice = 'device' | 'demo' | `city:${string}`
const CHOICE_KEY = 'sqm.location_choice'

function chosenArea(choice: Exclude<LocationChoice, 'device'>): Coarse {
  if (choice === 'demo') return DEMO_AREA
  const city = findCity(choice.slice('city:'.length))
  // An unknown slug means a stored choice outlived the city list; Pune is the safe landing.
  return city ? coarse(city.lat, city.lng) : DEMO_AREA
}

export type StartStatus = 'idle' | 'consent' | 'locating' | 'thinking' | 'error'

const LOCATION_MESSAGES: Record<LocationError, string> = {
  denied: 'Location permission is off. You can allow it in your browser, or pick a city to play in.',
  unavailable: "Couldn't find your position right now. Try again, or pick a city to play in.",
  timeout: 'Finding your position took too long. Try again, or pick a city to play in.',
  unsupported: "This browser can't share location, so pick a city to play in.",
}

/** Get a quest: just-in-time location consent → coarse position → POST /generate. */
export function useStartQuest(prefs: Prefs) {
  const { offer } = useQuest()
  const navigate = useNavigate()
  const [status, setStatus] = useState<StartStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [rateLimited, setRateLimited] = useState(false)

  const generate = useCallback(
    async (where: Coarse) => {
      setStatus('thinking')
      setError(null)
      setRateLimited(false)
      const req = buildQuestRequest(where, prefs)
      try {
        const quest = await api.generateQuest(req)
        rememberRequest(req)
        offer(quest)
        setStatus('idle')
        navigate('/quest')
      } catch (err) {
        setRateLimited(err instanceof ApiError && err.status === 429)
        setError(friendlyError(err))
        setStatus('error')
      }
    },
    [prefs, offer, navigate],
  )

  const withChoice = useCallback(
    async (choice: LocationChoice) => {
      writeJson(CHOICE_KEY, choice)
      if (choice !== 'device') return generate(chosenArea(choice))
      setStatus('locating')
      try {
        return await generate(await getCoarseLocation())
      } catch (code) {
        setError(LOCATION_MESSAGES[(code as LocationError) ?? 'unavailable'] ?? LOCATION_MESSAGES.unavailable)
        setStatus('error')
      }
    },
    [generate],
  )

  const start = useCallback(() => {
    const choice = readJson<LocationChoice>(CHOICE_KEY)
    if (!choice) {
      setStatus('consent')
      return
    }
    void withChoice(choice)
  }, [withChoice])

  // Back to the chooser after a failure, so "pick a city instead" is one tap and not a
  // forced trip through the demo area.
  const pickAgain = useCallback(() => {
    setError(null)
    setStatus('consent')
  }, [])

  return { status, error, rateLimited, start, withChoice, pickAgain, cancel: () => setStatus('idle') }
}
