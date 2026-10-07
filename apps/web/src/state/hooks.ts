import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

import { api } from '../lib/api'
import { loadPrefs, savePrefs, type Prefs } from '../lib/prefs'
import type { SettingsUpdate } from '../lib/types'

export function useProfile(enabled = true) {
  return useQuery({ queryKey: ['profile'], queryFn: api.profile, enabled, staleTime: 30_000 })
}

/** This week's Chronicle. Server-side idempotent, so refetching is a cheap read. */
export function useWeeklyRecap(enabled = true) {
  return useQuery({ queryKey: ['recap'], queryFn: api.weeklyRecap, enabled, staleTime: 60_000 })
}

/** Local-first preferences; the server copy is updated best-effort (it may be offline). */
export function usePrefs(): [Prefs, (update: Partial<Prefs>) => Prefs] {
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs)
  const qc = useQueryClient()
  const sync = useMutation({
    mutationFn: (body: SettingsUpdate) => api.updateSettings(body),
    onSuccess: (profile) => qc.setQueryData(['profile'], profile),
  })
  const { mutate } = sync
  const update = useCallback(
    (u: Partial<Prefs>) => {
      const next = savePrefs(u)
      setPrefs(next)
      const body: SettingsUpdate = {}
      if (u.persona) body.persona = u.persona
      if (u.interests) body.interests = u.interests
      if (u.radiusM) body.default_radius_m = u.radiusM
      if (u.voice !== undefined) body.voice = u.voice
      if (Object.keys(body).length) mutate(body)
      return next
    },
    [mutate],
  )
  return [prefs, update]
}

function subscribeOnline(cb: () => void) {
  window.addEventListener('online', cb)
  window.addEventListener('offline', cb)
  return () => {
    window.removeEventListener('online', cb)
    window.removeEventListener('offline', cb)
  }
}

export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribeOnline,
    () => navigator.onLine,
    () => true,
  )
}

/** Re-render every `ms` (Walk Mode clock). Pauses work when unmounted. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(t)
  }, [ms])
  return now
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
      mq?.addEventListener?.('change', cb)
      return () => mq?.removeEventListener?.('change', cb)
    },
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
    () => false,
  )
}
