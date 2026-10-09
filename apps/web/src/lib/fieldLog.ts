/**
 * Field-test log (MASTERSPEC §2.3, P21).
 *
 * The honest numbers for the write-up — how long quests actually took, how much of that time
 * the phone was awake — can only be measured in the field, and the API deliberately does not
 * return enough of a completion to reconstruct them. So each finished quest appends one row
 * here, in this browser only: no coordinates, no place names, no photos, no network. The
 * player exports it as CSV from /settings/export and feeds it to scripts/summarize_field.py.
 *
 * Nothing in the game reads this log; deleting it loses nothing but the field test.
 */

import { elapsedSeconds, type QuestRun } from './questMachine'
import { loadPrefs } from './prefs'
import { visibleSeconds } from './screenTime'
import { readJson, writeJson, removeKey } from './storage'
import type { Category, CompletionResult, Rarity, VerificationMethod } from './types'

export const FIELD_STORAGE_KEY = 'sqm.field.v1'
/** A field test is days, not years: keep the log bounded so storage can never fill up. */
export const FIELD_LOG_MAX = 500

export interface FieldEntry {
  /** Kept for de-duplication (the offline queue can report one completion twice). */
  quest_id: string
  /** Local calendar date, YYYY-MM-DD — never a timestamp, which pins down a routine. */
  date: string
  category: Category
  rarity: Rarity
  est_minutes: number
  elapsed_seconds: number
  screen_seconds: number
  /** Server-computed where available (it owns the number that pays the XP bonus). */
  screen_share: number | null
  verification_method: VerificationMethod
  /** 'llm' | 'fallback' from the X-Quest-Source header; null if the header was missing. */
  source: string | null
  /** Voice narration on at completion time — the "% voice-first" line in the summary. */
  voice: boolean
}

/** The CSV header, and the column order of every row. `quest_id` is deliberately not in it. */
export const FIELD_COLUMNS = [
  'date',
  'category',
  'rarity',
  'est_minutes',
  'elapsed_seconds',
  'screen_seconds',
  'screen_share',
  'verification_method',
  'source',
  'voice',
] as const

const isEntry = (v: unknown): v is FieldEntry => {
  if (!v || typeof v !== 'object') return false
  const e = v as Partial<FieldEntry>
  return typeof e.quest_id === 'string' && typeof e.date === 'string' && typeof e.category === 'string'
}

export function readFieldLog(): FieldEntry[] {
  const raw = readJson<unknown>(FIELD_STORAGE_KEY)
  return Array.isArray(raw) ? raw.filter(isEntry) : []
}

export function clearFieldLog(): void {
  removeKey(FIELD_STORAGE_KEY)
}

/** Appends one row, replacing any earlier row for the same quest. Never throws. */
export function appendFieldEntry(entry: FieldEntry): FieldEntry[] {
  const kept = readFieldLog().filter((e) => e.quest_id !== entry.quest_id)
  const next = [...kept, entry].slice(-FIELD_LOG_MAX)
  writeJson(FIELD_STORAGE_KEY, next)
  return next
}

/** Local YYYY-MM-DD (not UTC: a 1 a.m. quest belongs to the day the player had). */
export function localDate(now: number): string {
  const d = new Date(now)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/**
 * Builds the row for a completion. `run` is the state *before* the complete event, so the
 * screen timer is still running and `pending` holds what was actually sent to the server.
 */
export function entryFor(run: QuestRun, result: CompletionResult, now: number): FieldEntry | null {
  const quest = run.quest
  if (!quest) return null
  const elapsed = run.pending?.elapsed_seconds ?? elapsedSeconds(run, run.finishedAt ?? now)
  const screen = run.pending?.screen_seconds ?? (run.screen ? visibleSeconds(run.screen, now) : 0)
  return {
    quest_id: result.quest_id || quest.id,
    date: localDate(now),
    category: quest.category,
    rarity: quest.rarity,
    est_minutes: quest.est_minutes,
    elapsed_seconds: elapsed,
    screen_seconds: screen,
    screen_share: result.screen_share ?? (elapsed > 0 ? screen / elapsed : null),
    verification_method: quest.verification.method,
    source: quest.source ?? null,
    voice: loadPrefs().voice,
  }
}

/** Records a completion in the field log. Best-effort: the game never depends on it. */
export function recordCompletion(run: QuestRun, result: CompletionResult, now = Date.now()): void {
  const entry = entryFor(run, result, now)
  if (entry) appendFieldEntry(entry)
}

const cell = (v: unknown): string => {
  const s = v === null || v === undefined ? '' : String(v)
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function toCsv(entries: FieldEntry[]): string {
  const rows = entries.map((e) =>
    FIELD_COLUMNS.map((c) => {
      const v = e[c]
      // Round the share here so the CSV stays diff-friendly and the script reads it as-is.
      return cell(c === 'screen_share' && typeof v === 'number' ? v.toFixed(4) : v)
    }).join(','),
  )
  return [FIELD_COLUMNS.join(','), ...rows].join('\n') + '\n'
}

export function csvFilename(entries: FieldEntry[], now = Date.now()): string {
  const first = entries[0]?.date
  const last = entries[entries.length - 1]?.date
  const span = first && last && first !== last ? `${first}_${last}` : (first ?? localDate(now))
  return `sidequest-field-${span}.csv`
}
