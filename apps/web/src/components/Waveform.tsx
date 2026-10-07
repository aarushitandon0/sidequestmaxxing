/** Animated "voice" bars beside the Dungeon Master (static under reduced motion). */
export function Waveform({ active = true, bars = 18, className = '' }: { active?: boolean; bars?: number; className?: string }) {
  return (
    <span aria-hidden="true" className={`inline-flex h-6 items-center gap-[3px] ${className}`}>
      {Array.from({ length: bars }, (_, i) => {
        const h = 30 + ((i * 37) % 70)
        return (
          <span
            key={i}
            className={`w-[3px] rounded-full bg-current ${active ? 'wave-bar' : ''}`}
            style={{ height: `${h}%`, animationDelay: `${(i % 6) * 0.12}s`, opacity: active ? 1 : 0.55 }}
          />
        )
      })}
    </span>
  )
}
