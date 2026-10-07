import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api, ApiError, friendlyError } from '../lib/api'
import { DEMO_AREA, getCoarseLocation, type Coarse, type LocationError } from '../lib/location'
import type { Prefs } from '../lib/prefs'
import { buildQuestRequest, rememberRequest } from '../lib/questRequest'
import { readJson, writeJson } from '../lib/storage'
import { useQuest } from './QuestProvider'

export type LocationChoice = 'device' | 'demo'
const CHOICE_KEY = 'sqm.location_choice'

export type StartStatus = 'idle' | 'consent' | 'locating' | 'thinking' | 'error'

const LOCATION_MESSAGES: Record<LocationError, string> = {
  denied: "Location permission is off. You can allow it in your browser, or play in the demo area.",
  unavailable: "Couldn't find your position right now. Try again, or play in the demo area.",
  timeout: 'Finding your position took too long. Try again, or play in the demo area.',
  unsupported: "This browser can't share location. You can play in the demo area.",
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
      if (choice === 'demo') return generate(DEMO_AREA)
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

  return { status, error, rateLimited, start, withChoice, cancel: () => setStatus('idle') }
}
