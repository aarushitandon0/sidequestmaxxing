/**
 * Model storage in the Origin Private File System (OPFS): resumable downloads (HTTP Range),
 * import from a local file, and a streaming reader for MediaPipe. Nothing here uploads data.
 */

import { readJson, removeKey, writeJson } from '../lib/storage'

export const MODEL_FILE = 'gemma-3n-verifier.litertlm'
const META_KEY = 'sqm.verifier.meta'

export interface ModelMeta {
  source: 'url' | 'file'
  bytes: number
  total: number | null
  complete: boolean
}

export type Progress = (loaded: number, total: number | null) => void

export function hasOpfs(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.storage && 'getDirectory' in navigator.storage
}

export function modelMeta(): ModelMeta | null {
  return readJson<ModelMeta>(META_KEY)
}

async function dir(): Promise<FileSystemDirectoryHandle> {
  return navigator.storage.getDirectory()
}

/** Ask the browser to keep our data (best effort; Chrome decides by engagement). */
export async function requestPersistence(): Promise<boolean> {
  try {
    return (await navigator.storage.persist?.()) ?? false
  } catch {
    return false
  }
}

export async function freeSpace(): Promise<number | null> {
  try {
    const est = await navigator.storage.estimate()
    return est.quota != null && est.usage != null ? est.quota - est.usage : null
  } catch {
    return null
  }
}

function totalFrom(res: Response, offset: number): number | null {
  const range = res.headers.get('Content-Range') // bytes 100-199/1000
  const m = range?.match(/\/(\d+)$/)
  if (m) return Number(m[1])
  const len = res.headers.get('Content-Length')
  return len ? Number(len) + (res.status === 206 ? offset : 0) : null
}

async function pipe(
  reader: ReadableStreamDefaultReader<Uint8Array<ArrayBuffer>>,
  writable: FileSystemWritableFileStream,
  start: number,
  total: number | null,
  onProgress: Progress,
  source: ModelMeta['source'],
): Promise<number> {
  let loaded = start
  let lastSave = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    await writable.write(value)
    loaded += value.byteLength
    onProgress(loaded, total)
    if (loaded - lastSave > 8 * 1024 * 1024) {
      writeJson(META_KEY, { source, bytes: loaded, total, complete: false } satisfies ModelMeta)
      lastSave = loaded
    }
  }
  return loaded
}

/** Download (or resume) the model from `url` into OPFS. */
export async function downloadModel(url: string, onProgress: Progress, signal?: AbortSignal): Promise<void> {
  const handle = await (await dir()).getFileHandle(MODEL_FILE, { create: true })
  const meta = modelMeta()
  let offset = meta && meta.source === 'url' && !meta.complete ? (await handle.getFile()).size : 0
  const res = await fetch(url, { headers: offset ? { Range: `bytes=${offset}-` } : {}, signal })
  if (!res.ok || !res.body) throw new Error(`model download failed (${res.status})`)
  if (offset && res.status !== 206) offset = 0 // server ignored Range: start over
  const total = totalFrom(res, offset)
  const writable = await handle.createWritable({ keepExistingData: offset > 0 })
  try {
    if (offset > 0) await writable.seek(offset)
    else await writable.truncate(0)
    const loaded = await pipe(res.body.getReader(), writable, offset, total, onProgress, 'url')
    await writable.close()
    if (total != null && loaded !== total) throw new Error('model download incomplete')
    writeJson(META_KEY, { source: 'url', bytes: loaded, total, complete: true } satisfies ModelMeta)
  } catch (err) {
    await writable.close().catch(() => undefined)
    throw err
  }
}

/** Copy a model file the player already has (e.g. downloaded after accepting the Gemma terms). */
export async function importModel(file: File, onProgress: Progress): Promise<void> {
  const handle = await (await dir()).getFileHandle(MODEL_FILE, { create: true })
  const writable = await handle.createWritable()
  await writable.truncate(0)
  const loaded = await pipe(file.stream().getReader(), writable, 0, file.size, onProgress, 'file')
  await writable.close()
  writeJson(META_KEY, { source: 'file', bytes: loaded, total: file.size, complete: true } satisfies ModelMeta)
}

export async function openModelReader(): Promise<ReadableStreamDefaultReader<Uint8Array<ArrayBuffer>>> {
  const file = await (await (await dir()).getFileHandle(MODEL_FILE)).getFile()
  return file.stream().getReader()
}

export async function removeModel(): Promise<void> {
  try {
    await (await dir()).removeEntry(MODEL_FILE)
  } catch {
    // already gone
  }
  removeKey(META_KEY)
}
