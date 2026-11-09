/**
 * Editing the worship deck in the presenter window: delete, duplicate, move and hide slides,
 * change the words of text boxes, and save the result as a new .pptx.
 *
 * The opened file is changed in memory only; the original .pptx on disk is never touched.
 * Each edit returns where every slide came from, so prepared captions can follow (markers.ts).
 */
import { deleteSlide, duplicateSlide, moveSlide, savePptx, setSlideHidden } from '@genoffice/pptx-engine'
import { assembleDeck, buildSlide, type DeckSource, type PlayerDeck } from './deck'
import { boxLines, editable, setBoxLines, type ParagraphLike } from './textedit'

export type EditOp =
  | { kind: 'delete'; index: number }
  | { kind: 'duplicate'; index: number }
  | { kind: 'move'; index: number; to: number }
  | { kind: 'hide'; index: number; hidden: boolean }
  | { kind: 'text'; index: number; elementId: string; lines: string[] }

export interface EditResult {
  deck: PlayerDeck
  /** old 1-based slide number of each new position (null = new slide) */
  newToOld: (number | null)[]
  /** slide to show after the edit */
  index: number
}

export interface TextBox {
  id: string
  name: string
  lines: string[]
}

/** Text boxes on a slide whose words can be changed here (top-level text and shapes). */
export function textBoxes(source: DeckSource, index: number): TextBox[] {
  const slide = source.opened.deck.slides[index]
  if (!slide) return []
  const out: TextBox[] = []
  for (const el of slide.elements as any[]) {
    if ((el.type !== 'text' && el.type !== 'shape') || !editable(el.text?.paragraphs)) continue
    out.push({ id: el.id, name: el.name ?? '', lines: boxLines(el.text.paragraphs as ParagraphLike[]) })
  }
  return out
}

export function applyEdit(source: DeckSource, deck: PlayerDeck, op: EditOp): EditResult | null {
  const { opened } = source
  const n = deck.slides.length
  if (opened.deck.slides.length !== n) return null // out of step: refuse rather than guess
  const same = deck.slides.map((s) => s.no)
  const rebuilt = (newToOld: (number | null)[], index: number, fresh: number[] = []): EditResult => {
    const raw = newToOld.map((old, k) => (old == null || fresh.includes(k) ? buildSlide(source, k) : deck.slides[old - 1]!))
    return { deck: assembleDeck(deck.name, deck.fonts, raw), newToOld, index }
  }
  switch (op.kind) {
    case 'delete': {
      if (!deleteSlide(opened, op.index)) return null
      const newToOld = same.filter((_, i) => i !== op.index)
      return rebuilt(newToOld, Math.min(op.index, newToOld.length - 1))
    }
    case 'duplicate': {
      if (!duplicateSlide(opened, op.index)) return null
      const newToOld: (number | null)[] = [...same]
      newToOld.splice(op.index + 1, 0, null)
      return rebuilt(newToOld, op.index + 1)
    }
    case 'move': {
      const to = Math.max(0, Math.min(n - 1, op.to))
      if (to === op.index || !moveSlide(opened, op.index, to)) return null
      const newToOld = [...same]
      const [moved] = newToOld.splice(op.index, 1)
      newToOld.splice(to, 0, moved!)
      return rebuilt(newToOld, to)
    }
    case 'hide': {
      setSlideHidden(opened.deck.slides[op.index]!, op.hidden)
      return rebuilt(same, op.index, [op.index])
    }
    case 'text': {
      const el = opened.deck.slides[op.index]?.elements.find((e: any) => e.id === op.elementId) as any
      if (!el?.text?.paragraphs || !setBoxLines(el.text.paragraphs, op.lines)) return null
      el.dirty = true
      return rebuilt(same, op.index, [op.index])
    }
  }
}

/** The edited deck as a .pptx file. */
export async function savedPptx(source: DeckSource): Promise<Blob> {
  const bytes = await savePptx(source.opened)
  return new Blob([bytes as BlobPart], { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' })
}

/** Offers a file to the browser's downloads (Safari and Chrome). */
export function download(blob: Blob, name: string): void {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 60_000)
}
