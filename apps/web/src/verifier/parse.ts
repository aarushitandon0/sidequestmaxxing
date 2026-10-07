/** Robust parsing of the verifier model's reply (MASTERSPEC §7.6). Unsure → match=false. */

export interface VerifyOutcome {
  match: boolean
  confidence: number
  seen: string
}

export const ACCEPT_CONFIDENCE = 0.6
const NO_MATCH: VerifyOutcome = { match: false, confidence: 0, seen: '' }

/** Extract the first balanced JSON object from text that may contain extra words or fences. */
export function firstJsonObject(text: string): string | null {
  const start = text.indexOf('{')
  if (start < 0) return null
  let depth = 0
  let inString = false
  let escaped = false
  for (let i = start; i < text.length; i++) {
    const ch = text[i]
    if (inString) {
      if (escaped) escaped = false
      else if (ch === '\\') escaped = true
      else if (ch === '"') inString = false
      continue
    }
    if (ch === '"') inString = true
    else if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) return text.slice(start, i + 1)
    }
  }
  return null
}

export function parseVerifierOutput(text: string): VerifyOutcome {
  const raw = firstJsonObject(text)
  if (!raw) return NO_MATCH
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return NO_MATCH
  }
  if (!data || typeof data !== 'object') return NO_MATCH
  const d = data as Record<string, unknown>
  const confidence = typeof d.confidence === 'number' && Number.isFinite(d.confidence) ? Math.min(1, Math.max(0, d.confidence)) : 0
  const seen = typeof d.seen === 'string' ? d.seen.split(/\s+/).slice(0, 12).join(' ').slice(0, 120) : ''
  return { match: d.match === true, confidence, seen }
}

export function accepted(o: VerifyOutcome): boolean {
  return o.match && o.confidence >= ACCEPT_CONFIDENCE
}
