import './story.css'

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { ART, PORTRAIT } from '../components/art'
import {
  ArrowRightIcon,
  CompassIcon,
  GearIcon,
  HeadphonesIcon,
  LeafIcon,
  LockIcon,
  PhoneIcon,
  PlayIcon,
  StopIcon,
  XIcon,
} from '../components/Icons'
import { Medallion } from '../components/Medallion'
import { Waveform } from '../components/Waveform'
import { World } from '../components/World'
import { SKILL_LABEL } from '../lib/labels'
import { loadPrefs } from '../lib/prefs'
import { canSpeak } from '../lib/speech'
import { speakText, stopVoice } from '../lib/voice'
import { CATEGORIES } from '../lib/types'
import storyData from './data.json'
import type { StoryData } from './types'

export const REPO_URL = 'https://github.com/aarushitandon0/sidequestmaxxing'

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

/**
 * One scroll listener and one rAF loop drive every scene on the page.
 *
 * Each on-screen scene gets `--progress` (0..1) written onto its element, eased toward the
 * scroll-derived target with a time constant, so coarse wheel and trackpad steps arrive as
 * smooth motion instead of jumps. Off-screen scenes are unregistered and cost nothing, the
 * loop parks itself once every scene has settled, and `onProgress` is quantised so a scene
 * that keeps React state does not re-render once per frame.
 */
type SceneState = {
  el: HTMLElement
  target: number
  eased: number
  written: number
  sent: number
  onProgress?: (p: number) => void
}

const live = new Set<SceneState>()
let frame = 0
let stamp = 0

function measure(s: SceneState) {
  const r = s.el.getBoundingClientRect()
  const span = Math.max(1, r.height - window.innerHeight)
  s.target = Math.min(1, Math.max(0, -r.top / span))
}

function write(s: SceneState) {
  if (Math.abs(s.eased - s.written) < 0.001) return
  s.written = s.eased
  s.el.style.setProperty('--progress', s.eased.toFixed(4))
  const step = Math.round(s.eased * 12) / 12
  if (step !== s.sent) {
    s.sent = step
    s.onProgress?.(step)
  }
}

function tick(now: number) {
  frame = 0
  const dt = Math.min(64, stamp ? now - stamp : 16)
  stamp = now
  const k = 1 - Math.exp(-dt / 70)
  let moving = false
  for (const s of live) {
    measure(s)
    const d = s.target - s.eased
    s.eased = Math.abs(d) < 0.001 ? s.target : s.eased + d * k
    write(s)
    if (s.eased !== s.target) moving = true
  }
  if (moving) wake()
}

function wake() {
  if (!frame && live.size) frame = requestAnimationFrame(tick)
}

function onScroll() {
  stamp = 0
  wake()
}

function listen(on: boolean) {
  if (on) {
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
  } else {
    window.removeEventListener('scroll', onScroll)
    window.removeEventListener('resize', onScroll)
  }
}

/**
 * Registers one scene with the shared loop. The DEFAULT stays `--progress: 1` (final state),
 * so the page is readable without JS, and reduced motion opts out entirely.
 */
function useSceneProgress(onProgress?: (p: number) => void) {
  const ref = useRef<HTMLElement | null>(null)
  const cb = useRef(onProgress)
  useEffect(() => {
    cb.current = onProgress
  })
  useEffect(() => {
    const el = ref.current
    if (!el || reducedMotion() || typeof IntersectionObserver === 'undefined') return
    const state: SceneState = {
      el,
      target: 0,
      eased: 0,
      written: -1,
      sent: -1,
      onProgress: (p) => cb.current?.(p),
    }
    // Land on the measured value instead of animating in from 0 on first paint.
    measure(state)
    state.eased = state.target
    write(state)
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          if (!live.size) listen(true)
          measure(state)
          live.add(state)
          wake()
        } else {
          live.delete(state)
          if (!live.size) listen(false)
        }
      },
      // Wake a scene slightly before it enters, so nothing pops in half-animated.
      { rootMargin: '20% 0px' },
    )
    io.observe(el)
    return () => {
      io.disconnect()
      live.delete(state)
      // Hand the scene back to the stylesheet's --progress: 1 (its final, readable state).
      el.style.removeProperty('--progress')
      if (!live.size) {
        listen(false)
        if (frame) cancelAnimationFrame(frame)
        frame = 0
      }
    }
  }, [])
  return ref
}

