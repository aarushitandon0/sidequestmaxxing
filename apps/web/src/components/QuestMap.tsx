import 'leaflet/dist/leaflet.css'

import L from 'leaflet'
import { useEffect, useRef } from 'react'

import type { Coarse } from '../lib/location'
import type { Happening, PlaceRef } from '../lib/types'

/**
 * Event titles come from a third-party feed, so they are text in this HTML, never markup.
 * Both sinks need it: `divIcon({ html })` and `bindTooltip(<string>)` are each assigned with
 * innerHTML by Leaflet.
 */
const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

const pin = (cls: string, label: string) =>
  L.divIcon({
    className: '',
    html: `<span class="${cls}" aria-hidden="true"></span><span class="sr-only">${esc(label)}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
  })

/**
 * OpenStreetMap via Leaflet (MASTERSPEC §11.1 #9) with the required attribution.
 * Loaded lazily so it never weighs on the first load. Shows the quest place; the player's
 * approximate area only if they shared it (never sent anywhere from here).
 * An event-backed quest (P23) gets a diamond pin, so the distinction is shape and label, not
 * colour alone (MASTERSPEC §11.2).
 */
export default function QuestMap({
  place,
  you,
  happening,
  className = '',
}: {
  place: PlaceRef
  you?: Coarse | null
  happening?: Happening | null
  className?: string
}) {
  const el = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!el.current) return
    const map = L.map(el.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)
    const label = happening ? `Event: ${happening.title}` : place.name
    const tooltip = happening ? `${place.name} · ${happening.title}` : place.name
    const target = L.marker([place.lat, place.lng], {
      icon: pin(`sqm-pin ${happening ? 'sqm-pin-event' : 'sqm-pin-quest'}`, label),
      title: tooltip,
    })
    target.addTo(map).bindTooltip(esc(tooltip), { direction: 'top', offset: [0, -24] })
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
  }, [place, you, happening])
  return (
    <div
      ref={el}
      role="region"
      aria-label={`Map showing ${place.name}`}
      className={`sqm-map overflow-hidden rounded-2xl ${className.includes('border-') ? '' : 'border-2 border-edge'} ${className}`}
    />
  )
}
