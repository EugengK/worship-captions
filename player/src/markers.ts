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
 * (Slides with prepared captions are switched off separately: see liveTranslation.)
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


/** Prepared captions for one slide: language code → text (may hold line breaks). */
export type FixedCaption = Record<string, string>

export interface CaptionFile {
  title: string
  /** 1-based slide number → captions */
  slides: Map<number, FixedCaption>
  /** Start of the slide's Korean text, to notice a deck that changed after the file was made */
  expect: Map<number, string>
}

/**
 * Reads a prepared-captions file:
 *   { "title": "...", "slides": { "38": { "ko": "슬라이드 첫 글", "en": "...", "th": "..." }, ... } }
 * "ko" is only a check against the slide; every other key is a caption language.
 */
export function parseCaptionFile(text: string): CaptionFile {
  const data = JSON.parse(text)
  if (!data || typeof data !== 'object' || typeof data.slides !== 'object') {
    throw new Error('자막 파일 형식이 아닙니다 ("slides" 없음)')
  }
  const slides = new Map<number, FixedCaption>()
  const expect = new Map<number, string>()
  for (const [key, value] of Object.entries(data.slides as Record<string, unknown>)) {
    const no = Number(key)
    if (!Number.isInteger(no) || no < 1 || !value || typeof value !== 'object') continue
    const caption: FixedCaption = {}
    for (const [lang, t] of Object.entries(value as Record<string, unknown>)) {
      if (typeof t !== 'string' || !t.trim()) continue
      if (lang === 'ko') expect.set(no, t.trim())
      else caption[lang] = t.trim()
    }
    if (Object.keys(caption).length) slides.set(no, caption)
  }
  return { title: typeof data.title === 'string' ? data.title : '', slides, expect }
}

const squash = (s: string) => s.replace(/\s+/g, '')

/** Slide numbers whose text no longer starts the way the caption file expects. */
export function mismatchedSlides(file: CaptionFile, slideText: (no: number) => string | undefined): number[] {
  const out: number[] = []
  for (const [no, ko] of file.expect) {
    const text = slideText(no)
    if (text === undefined || !squash(text).startsWith(squash(ko).slice(0, 12))) out.push(no)
  }
  return out
}

/**
 * Live translation on a slide: prepared captions replace it (no cost) unless the notes
 * explicitly say [번역 ON]; otherwise the carried on/off state applies.
 */
export function liveTranslation(carried: boolean, marker: boolean | null, hasFixed: boolean): boolean {
  return hasFixed && marker !== true ? false : carried
}