/**
 * A scene sits on the same world as the hero: the World SVG fills the stage behind the
 * content (parallaxed by --progress), under a veil that is bright where the text sits and
 * clear at the seams, so the scenery reads as one continuous landscape down the page.
 * `world` only shifts/scales that SVG, so each scene looks out at a different stretch of it.
 */
function Scene({
  id,
  label,
  children,
  short = false,
  className = '',
  tone = 'day',
  world = '',
  onProgress,
}: {
  id: string
  label: string
  children: ReactNode
  short?: boolean
  className?: string
  tone?: 'day' | 'dusk'
  world?: string
  onProgress?: (p: number) => void
}) {
  const ref = useSceneProgress(onProgress)
  return (
    <section ref={ref} id={id} aria-labelledby={`${id}-title`} data-scene={id} className={`scene ${short ? 'scene-short' : ''} ${className}`}>
      <div className="scene-stage">
        <div className="scene-world" aria-hidden="true">
          <World tone={tone} className={`h-full w-full ${world}`} />
          <div className="scene-veil" />
        </div>
        <div className="mx-auto w-full max-w-6xl">{children}</div>
      </div>
      <span className="sr-only">{label}</span>
    </section>
  )
}

const at = (n: number) => ({ '--at': n }) as CSSProperties

function StoryNav() {
  return (
    <nav aria-label="Story" className="absolute inset-x-0 top-0 z-20 px-3 pt-3 md:px-6">
      <div className="hud-bar mx-auto flex max-w-[1400px] items-center gap-1 px-3 py-2 text-parchment-light sm:gap-3 md:px-4">
        <span className="logo-text hidden text-xl sm:inline md:text-2xl" aria-hidden="true">
          Sidequestmaxxing
        </span>
        <span className="flex-1" />
        <Link to="/home" className="min-h-11 rounded-xl px-3 py-2 no-underline hover:bg-forest-soft">Quests</Link>
        <Link to="/profile" className="min-h-11 rounded-xl px-3 py-2 no-underline hover:bg-forest-soft">Skills</Link>
        <Link to="/chronicle" className="min-h-11 rounded-xl px-3 py-2 no-underline hover:bg-forest-soft">Chronicle</Link>
        <Link to="/settings" className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl text-2xl hover:bg-forest-soft" aria-label="Settings">
          <GearIcon />
        </Link>
      </div>
    </nav>
  )
}

function StartLink({ className = '' }: { className?: string }) {
  const to = loadPrefs().onboarded ? '/home' : '/onboarding'
  return (
    <Link to={to} className={`btn btn-wood text-xl ${className}`}>
      Start your first quest <ArrowRightIcon />
    </Link>
  )
}

/* ---------------------------------------------------------------- 1. Hero */
function Hero() {
  return (
    <section id="hero" aria-labelledby="hero-title" data-scene="hero" className="scene scene-short relative overflow-hidden">
      <World className="absolute inset-0 h-full w-full" />
      <StoryNav />
      <div className="relative mx-auto grid min-h-dvh max-w-[1400px] grid-cols-1 items-center gap-8 px-4 pt-28 pb-16 lg:grid-cols-[1.05fr_1fr] lg:gap-12 lg:px-8">
        <div className="text-center lg:text-left">
          <h1 id="hero-title" className="logo-text text-4xl sm:text-7xl xl:text-8xl">
            Sidequestmaxxing
          </h1>
          <p className="hand-title mt-4 text-2xl sm:text-3xl xl:text-4xl">
            Real places. Meaningful quests.
            <br />A more interesting you.
          </p>
          <p className="mx-auto mt-4 max-w-xl rounded-2xl bg-parchment-light/85 px-4 py-3 text-lg text-ink-soft lg:mx-0">
            Your neighbourhood is full of side quests… you just need a reason to explore. Sidequestmaxxing means chasing
            fun, unexpected, secondary goals outside your routine, to build skills, break monotony, and spark joy.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3 lg:justify-start">
            <StartLink className="py-4 text-2xl" />
            <a href="#problem" className="btn btn-ghost">
              See how it works
            </a>
          </div>
        </div>
        <div className="parchment-frame hero-art mx-auto w-full max-w-2xl rotate-[-1deg]">
          <img
            src={ART.heroScene}
            decoding="async"
            fetchPriority="high"
            width={704}
            height={226}
            className="aspect-[704/226] w-full rounded-2xl object-cover"
            alt="An explorer with a backpack and a dog sit on a rock above a sunny old town with a river, castle and mountains. Signposts read Explore, Learn, Grow."
          />
        </div>
      </div>
      <span className="scroll-cue" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
          <path d="M5 8l7 7 7-7" />
        </svg>
      </span>
    </section>
  )
}

