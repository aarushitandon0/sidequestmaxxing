import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from 'react'

import { api, ApiError } from '../lib/api'
import { recordCompletion } from '../lib/fieldLog'
import { markJournalUnlocked } from '../lib/journal'
import { IDLE, isQuestRun, questReducer, type QuestRun } from '../lib/questMachine'
import { HEARTBEAT_MS } from '../lib/screenTime'
import { readJson, writeJson } from '../lib/storage'
import type { CompletionRequest, CompletionResult, Quest } from '../lib/types'

export const QUEST_STORAGE_KEY = 'sqm.quest.v1'

const isVisible = () => typeof document === 'undefined' || document.visibilityState === 'visible'

interface QuestApi {
  run: QuestRun
  offer: (quest: Quest) => void
  accept: (acceptedAt: string) => void
  startVerify: () => void
  back: () => void
  queue: (payload: CompletionRequest) => void
  complete: (result: CompletionResult) => void
  reset: () => void
}

const Ctx = createContext<QuestApi | null>(null)

function load(): QuestRun {
  const stored = readJson<unknown>(QUEST_STORAGE_KEY)
  return isQuestRun(stored) ? stored : IDLE
}

/**
 * Owns the active quest: persisted to localStorage (Walk Mode survives reloads/offline),
 * tracks visible screen seconds while a quest runs, and retries a queued completion when
 * the device is back online (verification works offline; the reward is claimed later).
 */
export function QuestProvider({ children }: { children: ReactNode }) {
  const [run, dispatch] = useReducer(questReducer, undefined, load)
  // The offline-retry effect completes a quest from a closure that predates the current run.
  const runRef = useRef(run)
  useEffect(() => {
    runRef.current = run
  }, [run])

  useEffect(() => {
    dispatch({ type: 'restore', now: Date.now(), visible: isVisible() })
  }, [])

  useEffect(() => {
    writeJson(QUEST_STORAGE_KEY, run)
  }, [run])

  const tracking = run.phase === 'accepted' || run.phase === 'verifying'
  useEffect(() => {
    if (!tracking) return
    const onVis = () => dispatch({ type: 'visibility', visible: isVisible(), now: Date.now() })
    const onHide = () => dispatch({ type: 'visibility', visible: false, now: Date.now() })
    document.addEventListener('visibilitychange', onVis)
    window.addEventListener('pagehide', onHide)
    const beat = window.setInterval(() => {
      if (isVisible()) dispatch({ type: 'beat', now: Date.now() })
    }, HEARTBEAT_MS)
    return () => {
      document.removeEventListener('visibilitychange', onVis)
      window.removeEventListener('pagehide', onHide)
      window.clearInterval(beat)
    }
  }, [tracking])

  // Offline queue: claim the reward as soon as the network is back.
  const pending = run.phase === 'verifying' ? run.pending : null
  const questId = run.quest?.id
  useEffect(() => {
    if (!pending || !questId) return
    let cancelled = false
    const attempt = async () => {
      if (typeof navigator !== 'undefined' && navigator.onLine === false) return
      try {
        const result = await api.completeQuest(questId, pending)
        if (!cancelled) {
          recordCompletion(runRef.current, result)
          markJournalUnlocked()
          dispatch({ type: 'complete', result, now: Date.now() })
        }
      } catch (err) {
        if (!cancelled && err instanceof ApiError && !err.isNetwork) dispatch({ type: 'unqueue' })
      }
    }
    void attempt()
    window.addEventListener('online', attempt)
    const timer = window.setInterval(attempt, 30_000)
    return () => {
      cancelled = true
      window.removeEventListener('online', attempt)
      window.clearInterval(timer)
    }
  }, [pending, questId])

  const offer = useCallback((quest: Quest) => dispatch({ type: 'offer', quest }), [])
  const accept = useCallback(
    (acceptedAt: string) => dispatch({ type: 'accept', acceptedAt, now: Date.now(), visible: isVisible() }),
    [],
  )
  const startVerify = useCallback(() => dispatch({ type: 'verify', now: Date.now() }), [])
  const back = useCallback(() => dispatch({ type: 'back' }), [])
  const queue = useCallback((payload: CompletionRequest) => dispatch({ type: 'queue', payload }), [])
  const complete = useCallback((result: CompletionResult) => {
    // Field log first: the reducer stops the screen timer and clears `pending`.
    recordCompletion(runRef.current, result)
    // First finished quest unlocks the Journal, offline included.
    markJournalUnlocked()
    dispatch({ type: 'complete', result, now: Date.now() })
  }, [])
  const reset = useCallback(() => dispatch({ type: 'reset' }), [])

  const value = useMemo(
    () => ({ run, offer, accept, startVerify, back, queue, complete, reset }),
    [run, offer, accept, startVerify, back, queue, complete, reset],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useQuest(): QuestApi {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useQuest must be used inside <QuestProvider>')
  return ctx
}
