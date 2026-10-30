/**
 * Opens a .pptx in the browser with IeumOffice's engine and prepares everything the
 * presenter and audience windows draw: render trees, image URLs, embedded fonts,
 * audio clips and the [번역 ON]/[번역 OFF] notes markers.
 */
import { openPptx, getSlideNotes, listEmbeddedFonts } from '@genoffice/pptx-engine'
import type { EmbeddedFontFace } from '@genoffice/pptx-engine'
import { buildRenderSlide } from '@genoffice/pptx-render'
import type { RenderSlide } from '@genoffice/pptx-render'
import { CanvasMetrics, registerFonts } from './fonts'
import { autoplayIds, notesMarker, translationStates } from './markers'

/** Width the slides are laid out at; screens scale this up or down. */
export const RENDER_WIDTH = 1920

export interface AudioClip {
  /** Element id: the matching render node is the speaker icon, hidden on the projector */
  sourceId: string
  url: string
  /** PowerPoint starts it by itself on entering the slide (not on a click) */
  autoplay: boolean
}

export interface PlayerSlide {
  no: number
  render: RenderSlide
  notes: string
  /** true/false when the notes carry a marker, null when the slide keeps the previous state */
  marker: boolean | null
  /** Translation state on this slide after carrying markers forward */
  translate: boolean
  audio: AudioClip[]
  /** Slide's first line of text, for the slide list */
  title: string
}

export interface PlayerDeck {
  name: string
  slides: PlayerSlide[]
  fonts: EmbeddedFontFace[]
  /** At least one slide has a marker; with none, translation stays on throughout */
  hasMarkers: boolean
}

const MIME: Record<string, string> = {
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', bmp: 'image/bmp',
  svg: 'image/svg+xml', webp: 'image/webp', tif: 'image/tiff', tiff: 'image/tiff',
  mp3: 'audio/mpeg', m4a: 'audio/mp4', wav: 'audio/wav', mp4: 'video/mp4', mov: 'video/quicktime',
}

function firstText(elements: any[]): string {
  for (const el of elements) {
    const t = el.type === 'group' ? firstText(el.children ?? []) :
      (el.text?.paragraphs ?? []).map((p: any) => p.runs.map((r: any) => r.text).join('')).join(' ').trim()
    if (t) return t.slice(0, 40)
  }
  return ''
}

export async function loadDeck(file: File, onProgress: (msg: string) => void): Promise<PlayerDeck> {
  onProgress('파일 읽는 중…')
  const bytes = new Uint8Array(await file.arrayBuffer())
  onProgress('슬라이드 해석 중…')
  const opened = await openPptx(bytes)
  const fonts = listEmbeddedFonts(opened.archive)
  onProgress('글꼴 준비 중…')
  await registerFonts(document, fonts)
  const metrics = new CanvasMetrics(fonts)

  const urls = new Map<string, string | undefined>()
  const media = (ref: string) => {
    if (urls.has(ref)) return urls.get(ref)
    const b = opened.archive.readBytes(ref)
    const mime = MIME[ref.split('.').pop()?.toLowerCase() ?? '']
    // emf/wmf previews have no browser decoder; the engine falls back to its own drawing
    const url = b && mime ? URL.createObjectURL(new Blob([b], { type: mime })) : undefined
    urls.set(ref, url)
    return url
  }

  const raw = opened.deck.slides.map((slide, i) => {
    if (i % 10 === 0) onProgress(`슬라이드 그리는 중… ${i + 1}/${opened.deck.slides.length}`)
    const render = buildRenderSlide(slide, opened.deck.size, { fitWidthPx: RENDER_WIDTH, media, metrics, slideNo: i + 1 })
    const notes = getSlideNotes(opened.archive, slide.path)
    const auto = autoplayIds(slide.originalXml)
    const audio: AudioClip[] = []
    for (const el of slide.elements as any[]) {
      if (el.type !== 'picture' || el.media?.kind !== 'audio' || !el.media.target || el.media.external) continue
      const url = media(el.media.target)
      // Element ids look like "pic_2"; the number is the shape id the timing XML targets
      if (url) audio.push({ sourceId: el.id, url, autoplay: auto.has(String(el.id).match(/(\d+)$/)?.[1] ?? '') })
    }
    return { no: i + 1, render, notes, marker: notesMarker(notes), audio, title: firstText(slide.elements) }
  })
  const states = translationStates(raw.map((s) => s.marker))
  return {
    name: file.name,
    slides: raw.map((s, i) => ({ ...s, translate: states[i]! })),
    fonts,
    hasMarkers: raw.some((s) => s.marker !== null),
  }
}

/** Every image URL in a render tree, so screens can decode them before the first draw. */
export function imageUrls(slides: PlayerSlide[]): Set<string> {
  const out = new Set<string>()
  const walk = (o: any) => {
    if (!o || typeof o !== 'object') return
    if (typeof o.dataUrl === 'string') out.add(o.dataUrl)
    for (const k in o) walk(o[k])
  }
  for (const s of slides) walk(s.render)
  return out
}

/** Decodes images in the given document (each window needs its own HTMLImageElements). */
export async function preloadImages(doc: Document, urls: Iterable<string>): Promise<Map<string, HTMLImageElement>> {
  const map = new Map<string, HTMLImageElement>()
  await Promise.all(
    [...urls].map(
      (u) =>
        new Promise<void>((res) => {
          const img = doc.createElement('img')
          img.onload = img.onerror = () => res()
          img.src = u
          map.set(u, img)
        }),
    ),
  )
  return map
}