/* ---------------------------------------------------------------- 2. The problem */
function Problem() {
  return (
    <Scene id="problem" label="Scene 2 of 8" world="world-a">
      <div className="grid items-center gap-8 md:grid-cols-2">
        <div className="mx-auto h-[232px] w-[140px] overflow-hidden rounded-[1.8rem] border-[6px] border-ink bg-parchment-light p-2 sm:h-[420px] sm:w-[220px] sm:rounded-[2.2rem] sm:border-8" aria-hidden="true">
          <div className="feed flex flex-col gap-2">
            {Array.from({ length: 14 }, (_, i) => (
              <div key={i} className="rounded-xl bg-parchment-deep p-2">
                <div className="h-16 rounded-lg bg-edge/50" />
                <div className="mt-2 h-2 w-3/4 rounded bg-edge/70" />
                <div className="mt-1 h-2 w-1/2 rounded bg-edge/50" />
              </div>
            ))}
          </div>
        </div>
        <div>
          <h2 id="problem-title" className="hand-title text-3xl sm:text-4xl">
            Most “outdoor” apps are maps you stare at.
          </h2>
          <p className="mt-2 text-lg sm:mt-3 sm:text-xl">
            This week's challenge rule shaped everything: <strong>the screen must be the shortest part</strong> of the
            experience. So Sidequestmaxxing is designed backwards: minimum screen, maximum time outside.
          </p>
          <div className="mt-4 sm:mt-5">
            <p className="flex items-center gap-2 text-base sm:text-lg">
              <PhoneIcon /> Screen time while scrolling a feed
            </p>
            <div className="xp-track mt-1 h-4">
              <div className="screen-bar h-full rounded-full bg-berry" />
            </div>
          </div>
        </div>
      </div>
    </Scene>
  )
}

/* ---------------------------------------------------------------- 3. The Dungeon Master */
const DEMO_BRIEFING =
  'A local spot with a hidden story. Find the old stone marker by the river and look for a particular leaf growing in the cracks.'

function DungeonMaster() {
  const [playing, setPlaying] = useState(false)
  useEffect(() => () => stopVoice(), [])
  // Uses the pre-generated demo clip when present (scripts/pregen_demo_audio.py), else browser voice.
  const listen = () => {
    if (playing) {
      stopVoice()
      setPlaying(false)
      return
    }
    setPlaying(true)
    void speakText(DEMO_BRIEFING, 'dramatic', () => setPlaying(false)).then((src) => {
      if (src === 'none') setPlaying(false)
    })
  }
  return (
    <Scene id="dm" label="Scene 3 of 8" world="world-b">
      <h2 id="dm-title" className="hand-title text-center text-3xl sm:text-4xl">
        Your Dungeon Master writes one quest for a real place near you.
      </h2>
      <p className="mx-auto mt-2 max-w-2xl text-center text-base text-ink-soft sm:text-lg">
        An open-weight model picks from real nearby places and writes a short, safe, spoken briefing. Example quest:
      </p>
      <div className="parchment mx-auto mt-4 grid max-w-3xl gap-3 p-3 sm:mt-5 sm:gap-4 sm:p-4 sm:grid-cols-[150px_1fr]">
        <img src={ART.sceneRiver} alt="" loading="lazy" decoding="async" className="beat hidden w-full rounded-xl object-cover sm:block sm:h-full" style={at(0)} />
        <div>
          <p className="beat text-2xl sm:text-3xl" style={at(0.1)}>The Riverbank Riddle</p>
          <ul className="beat mt-1 flex flex-wrap gap-2" style={at(0.25)}>
            <li className="chip">Nature</li>
            <li className="chip">Observation</li>
            <li className="chip">15 min</li>
          </ul>
          <div className="beat mt-2 flex items-start gap-2 sm:mt-3 sm:gap-3" style={at(0.4)}>
            <img src={PORTRAIT.chill} alt="" loading="lazy" decoding="async" className="h-11 w-11 rounded-full border-2 border-edge sm:h-14 sm:w-14" />
            <div className="bubble flex-1 max-sm:px-3 max-sm:py-2">
              <p>{DEMO_BRIEFING}</p>
              {canSpeak() ? (
                <div className="mt-1 flex items-center gap-3 text-moss">
                  <button type="button" onClick={listen} aria-pressed={playing}
                    aria-label={playing ? 'Stop the example briefing' : 'Listen to the example briefing'}
                    className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-moss text-parchment-light">
                    {playing ? <StopIcon /> : <PlayIcon />}
                  </button>
                  <Waveform active={playing} />
                </div>
              ) : null}
            </div>
          </div>
          <p className="beat mt-2 rounded-xl bg-parchment-light p-2 text-base sm:mt-3 sm:text-lg" style={at(0.6)}>
            <strong>Safety:</strong> stay on the path and keep away from the water's edge.
          </p>
        </div>
      </div>
    </Scene>
  )
}

