import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Happening, Quest } from '../lib/types'
import { QUEST } from '../test/fixtures'
import { QuestCard } from './QuestCard'

function setup(over: Partial<Parameters<typeof QuestCard>[0]> = {}) {
  const props = {
    quest: QUEST,
    persona: 'chill' as const,
    voice: true,
    rerollsLeft: 2,
    onAccept: vi.fn(),
    onReroll: vi.fn(),
    onSkip: vi.fn(),
    ...over,
  }
  render(<QuestCard {...props} />)
  return props
}

describe('QuestCard', () => {
  it('shows title, chips, briefing, objective, minutes and the safety note', () => {
    setup()
    expect(screen.getByRole('heading', { name: /the riverbank riddle/i })).toBeInTheDocument()
    expect(screen.getByText(/riverside park/i)).toBeInTheDocument()
    expect(screen.getByText('1.2 km', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Nature')).toBeInTheDocument()
    expect(screen.getByText('Common')).toBeInTheDocument()
    expect(screen.getByText(/15 min/)).toBeInTheDocument()
    expect(screen.getByText(/\+30 XP/)).toBeInTheDocument()
    expect(screen.getByText(QUEST.briefing)).toBeInTheDocument()
    expect(screen.getByText(QUEST.objective)).toBeInTheDocument()
    expect(screen.getByText(QUEST.safety_note)).toBeInTheDocument()
  })

  it('wires Accept, Reroll and Skip', () => {
    const p = setup()
    fireEvent.click(screen.getByRole('button', { name: /accept quest/i }))
    fireEvent.click(screen.getByRole('button', { name: /reroll/i }))
    fireEvent.click(screen.getByRole('button', { name: /^skip$/i }))
    expect(p.onAccept).toHaveBeenCalledOnce()
    expect(p.onReroll).toHaveBeenCalledOnce()
    expect(p.onSkip).toHaveBeenCalledOnce()
  })

  it('disables reroll after 3 per day and everything while busy', () => {
    setup({ rerollsLeft: 0 })
    expect(screen.getByRole('button', { name: /reroll/i })).toBeDisabled()
    expect(screen.getByText(/0 left today/)).toBeInTheDocument()
  })

  it('handles a place-less quest', () => {
    setup({ quest: { ...QUEST, place: null, place_id: null, distance_m: null } })
    expect(screen.getByText(/no destination needed/i)).toBeInTheDocument()
  })

  it('offers Listen only when voice is on', () => {
    setup({ voice: false })
    expect(screen.queryByRole('button', { name: /listen/i })).not.toBeInTheDocument()
  })
})

describe('QuestCard happening (P23)', () => {
  const NOW = new Date('2026-10-11T09:00:00+05:30')
  const happening: Happening = {
    title: 'Heritage Walk at Shaniwar Wada',
    when_text: 'Sat, Oct 11, 7:00 am',
    starts_at: '2026-10-11T07:00:00+05:30',
    ends_at: '2026-10-11T10:00:00+05:30',
    url: 'https://example.org/heritage-walk',
  }
  const withHappening = (over: Partial<Happening> = {}): Quest => ({
    ...QUEST,
    happening: { ...happening, ...over },
  })

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows a timing chip when the quest is a happening', () => {
    setup({ quest: withHappening() })
    expect(screen.getByText(/^(happening now|starts )/i)).toBeInTheDocument()
  })

  it('names the happening and its when_text', () => {
    setup({ quest: withHappening() })
    expect(screen.getByText('Heritage Walk at Shaniwar Wada')).toBeInTheDocument()
    expect(screen.getByText('Sat, Oct 11, 7:00 am')).toBeInTheDocument()
  })

  it('says "Starts" with a local time for a happening that has not begun', () => {
    setup({
      quest: withHappening({ starts_at: '2026-10-11T17:00:00+05:30', ends_at: '2026-10-11T19:00:00+05:30' }),
    })
    expect(screen.getByText(/^starts\s+\S/i)).toBeInTheDocument()
    expect(screen.queryByText('Happening now')).not.toBeInTheDocument()
  })

  it('links to the listing with a safe external target', () => {
    setup({ quest: withHappening() })
    const link = screen.getByRole('link', { name: /listing/i })
    expect(link).toHaveAttribute('href', happening.url)
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
  })

  it('omits the link when the happening has no url, keeping the chip (OQ-E1)', () => {
    setup({ quest: withHappening({ url: null }) })
    expect(screen.getByText('Happening now')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /listing/i })).not.toBeInTheDocument()
  })

  it('refuses a listing url that is not http(s)', () => {
    setup({ quest: withHappening({ url: "javascript:alert('x')" }) })
    expect(screen.queryByRole('link', { name: /listing/i })).not.toBeInTheDocument()
    expect(screen.getByText('Happening now')).toBeInTheDocument()
  })

  it('renders no chip and no link for an ordinary place quest', () => {
    setup()
    expect(screen.queryByText(/^(happening now|starts )/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /listing/i })).not.toBeInTheDocument()
  })

  it('shows no timing chip once the happening has ended', () => {
    setup({
      quest: withHappening({ starts_at: '2026-10-11T06:00:00+05:30', ends_at: '2026-10-11T08:00:00+05:30' }),
    })
    expect(screen.queryByText(/^(happening now|starts )/i)).not.toBeInTheDocument()
  })
})
