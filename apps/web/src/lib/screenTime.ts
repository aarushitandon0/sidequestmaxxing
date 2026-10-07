/**
 * Screen-time tracker (MASTERSPEC §11.2) — pure functions over a small serialisable state.
 *
 * Counts only seconds while the page is VISIBLE (Page Visibility API) between quest accept and
 * completion. State is persisted with the quest, so a reload doesn't reset it. If the tab is
 * killed while visible, the last heartbeat bounds what we count — never more than really passed.
 */

export interface ScreenTime {
  visibleMs: number
  visibleSince: number | null // epoch ms when the current visible span began
  lastBeat: number | null // last time we know the page was alive
}

export const HEARTBEAT_MS = 5000

export function startTracking(now: number, visible: boolean): ScreenTime {
  return { visibleMs: 0, visibleSince: visible ? now : null, lastBeat: now }
}

export function onVisibility(st: ScreenTime, visible: boolean, now: number): ScreenTime {
  if (visible && st.visibleSince === null) return { ...st, visibleSince: now, lastBeat: now }
  if (!visible && st.visibleSince !== null) {
    return {
      visibleMs: st.visibleMs + Math.max(0, now - st.visibleSince),
      visibleSince: null,
      lastBeat: now,
    }
  }
  return { ...st, lastBeat: now }
}

export function heartbeat(st: ScreenTime, now: number): ScreenTime {
  return { ...st, lastBeat: now }
}

/** After a reload: close any span left open by an unclean exit at its last heartbeat. */
export function restore(st: ScreenTime, now: number, visible: boolean): ScreenTime {
  let ms = st.visibleMs
  if (st.visibleSince !== null) {
    const end = Math.max(st.visibleSince, st.lastBeat ?? st.visibleSince)
    ms += end - st.visibleSince
  }
  return { visibleMs: ms, visibleSince: visible ? now : null, lastBeat: now }
}

export function stopTracking(st: ScreenTime, now: number): ScreenTime {
  return onVisibility(st, false, now)
}

export function visibleSeconds(st: ScreenTime, now: number): number {
  const open = st.visibleSince !== null ? Math.max(0, now - st.visibleSince) : 0
  return Math.round((st.visibleMs + open) / 1000)
}

/** Share of the quest the screen was on, 0..1. Never fabricated: null when unknown. */
export function screenShare(visibleSec: number, elapsedSec: number): number | null {
  if (elapsedSec <= 0) return null
  return Math.min(1, Math.max(0, visibleSec / elapsedSec))
}
