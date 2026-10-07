import { createContext, useContext, type ReactNode } from 'react'

import type { VerifyOutcome } from './parse'
import type { Progress } from './storage'
import type { Support } from './gemma'

/** Everything the UI needs from the verifier — injectable so tests use a mock (no WebGPU). */
export interface Verifier {
  modelUrl: string | null
  detectSupport: () => Promise<Support>
  installed: () => boolean
  download: (onProgress: Progress, signal?: AbortSignal) => Promise<void>
  importFile: (file: File, onProgress: Progress) => Promise<void>
  remove: () => Promise<void>
  verify: (image: Blob, photoPrompt: string) => Promise<VerifyOutcome & { latencyMs: number }>
}

const MODEL_URL: string | null = import.meta.env.VITE_GEMMA_MODEL_URL || null

/** Real implementation: heavy modules load only when actually used. */
export const gemmaVerifier: Verifier = {
  modelUrl: MODEL_URL,
  detectSupport: async () => (await import('./gemma')).detectSupport(),
  installed: () => {
    try {
      const raw = window.localStorage.getItem('sqm.verifier.meta')
      return raw ? (JSON.parse(raw) as { complete?: boolean }).complete === true : false
    } catch {
      return false
    }
  },
  download: async (onProgress, signal) => {
    if (!MODEL_URL) throw new Error('No model URL configured')
    const s = await import('./storage')
    await s.requestPersistence()
    await prefetchWasm()
    await s.downloadModel(MODEL_URL, onProgress, signal)
  },
  importFile: async (file, onProgress) => {
    const s = await import('./storage')
    await s.requestPersistence()
    await prefetchWasm()
    await s.importModel(file, onProgress)
  },
  remove: async () => {
    const [g, s] = await Promise.all([import('./gemma'), import('./storage')])
    await g.unload()
    await s.removeModel()
  },
  verify: async (image, prompt) => (await import('./gemma')).verifyPhoto(image, prompt),
}

/** Pull the one MediaPipe WASM variant this device needs through the service worker cache. */
async function prefetchWasm(): Promise<void> {
  const [{ WASM_BASE }, { FilesetResolver }] = await Promise.all([
    import('./gemma'),
    import('@mediapipe/tasks-genai'),
  ])
  const fileset = await FilesetResolver.forGenAiTasks(WASM_BASE)
  await Promise.all(
    [fileset.wasmLoaderPath, fileset.wasmBinaryPath].map((u) => fetch(u).then((r) => r.arrayBuffer())),
  )
}

/**
 * E2E builds only (VITE_E2E_FAKE_VERIFIER=1): headless browsers have no WebGPU. Vite inlines
 * the flag, so production builds drop this branch entirely.
 */
const e2eVerifier: Verifier = {
  modelUrl: null,
  detectSupport: async () => ({ ok: true }),
  installed: () => true,
  download: async () => undefined,
  importFile: async () => undefined,
  remove: async () => undefined,
  verify: async () => ({ match: true, confidence: 0.91, seen: 'an old stone marker', latencyMs: 1 }),
}

export const defaultVerifier: Verifier = import.meta.env.VITE_E2E_FAKE_VERIFIER === '1' ? e2eVerifier : gemmaVerifier

const Ctx = createContext<Verifier>(defaultVerifier)

export function VerifierProvider({ verifier, children }: { verifier: Verifier; children: ReactNode }) {
  return <Ctx.Provider value={verifier}>{children}</Ctx.Provider>
}

export function useVerifier(): Verifier {
  return useContext(Ctx)
}
