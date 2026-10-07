import { describe, expect, it } from 'vitest'

import { score } from '../../spike/score.ts'
import { parseFixtureName } from './GemmaVerify'

describe('gemma spike scoring', () => {
  it('parses fixture names', () => {
    expect(parseFixtureName('pos__three-different-leaves__01.jpg')).toEqual({ label: 'pos', prompt: 'three different leaves' })
    expect(parseFixtureName('random.jpg')).toBeNull()
  })

  it('computes precision/recall/accuracy with the 0.6 threshold', () => {
    const s = score([
      { file: 'a', label: 'pos', match: true, confidence: 0.9, latency_ms: 100 }, // tp
      { file: 'b', label: 'pos', match: true, confidence: 0.5, latency_ms: 300 }, // fn (low conf)
      { file: 'c', label: 'neg', match: true, confidence: 0.8, latency_ms: 200 }, // fp
      { file: 'd', label: 'neg', match: false, confidence: 0.9, latency_ms: 400 }, // tn
    ])
    expect(s).toMatchObject({ tp: 1, fn: 1, fp: 1, tn: 1, precision: 0.5, recall: 0.5, accuracy: 0.5, latency_ms_p50: 200 })
  })
})
