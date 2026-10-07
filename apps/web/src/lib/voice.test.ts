import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const QID = '6f1c2c1e-0000-4000-8000-000000000001'
const TEXT = 'Find the old stone marker by the river.'
const MP3 = new Uint8Array([0x49, 0x44, 0x33, 4, 0, 0, 1, 2, 3])

class FakeCache {
  store = new Map<string, Response>()
  async match(key: string) {
    const r = this.store.get(key)
    return r ? r.clone() : undefined
  }
  async put(key: string, res: Response) {
    this.store.set(key, res)
  }
}

let played: string[]
let playOk: boolean
let spoken: string[]
let cache: FakeCache
let manifest: Record<string, string>

class FakeAudio {
  onended: (() => void) | null = null
  constructor(public src: string) {}
  play() {
    if (!playOk) return Promise.reject(new Error('NotAllowedError'))
    played.push(this.src)
    return Promise.resolve()
  }
  pause() {}
}

function stubBrowser() {
  played = []
  spoken = []
  playOk = true
  cache = new FakeCache()
  manifest = {}
  vi.stubGlobal('Audio', FakeAudio)
  vi.stubGlobal('caches', { open: async () => cache })
  vi.stubGlobal('speechSynthesis', { cancel: vi.fn(), speak: (u: { text: string }) => spoken.push(u.text) })
  vi.stubGlobal('SpeechSynthesisUtterance', class {
    onend: (() => void) | null = null
    onerror: (() => void) | null = null
    rate = 1
    constructor(public text: string) {}
  })
  URL.createObjectURL = vi.fn(() => 'blob:fake')
  URL.revokeObjectURL = vi.fn()
}

function mockFetch(tts: () => Response | Promise<Response>) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- typed so tests can read the request body
  const fn = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url === '/demo-audio/manifest.json') return new Response(JSON.stringify({ clips: manifest }))
    return tts()
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

const audioOk = () => new Response(MP3, { status: 200, headers: { 'Content-Type': 'audio/mpeg' } })
const err = (status: number) =>
  new Response(JSON.stringify({ error: { code: 'x', message: 'y' } }), { status, headers: { 'Content-Type': 'application/json' } })

async function load() {
  vi.resetModules() // fresh manifest promise + state per test
  return import('./voice')
}

describe('voice layer (ElevenLabs → cache → browser speech)', () => {
  beforeEach(stubBrowser)
  afterEach(() => vi.unstubAllGlobals())

  it('plays server audio, sending only quest_id and kind, and caches it', async () => {
    const fetch = mockFetch(audioOk)
    const v = await load()
    expect(await v.speakQuest({ questId: QID, text: TEXT })).toBe('elevenlabs')
    const ttsCall = fetch.mock.calls.find(([u]) => String(u).endsWith('/v1/tts'))!
    expect(JSON.parse(String(ttsCall[1]!.body))).toEqual({ quest_id: QID, kind: 'briefing' })
    expect(String(ttsCall[1]!.body)).not.toContain('stone marker')
    expect(played).toEqual(['blob:fake'])
    expect(spoken).toEqual([])

    // Second time: from Cache Storage, no network (works offline).
    fetch.mockClear()
    expect(await v.speakQuest({ questId: QID, text: TEXT })).toBe('cache')
    expect(fetch.mock.calls.some(([u]) => String(u).endsWith('/v1/tts'))).toBe(false)
  })

  it.each([
    ['budget exceeded', () => err(429)],
    ['voice unavailable', () => err(503)],
    ['not found', () => err(404)],
    ['offline', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['json instead of audio', () => new Response('{}', { headers: { 'Content-Type': 'application/json' } })],
  ])('%s → browser speech with the same text', async (_name, tts) => {
    mockFetch(tts)
    const v = await load()
    expect(await v.speakQuest({ questId: QID, text: TEXT })).toBe('browser')
    expect(spoken).toEqual([TEXT])
    expect(played).toEqual([])
  })

  it('autoplay blocked → browser speech', async () => {
    mockFetch(audioOk)
    playOk = false
    const v = await load()
    expect(await v.speakQuest({ questId: QID, text: TEXT })).toBe('browser')
    expect(spoken).toEqual([TEXT])
  })

  it('a pre-generated demo clip wins and skips the API', async () => {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(TEXT))
    const hash = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
    manifest = { [hash]: 'riverbank.mp3' }
    const fetch = mockFetch(audioOk)
    const v = await load()
    expect(await v.speakQuest({ questId: QID, text: TEXT })).toBe('demo')
    expect(played).toEqual(['/demo-audio/riverbank.mp3'])
    expect(fetch.mock.calls.some(([u]) => String(u).endsWith('/v1/tts'))).toBe(false)
    expect(await v.speakText(TEXT)).toBe('demo')
  })

  it('stopping while the audio is loading plays nothing', async () => {
    let release: (r: Response) => void = () => undefined
    mockFetch(() => new Promise<Response>((r) => (release = r)))
    const v = await load()
    const pending = v.speakQuest({ questId: QID, text: TEXT })
    await new Promise((r) => setTimeout(r, 0))
    v.stopVoice()
    release(audioOk())
    expect(await pending).toBe('none')
    expect(played).toEqual([])
    expect(spoken).toEqual([])
  })
})
