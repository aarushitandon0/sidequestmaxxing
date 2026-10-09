import { afterEach, describe, expect, it, vi } from 'vitest'

import { QUEST } from '../test/fixtures'
import {
  appendFieldEntry,
  clearFieldLog,
  csvFilename,
  entryFor,
  FIELD_LOG_MAX,
  FIELD_STORAGE_KEY,
  localDate,
  readFieldLog,
  recordCompletion,
  toCsv,
  type FieldEntry,
} from './fieldLog'
import type { QuestRun } from './questMachine'
import type { CompletionResult } from './types'

const T0 = Date.parse('2026-10-07T18:30:00Z')

const entry = (over: Partial<FieldEntry> = {}): FieldEntry => ({
  quest_id: 'q1',
  date: '2026-10-07',
  category: 'naturalist',
  rarity: 'common',
  est_minutes: 15,
  elapsed_seconds: 1200,
  screen_seconds: 60,
  screen_share: 0.05,
  verification_method: 'photo',
  source: 'llm',
  voice: true,
  ...over,
})

const run = (over: Partial<QuestRun> = {}): QuestRun => ({
  phase: 'verifying',
  quest: { ...QUEST, source: 'llm' },
  acceptedAt: new Date(T0 - 1_200_000).toISOString(), // accepted 20 min ago
  screen: { visibleMs: 60_000, visibleSince: null, lastBeat: T0 },
  pending: null,
  result: null,
  finishedAt: T0,
  ...over,
})

const result = (over: Partial<CompletionResult> = {}): CompletionResult => ({
  quest_id: 'q1',
  xp_awarded: 42,
  level_ups: [],
  streak: 2,
  total_xp: 400,
  level: 3,
  within_radius: true,
  screen_share: 0.05,
  daily_cap_reached: false,
  ...over,
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('field log', () => {
  it('appends a row per completion and reads it back', () => {
    appendFieldEntry(entry())
    appendFieldEntry(entry({ quest_id: 'q2', category: 'foodie' }))
    expect(readFieldLog().map((e) => e.category)).toEqual(['naturalist', 'foodie'])
  })

  it('counts a quest once even if the offline queue reports it twice', () => {
    appendFieldEntry(entry({ elapsed_seconds: 1200 }))
    appendFieldEntry(entry({ elapsed_seconds: 1500 }))
    expect(readFieldLog()).toHaveLength(1)
    expect(readFieldLog()[0]?.elapsed_seconds).toBe(1500)
  })

  it('keeps the log bounded', () => {
    for (let i = 0; i < FIELD_LOG_MAX + 10; i++) appendFieldEntry(entry({ quest_id: `q${i}` }))
    const log = readFieldLog()
    expect(log).toHaveLength(FIELD_LOG_MAX)
    expect(log.at(-1)?.quest_id).toBe(`q${FIELD_LOG_MAX + 9}`)
  })

  it('survives corrupt or foreign storage', () => {
    localStorage.setItem(FIELD_STORAGE_KEY, 'not json')
    expect(readFieldLog()).toEqual([])
    localStorage.setItem(FIELD_STORAGE_KEY, JSON.stringify([{ nope: true }, entry()]))
    expect(readFieldLog()).toHaveLength(1)
  })

  it('never throws when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    expect(() => appendFieldEntry(entry())).not.toThrow()
  })

  it('clears without touching the rest of the game', () => {
    localStorage.setItem('sqm.prefs.v1', JSON.stringify({ voice: false }))
    appendFieldEntry(entry())
    clearFieldLog()
    expect(readFieldLog()).toEqual([])
    expect(localStorage.getItem('sqm.prefs.v1')).not.toBeNull()
  })
})

describe('building an entry from a run', () => {
  it('takes the seconds the server was actually told', () => {
    const e = entryFor(
      run({ pending: { verification: { method: 'honor' }, elapsed_seconds: 999, screen_seconds: 11 } }),
      result(),
      T0,
    )
    expect(e).toMatchObject({ elapsed_seconds: 999, screen_seconds: 11 })
  })

  it('derives the seconds from the run when nothing was queued', () => {
    const e = entryFor(run(), result(), T0)
    expect(e).toMatchObject({ elapsed_seconds: 1200, screen_seconds: 60 })
  })

  it('prefers the server screen share and falls back to the local ratio', () => {
    expect(entryFor(run(), result({ screen_share: 0.07 }), T0)?.screen_share).toBe(0.07)
    expect(entryFor(run(), result({ screen_share: null }), T0)?.screen_share).toBeCloseTo(0.05)
  })

  it('records the quest source, or null when the header was missing', () => {
    expect(entryFor(run(), result(), T0)?.source).toBe('llm')
    const noHeader = run({ quest: { ...QUEST, source: null } })
    expect(entryFor(noHeader, result(), T0)?.source).toBeNull()
  })

  it('records whether the voice was on', () => {
    localStorage.setItem('sqm.prefs.v1', JSON.stringify({ voice: false }))
    expect(entryFor(run(), result(), T0)?.voice).toBe(false)
  })

  it('holds no coordinates, place name, title or timestamp', () => {
    const e = entryFor(run(), result(), T0)
    const json = JSON.stringify(e)
    expect(json).not.toContain('18.52')
    expect(json).not.toContain('73.85')
    expect(json).not.toContain('Riverside')
    expect(json).not.toContain('Riverbank')
    expect(json).not.toContain('T18:30')
    expect(e?.date).toBe(localDate(T0))
  })

  it('ignores a run with no quest', () => {
    expect(entryFor(run({ quest: null }), result(), T0)).toBeNull()
    recordCompletion(run({ quest: null }), result(), T0)
    expect(readFieldLog()).toEqual([])
  })

  it('records a completion through the whole path', () => {
    recordCompletion(run(), result(), T0)
    expect(readFieldLog()).toHaveLength(1)
  })
})

describe('CSV', () => {
  it('writes the header even with no rows', () => {
    expect(toCsv([])).toBe(
      'date,category,rarity,est_minutes,elapsed_seconds,screen_seconds,screen_share,verification_method,source,voice\n',
    )
  })

  it('writes one line per entry, in column order, without the quest id', () => {
    const [header, row] = toCsv([entry()]).trim().split('\n')
    expect(header?.split(',')).toHaveLength(10)
    expect(row).toBe('2026-10-07,naturalist,common,15,1200,60,0.0500,photo,llm,true')
    expect(row).not.toContain('q1')
  })

  it('leaves a missing share empty rather than guessing', () => {
    expect(toCsv([entry({ screen_share: null })]).trim().split('\n')[1]).toContain(',,photo,')
  })

  it('quotes anything that could break a column', () => {
    const csv = toCsv([entry({ source: 'we"ird,value' })])
    expect(csv).toContain('"we""ird,value"')
  })

  it('names the file after the dates it covers', () => {
    expect(csvFilename([entry()])).toBe('sidequest-field-2026-10-07.csv')
    expect(csvFilename([entry(), entry({ quest_id: 'q2', date: '2026-10-09' })])).toBe(
      'sidequest-field-2026-10-07_2026-10-09.csv',
    )
    expect(csvFilename([], T0)).toBe(`sidequest-field-${localDate(T0)}.csv`)
  })
})
