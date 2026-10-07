import { PinIcon } from './Icons'

/** Plain-language reason before the browser's location prompt; a working alternative if declined. */
export function LocationConsent({ onDevice, onDemo, onCancel }: { onDevice: () => void; onDemo: () => void; onCancel: () => void }) {
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
        <button type="button" className="btn btn-ghost flex-1" onClick={onDemo}>
          Play in the demo area
        </button>
      </div>
      <button type="button" className="mt-2 min-h-11 w-full text-ink-soft underline" onClick={onCancel}>
        Not now
      </button>
    </section>
  )
}
