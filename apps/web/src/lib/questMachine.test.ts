import { describe, expect, it } from 'vitest'

import { IDLE, elapsedSeconds, questReducer, type QuestEvent, type QuestRun } from './questMachine'
import { visibleSeconds } from './screenTime'
import { QUEST } from '../test/fixtures'
import type { CompletionResult } from './types'

const RESULT: CompletionResult = {
  quest_id: 'q1',
  xp_awarded: 36,
  level_ups: [],
  streak: 1,
  total_xp: 36,
  level: 0,
  within_radius: null,
  screen_share: 0.04,
  daily_cap_reached: false,
}

const run = (events: QuestEvent[], start: QuestRun = IDLE) => events.reduce(questReducer, start)
const T0 = Date.parse('2026-10-07T10:00:00Z')

describe('quest state machine', () => {
  it('walks the happy path idle → offered → accepted → verifying → completed', () => {
    const s = run([
      { type: 'offer', quest: QUEST },
      { type: 'accept', acceptedAt: '2026-10-07T10:00:00Z', now: T0, visible: true },
      { type: 'visibility', visible: false, now: T0 + 3000 },
      { type: 'visibility', visible: true, now: T0 + 900_000 },
      { type: 'verify', now: T0 + 900_000 },
      { type: 'complete', result: RESULT, now: T0 + 960_000 },
    ])
    expect(s.phase).toBe('completed')
    expect(s.result).toEqual(RESULT)
    expect(visibleSeconds(s.screen!, T0 + 2_000_000)).toBe(63)
    expect(s.finishedAt).toBe(T0 + 900_000)
  })

  it.each<[QuestRun['phase'], QuestEvent]>([
    ['idle', { type: 'accept', acceptedAt: 'x', now: 0, visible: true }],
    ['idle', { type: 'verify', now: 0 }],
    ['idle', { type: 'complete', result: RESULT, now: 0 }],
  ])('rejects invalid transition from %s', (phase, event) => {
    const start = { ...IDLE, phase }
    expect(questReducer(start, event)).toBe(start)
  })

  it('cannot offer a new quest while one is active', () => {
    const active = run([
      { type: 'offer', quest: QUEST },
      { type: 'accept', acceptedAt: '2026-10-07T10:00:00Z', now: T0, visible: true },
    ])
    expect(questReducer(active, { type: 'offer', quest: { ...QUEST, id: 'q2' } })).toBe(active)
  })

  it('can go back from verifying unless a completion is queued', () => {
    const verifying = run([
      { type: 'offer', quest: QUEST },
      { type: 'accept', acceptedAt: '2026-10-07T10:00:00Z', now: T0, visible: true },
      { type: 'verify', now: T0 + 1000 },
    ])
    expect(questReducer(verifying, { type: 'back' }).phase).toBe('accepted')
    const queued = questReducer(verifying, {
      type: 'queue',
      payload: { verification: { method: 'honor' }, elapsed_seconds: 1, screen_seconds: 0 },
    })
    expect(queued.pending).not.toBeNull()
    expect(questReducer(queued, { type: 'back' })).toBe(queued)
  })

  it('reroll replaces an offered quest; reset clears everything', () => {
    const s = run([
      { type: 'offer', quest: QUEST },
      { type: 'offer', quest: { ...QUEST, id: 'q2' } },
    ])
    expect(s.quest?.id).toBe('q2')
    expect(questReducer(s, { type: 'reset' })).toEqual(IDLE)
  })

  it('stops counting screen time after completion', () => {
    const s = run([
      { type: 'offer', quest: QUEST },
      { type: 'accept', acceptedAt: '2026-10-07T10:00:00Z', now: T0, visible: true },
      { type: 'verify', now: T0 + 10_000 },
      { type: 'complete', result: RESULT, now: T0 + 20_000 },
      { type: 'visibility', visible: true, now: T0 + 999_000 },
    ])
    expect(visibleSeconds(s.screen!, T0 + 5_000_000)).toBe(20)
  })

  it('elapsed is computed from the server accepted_at', () => {
    const s = run([
      { type: 'offer', quest: QUEST },
      { type: 'accept', acceptedAt: '2026-10-07T10:00:00Z', now: T0, visible: true },
    ])
    expect(elapsedSeconds(s, T0 + 125_500)).toBe(125)
    expect(elapsedSeconds(IDLE, T0)).toBe(0)
  })
})
