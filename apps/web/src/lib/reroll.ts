import { readJson, writeJson } from './storage'
import { localDateKey } from './time'

/** Rerolls are limited to 3 per local day (MASTERSPEC §11.1). Client-side courtesy limit. */
export const MAX_REROLLS_PER_DAY = 3
const KEY = 'sqm.rerolls'

interface RerollLog {
  date: string
  count: number
}

export function rerollsLeft(now: Date = new Date()): number {
  const log = readJson<RerollLog>(KEY)
  const used = log && log.date === localDateKey(now) ? log.count : 0
  return Math.max(0, MAX_REROLLS_PER_DAY - used)
}

export function consumeReroll(now: Date = new Date()): number {
  const today = localDateKey(now)
  const log = readJson<RerollLog>(KEY)
  const count = (log && log.date === today ? log.count : 0) + 1
  writeJson(KEY, { date: today, count })
  return Math.max(0, MAX_REROLLS_PER_DAY - count)
}
