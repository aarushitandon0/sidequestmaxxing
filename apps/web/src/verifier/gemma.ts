/**
 * Gemma 3n photo verifier via MediaPipe LLM Inference for Web (WebGPU), loaded lazily.
 * API checked against @mediapipe/tasks-genai 0.10.29 genai.d.ts (DECISIONS D-47):
 * createFromOptions(fileset, { baseOptions: { modelAssetBuffer: reader }, maxNumImages, ... }),
 * generateResponse([string | { imageSource }]).
 * The photo is drawn onto a canvas and handed to the model in memory. It is never uploaded.
 */

import { verifierPrompt } from './prompt'
import { parseVerifierOutput, type VerifyOutcome } from './parse'
import { modelMeta, openModelReader } from './storage'

export const WASM_BASE = '/mediapipe-wasm'
const MAX_SIDE = 768

export type Support = { ok: true } | { ok: false; reason: 'no-webgpu' | 'no-adapter' | 'no-opfs' }

interface GpuNavigator {
  gpu?: { requestAdapter: () => Promise<unknown> }
}

export async function detectSupport(): Promise<Support> {
  const nav = navigator as Navigator & GpuNavigator
  if (!nav.gpu) return { ok: false, reason: 'no-webgpu' }
  try {
    if (!(await nav.gpu.requestAdapter())) return { ok: false, reason: 'no-adapter' }
  } catch {
    return { ok: false, reason: 'no-adapter' }
  }
  if (!navigator.storage || !('getDirectory' in navigator.storage)) return { ok: false, reason: 'no-opfs' }
  return { ok: true }
}

export function modelInstalled(): boolean {
  return modelMeta()?.complete === true
}

type Llm = { generateResponse: (q: unknown) => Promise<string>; close: () => void }
let llmPromise: Promise<Llm> | null = null

async function loadLlm(): Promise<Llm> {
  const { FilesetResolver, LlmInference } = await import('@mediapipe/tasks-genai')
  const fileset = await FilesetResolver.forGenAiTasks(WASM_BASE)
  const llm = await LlmInference.createFromOptions(fileset, {
    baseOptions: { modelAssetBuffer: await openModelReader() },
    maxTokens: 1024,
    topK: 1,
    temperature: 0,
    randomSeed: 7,
    maxNumImages: 1,
  })
  return llm as unknown as Llm
}

export function warmUp(): Promise<Llm> {
  llmPromise ??= loadLlm().catch((err: unknown) => {
    llmPromise = null
    throw err
  })
  return llmPromise
}

async function toCanvas(image: Blob): Promise<HTMLCanvasElement> {
  const bmp = await createImageBitmap(image)
  const scale = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bmp.width * scale)
  canvas.height = Math.round(bmp.height * scale)
  canvas.getContext('2d')?.drawImage(bmp, 0, 0, canvas.width, canvas.height)
  bmp.close()
  return canvas
}

/** Gemma chat turn format (applied manually; see DECISIONS D-47 [VERIFY on device]). */
export async function verifyPhoto(image: Blob, photoPrompt: string): Promise<VerifyOutcome & { latencyMs: number }> {
  const llm = await warmUp()
  const canvas = await toCanvas(image)
  const t0 = performance.now()
  const reply = await llm.generateResponse([
    '<start_of_turn>user\n',
    { imageSource: canvas },
    verifierPrompt(photoPrompt),
    '<end_of_turn>\n<start_of_turn>model\n',
  ])
  return { ...parseVerifierOutput(reply), latencyMs: Math.round(performance.now() - t0) }
}

export async function unload(): Promise<void> {
  if (!llmPromise) return
  const llm = await llmPromise.catch(() => null)
  llm?.close()
  llmPromise = null
}
