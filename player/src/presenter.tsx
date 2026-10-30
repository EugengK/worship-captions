/**
 * Presenter window (on the laptop): opens the worship .pptx, shows the current and next slide,
 * moves with ←/→ or a clicker, drives the projector window, plays the deck's audio and turns
 * live translation on and off from the [번역 ON]/[번역 OFF] markers in the slide notes.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { SlideThumb } from 'ieum-slides/SlideThumb'
import { imageUrls, loadDeck, preloadImages, type PlayerDeck } from './deck'
import { CHANNEL, Hub, LANGUAGES, MAX_LANGS, NEXT_KEYS, PREV_KEYS, toggleLang, type CaptionLine, type ShowMessage } from './link'
import './player.css'

declare global {
  interface Window {
    worshipPlayer?: { deck: PlayerDeck }
  }
}

/** Size of an element that may mount later (after the deck opens): use the returned callback as its ref. */
function useBox(): [(el: HTMLElement | null) => void, { w: number; h: number }] {
  const [box, setBox] = useState({ w: 0, h: 0 })
  const ro = useRef<ResizeObserver | null>(null)
  const ref = useCallback((el: HTMLElement | null) => {
    ro.current?.disconnect()
    if (!el) return
    ro.current = new ResizeObserver(([e]) => setBox({ w: e!.contentRect.width, h: e!.contentRect.height }))
    ro.current.observe(el)
  }, [])
  return [ref, box]
}

/** Fit a 16:9 slide inside a box. */
const fit = (box: { w: number; h: number }, aspect: number) => Math.max(0, Math.min(box.w, box.h * aspect))

