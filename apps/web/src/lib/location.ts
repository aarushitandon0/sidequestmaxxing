/**
 * Approximate location, requested just in time. Coordinates are rounded to 3 decimals
 * (~110 m) before they leave this module (MASTERSPEC §9.3).
 */

export interface Coarse {
  lat: number
  lng: number
}

export type LocationError = 'denied' | 'unavailable' | 'timeout' | 'unsupported'

export function roundCoord(v: number): number {
  return Math.round(v * 1000) / 1000
}

export function coarse(lat: number, lng: number): Coarse {
  return { lat: roundCoord(lat), lng: roundCoord(lng) }
}

export function getCoarseLocation(timeoutMs = 12000): Promise<Coarse> {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject('unsupported' satisfies LocationError)
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve(coarse(pos.coords.latitude, pos.coords.longitude)),
      (err) => {
        const code: LocationError =
          err.code === err.PERMISSION_DENIED
            ? 'denied'
            : err.code === err.TIMEOUT
              ? 'timeout'
              : 'unavailable'
        reject(code)
      },
      { enableHighAccuracy: false, maximumAge: 5 * 60_000, timeout: timeoutMs },
    )
  })
}

/** Used only when the player declines location: the spec's demo city (Pune centre). */
export const DEMO_AREA: Coarse & { name: string } = { lat: 18.52, lng: 73.856, name: 'Pune (demo area)' }

export function distanceM(a: Coarse, b: Coarse): number {
  const R = 6_371_008.8
  const toRad = (x: number) => (x * Math.PI) / 180
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)))
}
