import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { markJournalUnlocked } from '../lib/journal'
import { jsonResponse, renderAt } from '../test/render'
import { Journal } from './Journal'

const CATEGORIES = ['explorer', 'naturalist', 'social', 'foodie', 'creative', 'fitness', 'mindful']

function profile(questsCompleted: number) {
  return {
    persona: 'chill',
    interests: [],
    default_radius_m: 2500,
    skills: Object.fromEntries(CATEGORIES.map((c) => [c, { xp: 0, level: 0, title: null, next_level_xp: 40 }])),
    total_xp: 0,
    level: 0,
    next_level_xp: 120,
    streak_days: 0,
    quests_completed: questsCompleted,
    settings: { safe_mode: true, voice: true },
    recent: [],
  }
}

const mockProfile = (questsCompleted: number) =>
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse(profile(questsCompleted)))

describe('Journal', () => {
  beforeEach(() => window.localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('is sealed until the first quest is finished', async () => {
    mockProfile(0)
    renderAt('/journal', <Journal />)
    expect(await screen.findByRole('heading', { name: /still sealed/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /get your first quest/i })).toHaveAttribute('href', '/home')
    // Nothing to write into yet, so the composer must not be on the page at all.
    expect(screen.queryByLabelText(/what happened out there/i)).not.toBeInTheDocument()
  })

  it('opens once a quest has been completed locally, even with the API down', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))
    markJournalUnlocked()
    renderAt('/journal', <Journal />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Your Journal' })).toBeInTheDocument()
    expect(screen.getByLabelText(/what happened out there/i)).toBeInTheDocument()
  })

  it('opens from the server count when the local flag is missing', async () => {
    mockProfile(4)
    renderAt('/journal', <Journal />)
    await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'Your Journal' })).toBeInTheDocument())
    expect(screen.queryByRole('heading', { name: /still sealed/i })).not.toBeInTheDocument()
  })

  it('says so plainly when the browser cannot store a journal', async () => {
    // jsdom has no IndexedDB, which is exactly the private-mode case this must survive.
    mockProfile(1)
    renderAt('/journal', <Journal />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/cannot store a journal/i)
    // The composer stays: the player can still write, they just find out on save.
    expect(screen.getByLabelText(/what happened out there/i)).toBeInTheDocument()
  })

  it('promises on the page that photos never leave the device', async () => {
    mockProfile(1)
    renderAt('/journal', <Journal />)
    expect(await screen.findByText(/stay on this device/i)).toBeInTheDocument()
    expect(screen.getByText(/location data is stripped/i)).toBeInTheDocument()
  })
})
