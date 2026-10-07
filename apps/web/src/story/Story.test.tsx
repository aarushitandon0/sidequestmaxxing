import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { buildStoryData, parseField, parseResults } from '../../scripts/build_story_data.ts'
import committed from './data.json'
import Story, { Receipts } from './Story'
import type { StoryData } from './types'

const wrap = (ui: ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>)

describe('Story page', () => {
  it('renders all scenes with real headings (receipts hidden without eval data)', () => {
    wrap(<Story />)
    for (const name of [/sidequestmaxxing/i, /maps you stare at/i, /dungeon master writes one quest/i, /walk mode/i,
      /verified on your device/i, /grow seven skills/i, /what's open/i, /the quest unfolds/i]) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument()
    }
    expect(screen.queryByRole('heading', { name: /receipts/i })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /start your first quest/i }).length).toBeGreaterThan(0)
  })

  it('Receipts scene hides when there is no data', () => {
    const { container } = wrap(<Receipts data={{ results: null, field: null }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('Receipts shows exactly the numbers it is given', () => {
    const data: StoryData = {
      results: { source: 'evals/results.json', n: 120, metrics: [{ label: 'Full pass', baseline: 41.7, tuned: 88.3, unit: '%' }] },
      field: { source: 'evals/field.md', rows: [{ label: 'Quests completed', value: '7' }] },
    }
    wrap(<Receipts data={data} />)
    expect(screen.getByText('41.7 %')).toBeInTheDocument()
    expect(screen.getByText('88.3 %')).toBeInTheDocument()
    expect(screen.getByText(/n=120/)).toBeInTheDocument()
    expect(screen.getByText('Quests completed')).toBeInTheDocument()
  })

  it('uses the privacy wording from MASTERSPEC §9.3', () => {
    wrap(<Story />)
    expect(
      screen.getByText(/photos and exact movements stay on your device; the server sees an approximate area to find nearby places\./i),
    ).toBeInTheDocument()
  })
})

describe('build_story_data', () => {
  it('committed data.json matches what the evals/ folder produces (no hand-typed numbers)', () => {
    expect(committed).toEqual(buildStoryData(`${__dirname}/../../../..`))
  })

  it('parses results.json and rejects junk', () => {
    expect(parseResults('{"n": 120, "metrics": [{"label": "Full pass", "baseline": 0.4, "tuned": 0.9}]}')).toEqual({
      source: 'evals/results.json', n: 120, metrics: [{ label: 'Full pass', baseline: 0.4, tuned: 0.9 }],
    })
    expect(parseResults('not json')).toBeNull()
    expect(parseResults('{"metrics": []}')).toBeNull()
    expect(parseResults('{"metrics": [{"label": 3}]}')).toBeNull()
  })

  it('parses the first markdown table of field.md', () => {
    const md = '# Field\n\n| Metric | Value |\n|---|---|\n| Quests | 7 |\n| Median screen share | 6% |\n\n| other | table |\n|--|--|\n| x | y |'
    expect(parseField(md)?.rows).toEqual([
      { label: 'Quests', value: '7' },
      { label: 'Median screen share', value: '6%' },
    ])
    expect(parseField('no table')).toBeNull()
  })
})
