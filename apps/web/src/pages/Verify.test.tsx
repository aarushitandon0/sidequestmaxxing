import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { IDLE, type QuestRun } from '../lib/questMachine'
import { startTracking } from '../lib/screenTime'
import type { CompletionRequest } from '../lib/types'
import { QUEST_STORAGE_KEY } from '../state/QuestProvider'
import { QUEST } from '../test/fixtures'
import { jsonResponse, mockVerifier, renderAt, seedRun } from '../test/render'
import { Verify } from './Verify'

const T0 = Date.now() - 20 * 60_000
const verifying = (over: Partial<QuestRun> = {}): QuestRun => ({
  ...IDLE,
  phase: 'verifying',
  quest: QUEST,
  acceptedAt: new Date(T0).toISOString(),
  screen: { ...startTracking(T0, false), visibleMs: 30_000 },
  finishedAt: T0 + 18 * 60_000,
  ...over,
})
const RESULT = {
  quest_id: 'q1', xp_awarded: 36, level_ups: [], streak: 1, total_xp: 36, level: 0,
  within_radius: null, screen_share: 0.03, daily_cap_reached: false,
}
const photo = () => new File([new Uint8Array([0xff, 0xd8, 0xff, 1, 2, 3])], 'leaf.jpg', { type: 'image/jpeg' })

/** Every request body the app sent, as text. */
function sentBodies(spy: ReturnType<typeof vi.spyOn>): string[] {
  return spy.mock.calls.map((c: unknown[]) => {
    const init = c[1] as RequestInit | undefined
    const body = init?.body
    if (body == null) return ''
    expect(typeof body).toBe('string') // never Blob / FormData / ArrayBuffer
    return body as string
  })
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:local-preview')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('Verify', () => {
  it('photo → checked on device → claim sends only the verdict (no image data)', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(RESULT))
    const verify = vi.fn(mockVerifier().verify)
    seedRun(verifying())
    renderAt('/verify', <Verify />, { verifier: mockVerifier({ verify }) })

    const input = screen.getByLabelText(/take a photo/i)
    await act(async () => {
      fireEvent.change(input, { target: { files: [photo()] } })
    })
    expect(verify).toHaveBeenCalledWith(expect.any(File), QUEST.verification.photo_prompt)
    expect(await screen.findByText(/match found/i)).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalled() // checking the photo made zero network calls

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /claim reward/i }))
    })
    expect(fetchSpy).toHaveBeenCalledOnce()
    const [url] = fetchSpy.mock.calls[0]!
    expect(String(url)).toMatch(/\/v1\/quests\/q1\/complete$/)
    const [raw] = sentBodies(fetchSpy)
    const body = JSON.parse(raw!) as CompletionRequest
    expect(body.verification).toEqual({ method: 'photo', match: true, confidence: 0.9, seen: 'an old stone marker' })
    expect(body.elapsed_seconds).toBe(18 * 60)
    expect(body.screen_seconds).toBeGreaterThanOrEqual(30)
    expect(Object.keys(body).sort()).toEqual(['elapsed_seconds', 'screen_seconds', 'verification'])
    expect(raw).not.toMatch(/data:image|base64|blob:|jpeg|\\u00ff/i)
    expect(screen.getByTestId('location')).toHaveTextContent('/reward')
  })

  it('no match → offers retake, check-in and honor; nothing is claimed', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    seedRun(verifying())
    renderAt('/verify', <Verify />, {
      verifier: mockVerifier({ verify: async () => ({ match: false, confidence: 0.2, seen: 'a parked car', latencyMs: 900 }) }),
    })
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/take a photo/i), { target: { files: [photo()] } })
    })
    expect(await screen.findByText(/not quite/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retake photo/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /check in at riverside park/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /honor mode/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /claim reward/i })).not.toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('low confidence is not accepted even when match=true', async () => {
    seedRun(verifying())
    renderAt('/verify', <Verify />, {
      verifier: mockVerifier({ verify: async () => ({ match: true, confidence: 0.59, seen: '', latencyMs: 1 }) }),
    })
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/take a photo/i), { target: { files: [photo()] } })
    })
    expect(await screen.findByText(/not quite/i)).toBeInTheDocument()
  })

  it('verifier not installed → install card; check-in and honor still work', async () => {
    seedRun(verifying())
    renderAt('/verify', <Verify />, {
      verifier: mockVerifier({ installed: () => false, detectSupport: async () => ({ ok: false, reason: 'no-webgpu' }) }),
    })
    expect(screen.queryByLabelText(/take a photo/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /install the on-device photo checker/i }))
    expect(await screen.findByText(/doesn't support webgpu/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /honor mode/i })).toBeEnabled()
  })

  it('check-in sends rounded coordinates and no photo', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ...RESULT, within_radius: true }))
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition: (ok: PositionCallback) =>
          ok({ coords: { latitude: 18.520449, longitude: 73.851234 } } as GeolocationPosition),
      },
    })
    seedRun(verifying())
    renderAt('/verify', <Verify />)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /check in at/i }))
    })
    const body = JSON.parse(sentBodies(fetchSpy)[0]!) as CompletionRequest
    expect(body.verification).toEqual({ method: 'checkin' })
    expect(body.checkin).toEqual({ lat: 18.52, lng: 73.851 })
  })

  it('honor mode claims half XP without a photo', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(RESULT))
    seedRun(verifying())
    renderAt('/verify', <Verify />)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /honor mode/i }))
    })
    expect(JSON.parse(sentBodies(fetchSpy)[0]!).verification).toEqual({ method: 'honor' })
  })

  it('offline: the verdict is saved and claimed automatically when back online', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValue(jsonResponse(RESULT))
    const online = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    seedRun(verifying())
    renderAt('/verify', <Verify />)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /honor mode/i }))
    })
    expect(await screen.findByText(/verified — saved on your phone/i)).toBeInTheDocument()
    expect(screen.getByText(/claim your reward as soon as you're back online/i)).toBeInTheDocument()
    expect(fetchSpy).toHaveBeenCalledOnce() // no retries while offline
    online.mockReturnValue(true)
    await act(async () => {
      window.dispatchEvent(new Event('online'))
    })
    await waitFor(() => expect(JSON.parse(localStorage.getItem(QUEST_STORAGE_KEY)!).phase).toBe('completed'))
    expect(fetchSpy).toHaveBeenCalledTimes(2)
    expect(sentBodies(fetchSpy)[0]).toBe(sentBodies(fetchSpy)[1]) // the same verdict, replayed
  })

  it('server rejection (quest too short) is shown and the quest stays open', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ error: { code: 'quest_too_short', message: 'That was quick! Give the quest a bit more time.' } }, 422),
    )
    seedRun(verifying())
    renderAt('/verify', <Verify />)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /honor mode/i }))
    })
    expect(await screen.findByRole('alert')).toHaveTextContent(/that was quick/i)
    expect(JSON.parse(localStorage.getItem(QUEST_STORAGE_KEY)!).phase).toBe('verifying')
  })

  it('explains that verification works in airplane mode', () => {
    seedRun(verifying())
    renderAt('/verify', <Verify />)
    expect(screen.getByText(/works in airplane mode/i)).toBeInTheDocument()
  })
})
