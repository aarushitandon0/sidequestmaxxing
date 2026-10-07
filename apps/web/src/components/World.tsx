/**
 * The game world behind every screen: sky, sun, drifting clouds, mountains, rolling hills,
 * a tree line and grass — drawn as one inline SVG so it stays crisp on any screen size
 * (the template art is small; this scales to a 4K monitor for ~4 KB). Purely decorative.
 * `slice` keeps the horizon anchored to the bottom while wide screens show more sky/land.
 */

type Tone = 'day' | 'dusk'

const SKY: Record<Tone, [string, string, string]> = {
  day: ['#86c0e8', '#cfe6f1', '#f7ecd6'],
  dusk: ['#f2b179', '#f8d6a4', '#fbeacc'],
}

// Deterministic tree positions along the mid-hill crest (no randomness → stable renders).
const TREES = Array.from({ length: 34 }, (_, i) => {
  const x = i * 49 + ((i * 37) % 23)
  const y = 640 - 38 * Math.sin((x / 1600) * Math.PI * 2.2 + 0.6) - ((i * 13) % 9)
  const r = 16 + ((i * 7) % 12)
  return { x, y, r, dark: i % 3 === 0 }
})

const BLADES = Array.from({ length: 70 }, (_, i) => ({ x: i * 23 + ((i * 11) % 9), h: 10 + ((i * 17) % 16) }))

function Cloud({ x, y, s = 1, className = '' }: { x: number; y: number; s?: number; className?: string }) {
  return (
    <g className={className} transform={`translate(${x} ${y}) scale(${s})`} fill="#fffaf0">
      <ellipse cx="0" cy="20" rx="78" ry="22" opacity="0.95" />
      <circle cx="-34" cy="8" r="26" />
      <circle cx="4" cy="-4" r="36" />
      <circle cx="42" cy="10" r="24" />
      <ellipse cx="0" cy="30" rx="70" ry="10" fill="#dbe8ef" opacity="0.7" />
    </g>
  )
}

export function World({ tone = 'day', className = '' }: { tone?: Tone; className?: string }) {
  const [top, mid, low] = SKY[tone]
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className={`pointer-events-none select-none ${className}`}
      viewBox="0 0 1600 900"
      preserveAspectRatio="xMidYMax slice"
    >
      <defs>
        <linearGradient id="w-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={top} />
          <stop offset="0.55" stopColor={mid} />
          <stop offset="1" stopColor={low} />
        </linearGradient>
        <radialGradient id="w-sun" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#fff6d8" />
          <stop offset="0.35" stopColor="#ffe9a8" stopOpacity="0.9" />
          <stop offset="1" stopColor="#ffe9a8" stopOpacity="0" />
        </radialGradient>
      </defs>

      <rect width="1600" height="900" fill="url(#w-sky)" />
      <circle cx="1240" cy="250" r="190" fill="url(#w-sun)" />
      <circle cx="1240" cy="250" r="54" fill="#fff4cf" />

      <Cloud x={220} y={150} s={1.1} className="cloud cloud-a" />
      <Cloud x={720} y={95} s={0.8} className="cloud cloud-b" />
      <Cloud x={1450} y={180} s={0.95} className="cloud cloud-a" />
      <Cloud x={1000} y={330} s={0.6} className="cloud cloud-b" />

      {/* Far mountains with snow caps */}
      <path d="M0 560 L170 380 L280 470 L420 300 L560 460 L690 360 L860 520 L1010 330 L1150 470 L1290 350 L1440 480 L1600 400 L1600 900 L0 900 Z" fill="#a9bfcf" />
      <path d="M420 300 L465 352 L440 345 L420 362 L398 344 L378 350 Z M1010 330 L1052 378 L1030 372 L1010 388 L990 372 L968 380 Z M1290 350 L1325 390 L1305 386 L1290 398 L1272 386 L1255 392 Z M170 380 L205 418 L188 414 L170 426 L152 414 L138 420 Z" fill="#f4f7f8" />
      <path d="M0 600 L240 470 L420 560 L640 450 L860 580 L1080 470 L1300 560 L1600 470 L1600 900 L0 900 Z" fill="#8fa9a1" opacity="0.9" />

      {/* Mid hills + tree line */}
      <path d="M0 660 C220 590 420 600 640 640 C860 680 1060 590 1280 600 C1420 606 1520 630 1600 650 L1600 900 L0 900 Z" fill="#88ad69" />
      {TREES.map((t) => (
        <g key={t.x}>
          <rect x={t.x - 3} y={t.y} width="6" height={t.r * 0.9} fill="#5b4126" />
          <circle cx={t.x} cy={t.y} r={t.r} fill={t.dark ? '#3f6a3a' : '#4f7d45'} />
          <circle cx={t.x - t.r * 0.35} cy={t.y - t.r * 0.35} r={t.r * 0.45} fill="#6f9a58" opacity="0.7" />
        </g>
      ))}

      {/* A winding path toward the horizon */}
      <path d="M760 900 C780 820 700 780 760 730 C810 690 900 690 880 650" stroke="#e8d3a2" strokeWidth="26" fill="none" strokeLinecap="round" opacity="0.9" />

      {/* Near hills + grass */}
      <path d="M0 740 C260 690 520 720 760 760 C1000 800 1260 700 1600 730 L1600 900 L0 900 Z" fill="#5f8a4c" />
      <path d="M0 820 C300 790 620 830 900 820 C1180 810 1400 790 1600 805 L1600 900 L0 900 Z" fill="#45683a" />
      {BLADES.map((b) => (
        <path key={b.x} d={`M${b.x} 900 l4 -${b.h} l4 ${b.h} Z`} fill="#3a5a31" />
      ))}
    </svg>
  )
}
