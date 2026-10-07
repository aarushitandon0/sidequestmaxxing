import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError } from './api'
import { getDeviceId, isUuidV4 } from './device'
import { formatClock, formatDistance } from './labels'
import { coarse } from './location'
import { MAX_REROLLS_PER_DAY, consumeReroll, rerollsLeft } from './reroll'
import { localTimeIso } from './time'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('device id', () => {
  it('creates and keeps a random uuid v4', () => {
    const id = getDeviceId()
    expect(isUuidV4(id)).toBe(true)
    expect(getDeviceId()).toBe(id)
  })
})

describe('api client', () => {
  it('sends the device header and JSON body', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ id: 'q', status: 'accepted' })))
    await api.acceptQuest('q 1')
    const [url, init] = spy.mock.calls[0]!
    expect(String(url)).toMatch(/\/v1\/quests\/q%201\/accept$/)
    expect((init!.headers as Record<string, string>)['X-Device-Id']).toBe(getDeviceId())
  })

  it('maps error bodies and network failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: 'rate_limited', message: 'slow' } }), { status: 429 }),
    )
    await expect(api.profile()).rejects.toMatchObject({ status: 429, code: 'rate_limited' })
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('offline'))
    const err = await api.profile().catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).isNetwork).toBe(true)
  })

  it('has no way to upload images (photos never leave the device)', () => {
    const words = Object.keys(api).flatMap((k) => k.split(/(?=[A-Z])/).map((w) => w.toLowerCase()))
    for (const banned of ['photo', 'image', 'upload', 'file', 'files', 'blob', 'picture']) {
      expect(words).not.toContain(banned)
    }
    const source = Object.values(api).map(String).join('\n')
    expect(source).not.toMatch(/FormData|multipart|base64|Blob/)
  })
})

describe('helpers', () => {
  it('local time includes the UTC offset', () => {
    expect(localTimeIso(new Date())).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$/)
  })

  it('rounds coordinates to 3 decimals', () => {
    expect(coarse(18.52049, 73.85651)).toEqual({ lat: 18.52, lng: 73.857 })
  })

  it('formats clocks and distances', () => {
    expect(formatClock(65)).toBe('1:05')
    expect(formatClock(3725)).toBe('1:02:05')
    expect(formatDistance(1234)).toBe('1.2 km')
    expect(formatDistance(347)).toBe('350 m')
    expect(formatDistance(null)).toBeNull()
  })

  it('limits rerolls to 3 per local day', () => {
    const day = new Date(2026, 9, 7, 10)
    expect(rerollsLeft(day)).toBe(MAX_REROLLS_PER_DAY)
    consumeReroll(day)
    consumeReroll(day)
    expect(consumeReroll(day)).toBe(0)
    expect(rerollsLeft(day)).toBe(0)
    expect(rerollsLeft(new Date(2026, 9, 8, 10))).toBe(3)
  })
})
