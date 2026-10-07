import 'leaflet/dist/leaflet.css'

import L from 'leaflet'
import { useEffect, useRef } from 'react'

import type { Coarse } from '../lib/location'
import type { PlaceRef } from '../lib/types'

const pin = (cls: string, label: string) =>
  L.divIcon({
    className: '',
    html: `<span class="${cls}" aria-hidden="true"></span><span class="sr-only">${label}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
  })

/**
 * OpenStreetMap via Leaflet (MASTERSPEC §11.1 #9) with the required attribution.
 * Loaded lazily so it never weighs on the first load. Shows the quest place; the player's
 * approximate area only if they shared it (never sent anywhere from here).
 */
export default function QuestMap({ place, you, className = '' }: { place: PlaceRef; you?: Coarse | null; className?: string }) {
  const el = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!el.current) return
    const map = L.map(el.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)
    const target = L.marker([place.lat, place.lng], { icon: pin('sqm-pin sqm-pin-quest', place.name), title: place.name })
    target.addTo(map).bindTooltip(place.name, { direction: 'top', offset: [0, -24] })
    const points: L.LatLngExpression[] = [[place.lat, place.lng]]
    if (you) {
      L.marker([you.lat, you.lng], { icon: pin('sqm-pin sqm-pin-you', 'You are here (approximate)') }).addTo(map)
      points.push([you.lat, you.lng])
      L.polyline(points, { color: '#3b2a1e', weight: 3, dashArray: '2 8', lineCap: 'round' }).addTo(map)
    }
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [36, 36] })
    else map.setView([place.lat, place.lng], 15)
    return () => {
      map.remove()
    }
  }, [place, you])
  return (
    <div
      ref={el}
      role="region"
      aria-label={`Map showing ${place.name}`}
      className={`sqm-map overflow-hidden rounded-2xl ${className.includes('border-') ? '' : 'border-2 border-edge'} ${className}`}
    />
  )
}
