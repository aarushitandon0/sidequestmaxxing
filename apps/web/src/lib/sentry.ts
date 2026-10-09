/**
 * Frontend Sentry (MASTERSPEC §13, §9.3; DECISIONS D-63).
 *
 * Low trace sampling, PII off, and a scrubber that mirrors the backend's: coordinates and the
 * device id must never leave the device. Permission-denied errors are dropped — a player saying
 * "no" to the camera or to geolocation is a supported path with a working fallback, not a bug.
 */
import * as Sentry from '@sentry/react'
import type { ErrorEvent } from '@sentry/react'

import { readJson } from './storage'

export const DSN = import.meta.env.VITE_SENTRY_DSN
export const TRACES_SAMPLE_RATE = 0.1
const SCRUBBED = '[scrubbed]'

/** Same keys the API scrubs, plus the free text we never want to see. */
const SCRUBBED_KEYS = /^(lat|lng|lon|latitude|longitude|coords|coordinates|note|interests)$/i
const DEVICE_KEYS = /^(device_id|deviceid|x-device-id|sqm\.device_id)$/i
/** "18.52,73.85" anywhere in a string. */
const COORD_PAIR = /-?\d{1,3}\.\d{2,}\s*,\s*-?\d{1,3}\.\d{2,}/g

/**
 * This device's own id, if one has been stored — read without minting one.
 *
 * Only this exact value is redacted from free text, not every UUID: quest ids are UUIDs too,
 * and they are the thing you follow when reading a trace.
 */
function storedDeviceId(): string | null {
  return readJson<string>('sqm.device_id')
}

/** Dropped entirely: the player declined a permission, which the UI already handles. */
export const IGNORED_ERRORS = [
  'NotAllowedError',
  'PermissionDeniedError',
  'PermissionStatus',
  'User denied',
  'Permission denied',
  'denied geolocation',
  'The request is not allowed by the user agent',
]

function isPermissionNoise(event: ErrorEvent): boolean {
  const values = event.exception?.values ?? []
  const haystack = [
    event.message ?? '',
    ...values.map((v) => `${v.type ?? ''} ${v.value ?? ''}`),
  ].join(' ')
  // GeolocationPositionError.PERMISSION_DENIED is code 1 and carries no useful name.
  if (/\bcode\b\D{0,4}1\b/.test(haystack) && /geolocation/i.test(haystack)) return true
  return IGNORED_ERRORS.some((needle) => haystack.toLowerCase().includes(needle.toLowerCase()))
}

function stripUrl(url: string): string {
  // Query strings carry lat/lng on the way to /v1/places/near.
  const [base] = url.split('?')
  return base ?? url
}

function scrubString(value: string): string {
  const out = value.replace(COORD_PAIR, SCRUBBED)
  const device = storedDeviceId()
  return device ? out.split(device).join(SCRUBBED) : out
}

function scrubValue(value: unknown, key?: string): unknown {
  if (key && SCRUBBED_KEYS.test(key)) return SCRUBBED
  if (key && DEVICE_KEYS.test(key)) return SCRUBBED
  if (typeof value === 'string') {
    const stripped = /^https?:\/\//.test(value) ? stripUrl(value) : value
    return scrubString(stripped)
  }
  if (Array.isArray(value)) return value.map((v) => scrubValue(v))
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, scrubValue(v, k)]),
    )
  }
  return value
}

/** Exported for tests: no coordinates, no device id, no query strings, no permission noise. */
export function beforeSend(event: ErrorEvent): ErrorEvent | null {
  if (isPermissionNoise(event)) return null
  const scrubbed = scrubValue(event) as ErrorEvent
  if (scrubbed.request?.url) scrubbed.request.url = stripUrl(scrubbed.request.url)
  if (scrubbed.request) delete scrubbed.request.query_string
  return scrubbed
}

/** No-op without a DSN, so local dev and tests never phone home. Returns true if enabled. */
export function initSentry(): boolean {
  if (!DSN) return false
  Sentry.init({
    dsn: DSN,
    environment: import.meta.env.MODE,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: TRACES_SAMPLE_RATE,
    // v11 replaced `sendDefaultPii` with this granular switch (D-63). `urlQueryParams: false`
    // is the one that matters most to us: /v1/places/near carries lat/lng in its query string.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      stackFrameVariables: false,
    },
    ignoreErrors: IGNORED_ERRORS,
    beforeSend,
  })
  return true
}

/** Report a render crash from the error boundary; a no-op when Sentry was never initialised. */
export function reportError(error: unknown): void {
  if (!DSN) return
  Sentry.captureException(error)
}
