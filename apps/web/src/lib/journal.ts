/**
 * The Journal: photos and notes from finished quests, kept in IndexedDB on this device.
 *
 * Photos never leave the phone and there is no upload endpoint to send them to
 * (MASTERSPEC §9.3, CLAUDE.md invariant 2). Two consequences worth knowing:
 *
 * 1. `downscale` re-encodes every photo through a canvas, which drops the EXIF block —
 *    including the GPS tag a camera writes into it. The pixels survive; the coordinates of
 *    the player's home do not.
 * 2. Nothing here is backed up. "Delete my data" in Settings wipes it, and so does clearing
 *    site data. That is the trade for never uploading anything.
 *
 * localStorage is the wrong store for this (blobs, and a ~5 MB cap), so this is the one place
 * in the app that uses IndexedDB. Every call resolves rather than throwing on a storage
 * failure: private mode, a denied quota and a blocked upgrade are all normal, and the caller
 * gets an explicit error it can show instead of an unhandled rejection.
 */

import { readJson, writeJson } from './storage'

export const DB_NAME = 'sqm-journal'
export const DB_VERSION = 1
export const STORE = 'entries'

export interface JournalPhoto {
  id: string
  blob: Blob
  width: number
  height: number
}

export interface JournalEntry {
  id: string
  /** ISO timestamp, this device's clock. */
  createdAt: string
  /** Copied from the quest at save time so an entry still reads well on its own. */
  questTitle?: string
  placeName?: string
  category?: string
  caption: string
  photos: JournalPhoto[]
}

/** What the UI shows when storage refuses to cooperate. */
export class JournalError extends Error {
  constructor(
    message: string,
    readonly cause?: unknown,
  ) {
    super(message)
    this.name = 'JournalError'
  }
}

function newId(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  }
}

/** Injected in tests; the app always uses the real one. */
export type Factory = IDBFactory

export function available(factory: Factory | undefined = globalThis.indexedDB): boolean {
  return Boolean(factory)
}

function open(factory: Factory | undefined = globalThis.indexedDB): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!factory) {
      reject(new JournalError('This browser cannot store your journal.'))
      return
    }
    let request: IDBOpenDBRequest
    try {
      request = factory.open(DB_NAME, DB_VERSION)
    } catch (cause) {
      reject(new JournalError('Your journal could not be opened.', cause))
      return
    }
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id' })
        store.createIndex('createdAt', 'createdAt')
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(new JournalError('Your journal could not be opened.', request.error))
    // A second tab holding an old version open: surface it rather than hanging forever.
    request.onblocked = () => reject(new JournalError('Close the app in your other tabs and try again.'))
  })
}

function run<T>(
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore) => IDBRequest<T>,
  factory?: Factory,
): Promise<T> {
  return open(factory).then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        let request: IDBRequest<T>
        try {
          const tx = db.transaction(STORE, mode)
          request = work(tx.objectStore(STORE))
          tx.oncomplete = () => {
            db.close()
            resolve(request.result)
          }
          tx.onabort = () => {
            db.close()
            // A quota failure arrives here, and it is the one the player must understand.
            reject(new JournalError('There was no room to save that. Try a smaller photo.', tx.error))
          }
          tx.onerror = () => {
            db.close()
            reject(new JournalError('Your journal could not be written.', tx.error))
          }
        } catch (cause) {
          db.close()
          reject(new JournalError('Your journal could not be written.', cause))
        }
      }),
  )
}

export function listEntries(factory?: Factory): Promise<JournalEntry[]> {
  return run<JournalEntry[]>('readonly', (s) => s.getAll() as IDBRequest<JournalEntry[]>, factory).then(
    (entries) => entries.sort((a, b) => b.createdAt.localeCompare(a.createdAt)), // newest first
  )
}

export function getEntry(id: string, factory?: Factory): Promise<JournalEntry | undefined> {
  return run<JournalEntry | undefined>('readonly', (s) => s.get(id) as IDBRequest<JournalEntry | undefined>, factory)
}

export function countEntries(factory?: Factory): Promise<number> {
  return run<number>('readonly', (s) => s.count(), factory)
}

export interface NewEntry {
  caption: string
  questTitle?: string
  placeName?: string
  category?: string
  photos?: JournalPhoto[]
  createdAt?: string
}

export function saveEntry(entry: NewEntry, factory?: Factory): Promise<JournalEntry> {
  const full: JournalEntry = {
    id: newId(),
    createdAt: entry.createdAt ?? new Date().toISOString(),
    caption: entry.caption.trim(),
    questTitle: entry.questTitle,
    placeName: entry.placeName,
    category: entry.category,
    photos: entry.photos ?? [],
  }
  return run('readwrite', (s) => s.put(full), factory).then(() => full)
}

export function addPhotos(id: string, photos: JournalPhoto[], factory?: Factory): Promise<JournalEntry> {
  return getEntry(id, factory).then((existing) => {
    if (!existing) throw new JournalError('That journal entry is no longer here.')
    const updated: JournalEntry = { ...existing, photos: [...existing.photos, ...photos] }
    return run('readwrite', (s) => s.put(updated), factory).then(() => updated)
  })
}

export function deleteEntry(id: string, factory?: Factory): Promise<void> {
  return run('readwrite', (s) => s.delete(id), factory).then(() => undefined)
}

export function clearJournal(factory?: Factory): Promise<void> {
  return run('readwrite', (s) => s.clear(), factory).then(() => undefined)
}

export const MAX_EDGE_PX = 1600
export const JPEG_QUALITY = 0.82

/**
 * Shrink a picked photo and strip its metadata.
 *
 * The canvas round-trip is what removes EXIF (and with it the GPS tag), so this is a privacy
 * step as much as a size one — do not "optimise" it into storing the original File.
 */
export async function downscale(
  file: Blob,
  maxEdge = MAX_EDGE_PX,
): Promise<JournalPhoto> {
  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file)
  } catch (cause) {
    throw new JournalError("That file didn't look like a photo.", cause)
  }
  try {
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
    const width = Math.max(1, Math.round(bitmap.width * scale))
    const height = Math.max(1, Math.round(bitmap.height * scale))
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new JournalError('This browser could not process that photo.')
    ctx.drawImage(bitmap, 0, 0, width, height)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY),
    )
    if (!blob) throw new JournalError('This browser could not process that photo.')
    return { id: newId(), blob, width, height }
  } finally {
    bitmap.close()
  }
}

/**
 * Unlocking: the Journal appears only after the first completed quest.
 *
 * Deliberately in localStorage rather than IndexedDB, and deliberately OR-ed with the server
 * count: the flag is set the moment a quest completes, so the Journal unlocks even when the
 * API is unreachable, and the server's `quests_completed` covers a player whose local flag was
 * cleared but whose history is real.
 */
const UNLOCK_KEY = 'sqm.journal_unlocked'

export function markJournalUnlocked(): void {
  writeJson(UNLOCK_KEY, true)
}

export function journalUnlockedLocally(): boolean {
  return readJson<boolean>(UNLOCK_KEY) === true
}

export function isJournalUnlocked(questsCompleted?: number): boolean {
  return journalUnlockedLocally() || (questsCompleted ?? 0) > 0
}
