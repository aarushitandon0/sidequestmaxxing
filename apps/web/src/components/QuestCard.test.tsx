import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

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
