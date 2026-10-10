import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Happening, PlaceRef } from '../lib/types'
import QuestMap from './QuestMap'

const PLACE: PlaceRef = { id: 'way/1', name: 'Shaniwar Wada', lat: 18.519, lng: 73.855 }
const HAPPENING: Happening = {
  title: 'Heritage Walk at Shaniwar Wada',
  when_text: 'Sat, Oct 11, 7:00 am',
  starts_at: '2026-10-11T07:00:00+05:30',
  ends_at: '2026-10-11T10:00:00+05:30',
  url: null,
}

describe('QuestMap', () => {
  it('marks a place quest with the ordinary quest pin', () => {
    const { container } = render(<QuestMap place={PLACE} />)
    expect(container.querySelector('.sqm-pin-quest')).not.toBeNull()
    expect(container.querySelector('.sqm-pin-event')).toBeNull()
    expect(screen.getByText('Shaniwar Wada', { selector: '.sr-only' })).toBeInTheDocument()
  })

  it('gives an event-backed quest a distinct marker whose label names the event', () => {
    const { container } = render(<QuestMap place={PLACE} happening={HAPPENING} />)
    expect(container.querySelector('.sqm-pin-event')).not.toBeNull()
    expect(container.querySelector('.sqm-pin-quest')).toBeNull()
    expect(screen.getByText(/event: heritage walk at shaniwar wada/i, { selector: '.sr-only' })).toBeInTheDocument()
  })

  it('treats an event title as text, never as markup', () => {
    const title = '<img src=x onerror="alert(1)">Walk'
    const { container } = render(<QuestMap place={PLACE} happening={{ ...HAPPENING, title }} />)
    expect(container.querySelector('img[src="x"]')).toBeNull()
    expect(screen.getByText(`Event: ${title}`, { selector: '.sr-only' })).toBeInTheDocument()
  })
})
