import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { appendFieldEntry, readFieldLog, type FieldEntry } from '../lib/fieldLog'
import { renderAt } from '../test/render'
import { Export } from './Export'

const entry = (over: Partial<FieldEntry> = {}): FieldEntry => ({
  quest_id: 'q1',
  date: '2026-10-07',
  category: 'naturalist',
  rarity: 'common',
  est_minutes: 15,
  elapsed_seconds: 1200,
  screen_seconds: 60,
  screen_share: 0.05,
  verification_method: 'photo',
  source: 'llm',
  voice: true,
  ...over,
})

const openPage = () => renderAt('/settings/export', <Export />)

/** fireEvent + a flushed microtask queue: the clipboard handler is async. */
const click = async (el: HTMLElement) => {
  await act(async () => {
    fireEvent.click(el)
  })
}

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('field test export', () => {
  it('says there is nothing yet, with no download offered', () => {
    openPage()
    expect(screen.getByText(/Nothing logged yet/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Download CSV/ })).not.toBeInTheDocument()
  })

  it('summarizes the log and lists the rows', () => {
    appendFieldEntry(entry())
    appendFieldEntry(entry({ quest_id: 'q2', elapsed_seconds: 3000, screen_share: 0.2, source: 'fallback' }))
    openPage()
    const stat = (label: string) => screen.getByText(label).parentElement?.textContent ?? ''
    expect(stat('Quests')).toContain('2')
    expect(stat('Minutes outside')).toContain('70') // (1200 + 3000) / 60
    expect(stat('Median screen')).toContain('13%') // median of 5% and 20%
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3) // header + 2
    expect(within(table).getByText('fallback')).toBeInTheDocument()
  })

  it('downloads the CSV under the filename for its dates', async () => {
    appendFieldEntry(entry())
    const url = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:csv')
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    openPage()
    await click(screen.getByRole('button', { name: /Download CSV/ }))
    expect(url).toHaveBeenCalledOnce()
    expect(anchorClick).toHaveBeenCalledOnce()
    expect(revoke).toHaveBeenCalledWith('blob:csv')
    const blob = url.mock.calls[0]?.[0] as Blob
    expect(blob.type).toContain('text/csv')
    expect(await blob.text()).toContain('2026-10-07,naturalist,common,15,1200,60,0.0500,photo,llm,true')
  })

  it('copies the CSV when the clipboard allows it', async () => {
    appendFieldEntry(entry())
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    openPage()
    await click(screen.getByRole('button', { name: /Copy CSV/ }))
    expect(writeText).toHaveBeenCalledOnce()
    expect(String(writeText.mock.calls[0]?.[0])).toContain('date,category,rarity')
    expect(await screen.findByRole('status')).toHaveTextContent('Copied 1 rows')
  })

  it('stays quiet when the clipboard is blocked', async () => {
    appendFieldEntry(entry())
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    openPage()
    await click(screen.getByRole('button', { name: /Copy CSV/ }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('clears the log only after a confirmation', async () => {
    appendFieldEntry(entry())
    openPage()
    await click(screen.getByRole('button', { name: /Clear field log/ }))
    expect(readFieldLog()).toHaveLength(1) // not yet
    await click(screen.getByRole('button', { name: /Keep them/ }))
    expect(readFieldLog()).toHaveLength(1)
    await click(screen.getByRole('button', { name: /Clear field log/ }))
    await click(screen.getByRole('button', { name: /Yes, delete 1 rows/ }))
    expect(readFieldLog()).toEqual([])
    expect(screen.getByText(/Nothing logged yet/)).toBeInTheDocument()
  })

  it('tells the player what is and is not recorded', () => {
    openPage()
    expect(screen.getByText(/No coordinates, no place/)).toBeInTheDocument()
    expect(screen.getByText(/nothing here has ever been sent anywhere/)).toBeInTheDocument()
  })
})
