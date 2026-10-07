/** Shape of src/story/data.json (built by scripts/build_story_data.ts). */
export interface Metric {
  label: string
  baseline: number | string | null
  tuned: number | string | null
  unit?: string
}
export interface StoryData {
  results: { source: string; n: number | null; metrics: Metric[] } | null
  field: { source: string; rows: { label: string; value: string }[] } | null
}

