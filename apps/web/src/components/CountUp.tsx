import { useEffect, useState } from 'react'

import { usePrefersReducedMotion } from '../state/hooks'

/** Counts up to `value` in ≤ 1.5 s (MASTERSPEC §11.1 #6); instant with reduced motion. */
export function CountUp({ value, durationMs = 1200 }: { value: number; durationMs?: number }) {
  const reduced = usePrefersReducedMotion()
  const [shown, setShown] = useState(0)
  useEffect(() => {
    if (reduced) return
    let raf = 0
    const t0 = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / Math.min(durationMs, 1500))
      setShown(Math.round(value * (1 - (1 - p) ** 3)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, durationMs, reduced])
  return <span aria-hidden="true">{reduced ? value : shown}</span>
}
