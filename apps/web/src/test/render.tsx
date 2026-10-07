import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

import { makeQueryClient, Providers } from '../App'
import { QUEST_STORAGE_KEY } from '../state/QuestProvider'
import type { QuestRun } from '../lib/questMachine'
import { VerifierProvider, type Verifier } from '../verifier/context'

export const mockVerifier = (over: Partial<Verifier> = {}): Verifier => ({
  modelUrl: null,
  detectSupport: async () => ({ ok: true }),
  installed: () => true,
  download: async () => undefined,
  importFile: async () => undefined,
  remove: async () => undefined,
  verify: async () => ({ match: true, confidence: 0.9, seen: 'an old stone marker', latencyMs: 1200 }),
  ...over,
})

export function LocationProbe() {
  const loc = useLocation()
  return <output data-testid="location">{loc.pathname}</output>
}

export function seedRun(run: QuestRun) {
  localStorage.setItem(QUEST_STORAGE_KEY, JSON.stringify(run))
}

export function renderAt(path: string, element: ReactElement, opts: { verifier?: Verifier; routes?: Record<string, ReactElement> } = {}) {
  const client = makeQueryClient()
  client.setDefaultOptions({ queries: { retry: false } })
  return render(
    <Providers client={client}>
      <VerifierProvider verifier={opts.verifier ?? mockVerifier()}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={path} element={element} />
            {Object.entries(opts.routes ?? {}).map(([p, el]) => (
              <Route key={p} path={p} element={el} />
            ))}
            <Route path="*" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>
      </VerifierProvider>
    </Providers>,
  )
}

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
