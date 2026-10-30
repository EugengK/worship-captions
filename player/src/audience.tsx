/**
 * Projector window: the current slide, as large as the screen allows, with the caption band.
 * Opened by the presenter window, which owns the deck; this window only draws.
 */
import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { SlideThumb } from 'ieum-slides/SlideThumb'
import type { RenderSlide } from '@genoffice/pptx-render'
import { CaptionBand } from './CaptionBand'
import { imageUrls, preloadImages, type PlayerDeck } from './deck'
import { registerFonts } from './fonts'
import { CHANNEL, type ShowMessage } from './link'
import './player.css'

/** The speaker icon of an audio clip is not shown on the projector (PowerPoint hides it too). */
function withoutAudioIcons(r: RenderSlide): RenderSlide {
  const nodes = r.nodes.filter((n: any) => !(n.type === 'picture' && n.media === 'audio'))
  return nodes.length === r.nodes.length ? r : { ...r, nodes }
}

function useWindowSize() {
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight })
  useEffect(() => {
    const on = () => setSize({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return size
}

function Audience() {
  const [deck, setDeck] = useState<PlayerDeck | null>(null)
  const [images, setImages] = useState(new Map<string, HTMLImageElement>())
  const [state, setState] = useState({ index: 0, translate: false, black: false })
  const { w, h } = useWindowSize()
  const channel = useMemo(() => new BroadcastChannel(CHANNEL), [])

  useEffect(() => {
    const load = async () => {
      const d: PlayerDeck | undefined = (window.opener as any)?.worshipPlayer?.deck
      if (!d) return
      await registerFonts(document, d.fonts)
      setImages(await preloadImages(document, imageUrls(d.slides)))
      setDeck(d)
    }
    channel.onmessage = (ev: MessageEvent<ShowMessage>) => {
      const m = ev.data
      if (m.type === 'deck') void load()
      else if (m.type === 'state') setState({ index: m.index, translate: m.translate, black: m.black })
    }
    void load()
    channel.postMessage({ type: 'hello' } satisfies ShowMessage)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'f' || e.key === 'F') {
        void document.documentElement.requestFullscreen?.()
        return
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return
      e.preventDefault()
      channel.postMessage({ type: 'key', key: e.key } satisfies ShowMessage)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [channel])

  const slide = deck?.slides[state.index]
  const render = useMemo(() => (slide ? withoutAudioIcons(slide.render) : null), [slide])
  if (!deck || !render) {
    return (
      <div className="audience-wait">
        청중 화면입니다. 노트북의 발표자 화면에서 예배 PPT를 열어 주세요.
        <br />이 창을 프로젝터 화면으로 옮긴 뒤 F 키를 누르면 전체 화면이 됩니다.
      </div>
    )
  }
  // As large as fits; on a 16:10 projector the spare space stays below the slide for captions
  const width = Math.min(w, (h * render.widthPx) / render.heightPx)
  return (
    <div className="audience" onDoubleClick={() => void document.documentElement.requestFullscreen?.()}>
      <div className="audience-slide" style={{ width, visibility: state.black ? 'hidden' : 'visible' }}>
        <SlideThumb slide={render} images={images} width={width} />
      </div>
      <CaptionBand translate={state.translate} />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<Audience />)
