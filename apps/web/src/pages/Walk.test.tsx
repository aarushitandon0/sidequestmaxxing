import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { IDLE, type QuestRun } from '../lib/questMachine'
import { startTracking } from '../lib/screenTime'
import { QUEST } from '../test/fixtures'
import { savePrefs } from '../lib/prefs'
import { QUEST_STORAGE_KEY } from '../state/QuestProvider'
import { jsonResponse, renderAt, seedRun } from '../test/render'
import { Walk } from './Walk'

const T0 = Date.parse('2026-10-07T10:00:00Z')
const accepted = (): QuestRun => ({
  ...IDLE,
  phase: 'accepted',
  quest: QUEST,
  acceptedAt: new Date(T0).toISOString(),
  screen: startTracking(T0, true),
})

describe('Walk Mode', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(T0 + 5 * 60_000 + 7_000)
    savePrefs({ onboarded: true })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('shows elapsed time from accepted_at and keeps ticking (survives reloads by design)', () => {
    seedRun(accepted())
    renderAt('/walk', <Walk />)
    expect(screen.getByRole('heading', { name: /walk mode/i })).toBeInTheDocument()
    expect(screen.getByText('5:07')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(screen.getByText('6:07')).toBeInTheDocument()
    expect(screen.getByText(QUEST.objective)).toBeInTheDocument()
  })

  it("'I'm back' moves the quest to verifying", () => {
    seedRun(accepted())
    renderAt('/walk', <Walk />)
    fireEvent.click(screen.getByRole('button', { name: /i'm back/i }))
    expect(screen.getByTestId('location')).toHaveTextContent('/verify')
    const stored = JSON.parse(localStorage.getItem(QUEST_STORAGE_KEY)!) as QuestRun
    expect(stored.phase).toBe('verifying')
  })

  it('Stop quest asks first, then skips on the server and returns home', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ id: 'q1', status: 'skipped' }))
    seedRun(accepted())
    renderAt('/walk', <Walk />)
    fireEvent.click(screen.getByRole('button', { name: /stop quest/i }))
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /yes, stop/i }))
    })
    expect(String(fetchSpy.mock.calls[0]![0])).toMatch(/\/v1\/quests\/q1\/skip$/)
    expect(screen.getByTestId('location')).toHaveTextContent('/home')
  })

  it('has a repeat-audio button and never requests a wake lock', () => {
    const wake = vi.fn()
    Object.defineProperty(navigator, 'wakeLock', { value: { request: wake }, configurable: true })
    seedRun(accepted())
    renderAt('/walk', <Walk />)
    expect(screen.getByRole('button', { name: /repeat the briefing/i })).toBeInTheDocument()
    expect(wake).not.toHaveBeenCalled()
  })

  it('redirects home when no quest is active', () => {
    renderAt('/walk', <Walk />)
    expect(screen.getByTestId('location')).toHaveTextContent('/home')
  })
})
