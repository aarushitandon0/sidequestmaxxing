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
import { SKILL_LABEL } from '../lib/labels'
import { loadPrefs } from '../lib/prefs'
import { canSpeak, speak, stopSpeaking } from '../lib/speech'
import { CATEGORIES } from '../lib/types'
import storyData from './data.json'
import type { StoryData } from './types'

export const REPO_URL = 'https://github.com/aarushitandon0/sidequestmaxxing'
export const RENDER_DEPLOY_URL = `https://render.com/deploy?repo=${REPO_URL}`

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

/**
 * Writes --progress (0..1) onto the scene element while it is on screen. An
 * IntersectionObserver turns the scroll listener on/off, so off-screen scenes cost nothing.
 * No React re-render per frame unless `onProgress` is given.
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
    let raf = 0
    const update = () => {
      raf = 0
      const r = el.getBoundingClientRect()
      const span = Math.max(1, r.height - window.innerHeight)
      const p = Math.min(1, Math.max(0, -r.top / span))
      el.style.setProperty('--progress', p.toFixed(4))
      cb.current?.(p)
    }
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update)
    }
    const io = new IntersectionObserver(([entry]) => {
      if (entry?.isIntersecting) {
        window.addEventListener('scroll', onScroll, { passive: true })
        window.addEventListener('resize', onScroll)
        update()
      } else {
        window.removeEventListener('scroll', onScroll)
        window.removeEventListener('resize', onScroll)
      }
    })
    io.observe(el)
    update()
    return () => {
      io.disconnect()
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [])
  return ref
}

function Scene({
  id,
  label,
  children,
  short = false,
  className = '',
  onProgress,
}: {
  id: string
  label: string
  children: ReactNode
  short?: boolean
  className?: string
  onProgress?: (p: number) => void
}) {
  const ref = useSceneProgress(onProgress)
  return (
    <section ref={ref} id={id} aria-labelledby={`${id}-title`} data-scene={id} className={`scene ${short ? 'scene-short' : ''} ${className}`}>
      <div className="scene-stage">
        <div className="mx-auto w-full max-w-5xl">{children}</div>
      </div>
      <span className="sr-only">{label}</span>
    </section>
  )
}

const at = (n: number) => ({ '--at': n }) as CSSProperties

function StoryNav() {
  return (
    <nav aria-label="Story" className="absolute inset-x-0 top-0 z-20 flex items-center justify-end gap-1 px-4 py-3 text-ink sm:gap-4">
      <Link to="/home" className="min-h-11 px-2 py-2">Quests</Link>
      <Link to="/profile" className="min-h-11 px-2 py-2">Skills</Link>
      <Link to="/chronicle" className="min-h-11 px-2 py-2">Chronicle</Link>
      <Link to="/settings" className="inline-flex min-h-11 min-w-11 items-center justify-center text-2xl" aria-label="Settings">
        <GearIcon />
      </Link>
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
    <section id="hero" aria-labelledby="hero-title" data-scene="hero" className="scene scene-short relative hero-sky">
      <StoryNav />
      <div className="mx-auto max-w-5xl px-4 pt-20 text-center">
        <h1 id="hero-title" className="logo-text text-5xl sm:text-7xl">
          Sidequestmaxxing
        </h1>
        <p className="hand-title mt-4 text-2xl sm:text-3xl">
          Real places. Meaningful quests.
          <br />A more interesting you.
        </p>
        <StartLink className="mt-6" />
      </div>
      <div className="relative mx-auto mt-6 max-w-5xl overflow-hidden px-0 sm:px-4">
        <img
          src={ART.heroScene}
          width={704}
          height={226}
          className="hero-art w-full rounded-b-3xl object-cover"
          alt="An explorer with a backpack and a dog sit on a rock above a sunny old town with a river, castle and mountains. Signposts read Explore, Learn, Grow."
        />
      </div>
      <p className="mx-auto max-w-2xl px-4 py-6 text-center text-xl text-ink-soft">
        Your neighbourhood is full of side quests… you just need a reason to explore. Side quest maxxing means chasing fun,
        unexpected, secondary goals outside your routine — to build skills, break monotony, and spark joy.
      </p>
    </section>
  )
}

/* ---------------------------------------------------------------- 2. The problem */
function Problem() {
  return (
    <Scene id="problem" label="Scene 2 of 9">
      <div className="grid items-center gap-8 md:grid-cols-2">
        <div className="mx-auto h-[420px] w-[220px] overflow-hidden rounded-[2.2rem] border-8 border-ink bg-parchment-light p-2" aria-hidden="true">
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
          <h2 id="problem-title" className="hand-title text-4xl">
            Most “outdoor” apps are maps you stare at.
          </h2>
          <p className="mt-3 text-xl">
            This week's challenge rule shaped everything: <strong>the screen must be the shortest part</strong> of the
            experience. So Sidequestmaxxing is designed backwards — minimum screen, maximum time outside.
          </p>
          <div className="mt-5">
            <p className="flex items-center gap-2 text-lg">
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
  useEffect(() => () => stopSpeaking(), [])
  const listen = () => {
    if (playing) {
      stopSpeaking()
      setPlaying(false)
    } else if (speak(DEMO_BRIEFING, () => setPlaying(false))) setPlaying(true)
  }
  return (
    <Scene id="dm" label="Scene 3 of 9">
      <h2 id="dm-title" className="hand-title text-center text-4xl">
        Your Dungeon Master writes one quest — for a real place near you.
      </h2>
      <p className="mx-auto mt-2 max-w-2xl text-center text-lg text-ink-soft">
        An open-weight model picks from real nearby places and writes a short, safe, spoken briefing. Example quest:
      </p>
      <div className="parchment mx-auto mt-5 grid max-w-3xl gap-4 p-4 sm:grid-cols-[150px_1fr]">
        <img src={ART.sceneRiver} alt="" className="beat h-40 w-full rounded-xl object-cover sm:h-full" style={at(0)} />
        <div>
          <p className="beat text-3xl" style={at(0.1)}>The Riverbank Riddle</p>
          <ul className="beat mt-1 flex flex-wrap gap-2" style={at(0.25)}>
            <li className="chip">Nature</li>
            <li className="chip">Observation</li>
            <li className="chip">15 min</li>
          </ul>
          <div className="beat mt-3 flex items-start gap-3" style={at(0.4)}>
            <img src={PORTRAIT.chill} alt="" className="h-14 w-14 rounded-full border-2 border-edge" />
            <div className="bubble flex-1">
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
          <p className="beat mt-3 rounded-xl bg-parchment-light p-2" style={at(0.6)}>
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
    <Scene id="walk" label="Scene 4 of 9" className="text-parchment-light">
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
          <h2 id="walk-title" className="text-4xl">Walk Mode: the screen goes dark.</h2>
          <p className="mt-3 text-xl">
            Accept, pocket the phone, go. The Dungeon Master briefs you out loud; Walk Mode is a near-black screen with a
            timer and one big “I'm back” button. No wake lock, no map to stare at.
          </p>
          <p className="mt-3 flex items-center gap-2 text-lg">
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
    <Scene id="verified" label="Scene 5 of 9">
      <div className="grid items-center gap-8 md:grid-cols-2">
        <div className="relative mx-auto h-[380px] w-[220px]" aria-hidden="true">
          <div className="absolute inset-0 rounded-[2.2rem] border-8 border-ink bg-forest" />
          <div className="absolute inset-3 overflow-hidden rounded-[1.6rem]">
            <img src={ART.sceneVerify} alt="" className="photo-in h-full w-full object-cover" />
          </div>
          <div className="blocked absolute -top-6 -right-16 flex flex-col items-center text-berry">
            <span className="rounded-full bg-parchment-light p-2 text-3xl shadow"><XIcon /></span>
            <span className="text-sm">upload</span>
          </div>
        </div>
        <div>
          <h2 id="verified-title" className="hand-title text-4xl">
            Verified on your device.
          </h2>
          <p className="mt-3 text-xl">
            Take one photo. An open Gemma model running in your browser checks it — and the photo never leaves your phone.
            There is no upload endpoint at all.
          </p>
          <p className="mt-3 rounded-xl border-2 border-edge bg-parchment-light p-3 text-lg">
            <LockIcon className="mr-1 inline" />
            Photos and exact movements stay on your device; the server sees an approximate area to find nearby places.
          </p>
          <p className="mt-2 text-ink-soft">
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
    <Scene id="skills" label="Scene 6 of 9" onProgress={setP}>
      <h2 id="skills-title" className="hand-title text-center text-4xl">
        Grow seven skills by living them.
      </h2>
      <p className="text-center text-lg text-ink-soft">
        XP, levels and rarity are computed by the server — never by the model. (Levels shown are an example.)
      </p>
      <ul className="parchment mx-auto mt-6 grid max-w-3xl grid-cols-2 gap-5 p-6 sm:grid-cols-4">
        {CATEGORIES.map((c, i) => (
          <li key={c} className="branch flex flex-col items-center text-center" style={at(i * 0.09)}>
            <Medallion category={c} size={64} />
            <span className="mt-1 text-lg">{SKILL_LABEL[c]}</span>
            <span className="text-ink-soft">Lv. {Math.round(EXAMPLE_LEVELS[i]! * Math.min(1, p * 1.4))}</span>
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
    <Scene id="receipts" label="Scene 7 of 9" short>
      <h2 id="receipts-title" className="hand-title text-center text-4xl">
        Receipts
      </h2>
      <p className="text-center text-ink-soft">Every number here is copied from the repo's eval files at build time.</p>
      {data.results ? (
        <div className="parchment mx-auto mt-5 max-w-3xl overflow-x-auto p-4">
          <table className="w-full text-left text-lg">
            <caption className="pb-2 text-ink-soft">
              Baseline vs fine-tuned{data.results.n != null ? ` (n=${data.results.n} held-out contexts)` : ''} — source:{' '}
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

/* ---------------------------------------------------------------- 8. Open vs closed */
const OPEN = [
  ['Open-weight Dungeon Master', 'a small open model we can fine-tune, export and self-host, served by llama.cpp'],
  ['llama.cpp', 'the inference runtime; the same binary runs on a laptop'],
  ['Gemma 3n in the browser', 'on-device photo checks, so photos stay on the phone'],
  ['OpenStreetMap, Overpass, Open-Meteo', 'open data, no API key, no per-call cost'],
  ['BGE-small embeddings (fastembed)', 'semantic place search on a CPU'],
] as const
const HOSTED = [
  ['Render', 'hosting for the web app, API and the private model service'],
  ['MongoDB Atlas', 'places, quests and vector search'],
  ['ElevenLabs', 'the spoken voice (falls back to your browser’s voice)'],
  ['Sentry', 'tracing'],
  ['Tinker', 'the fine-tuning service'],
] as const

function OpenClosed() {
  return (
    <Scene id="open" label="Scene 8 of 9" short>
      <h2 id="open-title" className="hand-title text-center text-4xl">
        What's open, and what's hosted
      </h2>
      <p className="mx-auto max-w-2xl text-center text-lg text-ink-soft">
        The core intelligence is open-weight and exportable. Every hosted piece has a fallback, so the game keeps working
        when one goes down.
      </p>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <div className="parchment p-4">
          <h3 className="flex items-center gap-2 text-2xl text-moss"><LeafIcon /> Open</h3>
          <ul className="mt-2 space-y-2">
            {OPEN.map(([name, why]) => (
              <li key={name}><strong>{name}</strong> — {why}</li>
            ))}
          </ul>
        </div>
        <div className="parchment p-4">
          <h3 className="flex items-center gap-2 text-2xl text-wood"><CompassIcon /> Hosted / closed</h3>
          <ul className="mt-2 space-y-2">
            {HOSTED.map(([name, why]) => (
              <li key={name}><strong>{name}</strong> — {why}</li>
            ))}
          </ul>
        </div>
      </div>
    </Scene>
  )
}

/* ---------------------------------------------------------------- 9. Try it */
const STEPS = [
  ['1. You get a quest', 'The Dungeon Master sets the scene.'],
  ['2. You head out', 'The world becomes your map.'],
  ['3. You explore', 'Look closer. Notice more.'],
  ['4. You verify', 'One photo. On your device.'],
  ['5. You’re rewarded', 'XP, new skills, new stories.'],
] as const

function TryIt() {
  return (
    <Scene id="try" label="Scene 9 of 9" short>
      <div className="rounded-3xl bg-parchment-light/60 p-4">
        <h2 id="try-title" className="hand-title text-3xl">
          The Quest Unfolds <span className="text-lg text-ink-soft">A little story, told as you go.</span>
        </h2>
        <ol className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {STEPS.map(([title, line], i) => (
            <li key={title} className="reveal flex flex-col">
              <img src={ART.story[i]} alt="" className="h-28 w-full rounded-t-xl object-cover" />
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
          <a className="underline" href={REPO_URL}>Source code on GitHub</a>
          <a className="underline" href={RENDER_DEPLOY_URL}>Deploy your own on Render</a>
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
          tool — tell someone where you're going.
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
      <main>
        <Hero />
        <Problem />
        <DungeonMaster />
        <WalkScene />
        <VerifiedScene />
        <SkillScene />
        <Receipts data={storyData as StoryData} />
        <OpenClosed />
        <TryIt />
      </main>
    </div>
  )
}
