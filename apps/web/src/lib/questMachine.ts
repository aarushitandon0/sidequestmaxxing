/**
 * Quest lifecycle state machine: idle → offered → accepted → verifying → completed.
 * Pure reducer; the provider persists the state to localStorage so Walk Mode survives
 * reloads, backgrounding and lost signal. Invalid transitions leave the state unchanged.
 */

import {
  heartbeat,
  onVisibility,
  restore,
  startTracking,
  stopTracking,
  type ScreenTime,
} from './screenTime'
import type { CompletionRequest, CompletionResult, Quest } from './types'

export type Phase = 'idle' | 'offered' | 'accepted' | 'verifying' | 'completed'

export interface QuestRun {
  phase: Phase
  quest: Quest | null
  acceptedAt: string | null // server accepted_at (ISO) — the Walk Mode timer source
  screen: ScreenTime | null
  pending: CompletionRequest | null // a completion waiting for the network
  result: CompletionResult | null
  finishedAt: number | null // epoch ms when the player said "I'm back"
}

export const IDLE: QuestRun = {
  phase: 'idle',
  quest: null,
  acceptedAt: null,
  screen: null,
  pending: null,
  result: null,
  finishedAt: null,
}

export type QuestEvent =
  | { type: 'offer'; quest: Quest }
  | { type: 'accept'; acceptedAt: string; now: number; visible: boolean }
  | { type: 'verify'; now: number }
  | { type: 'back' }
  | { type: 'queue'; payload: CompletionRequest }
  | { type: 'unqueue' }
  | { type: 'complete'; result: CompletionResult; now: number }
  | { type: 'visibility'; visible: boolean; now: number }
  | { type: 'beat'; now: number }
  | { type: 'restore'; now: number; visible: boolean }
  | { type: 'reset' }

const tracking = (s: QuestRun) => s.phase === 'accepted' || s.phase === 'verifying'

export function questReducer(s: QuestRun, e: QuestEvent): QuestRun {
  switch (e.type) {
    case 'offer':
      if (s.phase === 'idle' || s.phase === 'offered' || s.phase === 'completed') {
        return { ...IDLE, phase: 'offered', quest: e.quest }
      }
      return s
    case 'accept':
      if (s.phase !== 'offered') return s
      return {
        ...s,
        phase: 'accepted',
        acceptedAt: e.acceptedAt,
        screen: startTracking(e.now, e.visible),
      }
    case 'verify':
      if (s.phase !== 'accepted') return s
      return { ...s, phase: 'verifying', finishedAt: s.finishedAt ?? e.now }
    case 'back':
      return s.phase === 'verifying' && !s.pending ? { ...s, phase: 'accepted', finishedAt: null } : s
    case 'queue':
      return s.phase === 'verifying' ? { ...s, pending: e.payload } : s
    case 'unqueue':
      return { ...s, pending: null }
    case 'complete':
      if (s.phase !== 'verifying') return s
      return {
        ...s,
        phase: 'completed',
        result: e.result,
        pending: null,
        screen: s.screen ? stopTracking(s.screen, e.now) : null,
      }
    case 'visibility':
      return tracking(s) && s.screen ? { ...s, screen: onVisibility(s.screen, e.visible, e.now) } : s
    case 'beat':
      return tracking(s) && s.screen ? { ...s, screen: heartbeat(s.screen, e.now) } : s
    case 'restore':
      return tracking(s) && s.screen ? { ...s, screen: restore(s.screen, e.now, e.visible) } : s
    case 'reset':
      return IDLE
  }
}

/** Seconds since the quest was accepted (server timestamp), up to `end` (epoch ms). */
export function elapsedSeconds(run: QuestRun, end: number): number {
  if (!run.acceptedAt) return 0
  return Math.max(0, Math.floor((end - Date.parse(run.acceptedAt)) / 1000))
}

/** Validate a persisted run (old/corrupt storage must never crash Walk Mode). */
export function isQuestRun(v: unknown): v is QuestRun {
  if (!v || typeof v !== 'object') return false
  const r = v as Partial<QuestRun>
  const phases: Phase[] = ['idle', 'offered', 'accepted', 'verifying', 'completed']
  if (!r.phase || !phases.includes(r.phase)) return false
  if (r.phase !== 'idle' && (!r.quest || typeof r.quest.id !== 'string')) return false
  if ((r.phase === 'accepted' || r.phase === 'verifying') && (!r.acceptedAt || !r.screen)) return false
  return true
}
