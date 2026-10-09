import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { AppShell, ErrorBoundary, OfflineBanner, UpdatePrompt } from './components/Shell'
import { Chronicle } from './pages/Chronicle'
import { Export } from './pages/Export'
import { Home } from './pages/Home'
import { MapPage } from './pages/MapPage'
import { NotFound } from './pages/NotFound'
import { Onboarding } from './pages/Onboarding'
import { Profile } from './pages/Profile'
import { QuestPage } from './pages/QuestPage'
import { Reward } from './pages/Reward'
import { Settings } from './pages/Settings'
import { Verify } from './pages/Verify'
import { Walk } from './pages/Walk'
import { QuestProvider } from './state/QuestProvider'

// The story is the public landing; lazy so the app shell stays small (MASTERSPEC §11.4).
const Story = lazy(() => import('./story/Story'))
// P11 spike page: dev builds only (never shipped).
const GemmaSpike = import.meta.env.DEV ? lazy(() => import('./spike/GemmaVerify')) : null

export function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })
}

const queryClient = makeQueryClient()

const shell = (page: ReactNode) => <AppShell>{page}</AppShell>
// Walk Mode / Verify / Onboarding are immersive: no navigation chrome.
const bare = (page: ReactNode) => (
  <>
    <OfflineBanner />
    {page}
  </>
)

export function AppRoutes() {
  return (
    <Suspense fallback={<p role="status" className="p-6 text-center">Unrolling the map…</p>}>
      <Routes>
        <Route path="/" element={<Story />} />
        <Route path="/story" element={<Story />} />
        <Route path="/onboarding" element={bare(<Onboarding />)} />
        <Route path="/home" element={shell(<Home />)} />
        <Route path="/quest" element={shell(<QuestPage />)} />
        <Route path="/walk" element={bare(<Walk />)} />
        <Route path="/verify" element={bare(<Verify />)} />
        <Route path="/reward" element={shell(<Reward />)} />
        <Route path="/profile" element={shell(<Profile />)} />
        <Route path="/chronicle" element={shell(<Chronicle />)} />
        <Route path="/settings" element={shell(<Settings />)} />
        {/* Hidden field-test tooling (P21): reachable by URL only, never linked. */}
        <Route path="/settings/export" element={shell(<Export />)} />
        <Route path="/map" element={shell(<MapPage />)} />
        {GemmaSpike ? <Route path="/spike/gemma" element={<GemmaSpike />} /> : null}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}

export function Providers({ children, client = queryClient }: { children: ReactNode; client?: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <QuestProvider>{children}</QuestProvider>
    </QueryClientProvider>
  )
}

export function App() {
  return (
    <ErrorBoundary>
      <Providers>
        <BrowserRouter>
          <AppRoutes />
          <UpdatePrompt />
        </BrowserRouter>
      </Providers>
    </ErrorBoundary>
  )
}
