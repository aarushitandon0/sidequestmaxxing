import { useState } from 'react'

import { Link } from 'react-router-dom'

import {
  clearFieldLog,
  csvFilename,
  readFieldLog,
  toCsv,
  type FieldEntry,
} from '../lib/fieldLog'

const share = (entries: FieldEntry[]) => {
  const shares = entries
    .map((e) => e.screen_share)
    .filter((v): v is number => typeof v === 'number')
    .sort((a, b) => a - b)
  if (!shares.length) return null
  const mid = Math.floor(shares.length / 2)
  const hi = shares[mid] ?? 0
  const median = shares.length % 2 ? hi : ((shares[mid - 1] ?? hi) + hi) / 2
  return Math.round(median * 100)
}

/**
 * Hidden field-test export (P21): /settings/export, deliberately not linked from anywhere.
 * It is a tool for whoever is running the field test, not a game screen — the numbers it
 * shows are the ones that go in the write-up, and the CSV is the only thing that leaves.
 */
export function Export() {
  const [entries, setEntries] = useState<FieldEntry[]>(() => readFieldLog())
  const [copied, setCopied] = useState(false)
  const [confirm, setConfirm] = useState(false)

  const csv = toCsv(entries)
  const minutes = Math.round(entries.reduce((s, e) => s + e.elapsed_seconds, 0) / 60)
  const median = share(entries)

  const download = () => {
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = csvFilename(entries)
    a.click()
    URL.revokeObjectURL(url)
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(csv)
      setCopied(true)
    } catch {
      setCopied(false) // no clipboard permission: the download still works
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <h1 className="sign-title self-start text-3xl">Field test export</h1>

      <section aria-labelledby="fx-log" className="parchment p-4 sm:p-5">
        <h2 id="fx-log" className="text-2xl">Your completions</h2>
        <p className="mt-1 text-ink-soft">
          Recorded on this device only, one row per finished quest. No coordinates, no place
          names, no photos — nothing here has ever been sent anywhere.
        </p>
        <dl className="mt-3 grid grid-cols-3 gap-3 text-center">
          <div className="rounded-xl bg-parchment-deep/40 p-3">
            <dt className="text-sm text-ink-soft">Quests</dt>
            <dd className="text-3xl">{entries.length}</dd>
          </div>
          <div className="rounded-xl bg-parchment-deep/40 p-3">
            <dt className="text-sm text-ink-soft">Minutes outside</dt>
            <dd className="text-3xl">{minutes}</dd>
          </div>
          <div className="rounded-xl bg-parchment-deep/40 p-3">
            <dt className="text-sm text-ink-soft">Median screen</dt>
            <dd className="text-3xl">{median === null ? '—' : `${median}%`}</dd>
          </div>
        </dl>

        {entries.length === 0 ? (
          <p className="mt-4">
            Nothing logged yet. Finish a quest and it shows up here.{' '}
            <Link to="/home" className="underline">
              Start one
            </Link>
            .
          </p>
        ) : (
          <>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" className="btn btn-wood" onClick={download}>
                Download CSV
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => void copy()}>
                Copy CSV
              </button>
            </div>
            {copied ? (
              <p role="status" className="mt-1 text-sm">
                Copied {entries.length} rows to your clipboard.
              </p>
            ) : null}
            <p className="mt-3 text-sm text-ink-soft">
              Then: <code>python scripts/summarize_field.py &lt;file.csv&gt;</code>
            </p>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Logged quest completions</caption>
                <thead>
                  <tr className="border-b border-edge/50">
                    <th scope="col" className="py-1 pr-3">Date</th>
                    <th scope="col" className="py-1 pr-3">Skill</th>
                    <th scope="col" className="py-1 pr-3">Minutes</th>
                    <th scope="col" className="py-1 pr-3">Screen</th>
                    <th scope="col" className="py-1">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {[...entries].reverse().map((e) => (
                    <tr key={e.quest_id} className="border-b border-edge/30">
                      <td className="py-1 pr-3">{e.date}</td>
                      <td className="py-1 pr-3">{e.category}</td>
                      <td className="py-1 pr-3">{Math.round(e.elapsed_seconds / 60)}</td>
                      <td className="py-1 pr-3">
                        {e.screen_share === null ? '—' : `${Math.round(e.screen_share * 100)}%`}
                      </td>
                      <td className="py-1">{e.source ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section aria-labelledby="fx-clear" className="parchment p-4 sm:p-5">
        <h2 id="fx-clear" className="text-2xl">Clear the log</h2>
        <p className="mt-1 text-ink-soft">
          Deletes the rows above. Your XP, streak and chronicle are not affected.
        </p>
        {confirm ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-wood"
              onClick={() => {
                clearFieldLog()
                setEntries([])
                setConfirm(false)
              }}
            >
              Yes, delete {entries.length} rows
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setConfirm(false)}>
              Keep them
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="btn btn-ghost mt-3"
            disabled={!entries.length}
            onClick={() => setConfirm(true)}
          >
            Clear field log
          </button>
        )}
      </section>
    </div>
  )
}
