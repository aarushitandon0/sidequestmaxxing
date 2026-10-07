import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'

import { formatDistance } from '../lib/labels'
import { useQuest } from '../state/QuestProvider'

const QuestMap = lazy(() => import('../components/QuestMap'))

/** Optional map (MASTERSPEC §11.1 #9): the active quest's place on OpenStreetMap. */
export function MapPage() {
  const { run } = useQuest()
  const place = run.quest?.place
  return (
    <div className="flex flex-col gap-4">
      <h1 className="hand-title text-4xl">Map</h1>
      {place && run.quest ? (
        <>
          <div className="parchment flex flex-wrap items-center gap-3 p-3">
            <p className="flex-1 text-xl">
              {run.quest.title} — {place.name}
              {run.quest.distance_m != null ? ` · ${formatDistance(run.quest.distance_m)}` : ''}
            </p>
            <Link className="btn btn-moss" to={run.phase === 'offered' ? '/quest' : run.phase === 'completed' ? '/reward' : '/walk'}>
              Open quest
            </Link>
          </div>
          <Suspense fallback={<div className="parchment h-[60dvh]" aria-hidden="true" />}>
            <QuestMap place={place} className="h-[60dvh]" />
          </Suspense>
          <p className="text-ink-soft">Not a navigation tool — follow signs, paths and crossings.</p>
        </>
      ) : (
        <div className="parchment p-6 text-center">
          <p className="text-xl">No quest place to show yet.</p>
          <Link to="/home" className="btn btn-wood mt-3">
            Get a quest
          </Link>
        </div>
      )}
    </div>
  )
}
