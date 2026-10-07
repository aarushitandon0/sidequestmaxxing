import { Component, useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'

import { PORTRAIT } from './art'
import { BookIcon, GearIcon, HomeIcon, MapIcon, StarIcon, WifiOffIcon } from './Icons'
import { XpBar } from './XpBar'
import { useOnline, useProfile } from '../state/hooks'
import { loadPrefs } from '../lib/prefs'

const NAV = [
  { to: '/home', label: 'Quests', Icon: HomeIcon },
  { to: '/map', label: 'Map', Icon: MapIcon },
  { to: '/profile', label: 'Skills', Icon: StarIcon },
  { to: '/chronicle', label: 'Chronicle', Icon: BookIcon },
  { to: '/settings', label: 'Settings', Icon: GearIcon },
] as const

export function Logo({ className = '' }: { className?: string }) {
  return (
    <Link to="/" className={`inline-block no-underline ${className}`} aria-label="Sidequestmaxxing — story">
      <span className="logo-text text-2xl">Sidequestmaxxing</span>
    </Link>
  )
}

export function OfflineBanner() {
  const online = useOnline()
  if (online) return null
  return (
    <div role="status" className="flex items-center justify-center gap-2 bg-wood-dark px-4 py-2 text-wood-text">
      <WifiOffIcon /> You're offline. Your active quest still works — rewards sync when you're back.
    </div>
  )
}

/** "Lv. 3 Explorer" card (design template, top right). */
export function LevelCard() {
  const profile = useProfile()
  const persona = loadPrefs().persona
  if (!profile.data) return null
  const p = profile.data
  const prev = 120 * p.level * p.level
  return (
    <div className="parchment flex items-center gap-3 px-3 py-2">
      <img src={PORTRAIT[persona]} alt="" className="h-12 w-12 rounded-full border-2 border-edge object-cover" />
      <div className="min-w-36">
        <p className="leading-none">
          Lv. {p.level} Explorer
          {p.streak_days > 0 ? <span className="ml-2 text-ink-soft">· {p.streak_days}-day streak</span> : null}
        </p>
        <div className="mt-1.5">
          <XpBar value={p.total_xp - prev} max={p.next_level_xp - prev} label="Overall level progress" />
        </div>
        <p className="mt-0.5 text-right text-sm text-ink-soft">
          {p.total_xp} / {p.next_level_xp} XP
        </p>
      </div>
    </div>
  )
}

/** App frame: wooden sidebar on wide screens, bottom tab bar on phones (≥ 44 px targets). */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh md:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-parchment focus:p-2">
        Skip to content
      </a>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-[1100] border-t-4 border-wood-dark bg-forest md:sticky md:top-0 md:h-dvh md:w-28 md:border-t-0 md:border-r-4"
      >
        <div className="hidden px-2 pt-4 pb-6 text-center md:block">
          <Link to="/" className="logo-text block text-base leading-tight" aria-label="Sidequestmaxxing story">
            Side
            <br />
            quest
            <br />
            maxxing
          </Link>
        </div>
        <ul className="flex justify-around md:flex-col md:gap-2 md:px-2">
          {NAV.map(({ to, label, Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  `flex min-h-14 min-w-14 flex-col items-center justify-center gap-0.5 rounded-xl px-2 py-1 text-sm no-underline md:py-3 ${
                    isActive ? 'bg-parchment text-ink shadow-md' : 'text-parchment-deep hover:bg-forest-soft'
                  }`
                }
              >
                <Icon className="text-2xl" />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex-1 pb-24 md:pb-0">
        <OfflineBanner />
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-5xl px-4 py-5 md:px-8 md:py-8">
          {children}
        </main>
      </div>
    </div>
  )
}

interface EBState {
  error: Error | null
}

export class ErrorBoundary extends Component<{ children: ReactNode }, EBState> {
  state: EBState = { error: null }

  // No PII: nothing is reported anywhere yet (frontend Sentry is P19).
  static getDerivedStateFromError(error: Error): EBState {
    return { error }
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <main className="mx-auto max-w-md p-6">
        <div className="parchment p-6 text-center" role="alert">
          <h1 className="hand-title text-3xl">A branch fell on the path.</h1>
          <p className="mt-2">Something broke on our side. Your active quest is saved.</p>
          <button type="button" className="btn btn-wood mt-4" onClick={() => window.location.assign('/home')}>
            Back to the quest board
          </button>
        </div>
      </main>
    )
  }
}

/** PWA update prompt: shown when a new service worker is waiting (see main.tsx). */
export function UpdatePrompt() {
  const [update, setUpdate] = useState<null | (() => void)>(null)
  useEffect(() => {
    const onReady = (e: Event) => setUpdate(() => (e as CustomEvent<() => void>).detail)
    window.addEventListener('sqm:update-ready', onReady)
    return () => window.removeEventListener('sqm:update-ready', onReady)
  }, [])
  if (!update) return null
  return (
    <div role="status" className="parchment fixed right-4 bottom-24 left-4 z-[1200] flex items-center gap-3 p-3 md:left-auto md:w-96">
      <p className="flex-1">A fresh version of the realm is ready.</p>
      <button type="button" className="btn btn-moss" onClick={update}>
        Reload
      </button>
      <button type="button" className="btn btn-ghost" onClick={() => setUpdate(null)} aria-label="Dismiss update">
        Later
      </button>
    </div>
  )
}
