// The ONE verifier prompt lives in /prompts (single source; hashed in prompts/HASHES.txt).
import template from '../../../../prompts/verifier.gemma.txt?raw'

export const VERIFIER_TEMPLATE: string = template

/** Fill {photo_prompt}. The photo prompt comes from our own validated quest (V6: never people). */
export function verifierPrompt(photoPrompt: string): string {
  const safe = photoPrompt.replace(/["\n\r]/g, ' ').slice(0, 100)
  return VERIFIER_TEMPLATE.replace('{photo_prompt}', safe)
}
