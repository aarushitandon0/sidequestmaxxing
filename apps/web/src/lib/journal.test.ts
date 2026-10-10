import { beforeEach, describe, expect, it } from 'vitest'

import {
  addPhotos,
  available,
  clearJournal,
  countEntries,
  deleteEntry,
  isJournalUnlocked,
  journalUnlockedLocally,
  JournalError,
  listEntries,
  markJournalUnlocked,
  saveEntry,
  STORE,
  type JournalPhoto,
} from './journal'

/**
 * A minimal in-memory IndexedDB, because jsdom has none and the journal is the one part of
 * the app that needs it. It covers only what `journal.ts` actually calls, plus a switch to
 * force a transaction abort, which is how a real quota failure arrives.
 */
function stubFactory(options: { abort?: boolean } = {}) {
  const data = new Map<string, unknown>()

  const request = <T>(result: () => T) => {
    const req = { result: undefined as T, onsuccess: null, onerror: null } as unknown as IDBRequest<T>
    queueMicrotask(() => {
      ;(req as { result: T }).result = result()
    })
    return req
  }

  const store = {
    getAll: () => request(() => [...data.values()]),
    get: (id: string) => request(() => data.get(id)),
    count: () => request(() => data.size),
    put: (value: { id: string }) =>
      request(() => {
        if (!options.abort) data.set(value.id, value)
        return value.id
      }),
    delete: (id: string) => request(() => void data.delete(id)),
    clear: () => request(() => void data.clear()),
    createIndex: () => undefined,
  }

  const db = {
    objectStoreNames: { contains: () => true },
    createObjectStore: () => store,
    transaction: () => {
      const tx = {
        objectStore: () => store,
        error: options.abort ? new DOMException('QuotaExceededError') : null,
        oncomplete: null as null | (() => void),
        onabort: null as null | (() => void),
        onerror: null as null | (() => void),
      }
      // Settle after the request microtask has filled in its result.
      queueMicrotask(() => queueMicrotask(() => (options.abort ? tx.onabort?.() : tx.oncomplete?.())))
      return tx
    },
    close: () => undefined,
  }

  return {
    open: () => {
      const req = {
        result: db,
        onsuccess: null as null | (() => void),
        onupgradeneeded: null as null | (() => void),
        onerror: null,
        onblocked: null,
        error: null,
      }
      queueMicrotask(() => {
        req.onupgradeneeded?.()
        req.onsuccess?.()
      })
      return req
    },
  } as unknown as IDBFactory
}

const photo = (id: string): JournalPhoto => ({
  id,
  blob: new Blob(['x'], { type: 'image/jpeg' }),
  width: 10,
  height: 10,
})

describe('journal storage', () => {
  it('saves an entry and reads it back', async () => {
    const f = stubFactory()
    const saved = await saveEntry({ caption: '  a green door  ' }, f)
    expect(saved.caption).toBe('a green door') // trimmed
    expect(saved.id).toBeTruthy()
    expect(saved.createdAt).toMatch(/^\d{4}-/)
    const rows = await listEntries(f)
    expect(rows).toHaveLength(1)
    expect(rows[0]?.caption).toBe('a green door')
  })

  it('lists the newest entry first', async () => {
    const f = stubFactory()
    await saveEntry({ caption: 'older', createdAt: '2026-10-01T10:00:00.000Z' }, f)
    await saveEntry({ caption: 'newer', createdAt: '2026-10-09T10:00:00.000Z' }, f)
    await saveEntry({ caption: 'middle', createdAt: '2026-10-05T10:00:00.000Z' }, f)
    expect((await listEntries(f)).map((e) => e.caption)).toEqual(['newer', 'middle', 'older'])
  })

  it('keeps the quest context handed to it', async () => {
    const f = stubFactory()
    await saveEntry(
      { caption: 'done', questTitle: 'Door Detective', placeName: 'Riverside Gardens', category: 'explorer' },
      f,
    )
    const [entry] = await listEntries(f)
    expect(entry?.questTitle).toBe('Door Detective')
    expect(entry?.placeName).toBe('Riverside Gardens')
    expect(entry?.category).toBe('explorer')
  })

  it('appends photos to an existing entry', async () => {
    const f = stubFactory()
    const saved = await saveEntry({ caption: 'walk', photos: [photo('a')] }, f)
    const updated = await addPhotos(saved.id, [photo('b'), photo('c')], f)
    expect(updated.photos.map((p) => p.id)).toEqual(['a', 'b', 'c'])
  })

  it('refuses to add photos to an entry that is gone', async () => {
    const f = stubFactory()
    await expect(addPhotos('nope', [photo('a')], f)).rejects.toBeInstanceOf(JournalError)
  })

  it('deletes one entry and clears them all', async () => {
    const f = stubFactory()
    const a = await saveEntry({ caption: 'one' }, f)
    await saveEntry({ caption: 'two' }, f)
    await deleteEntry(a.id, f)
    expect(await countEntries(f)).toBe(1)
    await clearJournal(f)
    expect(await countEntries(f)).toBe(0)
  })

  it('turns a storage abort into a message the player can act on', async () => {
    const f = stubFactory({ abort: true })
    // A quota failure is the realistic cause, and "no room" is the only useful thing to say.
    await expect(saveEntry({ caption: 'too big' }, f)).rejects.toThrow(/no room/i)
  })

  it('reports a browser with no IndexedDB instead of throwing', async () => {
    expect(available(undefined)).toBe(false)
    await expect(listEntries(undefined as unknown as IDBFactory)).rejects.toBeInstanceOf(JournalError)
  })
})

describe('journal unlocking', () => {
  beforeEach(() => window.localStorage.clear())

  it('starts locked', () => {
    expect(journalUnlockedLocally()).toBe(false)
    expect(isJournalUnlocked()).toBe(false)
    expect(isJournalUnlocked(0)).toBe(false)
  })

  it('unlocks on the first completed quest, offline included', () => {
    markJournalUnlocked()
    expect(journalUnlockedLocally()).toBe(true)
    // No server count available (API down) and it is still unlocked: that is the point.
    expect(isJournalUnlocked(undefined)).toBe(true)
  })

  it('unlocks from the server count when the local flag was cleared', () => {
    expect(journalUnlockedLocally()).toBe(false)
    expect(isJournalUnlocked(3)).toBe(true)
  })

  it('uses the store name the app shipped with', () => {
    // Changing this silently would orphan every photo already on a player's device.
    expect(STORE).toBe('entries')
  })
})
