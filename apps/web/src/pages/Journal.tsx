import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { ART } from '../components/art'
import { CameraIcon, ImageIcon, LeafIcon, LockIcon, ScrollIcon, XIcon } from '../components/Icons'
import {
  available,
  deleteEntry,
  downscale,
  isJournalUnlocked,
  JournalError,
  listEntries,
  saveEntry,
  type JournalEntry,
  type JournalPhoto,
} from '../lib/journal'
import { useProfile } from '../state/hooks'

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })

/** One stored photo. Owns its blob URL so it is always revoked when the photo leaves the page. */
function Photo({ photo, alt }: { photo: JournalPhoto; alt: string }) {
  const url = useMemo(() => URL.createObjectURL(photo.blob), [photo.blob])
  // Revoked when the photo leaves the page, or the browser holds the blob for the session.
  useEffect(() => () => URL.revokeObjectURL(url), [url])
  return (
    <img
      src={url}
      alt={alt}
      width={photo.width}
      height={photo.height}
      className="aspect-square w-full rounded-xl border-2 border-parchment-light object-cover"
    />
  )
}

/** The "add to your journal" form: a note, and as many photos as you like. */
interface QuestContext {
  questTitle?: string
  placeName?: string
  category?: string
}

function Composer({ onSaved, context }: { onSaved: () => void; context: QuestContext }) {
  const [caption, setCaption] = useState('')
  const [photos, setPhotos] = useState<JournalPhoto[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const pick = async (files: FileList | null) => {
    if (!files?.length) return
    setError(null)
    setBusy(true)
    const added: JournalPhoto[] = []
    const failed: string[] = []
    for (const file of Array.from(files)) {
      try {
        added.push(await downscale(file))
      } catch {
        failed.push(file.name)
      }
    }
    setPhotos((p) => [...p, ...added])
    // Partial success is the common case with a multi-select, so say which ones went wrong
    // rather than throwing the good ones away.
    if (failed.length) setError(`Couldn't read ${failed.length} of those files.`)
    setBusy(false)
    if (fileInput.current) fileInput.current.value = ''
  }

  const save = async () => {
    if (!caption.trim() && !photos.length) {
      setError('Add a note or a photo first.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await saveEntry({ caption, photos, ...context })
      setCaption('')
      setPhotos([])
      onSaved()
    } catch (err) {
      setError(err instanceof JournalError ? err.message : 'That could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="add-title" className="parchment p-4 sm:p-5">
      <h2 id="add-title" className="hand-title flex items-center gap-2 text-2xl">
        <CameraIcon className="text-moss" /> Add to your journal
      </h2>
      {context.questTitle ? (
        <p className="mt-1 text-ink-soft">
          Filing under <strong>{context.questTitle}</strong>
          {context.placeName ? ` at ${context.placeName}` : ''}.
        </p>
      ) : null}

      <label htmlFor="caption" className="mt-3 block text-lg">
        What happened out there?
      </label>
      <textarea
        id="caption"
        value={caption}
        onChange={(e) => setCaption(e.target.value)}
        rows={3}
        placeholder="Found a door painted five different greens."
        className="mt-1 w-full rounded-xl border-2 border-wood-dark/40 bg-parchment-light p-3 text-lg"
      />

      {photos.length ? (
        <ul className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
          {photos.map((p, i) => (
            <li key={p.id} className="relative">
              <Photo photo={p} alt={`Photo ${i + 1} ready to save`} />
              <button
                type="button"
                aria-label={`Remove photo ${i + 1}`}
                onClick={() => setPhotos((all) => all.filter((x) => x.id !== p.id))}
                className="absolute -top-2 -right-2 flex h-9 w-9 items-center justify-center rounded-full border-2 border-wood-dark bg-parchment text-ink shadow"
              >
                <XIcon />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <label className="btn btn-ghost flex-1 cursor-pointer justify-center">
          <ImageIcon /> Add photos
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            multiple
            className="sr-only"
            onChange={(e) => void pick(e.target.files)}
          />
        </label>
        <button type="button" className="btn btn-moss flex-1" onClick={() => void save()} disabled={busy}>
          {busy ? 'Saving…' : 'Save entry'}
        </button>
      </div>

      {error ? (
        <p role="alert" className="mt-2 text-ink">
          {error}
        </p>
      ) : null}
      <p className="mt-2 text-sm text-ink-soft">
        Photos stay on this device — there is nowhere to upload them to. Location data is stripped
        from every picture before it is saved.
      </p>
    </section>
  )
}

/** The Journal (P24): the player's own photos and notes, stored only on this device. */
export function Journal() {
  const profile = useProfile()
  const [entries, setEntries] = useState<JournalEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const storable = available()
  const unlocked = isJournalUnlocked(profile.data?.quests_completed)
  // Handed over by the "add this to your journal" button on the reward screen.
  const context = (useLocation().state ?? {}) as QuestContext

  const reload = useCallback(() => {
    if (!available()) return // handled in render: nothing to load, and nothing to wait for
    listEntries()
      .then((rows) => {
        setEntries(rows)
        setError(null)
      })
      .catch((err: unknown) => {
        setError(err instanceof JournalError ? err.message : 'Your journal could not be opened.')
        setEntries([])
      })
  }, [])

  useEffect(() => {
    if (unlocked && storable) reload()
  }, [unlocked, storable, reload])

  const shownError = storable ? error : 'This browser cannot store a journal.'

  const remove = async (id: string) => {
    try {
      await deleteEntry(id)
      reload()
    } catch {
      setError('That entry could not be removed.')
    }
  }

  // Without the local flag the unlock depends on the server count, so claiming "sealed" before
  // the profile arrives would flash the locked panel at a player who has finished dozens.
  if (!unlocked && profile.isPending) {
    return (
      <p role="status" className="parchment p-5">
        Looking for your journal…
      </p>
    )
  }

  if (!unlocked) {
    return (
      <div className="mx-auto max-w-2xl">
        <div className="parchment-frame">
          <section aria-labelledby="locked-title" className="parchment p-6 text-center">
            <LockIcon className="mx-auto text-5xl text-wood-dark" />
            <h1 id="locked-title" className="hand-title mt-2 text-3xl">
              Your journal is still sealed
            </h1>
            <p className="mt-2 text-lg">
              Finish your first side quest and the journal opens. Then every quest after it can have
              your photos and notes in it.
            </p>
            <img src={ART.sceneForest} alt="" className="mx-auto mt-4 h-40 w-full rounded-xl object-cover" />
            <Link to="/home" className="btn btn-moss mt-5 inline-flex">
              <LeafIcon /> Get your first quest
            </Link>
          </section>
        </div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 lg:gap-6">
      <div className="lg:col-span-12">
        <h1 className="hand-title flex items-center gap-2 text-4xl">
          <ScrollIcon className="text-gold" /> Your Journal
        </h1>
        <p className="mt-1 text-lg text-parchment-deep">
          {entries === null && storable
            ? 'Opening…'
            : entries?.length
              ? `${entries.length} ${entries.length === 1 ? 'entry' : 'entries'}, kept on this device.`
              : 'Nothing in it yet.'}
        </p>
      </div>

      <div className="lg:col-span-5">
        <Composer onSaved={reload} context={context} />
      </div>

      <div className="lg:col-span-7">
        {shownError ? (
          <p role="alert" className="parchment p-4">
            {shownError}
          </p>
        ) : null}

        {entries === null && storable ? (
          <p role="status" className="parchment p-4">
            Opening your journal…
          </p>
        ) : null}

        {entries?.length === 0 && !shownError ? (
          <section className="parchment p-5 text-center">
            <ScrollIcon className="mx-auto text-4xl text-wood-dark" />
            <p className="mt-2 text-lg">
              Your first entry goes here. A photo of a door, a note about a bird — anything you want
              to keep.
            </p>
          </section>
        ) : null}

        <ul className="flex flex-col gap-4">
          {entries?.map((entry) => (
            <li key={entry.id}>
              <article className="parchment p-4">
                <div className="flex items-start gap-3">
                  <div className="flex-1">
                    {entry.questTitle ? <h2 className="hand-title text-2xl">{entry.questTitle}</h2> : null}
                    <p className="text-sm text-ink-soft">
                      {fmtDate(entry.createdAt)}
                      {entry.placeName ? ` · ${entry.placeName}` : ''}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost min-h-11"
                    onClick={() => void remove(entry.id)}
                    aria-label={`Delete entry from ${fmtDate(entry.createdAt)}`}
                  >
                    <XIcon />
                  </button>
                </div>
                {entry.caption ? <p className="mt-2 text-lg">{entry.caption}</p> : null}
                {entry.photos.length ? (
                  <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {entry.photos.map((p, i) => (
                      <li key={p.id}>
                        <Photo
                          photo={p}
                          alt={
                            entry.caption
                              ? `${entry.caption} (photo ${i + 1} of ${entry.photos.length})`
                              : `Journal photo ${i + 1} from ${fmtDate(entry.createdAt)}`
                          }
                        />
                      </li>
                    ))}
                  </ul>
                ) : null}
              </article>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
