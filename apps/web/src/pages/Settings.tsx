import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'

import { PersonaPicker } from '../components/PersonaPicker'
import { api, friendlyError } from '../lib/api'
import { INTEREST_OPTIONS, RADIUS_OPTIONS } from '../lib/prefs'
import { clearAppStorage } from '../lib/storage'
import { usePrefs } from '../state/hooks'
import { VerifierInstall } from './VerifierInstall'

export function Settings() {
  const [prefs, update] = usePrefs()
  const [confirm, setConfirm] = useState(false)
  const del = useMutation({
    mutationFn: api.deleteProfile,
    onSuccess: () => {
      clearAppStorage() // device id, prefs, active quest — a fresh start
      window.location.assign('/')
    },
  })

  const toggleInterest = (i: string) => {
    const has = prefs.interests.includes(i)
    update({ interests: has ? prefs.interests.filter((x) => x !== i) : [...prefs.interests, i].slice(0, 6) })
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <h1 className="hand-title text-4xl">Settings</h1>

      <section aria-labelledby="s-dm" className="parchment p-4">
        <h2 id="s-dm" className="text-2xl">Your Dungeon Master</h2>
        <div className="mt-3">
          <PersonaPicker value={prefs.persona} onChange={(p) => update({ persona: p })} />
        </div>
      </section>

      <section aria-labelledby="s-int" className="parchment p-4">
        <h2 id="s-int" className="text-2xl">Interests & range</h2>
        <div className="mt-2 flex flex-wrap gap-2">
          {INTEREST_OPTIONS.map((i) => (
            <button key={i} type="button" className="toggle-chip" aria-pressed={prefs.interests.includes(i)} onClick={() => toggleInterest(i)}>
              {i}
            </button>
          ))}
        </div>
        <div role="radiogroup" aria-label="Quest radius" className="mt-4 flex gap-2">
          {RADIUS_OPTIONS.map((r) => (
            <button key={r.value} type="button" role="radio" aria-checked={prefs.radiusM === r.value} className="toggle-chip" onClick={() => update({ radiusM: r.value })}>
              {r.label}
            </button>
          ))}
        </div>
        <label className="mt-4 flex min-h-11 items-center gap-3 text-lg">
          <input type="checkbox" className="h-6 w-6 accent-moss" checked={prefs.voice} onChange={(e) => update({ voice: e.target.checked })} />
          Spoken briefings
        </label>
      </section>

      <section aria-labelledby="s-ver" className="parchment p-4">
        <h2 id="s-ver" className="text-2xl">Photo checks</h2>
        <div className="mt-2">
          <VerifierInstall />
        </div>
      </section>

      <section aria-labelledby="s-priv" className="parchment p-4">
        <h2 id="s-priv" className="text-2xl">Privacy & safety</h2>
        <ul className="mt-2 list-disc space-y-1 pl-6">
          <li>Photos and exact movements stay on your device; the server sees an approximate area to find nearby places.</li>
          <li>You're identified only by a random ID on this device. No account, no email, no name.</li>
          <li>Sidequestmaxxing is a game. It is not an emergency or navigation tool. Tell someone where you're going.</li>
          <li>
            Map data © <a className="underline" href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors.
          </li>
        </ul>
        {confirm ? (
          <div role="alertdialog" aria-labelledby="del-q" className="mt-4 rounded-xl border-2 border-berry/50 p-3">
            <p id="del-q">Delete your XP, quests, memories and this device's ID? This can't be undone.</p>
            <div className="mt-2 flex gap-2">
              <button type="button" className="btn bg-berry text-parchment-light" onClick={() => del.mutate()} disabled={del.isPending}>
                {del.isPending ? 'Deleting…' : 'Yes, delete everything'}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setConfirm(false)}>
                Cancel
              </button>
            </div>
            {del.isError ? <p role="alert" className="mt-2 text-berry">{friendlyError(del.error)}</p> : null}
          </div>
        ) : (
          <button type="button" className="btn btn-ghost mt-4 text-berry" onClick={() => setConfirm(true)}>
            Delete my data
          </button>
        )}
      </section>
    </div>
  )
}
