import type { Category } from '../lib/types'
import { BootIcon, BowlIcon, BrushIcon, CompassIcon, EyeIcon, LeafIcon, PeopleIcon } from './Icons'

const ICON = {
  explorer: CompassIcon,
  naturalist: LeafIcon,
  social: PeopleIcon,
  foodie: BowlIcon,
  creative: BrushIcon,
  fitness: BootIcon,
  mindful: EyeIcon,
} as const

const FILL: Record<Category, string> = {
  explorer: '#2c4f6b',
  naturalist: '#3f6b3c',
  social: '#7a4a2b',
  foodie: '#8a5a1f',
  creative: '#2d4d7a',
  fitness: '#5b3a6b',
  mindful: '#3d6b5d',
}

/** Gold-ringed skill medallion (design template skill tree). */
export function Medallion({ category, size = 64, dim = false }: { category: Category; size?: number; dim?: boolean }) {
  const Icon = ICON[category]
  return (
    <span
      aria-hidden="true"
      className="inline-flex items-center justify-center rounded-full"
      style={{
        width: size,
        height: size,
        background: `radial-gradient(circle at 35% 30%, rgb(255 255 255 / .25), transparent 55%), ${FILL[category]}`,
        border: `${Math.max(3, size / 14)}px solid #e2b55c`,
        boxShadow: '0 0 0 2px #7a5420, 0 6px 12px rgb(59 42 30 / .3)',
        color: '#f6e7c4',
        fontSize: size * 0.48,
        filter: dim ? 'saturate(.55) opacity(.8)' : undefined,
      }}
    >
      <Icon />
    </span>
  )
}

export function CategoryIcon({ category }: { category: Category }) {
  const Icon = ICON[category]
  return <Icon />
}
