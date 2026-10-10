import { useState } from 'react'

import { PinIcon } from './Icons'
import { SEEDED_CITIES } from '../lib/cities'

/** Plain-language reason before the browser's location prompt; a working alternative if declined. */
export function LocationConsent({
  onDevice,
  onCity,
  onCancel,
}: {
  onDevice: () => void
  onCity: (slug: string) => void
  onCancel: () => void
}) {
  const [picking, setPicking] = useState(false)

  return (
    <section aria-labelledby="loc-title" className="parchment rise p-5">
      <h2 id="loc-title" className="hand-title flex items-center gap-2 text-2xl">
        <PinIcon /> Where's your adventure?
      </h2>
      <p className="mt-2">
        To find real places near you, we use your <strong>approximate area</strong> (rounded to about 100 m). Your exact
        location and your movements stay on your phone.
      </p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <button type="button" className="btn btn-moss flex-1" onClick={onDevice}>
          Use my location
        </button>
        <button
          type="button"
          className="btn btn-ghost flex-1"
          aria-expanded={picking}
          onClick={() => setPicking((p) => !p)}
        >
          Pick a city instead
        </button>
      </div>

      {picking ? (
        <div className="mt-3">
          <h3 className="text-lg">Play somewhere else</h3>
          <p className="text-sm text-ink-soft">
            Real parks, markets and libraries in any of these. You can still head out wherever you
            actually are — the quest just comes from here.
          </p>
          <ul className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {SEEDED_CITIES.map((city) => (
              <li key={city.slug}>
                <button type="button" className="toggle-chip w-full" onClick={() => onCity(city.slug)}>
                  {city.name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <button type="button" className="mt-2 min-h-11 w-full text-ink-soft underline" onClick={onCancel}>
        Not now
      </button>
    </section>
  )
}
