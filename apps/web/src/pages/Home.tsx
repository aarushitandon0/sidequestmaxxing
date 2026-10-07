import { useQuery } from '@tanstack/react-query'

import { api } from '../lib/api'

function StatusPill({ label, value }: { label: string; value: string }) {
  const tone =
    value === 'ok' ? 'bg-moss-light text-parchment' : value === 'down' ? 'bg-berry text-parchment' : 'bg-parchment-deep text-bark'
  return (
    <li className={`rounded-full px-3 py-1 text-sm font-medium ${tone}`}>
      {label}: {value}
    </li>
  )
}

export function Home() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col gap-8 px-5 py-10">
      <header>
        <p className="text-sm font-semibold tracking-widest text-moss-light uppercase">Quest log</p>
        <h1 className="font-[family-name:var(--font-display)] text-4xl leading-tight text-moss">
          Your city is the game.
        </h1>
        <p className="mt-3 text-lg">Your phone is just the quest log. Grab a quest, pocket the phone, go outside.</p>
      </header>

      <button
        type="button"
        disabled
        className="min-h-14 rounded-2xl bg-lantern px-6 text-lg font-bold text-bark shadow-[0_4px_0_var(--color-bark)] disabled:opacity-60"
      >
        Get a quest (coming soon)
      </button>

      <section aria-labelledby="status-heading" className="rounded-2xl border-2 border-parchment-deep p-4">
        <h2 id="status-heading" className="font-semibold">
          Dungeon status
        </h2>
        {health.isPending && <p role="status">Checking the realm…</p>}
        {health.isError && (
          <p role="alert" className="text-berry">
            Can't reach the Dungeon Master right now.
          </p>
        )}
        {health.isSuccess && (
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Service status">
            <StatusPill label="api" value={health.data.status} />
            <StatusPill label="db" value={health.data.db} />
            <StatusPill label="llm" value={health.data.llm} />
          </ul>
        )}
      </section>
    </main>
  )
}
