/**
 * Per-slide rules of the worship player that need no browser: the [번역 ON]/[번역 OFF] notes
 * markers and which audio clips PowerPoint starts by itself.
 */

const ON = /\[\s*번역\s*ON\s*\]/i
const OFF = /\[\s*번역\s*OFF\s*\]/i

/** Reads the marker in a slide's notes; OFF wins if someone wrote both. */
export function notesMarker(notes: string): boolean | null {
  if (OFF.test(notes)) return false
  if (ON.test(notes)) return true
  return null
}

/**
 * Carries markers forward. Before the first marker translation is off, so the opening
 * hymns stay quiet; a deck with no markers at all keeps translation on throughout.
 */
export function translationStates(markers: (boolean | null)[]): boolean[] {
  const any = markers.some((m) => m !== null)
  let on = !any
  return markers.map((m) => (on = m ?? on))
}

/** Media started by PowerPoint without a click: a mediacall effect that is not a click effect. */
export function autoplayIds(slideXml: string): Set<string> {
  const ids = new Set<string>()
  const re = /<p:cTn[^>]*presetClass="mediacall"[^>]*>[\s\S]*?<p:spTgt spid="(\d+)"/g
  for (const m of slideXml.matchAll(re)) {
    const tag = m[0].slice(0, m[0].indexOf('>'))
    if (!/nodeType="clickEffect"/.test(tag)) ids.add(m[1]!)
  }
  return ids
}

