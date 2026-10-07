import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { accepted, firstJsonObject, parseVerifierOutput } from './parse'
import { VERIFIER_TEMPLATE, verifierPrompt } from './prompt'

const PROMPTS = resolve(__dirname, '../../../../prompts')

describe('verifier output parsing', () => {
  it.each([
    ['{"match": true, "confidence": 0.82, "seen": "a stone marker"}', true, 0.82],
    ['Sure! ```json\n{"match": true, "confidence": 0.7, "seen": "leaf {big}"}\n``` done', true, 0.7],
    ['{"match": "yes", "confidence": 0.9}', false, 0.9], // only literal true counts
    ['{"match": true, "confidence": 7}', true, 1], // clamped
    ['{"match": true}', true, 0],
    ['no json at all', false, 0],
    ['{"match": true, "confidence": 0.9', false, 0], // truncated
    ['[1,2,3]', false, 0],
  ])('%s', (text, match, confidence) => {
    const out = parseVerifierOutput(text)
    expect(out.match).toBe(match)
    expect(out.confidence).toBeCloseTo(confidence)
  })

  it('caps seen at 12 words', () => {
    const out = parseVerifierOutput(JSON.stringify({ match: true, confidence: 1, seen: 'a b c d e f g h i j k l m n o' }))
    expect(out.seen.split(' ')).toHaveLength(12)
  })

  it('finds the first balanced object even with braces in strings', () => {
    expect(firstJsonObject('x {"a":"}{","b":{"c":1}} y {"z":2}')).toBe('{"a":"}{","b":{"c":1}}')
  })

  it('accepts only match && confidence >= 0.6', () => {
    expect(accepted({ match: true, confidence: 0.6, seen: '' })).toBe(true)
    expect(accepted({ match: true, confidence: 0.59, seen: '' })).toBe(false)
    expect(accepted({ match: false, confidence: 1, seen: '' })).toBe(false)
  })
})

describe('verifier prompt (single source in /prompts)', () => {
  it('is byte-identical to prompts/verifier.gemma.txt and its committed hash', () => {
    const file = readFileSync(resolve(PROMPTS, 'verifier.gemma.txt'))
    expect(VERIFIER_TEMPLATE).toBe(file.toString('utf8'))
    const hashes = readFileSync(resolve(PROMPTS, 'HASHES.txt'), 'utf8')
    const digest = createHash('sha256').update(file).digest('hex')
    expect(hashes).toContain(`${digest}  verifier.gemma.txt`)
  })

  it('fills the photo prompt and strips quotes/newlines', () => {
    const p = verifierPrompt('an old "stone"\nmarker')
    expect(p).toContain('decide if this photo shows: "an old  stone  marker"')
    expect(p).not.toContain('{photo_prompt}')
  })
})
