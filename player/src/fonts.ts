/**
 * Fonts for the worship player: registers the deck's embedded faces and measures text with
 * the browser's own canvas, so line breaks are computed with the same fonts the screen draws.
 *
 * Windows Korean fonts (굴림, 돋움, 바탕…) are not on a Mac; they fall back to the Mac's
 * Korean fonts below. That changes widths a little, so a line may break in a different place
 * than in PowerPoint on Windows.
 */
import type { EmbeddedFontFace } from '@genoffice/pptx-engine'
import type { FontMetrics, FontMetricsProvider, RunStyle } from '@genoffice/pptx-render'

const GOTHIC = ['Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', 'Noto Sans CJK KR']
const MYUNGJO = ['AppleMyungjo', 'Nanum Myeongjo', 'NanumMyeongjo', 'Noto Serif KR']

/** Mac stand-ins for fonts a Windows-made deck often names (tried after the font itself). */
const ALIASES: [RegExp, string[]][] = [
  [/^(굴림|굴림체|새굴림|돋움|돋움체|gulim|gulimche|dotum|dotumche)$/i, GOTHIC],
  [/^(맑은 고딕|malgun gothic)$/i, ['Malgun Gothic', ...GOTHIC]],
  [/^(나눔고딕|nanumgothic|nanum gothic)/i, ['NanumGothic', 'Nanum Gothic', ...GOTHIC]],
  [/^(나눔스퀘어|nanumsquare)/i, ['NanumSquare', 'NanumGothic', 'Nanum Gothic', ...GOTHIC]],
  [/^(나눔명조|nanummyeongjo)/i, ['NanumMyeongjo', 'Nanum Myeongjo', ...MYUNGJO]],
  [/^(바탕|바탕체|궁서|궁서체|batang|gungsuh)$/i, MYUNGJO],
]

const quote = (f: string) => `"${f.replace(/"/g, '')}"`

/** CSS font-family list for a deck font: itself, Mac stand-ins, then any Korean sans-serif. */
export function familyStack(family: string): string {
  const names = [family]
  for (const [re, alts] of ALIASES) if (re.test(family.trim())) names.push(...alts)
  names.push(...GOTHIC)
  return [...new Set(names)].map(quote).join(', ') + ', sans-serif'
}

const STYLE: Record<EmbeddedFontFace['style'], FontFaceDescriptors> = {
  regular: { weight: '400', style: 'normal' },
  bold: { weight: '700', style: 'normal' },
  italic: { weight: '400', style: 'italic' },
  boldItalic: { weight: '700', style: 'italic' },
}

/** Adds the deck's embedded faces to a window's fonts; a face that fails to load is skipped. */
export async function registerFonts(doc: Document, faces: EmbeddedFontFace[]): Promise<void> {
  const view = doc.defaultView as (Window & typeof globalThis) | null
  if (!view) return
  await Promise.all(
    faces.map(async (f) => {
      try {
        // Copy into the target window's realm: FontFace rejects buffers from another window
        const bytes = new view.Uint8Array(f.sfnt.length)
        bytes.set(f.sfnt)
        const face = new view.FontFace(f.typeface, bytes.buffer, STYLE[f.style])
        await face.load()
        doc.fonts.add(face)
      } catch (e) {
        console.warn('embedded font skipped', f.typeface, f.style, e)
      }
    }),
  )
}

export class CanvasMetrics implements FontMetricsProvider {
  private ctx: CanvasRenderingContext2D
  private lines = new Map<string, FontMetrics>()
  private widths = new Map<string, number>()

  constructor(_faces: EmbeddedFontFace[] = []) {
    this.ctx = document.createElement('canvas').getContext('2d')!
  }

  private font(style: RunStyle): string {
    return `${style.italic ? 'italic ' : ''}${style.bold ? 'bold ' : ''}${style.fontSizePx}px ${familyStack(style.fontFamily)}`
  }

  metrics(style: RunStyle): FontMetrics {
    const font = this.font(style)
    let m = this.lines.get(font)
    if (!m) {
      this.ctx.font = font
      const t = this.ctx.measureText('가Hg')
      const ascent = t.fontBoundingBoxAscent || style.fontSizePx * 0.88
      const descent = t.fontBoundingBoxDescent || style.fontSizePx * 0.24
      m = { ascent, descent, lineHeight: ascent + descent }
      this.lines.set(font, m)
    }
    return m
  }

  measure(text: string, style: RunStyle): number {
    const font = this.font(style)
    const key = font + '\u0000' + text
    let w = this.widths.get(key)
    if (w === undefined) {
      this.ctx.font = font
      w = this.ctx.measureText(text).width
      if (this.widths.size > 200_000) this.widths.clear()
      this.widths.set(key, w)
    }
    return w
  }

  displayFamily(style: RunStyle): string {
    return familyStack(style.fontFamily)
  }
}
