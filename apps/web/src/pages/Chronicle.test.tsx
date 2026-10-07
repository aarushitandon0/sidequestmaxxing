import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse, renderAt } from '../test/render'
import { Chronicle } from './Chronicle'

const STORY = 'You walked to Kamala Garden and counted three kinds of birds before the light turned gold.'

function profile(recent: unknown[]) {
  return {
    persona: 'chill', interests: [], default_radius_m: 2500,
    skills: Object.fromEntries(['explorer', 'naturalist', 'social', 'foodie', 'creative', 'fitness', 'mindful']
      .map((c) => [c, { xp: 0, level: 0, title: null, next_level_xp: 40 }])),
    total_xp: 30, level: 0, next_level_xp: 120, streak_days: 1, quests_completed: recent.length,
    settings: { safe_mode: true, voice: true }, recent,
  }
}

const DONE = {
  quest_id: 'q1', completed_at: new Date().toISOString(), title: 'The Three-Bark Survey', category: 'naturalist',
  xp_awarded: 30, verification_method: 'honor', place_name: 'Kamala Garden', minutes_outside: 35, screen_share: 0.02,
}

function mockApi(recap: unknown, recent: unknown[] = [DONE]) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) =>
    String(url).includes('/v1/recap/weekly') ? jsonResponse(recap) : jsonResponse(profile(recent)),
  )
}

describe('Chronicle', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows the written weekly story with a Listen button and shares it as plain text', async () => {
    const fetchSpy = mockApi({
      id: 'r1', week_start: '2026-10-01', week_end: '2026-10-07', text: STORY, source: 'llm',
      stats: { quests: 1, minutes: 35, top_category: 'naturalist' }, created_at: new Date().toISOString(),
    })
    const writeText = vi.fn(async () => undefined)
    Object.defineProperty(navigator, 'share', { value: undefined, configurable: true })
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderAt('/chronicle', <Chronicle />)

    expect(await screen.findByText(STORY)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /listen to the dungeon master/i })).toBeInTheDocument()
    const call = fetchSpy.mock.calls.find((c) => String(c[0]).includes('/v1/recap/weekly'))!
    expect((call[1] as RequestInit).method).toBe('POST')

    fireEvent.click(screen.getByRole('button', { name: /share as text/i }))
    expect(await screen.findByText(/copied to your clipboard/i)).toBeInTheDocument()
    const shared = String((writeText.mock.calls[0] as unknown[])[0])
    expect(shared).toContain(STORY)
    expect(shared).not.toMatch(/https?:|\d+\.\d{3,}/) // no links or coordinates
  })

  it('an empty week shows the call to adventure, not a story', async () => {
    mockApi({
      id: null, week_start: '2026-10-01', week_end: '2026-10-07', text: 'No quests yet.', source: 'empty',
      stats: { quests: 0, minutes: 0, top_category: null }, created_at: null,
    }, [])
    renderAt('/chronicle', <Chronicle />)
    expect(await screen.findByRole('link', { name: /start a quest/i })).toBeInTheDocument()
    expect(screen.queryByText('No quests yet.')).not.toBeInTheDocument()
  })

  it('still shows the week when the recap request fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) =>
      String(url).includes('/v1/recap/weekly') ? jsonResponse({ error: { code: 'db', message: 'down' } }, 503) : jsonResponse(profile([DONE])),
    )
    renderAt('/chronicle', <Chronicle />)
    expect(await screen.findByText('The Three-Bark Survey')).toBeInTheDocument()
  })
})
