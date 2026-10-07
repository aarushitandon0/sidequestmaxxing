/**
 * Browser speech (MASTERSPEC §2.4 fallback voice). The ElevenLabs voice (P13) will try the
 * server first and fall back here. The text is always also shown on screen.
 */

export function canSpeak(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

export function speak(text: string, onEnd?: () => void): boolean {
  if (!canSpeak()) return false
  const synth = window.speechSynthesis
  synth.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.rate = 0.98
  u.onend = () => onEnd?.()
  u.onerror = () => onEnd?.()
  synth.speak(u)
  return true
}

export function stopSpeaking(): void {
  if (canSpeak()) window.speechSynthesis.cancel()
}
