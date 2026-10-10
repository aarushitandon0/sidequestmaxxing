# Sidequestmaxxing — intro film: audio script

Companion to `sidequestmaxxing_intro.mp4` (1920×1080, 2.39:1 letterbox, 30 fps, **85.1 s**, no audio).

The picture is already cut and locked, so every cue below is pinned to a real timecode in
that file. On-screen text is listed because music and VO should breathe around it, never
fight it.

Three layers: **MUSIC**, **AMBIENCE/SFX**, **VO**. The film reads fine with music and
ambience only — the VO is optional and the on-screen captions already carry the argument.

---

## The one rule

The whole film turns on a single idea: **the digital layer gets quieter as the real world
gets louder.** Notification blips and interface sounds belong only before 0:40. After the
blackout there should be no UI sound at all — only footsteps, air, and birds. If a sound
designer takes one note from this document, take that one.

---

## ACT I · The loop — 0:00–0:18.4

Mood: muted, repetitive, slightly melancholic. Nothing resolves.

| Time | Layer | Cue |
|---|---|---|
| 0:00 | MUSIC | Felt piano, ~70 bpm. Two chords only — **Am → Em**, alternating every bar. Motif: A–C–E–C, one note per beat. Soft, close-mic'd, a little pedal noise. Never resolves to a major chord. |
| 0:00 | AMB | Rain against glass, steady, gentle gusts every ~8 s. Low room tone underneath. Keep rain around −26 LUFS; it should feel like weather, not static. |
| 0:01.3 / 0:02.7 / 0:04.0 | SFX | Three notification blips, each slightly **duller and quieter** than the last. Muffled, as if heard through the phone in his hand. |
| 0:06.4 | MUSIC | Same loop continues through the cut — the point is that nothing changed. |
| 0:11.2–0:11.9 | ALL | **Dip to black.** Duck everything to ~12 %. Rain stays faintly audible. |
| 0:11.9–0:18.4 | MUSIC | Loop breaks. One sustained low A. Three single notes only — A, then E, then a high A at 0:17 — with long gaps. Let the silence sit. |
| 0:16 → 0:18.4 | AMB | Rain fades out almost completely. |

**VO (optional), 0:02.3–0:05.8** — matches the on-screen caption:
> "Some days the world shrinks to one glowing rectangle."

---

## ACT II · The reveal — 0:18.4–0:40.1

| Time | Layer | Cue |
|---|---|---|
| **0:18.45** | SFX | **The chime.** A bell cluster — A5, E6, A6 — bright, long tail. This is the single loudest moment in the first half; let it ring over the gold flash. |
| 0:18.5 | MUSIC | The theme arrives in major: **F → C → G → Am**, same tempo, same instrument. It should be recognisable as the Act I motif, now resolved. Add a quiet arpeggio an octave up. |
| 0:24.7 | MUSIC | Hold the progression steady under the UI shots — minimal movement, no build yet. |
| 0:33.8 | SFX | Very soft interface tone as the quest is read aloud. Last UI sound in the film. |
| 0:37.8 | MUSIC | Begin pulling elements out. Arpeggio drops first, then the upper pad. |
| **0:40.1–0:41.9** | ALL | **The blackout.** Cut everything to ~10 %. One low hum only. This is the hinge of the film — it must feel like the sound was switched off, not faded. |

**VO 0:25.3–0:28.8** (caption on screen):
> "Tell it how much time you have — and what kind of adventure you're in the mood for."

**VO 0:29.9–0:33.4** (caption on screen):
> "An open-weight AI Dungeon Master writes one real quest, from the actual places around you."

---

## ACT III · Outside — 0:41.4–1:09.2

The world replaces the interface. Everything here is acoustic and real.

| Time | Layer | Cue |
|---|---|---|
| 0:41.4 | AMB | Outdoor air swells up as the door opens — open, bright, a little traffic in the far distance. |
| 0:42.4 | SFX | **Footsteps begin**, ~0.55 s apart, natural variation. They continue to about 0:55. |
| 0:43.6 | AMB | First birdsong. Sparse and high. Repeat at roughly 0:46.9, 0:50.2, 0:53.8, 0:57.9. |
| 0:41.5 | MUSIC | Theme returns fuller — **F → C → G → C**. Warmer, strings or a second piano voice. |
| **0:45.6** | SFX | Low, soft "stamp" as WALK MODE: ACTIVE resolves on screen. Felt more than heard. |
| 0:47.2 | MUSIC | Lift into the montage. Add a light off-beat pluck. Energy up, still unhurried — this is joy, not urgency. |
| 0:53.5 | MUSIC | Pull back slightly under the verification beat so the badge reads. |
| **0:59.0** | SFX | **Quest-complete flourish.** Ascending pentatonic bells — C, E, G, C. Bright and generous. |
| 0:59.0 | SFX | Light sparkle shimmer under the XP count-up, resolving as it reaches +50. |
| 1:04.1 | MUSIC | Settle. Sunset beat — let it breathe, drop to pad and single notes. |

**VO 1:00.4–1:04.0** (caption on screen, right-hand column):
> "It rewards you for going outside — not for staying in the app."

---

## ACT IV · The thesis — 1:09.2–1:25.1

| Time | Layer | Cue |
|---|---|---|
| 1:09.2 | MUSIC | Final progression, slowing: **F → G → C**. Full and warm. |
| 1:09.2 | AMB | Evening air. One or two distant birds. Nothing else. |
| 1:14.0 | MUSIC | Arrive on **C major** and hold. Let it ring under the title. No new material after this point. |
| 1:14.0–1:24 | — | **Hold.** Roughly ten seconds on the final composition. Resist the urge to fill it. |
| 1:24.3–1:25.1 | ALL | Fade to black and to silence together. |

**VO 1:10.6–1:14.8** (caption on screen):
> "Every street you haven't walked is an unopened quest."

**Optional closing VO**, 1:16–1:20, over the held title — only if the film is running without
the captions:
> "Sidequestmaxxing. Your city is the game. Your phone is just the quest log."

---

## Mix notes

- **Target:** −14 LUFS integrated for web. True peak −1 dBTP.
- **Dynamic range matters more than loudness here.** The chime at 0:18.45 and the flourish at
  0:59 should measure clearly hotter than everything around them. The blackout at 0:40 should
  measure clearly quieter. If the whole thing sits at one level, the edit stops working.
- **Music sits under, not over.** Duck ~3 dB beneath any VO.
- Keep the low end clean below 60 Hz — this will mostly be watched on laptop and phone speakers.
- If you use a licensed track instead of a custom score, look for solo piano or acoustic
  folk with a clear major-key lift around 20 s in, and edit the track so its brightest moment
  lands on 0:18.45.

---

## Accessibility

The film must ship with captions regardless of whether VO is recorded — this is a
project invariant (text alternative for all audio). The five on-screen caption lines above
are burned into the picture already; if VO is added, supply a `.vtt` covering the VO and
the significant sound cues (rain, chime, footsteps, quest-complete).
