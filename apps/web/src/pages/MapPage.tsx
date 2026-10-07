import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'

import { ART, CATEGORY_ART } from '../components/art'
import { PinIcon } from '../components/Icons'
import { formatDistance } from '../lib/labels'
import { useQuest } from '../state/QuestProvider'

const QuestMap = lazy(() => import('../components/QuestMap'))

/** Optional map (MASTERSPEC §11.1 #9): the active quest's place on OpenStreetMap. */
export function MapPage() {
  const { run } = useQuest()
  const place = run.quest?.place
  return (
    <div className="flex flex-col gap-5">
      <h1 className="sign-title self-start text-3xl">Map</h1>
      {place && run.quest ? (
        <div className="grid gap-5 lg:grid-cols-[1fr_340px] lg:gap-6">
          <Suspense fallback={<div className="parchment h-[60dvh] lg:h-[calc(100dvh-12rem)]" aria-hidden="true" />}>
            <QuestMap place={place} className="h-[60dvh] border-4 border-wood shadow-xl lg:h-[calc(100dvh-12rem)]" />
          </Suspense>
          <aside className="parchment flex flex-col gap-3 self-start p-5" aria-label="Quest place">
            <img src={CATEGORY_ART[run.quest.category]} alt="" className="h-36 w-full rounded-xl object-cover" />
            <h2 className="hand-title text-2xl">{run.quest.title}</h2>
            <p className="flex items-center gap-1 text-lg">
              <PinIcon className="text-gold" /> {place.name}
              {run.quest.distance_m != null ? ` · ${formatDistance(run.quest.distance_m)}` : ''}
            </p>
            <p className="text-ink-soft">{run.quest.objective}</p>
            <Link className="btn btn-moss" to={run.phase === 'offered' ? '/quest' : run.phase === 'completed' ? '/reward' : '/walk'}>
              Open quest
            </Link>
            <p className="text-sm text-ink-soft">Not a navigation tool — follow signs, paths and crossings.</p>
          </aside>
        </div>
      ) : (
        <div className="parchment-frame mx-auto w-full max-w-3xl">
          <div className="parchment grid items-center gap-6 p-6 sm:grid-cols-[1fr_1.2fr] sm:p-8">
            <img src={ART.sceneRiver} alt="" className="h-56 w-full rounded-xl object-cover" />
            <div>
              <p className="hand-title text-3xl">No quest place to show yet.</p>
              <p className="mt-2 text-ink-soft">Once you have a quest, its place appears here on OpenStreetMap.</p>
              <Link to="/home" className="btn btn-wood mt-4">
                Get a quest
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
