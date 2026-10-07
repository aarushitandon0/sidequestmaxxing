import type { ReactNode, SVGProps } from 'react'

/** Small hand-drawn-style line icons (inline SVG, currentColor). Decorative by default. */
type IconProps = SVGProps<SVGSVGElement> & { title?: string }

function Svg({ title, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  )
}

export const LeafIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 19c0-8 5-13 14-14-1 9-6 14-14 14Z" />
    <path d="M5 19 13 11" />
  </Svg>
)
export const CompassIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="m15.5 8.5-2 5-5 2 2-5 5-2Z" />
  </Svg>
)
export const MapIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m3 6 6-2 6 2 6-2v14l-6 2-6-2-6 2V6Z" />
    <path d="M9 4v14M15 6v14" />
  </Svg>
)
export const ScrollIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 4h11a2 2 0 0 1 0 4H7" />
    <path d="M7 4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8" />
    <path d="M9 12h6M9 15h4" />
  </Svg>
)
export const StarIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z" />
  </Svg>
)
export const BookIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 5c3-1 6-1 8 1 2-2 5-2 8-1v14c-3-1-6-1-8 1-2-2-5-2-8-1V5Z" />
    <path d="M12 6v14" />
  </Svg>
)
export const GearIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10.3 3h3.4l.5 2.4a7 7 0 0 1 1.8 1l2.3-.8 1.7 2.9-1.8 1.6a7 7 0 0 1 0 2l1.8 1.6-1.7 2.9-2.3-.8a7 7 0 0 1-1.8 1l-.5 2.4h-3.4l-.5-2.4a7 7 0 0 1-1.8-1l-2.3.8-1.7-2.9 1.8-1.6a7 7 0 0 1 0-2L4 8.5l1.7-2.9 2.3.8a7 7 0 0 1 1.8-1L10.3 3Z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
)
export const HeadphonesIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 15v-3a8 8 0 0 1 16 0v3" />
    <rect x="3" y="14" width="4" height="6" rx="1.5" />
    <rect x="17" y="14" width="4" height="6" rx="1.5" />
  </Svg>
)
export const PlayIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 5v14l11-7L8 5Z" fill="currentColor" />
  </Svg>
)
export const StopIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
  </Svg>
)
export const CameraIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 8h3l2-3h6l2 3h3v11H4V8Z" />
    <circle cx="12" cy="13" r="3.5" />
  </Svg>
)
export const PinIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 21s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12Z" />
    <circle cx="12" cy="9" r="2.5" />
  </Svg>
)
export const CheckIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Svg>
)
export const XIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
)
export const ArrowRightIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Svg>
)
export const ClockIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Svg>
)
export const SunIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" fill="currentColor" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Svg>
)
export const FlameIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 21c4 0 7-2.7 7-6.5 0-4-3-6-4-9.5-2 2-2 4-3 5-1-1-1.5-2-1.5-3.5C7 9 5 11.5 5 14.5 5 18.3 8 21 12 21Z" />
  </Svg>
)
export const PeopleIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="9" cy="8" r="3" />
    <circle cx="17" cy="9" r="2.5" />
    <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M15 14.5c3 0 6 2 6 5.5" />
  </Svg>
)
export const BowlIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 11h18a9 9 0 0 1-18 0Z" />
    <path d="M9 7c0-1.5 1-2 1-3.5M13 7c0-1.5 1-2 1-3.5" />
  </Svg>
)
export const BrushIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 4 11 13" />
    <path d="M11 13c-3 0-4 2-4 4s-1.5 3-3 3c4 1 9 0 9-4 0-1.2-.8-2.2-2-3Z" />
  </Svg>
)
export const BootIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 3h5v8l6 3c1.5.8 2 1.8 2 3v2H4V4" />
    <path d="M4 15h16M9 7h3M9 10h3" />
  </Svg>
)
export const EyeIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
)
export const LockIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="5" y="11" width="14" height="10" rx="2" />
    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </Svg>
)
export const PhoneIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="7" y="2.5" width="10" height="19" rx="2" />
    <path d="M11 18.5h2" />
  </Svg>
)
export const ImageIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <circle cx="9" cy="10" r="1.8" />
    <path d="m21 16-5-5-8 8" />
  </Svg>
)
export const UserIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8" />
  </Svg>
)
export const HomeIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m3 11 9-7 9 7" />
    <path d="M5 10v10h14V10" />
  </Svg>
)
export const WifiOffIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2 8.5a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0M8.5 15.5a6 6 0 0 1 7 0" />
    <circle cx="12" cy="19" r="1" fill="currentColor" />
    <path d="M3 3l18 18" />
  </Svg>
)
