import { describe, expect, it } from 'vitest'

import {
  heartbeat,
  onVisibility,
  restore,
  screenShare,
  startTracking,
  stopTracking,
  visibleSeconds,
} from './screenTime'

const T0 = 1_000_000

describe('screen-time tracker', () => {
  it('counts only visible spans', () => {
    let st = startTracking(T0, true)
    st = onVisibility(st, false, T0 + 10_000) // 10 s visible, then pocketed
    st = onVisibility(st, true, T0 + 600_000) // back after 10 min hidden
    st = stopTracking(st, T0 + 605_000) // 5 s more visible
    expect(visibleSeconds(st, T0 + 700_000)).toBe(15)
  })

  it('starts hidden when accepted from a background tab', () => {
    let st = startTracking(T0, false)
    expect(visibleSeconds(st, T0 + 50_000)).toBe(0)
    st = onVisibility(st, true, T0 + 50_000)
    expect(visibleSeconds(st, T0 + 52_000)).toBe(2)
  })

  it('ignores duplicate visibility events', () => {
    let st = startTracking(T0, true)
    st = onVisibility(st, true, T0 + 5_000)
    st = onVisibility(st, false, T0 + 8_000)
    st = onVisibility(st, false, T0 + 20_000)
    expect(visibleSeconds(st, T0 + 30_000)).toBe(8)
  })

  it('bounds an unclean exit by the last heartbeat on restore', () => {
    let st = startTracking(T0, true)
    st = heartbeat(st, T0 + 5_000)
    // tab killed at ~T0+7s while visible; reopened (visible) at T0+300s
    st = restore(st, T0 + 300_000, true)
    expect(visibleSeconds(st, T0 + 300_000)).toBe(5)
    expect(visibleSeconds(st, T0 + 303_000)).toBe(8)
  })

  it('restore after a clean hide adds nothing', () => {
    let st = startTracking(T0, true)
    st = onVisibility(st, false, T0 + 4_000)
    st = restore(st, T0 + 100_000, false)
    expect(visibleSeconds(st, T0 + 200_000)).toBe(4)
  })

  it('computes screen share and never invents it', () => {
    expect(screenShare(60, 1200)).toBeCloseTo(0.05)
    expect(screenShare(5000, 1200)).toBe(1)
    expect(screenShare(10, 0)).toBeNull()
  })
})
