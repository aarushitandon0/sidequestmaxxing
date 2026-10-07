/** localStorage that never throws (private mode, quota, disabled storage). */

export function readJson<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Storage unavailable: the app keeps working for this session.
  }
}

export function removeKey(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // ignore
  }
}

export function clearAppStorage(prefix = 'sqm.'): void {
  try {
    const keys: string[] = []
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i)
      if (k?.startsWith(prefix)) keys.push(k)
    }
    keys.forEach((k) => window.localStorage.removeItem(k))
  } catch {
    // ignore
  }
}
