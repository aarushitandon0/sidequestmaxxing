import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <main className="mx-auto max-w-md px-5 py-10">
      <h1 className="font-[family-name:var(--font-display)] text-3xl text-moss">This path is overgrown.</h1>
      <Link to="/" className="mt-4 inline-block min-h-11 py-2 text-moss-light underline">
        Back to the quest board
      </Link>
    </main>
  )
}
