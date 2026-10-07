import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Home } from './Home'

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Home', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows service status from /healthz', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', db: 'down', llm: 'unknown' }), { status: 200 }),
    )
    renderHome()
    expect(await screen.findByText('db: down')).toBeInTheDocument()
    expect(screen.getByText('api: ok')).toBeInTheDocument()
  })

  it('shows a friendly error when the API is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('network'))
    renderHome()
    expect(await screen.findByRole('alert')).toHaveTextContent(/can't reach/i)
  })
})
