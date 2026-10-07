import { readJson, writeJson } from './storage'

const KEY = 'sqm.device_id'
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function uuidv4(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const b = crypto.getRandomValues(new Uint8Array(16))
  b[6] = (b[6]! & 0x0f) | 0x40
  b[8] = (b[8]! & 0x3f) | 0x80
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}

/** Anonymous random device id (MASTERSPEC §9.3): no email, no name, no fingerprinting. */
export function getDeviceId(): string {
  const existing = readJson<string>(KEY)
  if (existing && UUID_V4.test(existing)) return existing
  const id = uuidv4()
  writeJson(KEY, id)
  return id
}

export function isUuidV4(value: string): boolean {
  return UUID_V4.test(value)
}