/* ---------------------------------------------------------------- 4. Walk Mode */
function WalkScene() {
  return (
    <Scene id="walk" label="Scene 4 of 8" tone="dusk" world="world-c" className="text-parchment-light">
      <div className="walk-dim pointer-events-none absolute inset-0 bg-forest-deep" aria-hidden="true" />
      <div className="relative grid items-center gap-8 md:grid-cols-2">
        <svg viewBox="0 0 400 300" className="w-full rounded-3xl border-4 border-edge bg-parchment" role="img"
          aria-label="A stylised map: a dotted route draws itself from your door to a riverside quest pin.">
          <path d="M0 210 C80 180 120 240 200 200 S320 150 400 180 L400 300 L0 300Z" fill="#a4ccec" opacity=".8" />
          <path d="M40 60 H360 M80 20 V280 M240 20 V280 M20 140 H380" stroke="#e5cf9f" strokeWidth="10" />
          <g fill="#6b8f5e" opacity=".8">
            <circle cx="150" cy="80" r="16" /><circle cx="170" cy="95" r="12" /><circle cx="300" cy="90" r="18" />
            <circle cx="320" cy="110" r="12" /><circle cx="60" cy="250" r="14" />
          </g>
          <path className="route" d="M70 250 C110 220 120 170 160 150 S240 120 260 90 S300 60 320 50" fill="none" stroke="#3b2a1e"
            strokeWidth="5" strokeLinecap="round" strokeDasharray="1000" />
          <g className="pop" style={at(0.05)}><circle cx="70" cy="250" r="10" fill="#e8a33d" stroke="#fdf3e2" strokeWidth="3" /></g>
          <g className="pop" style={at(0.45)}><circle cx="160" cy="150" r="7" fill="#436440" stroke="#fdf3e2" strokeWidth="3" /></g>
          <g className="pop" style={at(0.85)}>
            <path d="M320 50 c-12 0-20 9-20 20 0 15 20 32 20 32 s20-17 20-32c0-11-8-20-20-20Z" fill="#436440" stroke="#fdf3e2" strokeWidth="3" />
          </g>
        </svg>
        <div>
          <h2 id="walk-title" className="text-3xl sm:text-4xl">Walk Mode: the screen goes dark.</h2>
          <p className="mt-2 text-lg sm:mt-3 sm:text-xl">
            Accept, pocket the phone, go. The Dungeon Master briefs you out loud; Walk Mode is a near-black screen with a
            timer and one big “I'm back” button. No wake lock, no map to stare at.
          </p>
          <p className="mt-3 flex items-center gap-2 text-base sm:text-lg">
            <HeadphonesIcon /> Your quest is live. Keep your phone in your pocket and explore.
          </p>
        </div>
      </div>
    </Scene>
  )
}

