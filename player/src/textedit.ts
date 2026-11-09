/**
 * Changing the words of a text box without touching its formatting.
 *
 * A box's text is shown as lines: one per paragraph, plus one per soft line break inside a
 * paragraph (Shift+Enter in PowerPoint). Each line keeps the font, size and colour of its first
 * run. With the same number of lines the run structure stays exactly as it was, so the engine
 * patches only the words in the saved file. Added lines continue the last line's style (as soft
 * breaks in its paragraph); removed lines are dropped from the end.
 */

export interface RunLike {
  text: string
  rawXml?: string
  field?: unknown
  [k: string]: unknown
}
export interface ParagraphLike {
  runs: RunLike[]
  [k: string]: unknown
}

const isBreak = (r: RunLike) => r.text === '\n' && !r.field
/** Runs whose words can be replaced (not an equation block, not a slide-number field) */
const isPlain = (r: RunLike) => !isBreak(r) && !r.rawXml && !r.field

interface Segment {
  para: number
  /** run indices between soft breaks */
  runs: number[]
  /** index of the soft break that starts this line (-1 for a paragraph's first line) */
  brk: number
}

function segmentsOf(paragraphs: ParagraphLike[]): Segment[] {
  const out: Segment[] = []
  paragraphs.forEach((p, pi) => {
    if (!p.runs.length) return // an empty line keeps no style to write with: left as is
    let cur: Segment = { para: pi, runs: [], brk: -1 }
    p.runs.forEach((r, ri) => {
      if (isBreak(r)) {
        out.push(cur)
        cur = { para: pi, runs: [], brk: ri }
      } else cur.runs.push(ri)
    })
    out.push(cur)
  })
  return out
}

/** The box's words as editable lines. */
export function boxLines(paragraphs: ParagraphLike[]): string[] {
  return segmentsOf(paragraphs).map((s) => s.runs.map((ri) => paragraphs[s.para]!.runs[ri]!.text).join(''))
}

/** Whether the box can be edited here (has at least one plain run). */
export function editable(paragraphs: ParagraphLike[] | undefined): boolean {
  return !!paragraphs?.some((p) => p.runs.some(isPlain))
}

function setSegment(paragraphs: ParagraphLike[], seg: Segment, text: string): void {
  const runs = paragraphs[seg.para]!.runs
  const carrier = seg.runs.find((ri) => isPlain(runs[ri]!))
  if (carrier === undefined) return
  for (const ri of seg.runs) if (isPlain(runs[ri]!)) runs[ri]!.text = ri === carrier ? text : ''
}

/**
 * Writes `lines` into the paragraphs (in place). Returns false when nothing changed.
 */
export function setBoxLines(paragraphs: ParagraphLike[], lines: string[]): boolean {
  const before = boxLines(paragraphs)
  if (before.length === lines.length && before.every((t, i) => t === lines[i])) return false
  const segs = segmentsOf(paragraphs)
  if (!segs.length) return false
  const n = Math.min(segs.length, lines.length)
  for (let i = 0; i < n; i++) setSegment(paragraphs, segs[i]!, lines[i]!)

  if (lines.length > segs.length) {
    // Extra lines: soft breaks in the last line's paragraph, in its style
    const last = segs[segs.length - 1]!
    const runs = paragraphs[last.para]!.runs
    const styleRun = [...last.runs].reverse().map((ri) => runs[ri]!).find(isPlain) ?? runs.find(isPlain)
    if (!styleRun) return true
    const breakRun = runs.find(isBreak) ?? { ...styleRun, text: '\n' }
    // insert after the last run of the last segment
    let at = (last.runs.length ? last.runs[last.runs.length - 1]! : runs.length - 1) + 1
    for (const extra of lines.slice(segs.length)) {
      runs.splice(at, 0, { ...breakRun, text: '\n' }, { ...styleRun, text: extra })
      at += 2
    }
  } else if (lines.length < segs.length) {
    // Fewer lines: drop the surplus from the end (whole paragraphs where nothing is left)
    for (let i = segs.length - 1; i >= lines.length; i--) {
      const seg = segs[i]!
      const p = paragraphs[seg.para]!
      if (seg.brk < 0) {
        // a paragraph's first line (its later lines are already gone): drop the paragraph,
        // unless it is the box's first one, which keeps the box's style
        if (i > 0) paragraphs.splice(seg.para, 1)
        else for (const ri of seg.runs) if (isPlain(p.runs[ri]!)) p.runs[ri]!.text = ''
      } else {
        // the soft break that starts the line, and the line's runs
        const end = seg.runs.length ? seg.runs[seg.runs.length - 1]! : seg.brk
        p.runs.splice(seg.brk, end - seg.brk + 1)
      }
    }
  }
  return true
}
