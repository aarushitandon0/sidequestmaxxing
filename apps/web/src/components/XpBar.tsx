/** XP progress bar with an accessible progressbar role. */
export function XpBar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  return (
    <div
      className="xp-track"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
    >
      <div className="xp-fill transition-transform duration-700" style={{ transform: `scaleX(${pct / 100})` }} />
    </div>
  )
}
