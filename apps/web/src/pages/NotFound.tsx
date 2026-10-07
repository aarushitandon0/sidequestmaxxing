import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <main className="mx-auto max-w-md px-5 py-10">
      <div className="parchment p-6 text-center">
        <h1 className="hand-title text-3xl">This path is overgrown.</h1>
        <Link to="/home" className="btn btn-wood mt-4">
          Back to the quest board
        </Link>
      </div>
    </main>
  )
}
