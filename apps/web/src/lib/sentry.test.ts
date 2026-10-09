import type { ErrorEvent } from '@sentry/react'
import { describe, expect, it } from 'vitest'

import { DSN, beforeSend, initSentry } from './sentry'

const event = (patch: Partial<ErrorEvent>): ErrorEvent => ({ ...patch }) as ErrorEvent

describe('beforeSend', () => {
  it('is a no-op init without a DSN, so tests and local dev never phone home', () => {
    expect(DSN).toBeFalsy()
    expect(initSentry()).toBe(false)
  })

  it('redacts coordinate keys wherever they appear', () => {
    const out = beforeSend(
      event({
        extra: { lat: 18.521, lng: 73.856, place_id: 'way/42' },
        contexts: { quest: { latitude: 18.5, longitude: 73.8, category: 'naturalist' } },
      }),
    )
    const dump = JSON.stringify(out)
    expect(dump).not.toContain('18.5')
    expect(dump).not.toContain('73.8')
    // Non-coordinate context is kept: a trace with nothing in it is useless.
    expect(dump).toContain('way/42')
    expect(dump).toContain('naturalist')
  })

  it('redacts a coordinate pair written into free text', () => {
    const out = beforeSend(
      event({ message: 'geolocation failed near 18.5204,73.8567 while routing' }),
    )
    expect(out?.message).not.toContain('18.5204')
    expect(out?.message).toContain('while routing')
  })

  it('redacts the device id by key, and this device id where it appears in text', () => {
    const id = '3f1c6c3e-1b7a-4f7e-9d7a-2b0c1d2e3f40'
    window.localStorage.setItem('sqm.device_id', JSON.stringify(id))
    const out = beforeSend(
      event({
        tags: { device_id: id },
        exception: { values: [{ type: 'Error', value: `quest lookup failed for ${id}` }] },
      }),
    )
    expect(JSON.stringify(out)).not.toContain(id)
    window.localStorage.removeItem('sqm.device_id')
  })

  it('keeps quest ids, which are UUIDs too and are what you follow in a trace', () => {
    const quest = '9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d'
    const out = beforeSend(event({ tags: { quest_id: quest } }))
    expect(JSON.stringify(out)).toContain(quest)
  })

  it('strips query strings from request urls', () => {
    const out = beforeSend(
      event({
        request: {
          url: 'https://api.test/v1/places/near?lat=18.52&lng=73.85',
          query_string: 'lat=18.52&lng=73.85',
        },
      }),
    )
    expect(out?.request?.url).toBe('https://api.test/v1/places/near')
    expect(out?.request?.query_string).toBeUndefined()
    expect(JSON.stringify(out)).not.toContain('18.52')
  })

  it('drops permission-denied noise: saying no to the camera is a supported path', () => {
    const denials = [
      { type: 'NotAllowedError', value: 'Permission denied' },
      { type: 'Error', value: 'The request is not allowed by the user agent' },
      { type: 'GeolocationPositionError', value: 'User denied Geolocation' },
    ]
    for (const value of denials) {
      expect(beforeSend(event({ exception: { values: [value] } }))).toBeNull()
    }
  })

  it('keeps real errors', () => {
    const real = event({ exception: { values: [{ type: 'TypeError', value: 'x is not a fn' }] } })
    expect(beforeSend(real)).not.toBeNull()
  })
})
