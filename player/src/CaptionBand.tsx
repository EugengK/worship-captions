/**
 * Translated caption band at the bottom of the projector screen.
 *
 * Shows the latest lines from the caption hub and hides itself after 8 s without new ones.
 * While translation is off (hymns, creed, Bible reading) it stays hidden, except for the
 * last sentence or two still arriving in the first seconds after it was switched off.
 */
import React, { useEffect, useRef, useState } from 'react'
import { Hub, type CaptionLine } from './link'

const HIDE_AFTER_MS = 8000
const GRACE_AFTER_OFF_MS = 6000

export function CaptionBand({ translate, langs }: { translate: boolean; langs: string[] }): React.ReactElement | null {
  const [lines, setLines] = useState<CaptionLine[]>([])
  const [visible, setVisible] = useState(false)
  const hideTimer = useRef<number | undefined>(undefined)
  const offSince = useRef<number | null>(translate ? null : 0)

  useEffect(() => {
    if (translate) {
      offSince.current = null
    } else {
      offSince.current = Date.now()
      const t = window.setTimeout(() => setVisible(false), GRACE_AFTER_OFF_MS)
      return () => window.clearTimeout(t)
    }
  }, [translate])

  useEffect(() => {
    const hub = new Hub((msg) => {
      if (msg.type === 'caption' && Array.isArray(msg.lines)) {
        const off = offSince.current
        if (off !== null && Date.now() - off > GRACE_AFTER_OFF_MS) return
        const next = msg.lines.filter((l) => l && typeof l.text === 'string' && l.text.trim())
        if (!next.length) return
        setLines(next)
        setVisible(true)
        window.clearTimeout(hideTimer.current)
        hideTimer.current = window.setTimeout(() => setVisible(false), HIDE_AFTER_MS)
      } else if (msg.type === 'clear') {
        window.clearTimeout(hideTimer.current)
        setVisible(false)
      }
    })
    return () => {
      hub.close()
      window.clearTimeout(hideTimer.current)
    }
  }, [])

  // Only the languages picked on the presenter screen, in that order
  const shown = langs.map((c) => lines.find((l) => l.lang === c)).filter((l): l is CaptionLine => !!l)
  if (!shown.length) return null
  return (
    <div className={`caption-band n${shown.length}`} aria-live="polite" style={{ opacity: visible ? 1 : 0 }}>
      {shown.map((l, i) => (
        <div key={i} lang={l.lang} className={i === 0 ? 'caption-first' : 'caption-second'}>
          {l.text}
        </div>
      ))}
    </div>
  )
}
