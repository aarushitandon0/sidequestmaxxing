import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { IDLE } from '../lib/questMachine'
import { loadPrefs, savePrefs } from '../lib/prefs'
import { QUEST } from '../test/fixtures'
import { jsonResponse, renderAt, seedRun } from '../test/render'
import { Home } from './Home'
import { Onboarding } from './Onboarding'
import { Reward } from './Reward'
import { Settings } from './Settings'
import { VerifierInstall } from './VerifierInstall'
import { mockVerifier } from '../test/render'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

const PROFILE = {
  persona: 'chill', interests: [], default_radius_m: 2500,
  skills: Object.fromEntries(['explorer', 'naturalist', 'social', 'foodie', 'creative', 'fitness', 'mindful']
    .map((c) => [c, { xp: 0, level: 0, title: null, next_level_xp: 40 }])),
  total_xp: 0, level: 0, next_level_xp: 120, streak_days: 0, quests_completed: 0,
  settings: { safe_mode: true, voice: true }, recent: [],
}

describe('Onboarding', () => {
  it('takes 3 taps: persona → continue → safety promise', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(PROFILE))
    renderAt('/onboarding', <Onboarding />)
    fireEvent.click(screen.getByRole('radio', { name: /dramatic/i })) // tap 1
    fireEvent.click(screen.getByRole('button', { name: /continue/i })) // tap 2
    expect(screen.getByText(/tell someone where you're going/i)).toBeInTheDocument()
    expect(screen.getByText(/not an emergency or navigation tool/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /i'll tell someone/i })) // tap 3
    expect(screen.getByTestId('location')).toHaveTextContent('/home')
    expect(loadPrefs()).toMatchObject({ persona: 'dramatic', onboarded: true, safetyAck: true })
  })
})

describe('Quest board', () => {
  it('sends new players to onboarding', () => {
    renderAt('/home', <Home />)
    expect(screen.getByTestId('location')).toHaveTextContent('/onboarding')
  })

  it('asks for location just in time; the demo area works without permission', async () => {
    savePrefs({ onboarded: true, interests: ['birds'] })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) =>
      String(url).includes('/generate') ? jsonResponse(QUEST) : jsonResponse(PROFILE),
    )
    renderAt('/home', <Home />)
    fireEvent.click(screen.getByRole('button', { name: /get a quest/i }))
    expect(screen.getByText(/approximate area/i)).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /play in the demo area/i }))
    })
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/quest'))
    const call = fetchSpy.mock.calls.find((c) => String(c[0]).includes('/generate'))!
    const body = JSON.parse((call[1] as RequestInit).body as string)
    expect(body).toMatchObject({ lat: 18.52, lng: 73.856, mood: 'curious', interests: ['birds'], mode: 'walk' })
    expect(body.local_time_iso).toMatch(/[+-]\d\d:\d\d$/)
  })

  it('shows a friendly rate-limit message', async () => {
    savePrefs({ onboarded: true })
    localStorage.setItem('sqm.location_choice', JSON.stringify('demo'))
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) =>
      String(url).includes('/generate')
        ? jsonResponse({ error: { code: 'rate_limited', message: 'x' } }, 429)
        : jsonResponse(PROFILE),
    )
    renderAt('/home', <Home />)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /get a quest/i }))
    })
    expect(await screen.findByRole('alert')).toHaveTextContent(/slow down, adventurer/i)
  })
})

describe('Reward', () => {
  it('shows XP, minutes outside and the real screen share', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(PROFILE))
    const accepted = Date.parse('2026-10-07T10:00:00Z')
    seedRun({
      ...IDLE, phase: 'completed', quest: QUEST, acceptedAt: new Date(accepted).toISOString(),
      screen: null, finishedAt: accepted + 21 * 60_000,
      result: { quest_id: 'q1', xp_awarded: 36, streak: 1, total_xp: 36, level: 0, within_radius: null,
        screen_share: 0.04, daily_cap_reached: false,
        level_ups: [{ kind: 'category', category: 'naturalist', from_level: 0, to_level: 1, title: 'Sprout' }] },
    })
    renderAt('/reward', <Reward />)
    expect(screen.getByRole('heading', { name: /quest complete/i })).toBeInTheDocument()
    expect(screen.getByText('36 XP earned')).toBeInTheDocument()
    expect(screen.getByText(/\+21 min outside/)).toBeInTheDocument()
    expect(screen.getByText(/your screen was on for 4% of this quest/i)).toBeInTheDocument()
    expect(screen.getByText(/nature lore reached level 1 — “sprout”/i)).toBeInTheDocument()
  })
})

describe('Settings', () => {
  it('Delete my data calls DELETE /v1/profile after confirming', async () => {
    savePrefs({ onboarded: true })
    const assign = vi.fn()
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, assign })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    renderAt('/settings', <Settings />, { verifier: mockVerifier({ installed: () => false }) })
    fireEvent.click(screen.getByRole('button', { name: /delete my data/i }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /yes, delete everything/i }))
    })
    const del = fetchSpy.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === 'DELETE')
    expect(String(del?.[0])).toMatch(/\/v1\/profile$/)
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/'))
    expect(localStorage.getItem('sqm.prefs.v1')).toBeNull()
  })
})

describe('Verifier install', () => {
  it('imports a local model file with progress and never blocks', async () => {
    const importFile = vi.fn(async (_f: File, onProgress: (l: number, t: number | null) => void) => {
      onProgress(5, 10)
    })
    let installed = false
    renderAt('/s', <VerifierInstall />, {
      verifier: mockVerifier({ installed: () => installed, importFile: async (f, p) => { await importFile(f, p); installed = true } }),
    })
    const input = await screen.findByLabelText(/use a model file i already have/i)
    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(['x'], 'gemma.litertlm')] } })
    })
    expect(importFile).toHaveBeenCalled()
    expect(await screen.findByText(/checker is installed/i)).toBeInTheDocument()
  })

  it('explains the gated model when no download URL is configured', async () => {
    renderAt('/s', <VerifierInstall />, { verifier: mockVerifier({ installed: () => false }) })
    expect(await screen.findByText(/gated behind google's gemma terms/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /download the checker/i })).not.toBeInTheDocument()
  })
})
