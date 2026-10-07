import { Component, useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'

import { PORTRAIT } from './art'
import { BookIcon, GearIcon, HomeIcon, MapIcon, StarIcon, WifiOffIcon } from './Icons'
import { World } from './World'
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

/** Compact HUD chip for the top bar: portrait, level, XP bar, streak. */
export function HudLevel() {
  const profile = useProfile()
  const persona = loadPrefs().persona
  const p = profile.data
  const prev = p ? 120 * p.level * p.level : 0
  return (
    <Link to="/profile" className="flex min-h-11 items-center gap-2 rounded-full bg-forest-deep/60 py-1 pr-4 pl-1 text-parchment-light no-underline hover:bg-forest-deep/80">
      <img src={PORTRAIT[persona]} alt="" className="h-10 w-10 rounded-full border-2 border-gold-light object-cover" />
      {p ? (
        <span className="flex flex-col leading-none">
          <span className="text-base">
            Lv. {p.level}
            {p.streak_days > 0 ? <span className="ml-1.5 text-gold-light">· {p.streak_days}d streak</span> : null}
          </span>
          <span className="mt-1 hidden w-28 sm:block">
            <XpBar value={p.total_xp - prev} max={p.next_level_xp - prev} label="Level progress" />
          </span>
        </span>
      ) : (
        <span className="text-base">Explorer</span>
      )}
    </Link>
  )
}

/**
 * App frame: the illustrated world fills the window; a floating HUD bar (logo, nav, level)
 * sits on top on wide screens, a bottom tab bar on phones (≥ 44 px targets). Pages lay out
 * in wide multi-column grids over the scenery instead of one narrow column.
 */
export function AppShell({ children, tone = 'day' }: { children: ReactNode; tone?: 'day' | 'dusk' }) {
  return (
    <div className="relative min-h-dvh">
      <World tone={tone} className="fixed inset-0 z-0 h-full w-full" />
      <div className="relative z-10 flex min-h-dvh flex-col">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-parchment focus:p-2">
          Skip to content
        </a>
        <header className="sticky top-0 z-[1100] px-3 pt-3 lg:px-6">
          <div className="hud-bar mx-auto flex max-w-[1400px] items-center gap-3 px-3 py-2 lg:px-4">
            <Link to="/" className="logo-text shrink-0 text-xl no-underline xl:text-2xl" aria-label="Sidequestmaxxing story">
              Sidequestmaxxing
            </Link>
            <nav aria-label="Main" className="fixed inset-x-0 bottom-0 border-t-4 border-wood-dark bg-forest lg:static lg:flex-1 lg:border-0 lg:bg-transparent">
              <ul className="flex justify-around lg:justify-center lg:gap-1">
                {NAV.map(({ to, label, Icon }) => (
                  <li key={to}>
                    <NavLink
                      to={to}
                      className={({ isActive }) =>
                        `flex min-h-14 min-w-12 flex-col items-center justify-center gap-0.5 rounded-xl px-1.5 py-1 text-[0.8rem] no-underline sm:min-w-14 sm:px-2 sm:text-sm lg:min-h-11 lg:flex-row lg:gap-1.5 lg:px-3 lg:text-base xl:gap-2 xl:px-4 xl:text-lg ${
                          isActive ? 'bg-parchment text-ink shadow-md' : 'text-parchment-deep hover:bg-forest-soft'
                        }`
                      }
                    >
                      <Icon className="text-2xl lg:text-xl" />
                      {label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </nav>
            <div className="ml-auto lg:ml-0">
              <HudLevel />
            </div>
          </div>
        </header>
        <OfflineBanner />
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1400px] flex-1 px-4 pt-5 pb-28 lg:px-6 lg:pt-6 lg:pb-10">
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