/* ---------------------------------------------------------------- 5. Verified on your device */
function VerifiedScene() {
  return (
    <Scene id="verified" label="Scene 5 of 8" world="world-d">
      <div className="grid items-center gap-8 md:grid-cols-2">
        <div className="relative mx-auto h-[230px] w-[135px] sm:h-[380px] sm:w-[220px]" aria-hidden="true">
          <div className="absolute inset-0 rounded-[1.8rem] border-[6px] border-ink bg-forest sm:rounded-[2.2rem] sm:border-8" />
          <div className="absolute inset-2 overflow-hidden rounded-[1.3rem] sm:inset-3 sm:rounded-[1.6rem]">
            <img src={ART.sceneVerify} alt="" loading="lazy" decoding="async" className="photo-in h-full w-full object-cover" />
          </div>
          <div className="blocked absolute -top-4 -right-12 flex flex-col items-center text-berry sm:-top-6 sm:-right-16">
            <span className="rounded-full bg-parchment-light p-2 text-3xl shadow"><XIcon /></span>
            <span className="text-sm">upload</span>
          </div>
        </div>
        <div>
          <h2 id="verified-title" className="hand-title text-3xl sm:text-4xl">
            Verified on your device.
          </h2>
          <p className="mt-2 text-lg sm:mt-3 sm:text-xl">
            Take one photo. An open Gemma model running in your browser checks it, and the photo never leaves your phone.
            There is no upload endpoint at all.
          </p>
          <p className="mt-3 rounded-xl border-2 border-edge bg-parchment-light p-2 text-base sm:p-3 sm:text-lg">
            <LockIcon className="mr-1 inline" />
            Photos and exact movements stay on your device; the server sees an approximate area to find nearby places.
          </p>
          <p className="mt-2 text-sm text-ink-soft sm:text-base">
            No WebGPU or no download? Check in at the place, or use honor mode for half XP. (It's single-player, so a
            spoofed check only fools yourself.)
          </p>
        </div>
      </div>
    </Scene>
  )
}

/* ---------------------------------------------------------------- 6. Skill tree */
const EXAMPLE_LEVELS = [2, 3, 1, 1, 2, 1, 2] // illustrative animation only — not player data

function SkillScene() {
  const [p, setP] = useState(1)
  return (
    <Scene id="skills" label="Scene 6 of 8" world="world-b" onProgress={setP}>
      <h2 id="skills-title" className="hand-title text-center text-3xl sm:text-4xl">
        Grow seven skills by living them.
      </h2>
      <p className="text-center text-base text-ink-soft sm:text-lg">
        XP, levels and rarity are computed by the server, never by the model. (Levels shown are an example.)
      </p>
      <ul className="parchment mx-auto mt-4 grid max-w-3xl grid-cols-4 gap-3 p-3 sm:mt-6 sm:gap-5 sm:p-6">
        {CATEGORIES.map((c, i) => (
          <li key={c} className="branch flex flex-col items-center text-center" style={at(i * 0.09)}>
            <Medallion category={c} size={64} />
            <span className="mt-1 text-sm leading-tight sm:text-lg">{SKILL_LABEL[c]}</span>
            <span className="text-sm text-ink-soft sm:text-base">Lv. {Math.round(EXAMPLE_LEVELS[i]! * Math.min(1, p * 1.4))}</span>
          </li>
        ))}
      </ul>
    </Scene>
  )
}

