/**
 * The cities whose places are seeded in Atlas (P24).
 *
 * Quests with real named places only exist where `places` has been seeded, and nothing
 * fetches OSM on a request path (docs/DECISIONS.md D-84). So a player whose GPS puts them
 * outside all of these — or who would rather not share a location at all — needs a way to
 * say "play here instead" and still get a real park with a real name.
 *
 * Each centre is the middle of that city's bounding box in `scripts/seed_cities.py`. Keep the
 * two lists in step: a city here that was never seeded gives a player place-less quests while
 * promising them a city, which is worse than not offering it.
 */

export interface City {
  slug: string
  name: string
  lat: number
  lng: number
}

export const SEEDED_CITIES: readonly City[] = [
  { slug: 'pune', name: 'Pune', lat: 18.525, lng: 73.85 },
  { slug: 'mumbai', name: 'Mumbai', lat: 19.085, lng: 72.875 },
  { slug: 'delhi', name: 'Delhi', lat: 28.61, lng: 77.2 },
  { slug: 'bengaluru', name: 'Bengaluru', lat: 12.97, lng: 77.61 },
  { slug: 'london', name: 'London', lat: 51.51, lng: -0.115 },
  { slug: 'new-york', name: 'New York', lat: 40.75, lng: -73.965 },
  { slug: 'san-francisco', name: 'San Francisco', lat: 37.77, lng: -122.45 },
  { slug: 'berlin', name: 'Berlin', lat: 52.51, lng: 13.385 },
  { slug: 'toronto', name: 'Toronto', lat: 43.67, lng: -79.395 },
  { slug: 'sydney', name: 'Sydney', lat: -33.87, lng: 151.215 },
  { slug: 'singapore', name: 'Singapore', lat: 1.325, lng: 103.84 },
  { slug: 'dubai', name: 'Dubai', lat: 25.235, lng: 55.275 },
] as const

export function findCity(slug: string): City | undefined {
  return SEEDED_CITIES.find((c) => c.slug === slug)
}