function Presenter() {
  const [deck, setDeck] = useState<PlayerDeck | null>(null)
  const [images, setImages] = useState(new Map<string, HTMLImageElement>())
  const [progress, setProgress] = useState('')
  const [index, setIndex] = useState(0)
  const [translate, setTranslate] = useState(false)
  const [langs, setLangs] = useState<string[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('worshipPlayer.langs') || '[]')
      return Array.isArray(saved) && saved[0] === 'en' ? saved.slice(0, MAX_LANGS) : ['en']
    } catch {
      return ['en']
    }
  })
  const [black, setBlack] = useState(false)
  const [hubUp, setHubUp] = useState(false)
  const [lastCaption, setLastCaption] = useState<CaptionLine[]>([])
  const [playing, setPlaying] = useState<string | null>(null)
  const audience = useRef<Window | null>(null)
  const audio = useRef(new Map<string, HTMLAudioElement>())
  const channel = useMemo(() => new BroadcastChannel(CHANNEL), [])
  const hub = useMemo(
    () =>
      new Hub(
        (m) => m.type === 'caption' && setLastCaption(m.lines),
        (up) => setHubUp(up),
      ),
    [],
  )

  const open = useCallback(
    async (file: File) => {
      setProgress('여는 중…')
      try {
        const d = await loadDeck(file, setProgress)
        setProgress('그림 준비 중…')
        setImages(await preloadImages(document, imageUrls(d.slides)))
        window.worshipPlayer = { deck: d }
        setDeck(d)
        setIndex(0)
        setTranslate(d.slides[0]?.translate ?? false)
        setProgress('')
        channel.postMessage({ type: 'deck' } satisfies ShowMessage)
      } catch (e) {
        console.error(e)
        setProgress(`열지 못했습니다: ${(e as Error).message}`)
      }
    },
    [channel],
  )

  const go = useCallback(
    (to: number) => {
      if (!deck) return
      const next = Math.max(0, Math.min(deck.slides.length - 1, to))
      if (next === index) return
      const s = deck.slides[next]!
      // A marker on the new slide decides; a jump takes the state worked out for that slide;
      // otherwise the current state (possibly switched by hand with T) carries on.
      if (s.marker !== null) setTranslate(s.marker)
      else if (Math.abs(next - index) > 1) setTranslate(s.translate)
      setIndex(next)
    },
    [deck, index],
  )

  const handleKey = useCallback(
    (key: string) => {
      if (NEXT_KEYS.has(key)) go(index + 1)
      else if (PREV_KEYS.has(key)) go(index - 1)
      else if (key === 'Home') go(0)
      else if (key === 'End' && deck) go(deck.slides.length - 1)
      else if (key === 'b' || key === 'B' || key === '.') setBlack((b) => !b)
      else if (key === 't' || key === 'T') setTranslate((t) => !t)
    },
    [go, index, deck],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || (e.target as HTMLElement).tagName === 'INPUT') return
      e.preventDefault()
      handleKey(e.key)
    }
    window.addEventListener('keydown', onKey)
    channel.onmessage = (ev: MessageEvent<ShowMessage>) => {
      if (ev.data.type === 'key') handleKey(ev.data.key)
      else if (ev.data.type === 'hello') channel.postMessage({ type: 'state', index, translate, black, langs } satisfies ShowMessage)
    }
    return () => window.removeEventListener('keydown', onKey)
  }, [handleKey, channel, index, translate, black, langs])

  // Projector follows the presenter
  useEffect(() => {
    channel.postMessage({ type: 'state', index, translate, black, langs } satisfies ShowMessage)
  }, [channel, index, translate, black, langs])

  // Translation engine follows the slide (it stops sending sound to Google while off).
  // Sent when the state changes and again whenever the hub (re)connects.
  const slideNo = useRef(1)
  slideNo.current = index + 1
  useEffect(() => {
    if (deck && hubUp) hub.send({ type: 'control', translate, langs, slide: slideNo.current })
  }, [hub, deck, translate, langs, hubUp])

  useEffect(() => {
    try {
      localStorage.setItem('worshipPlayer.langs', JSON.stringify(langs))
    } catch {
      /* private mode: the choice is just not remembered */
    }
  }, [langs])

  // Audio: stop on leaving a slide, start clips PowerPoint would start by itself
  useEffect(() => {
    for (const a of audio.current.values()) a.pause()
    setPlaying(null)
    const s = deck?.slides[index]
    for (const clip of s?.audio ?? []) {
      if (!clip.autoplay) continue
      const a = audioFor(clip.url)
      a.currentTime = 0
      void a.play().then(() => setPlaying(clip.url)).catch(() => {})
    }
  }, [deck, index])

  const audioFor = (url: string) => {
    let a = audio.current.get(url)
    if (!a) {
      a = new Audio(url)
      a.onended = () => setPlaying(null)
      audio.current.set(url, a)
    }
    return a
  }
  const toggleAudio = (url: string) => {
    const a = audioFor(url)
    if (a.paused) void a.play().then(() => setPlaying(url))
    else {
      a.pause()
      setPlaying(null)
    }
  }

  // Opens the projector window. In Chrome, with the "window management" permission (asked once),
  // it lands on the other screen at full size and asks for fullscreen; anywhere else the window
  // opens normally and one click inside it makes it fullscreen.
  const openAudience = async () => {
    if (audience.current && !audience.current.closed) {
      audience.current.focus()
      return
    }
    let features = 'popup,width=960,height=600'
    try {
      const getScreens = (window as any).getScreenDetails as (() => Promise<any>) | undefined
      if (getScreens) {
        const d = await getScreens()
        const other = d.screens.find((s: any) => s !== d.currentScreen)
        if (other) {
          features = `popup,fullscreen,left=${other.availLeft},top=${other.availTop},width=${other.availWidth},height=${other.availHeight}`
        }
      }
    } catch {
      /* permission refused or not supported: normal window */
    }
    const w = window.open('audience.html' + location.search, 'worship-audience', features)
    if (!w) {
      setProgress('청중 화면이 차단되었습니다. 주소창 오른쪽의 팝업 차단 표시에서 "항상 허용"을 고른 뒤 다시 누르세요.')
      return
    }
    setProgress('')
    audience.current = w
  }

  const [mainRef, mainBox] = useBox()
  const [sideRef, sideBox] = useBox()
  const stripRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    stripRef.current?.querySelector(`[data-i="${index}"]`)?.scrollIntoView({ block: 'nearest', inline: 'center' })
  }, [index])

  if (!deck) {
    return (
      <div
        className="open-screen"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          const f = e.dataTransfer.files[0]
          if (f) void open(f)
        }}
      >
        <h1>예배 발표기</h1>
        <p>호바트한인교회 · 실시간 번역 자막</p>
        <label className="big-button">
          예배 PPT 열기 (.pptx)
          <input type="file" accept=".pptx" hidden onChange={(e) => e.target.files?.[0] && void open(e.target.files[0])} />
        </label>
        <p className="hint">또는 pptx 파일을 이 창에 끌어다 놓으세요.</p>
        {progress && <p className="progress">{progress}</p>}
      </div>
    )
  }

  const slide = deck.slides[index]!
  const nextSlide = deck.slides[index + 1]
  const aspect = slide.render.widthPx / slide.render.heightPx
  return (
    <div className="presenter">
      <header>
        <strong>예배 발표기</strong>
        <span className="file">{deck.name}</span>
        <button onClick={() => void openAudience()}>청중 화면 열기</button>
        <span className="langs" title={`자막 언어 (최대 ${MAX_LANGS}개, 영어는 기본)`}>
          {LANGUAGES.map((l) => {
            const on = langs.includes(l.code)
            const full = !on && langs.length >= MAX_LANGS
            return (
              <button
                key={l.code}
                className={on ? 'lang on' : 'lang'}
                disabled={l.code === 'en' || full}
                onClick={() => setLangs((cur) => toggleLang(cur, l.code))}
              >
                {l.label}
              </button>
            )
          })}
        </span>
        <button className={translate ? 'pill on' : 'pill off'} onClick={() => setTranslate((t) => !t)} title="T 키">
          {translate ? '번역 켜짐' : '번역 꺼짐'}
        </button>
        <span className={hubUp ? 'dot up' : 'dot down'} title="자막 서버 (caption_hub.py)">
          {hubUp ? '자막 서버 연결됨' : '자막 서버 없음'}
        </span>
        {black && <span className="pill black">화면 가림 (B)</span>}
        {progress && <span className="warn">{progress}</span>}
        <span className="count">
          {index + 1} / {deck.slides.length}
        </span>
      </header>
      <main>
        <div className="current" ref={mainRef}>
          <SlideThumb slide={slide.render} images={images} width={fit(mainBox, aspect)} />
        </div>
        <aside ref={sideRef}>
          <div className="label">다음</div>
          {nextSlide ? (
            <SlideThumb slide={nextSlide.render} images={images} width={fit({ w: sideBox.w, h: sideBox.h * 0.4 }, aspect)} />
          ) : (
            <div className="end">마지막 슬라이드입니다</div>
          )}
          {slide.audio.map((c) => (
            <button key={c.url} className="audio" onClick={() => toggleAudio(c.url)}>
              {playing === c.url ? '■ 음악 멈추기' : '▶ 음악 재생'}
              {c.autoplay ? ' (자동 재생 슬라이드)' : ''}
            </button>
          ))}
          <div className="label">노트</div>
          <div className="notes">{slide.notes || '(노트 없음)'}</div>
          <div className="label">최근 자막</div>
          <div className="last-caption">
            {lastCaption.length ? lastCaption.map((l, i) => <div key={i}>{l.text}</div>) : '(아직 없음)'}
          </div>
          <div className="keys">→ / ← 넘기기 · T 번역 켜기/끄기 · B 화면 가림 · Home/End 처음/끝</div>
        </aside>
      </main>
      <div className="strip" ref={stripRef}>
        {deck.slides.map((s, i) => (
          <button
            key={i}
            data-i={i}
            className={(i === index ? 'thumb current ' : 'thumb ') + (s.translate ? 'tr-on' : 'tr-off')}
            onClick={() => go(i)}
            title={s.title}
          >
            <SlideThumb slide={s.render} images={images} width={144} />
            <span>
              {s.no}
              {s.marker === true ? ' · 번역 ON' : s.marker === false ? ' · 번역 OFF' : ''}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<Presenter />)