/* ---------------------------------------------------------------- 7. Receipts */
export function Receipts({ data }: { data: StoryData }) {
  if (!data.results && !data.field) return null
  return (
    <Scene id="receipts" label="Scene 7 of 8" short world="world-a">
      <h2 id="receipts-title" className="hand-title text-center text-4xl">
        Receipts
      </h2>
      <p className="text-center text-ink-soft">Every number here is copied from the repo's eval files at build time.</p>
      {data.results ? (
        <div className="parchment mx-auto mt-5 max-w-3xl overflow-x-auto p-4">
          <table className="w-full text-left text-lg">
            <caption className="pb-2 text-ink-soft">
              Baseline vs fine-tuned{data.results.n != null ? ` (n=${data.results.n} held-out contexts)` : ''}. Source:{' '}
              {data.results.source}
            </caption>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Baseline</th>
                <th scope="col">Tuned</th>
              </tr>
            </thead>
            <tbody>
              {data.results.metrics.map((m) => (
                <tr key={m.label} className="border-t border-edge/50">
                  <th scope="row" className="py-1 font-normal">{m.label}</th>
                  <td>{m.baseline ?? '—'}{m.unit && m.baseline != null ? ` ${m.unit}` : ''}</td>
                  <td>{m.tuned ?? '—'}{m.unit && m.tuned != null ? ` ${m.unit}` : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {data.field ? (
        <div className="parchment mx-auto mt-5 max-w-3xl p-4">
          <h3 className="text-2xl">From the field</h3>
          <dl className="mt-2 grid gap-2 sm:grid-cols-2">
            {data.field.rows.map((r) => (
              <div key={r.label} className="rounded-xl bg-parchment-light p-2">
                <dt className="text-ink-soft">{r.label}</dt>
                <dd className="text-2xl">{r.value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-sm text-ink-soft">Source: {data.field.source}</p>
        </div>
      ) : null}
    </Scene>
  )
}

/* ---------------------------------------------------------------- 8. Try it */
const STEPS = [
  ['1. You get a quest', 'The Dungeon Master sets the scene.'],
  ['2. You head out', 'The world becomes your map.'],
  ['3. You explore', 'Look closer. Notice more.'],
  ['4. You verify', 'One photo. On your device.'],
  ['5. You’re rewarded', 'XP, new skills, new stories.'],
] as const

function TryIt() {
  return (
    <Scene id="try" label="Scene 8 of 8" short tone="dusk" world="world-c">
      <div className="rounded-3xl bg-parchment-light/60 p-4">
        <h2 id="try-title" className="hand-title text-3xl">
          The Quest Unfolds <span className="text-lg text-ink-soft">A little story, told as you go.</span>
        </h2>
        <ol className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {STEPS.map(([title, line], i) => (
            <li key={title} className="reveal flex flex-col">
              <img src={ART.story[i]} alt="" loading="lazy" decoding="async" className="h-28 w-full rounded-t-xl object-cover" />
              <div className="parchment -mt-2 flex-1 p-2">
                <p className="text-lg leading-tight">{title}</p>
                <p className="text-sm text-ink-soft">{line}</p>
              </div>
            </li>
          ))}
          <li className="reveal parchment flex flex-col items-center justify-center p-3 text-center text-xl">
            Same place.
            <br />
            New story.
            <span className="mt-2 text-2xl">Every day.</span>
            <LeafIcon className="mt-2 text-moss" />
          </li>
        </ol>
      </div>

      <div className="mt-8 text-center">
        <StartLink />
        <p className="mt-4 flex flex-wrap justify-center gap-4 text-lg">
          <a className="underline" href={REPO_URL}>github.com/aarushitandon0/sidequestmaxxing</a>
        </p>
      </div>

      <ul className="mt-8 grid grid-cols-2 gap-4 text-ink-soft sm:grid-cols-5" aria-label="Features">
        <li className="flex items-center gap-2"><LeafIcon className="text-2xl text-moss" /> Real-world quests</li>
        <li className="flex items-center gap-2"><HeadphonesIcon className="text-2xl text-moss" /> Voice-led adventure</li>
        <li className="flex items-center gap-2"><PhoneIcon className="text-2xl text-moss" /> Minimal screen time</li>
        <li className="flex items-center gap-2"><LockIcon className="text-2xl text-moss" /> On-device privacy</li>
        <li className="flex items-center gap-2"><CompassIcon className="text-2xl text-moss" /> Open source</li>
      </ul>

      <footer className="mt-8 border-t border-edge/50 pt-4 text-sm text-ink-soft">
        <p className="hand-title text-right text-2xl">Go outside. Level up.</p>
        <p className="mt-2">
          Map data © <a className="underline" href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors.
          Weather by <a className="underline" href="https://open-meteo.com/">Open-Meteo</a>. Photo checks: Gemma 3n under the
          Gemma Terms of Use. Fonts: Patrick Hand and Lilita One (SIL Open Font License). Not an emergency or navigation
          tool. Tell someone where you're going.
        </p>
      </footer>
    </Scene>
  )
}

/** Scrollytelling story (MASTERSPEC §11.4) — the public landing at / and /story. */
export default function Story() {
  return (
    <div className="bg-page">
      <a href="#problem" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-parchment focus:p-2">
        Skip the intro
      </a>
      <div className="scroll-rail" aria-hidden="true">
        <span />
      </div>
      <main>
        <Hero />
        <Problem />
        <DungeonMaster />
        <WalkScene />
        <VerifiedScene />
        <SkillScene />
        <Receipts data={storyData as StoryData} />
        <TryIt />
      </main>
    </div>
  )
}
