/**
 * Presenter window (on the laptop): opens the worship .pptx, shows the current and next slide,
 * moves with ←/→ or a clicker, drives the projector window, plays the deck's audio and turns
 * live translation on and off from the [번역 ON]/[번역 OFF] markers in the slide notes.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { SlideThumb } from 'ieum-slides/SlideThumb'
import { imageUrls, loadDeck, preloadImages, type PlayerDeck } from './deck'
import { liveTranslation, mismatchedSlides, parseCaptionFile, translationStates, type CaptionFile } from './markers'
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
  // Carried on/off state (notes markers, T key); `live` below is what actually applies on this slide
  const [translate, setTranslate] = useState(false)
  const [captions, setCaptions] = useState<CaptionFile | null>(null)
  const [captionWarn, setCaptionWarn] = useState('')
  const [langs, setLangs] = useState<string[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('worshipPlayer.langs') || '[]')
      return Array.isArray(saved) && saved[0] === 'en' ? saved.slice(0, MAX_LANGS) : ['en']
    } catch {
      return ['en']
    }
  })
  const [black, setBlack] = useState(false)
  // Caption text size on the projector (1 = default), kept between services
  const [capScale, setCapScale] = useState(() => {
    try {
      return Number(localStorage.getItem('worshipPlayer.capScale')) || 1
    } catch {
      return 1
    }
  })
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

  const loadCaptions = useCallback(async (file: File, d: PlayerDeck | null) => {
    try {
      const c = parseCaptionFile(await file.text())
      setCaptions(c)
      const bad = d ? mismatchedSlides(c, (no) => d.slides[no - 1]?.title) : []
      setCaptionWarn(
        bad.length
          ? `자막 파일과 슬라이드 내용이 다른 곳: ${bad.join(', ')}번 (PPT가 바뀌었으면 자막 파일을 새로 받아야 합니다)`
          : '',
      )
    } catch (e) {
      setCaptions(null)
      setCaptionWarn(`자막 파일을 읽지 못했습니다: ${(e as Error).message}`)
    }
  }, [])

  /** Takes the .pptx and, optionally, its prepared-captions .json (picked or dropped together). */
  const open = useCallback(
    async (files: File[]) => {
      const pptx = files.find((f) => /\.pptx$/i.test(f.name))
      const json = files.find((f) => /\.json$/i.test(f.name))
      if (!pptx) {
        if (json) await loadCaptions(json, deck)
        return
      }
      setProgress('여는 중…')
      try {
        const d = await loadDeck(pptx, setProgress)
        setProgress('그림 준비 중…')
        setImages(await preloadImages(document, imageUrls(d.slides)))
        window.worshipPlayer = { deck: d }
        setDeck(d)
        setIndex(0)
        setTranslate(d.slides[0]?.translate ?? false)
        setProgress('')
        if (json) await loadCaptions(json, d)
        else if (captions) setCaptionWarn(mismatchedSlides(captions, (no) => d.slides[no - 1]?.title).length ? '자막 파일이 이 PPT와 맞지 않을 수 있습니다' : '')
        channel.postMessage({ type: 'deck' } satisfies ShowMessage)
      } catch (e) {
        console.error(e)
        setProgress(`열지 못했습니다: ${(e as Error).message}`)
      }
    },
    [channel, deck, captions, loadCaptions],
  )

  // On/off markers: the slide's notes, else the caption file's "live" entry
  const markers = useMemo(
    () => deck?.slides.map((s) => s.marker ?? captions?.live.get(s.no) ?? null) ?? [],
    [deck, captions],
  )
  const carried = useMemo(() => translationStates(markers), [markers])
  useEffect(() => {
    // A newly opened caption file can change the state of the slide already on screen
    if (captions && markers.length) setTranslate(carried[index] ?? false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [captions])

  const go = useCallback(
    (to: number) => {
      if (!deck) return
      const next = Math.max(0, Math.min(deck.slides.length - 1, to))
      if (next === index) return
      // A marker on the new slide decides; a jump takes the state worked out for that slide;
      // otherwise the current state (possibly switched by hand with T) carries on.
      if (markers[next] != null) setTranslate(markers[next]!)
      else if (Math.abs(next - index) > 1) setTranslate(carried[next]!)
      setIndex(next)
    },
    [deck, index, markers, carried],
  )

  const handleKey = useCallback(
    (key: string) => {
      if (NEXT_KEYS.has(key)) go(index + 1)
      else if (PREV_KEYS.has(key)) go(index - 1)
      else if (key === 'Home') go(0)
      else if (key === 'End' && deck) go(deck.slides.length - 1)
      else if (key === 'b' || key === 'B' || key === '.') setBlack((b) => !b)
      else if (key === 't' || key === 'T') setTranslate((t) => !t)
      else if (key === '+' || key === '=') setCapScale((v) => Math.min(2, Math.round((v + 0.1) * 10) / 10))
      else if (key === '-' || key === '_') setCapScale((v) => Math.max(0.6, Math.round((v - 0.1) * 10) / 10))
    },
    [go, index, deck],
  )

  const fixed = captions?.slides.get(index + 1) ?? null
  const live = deck ? liveTranslation(translate, markers[index] ?? null, !!fixed) : false
  const show: ShowMessage = { type: 'state', index, translate: live, black, langs, fixed, scale: capScale }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || (e.target as HTMLElement).tagName === 'INPUT') return
      e.preventDefault()
      handleKey(e.key)
    }
    window.addEventListener('keydown', onKey)
    channel.onmessage = (ev: MessageEvent<ShowMessage>) => {
      if (ev.data.type === 'key') handleKey(ev.data.key)
      else if (ev.data.type === 'hello') channel.postMessage(show)
    }
    return () => window.removeEventListener('keydown', onKey)
  }, [handleKey, channel, show])

  // Projector follows the presenter
  useEffect(() => {
    channel.postMessage(show)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel, index, live, black, langs, fixed, capScale])

  // Congregation phones get the prepared captions too (they hear and read them in their language)
  useEffect(() => {
    if (fixed && hubUp) {
      hub.send({ type: 'caption', source: 'slide', lines: Object.entries(fixed).map(([lang, text]) => ({ lang, text })) })
    }
  }, [hub, fixed, hubUp])

  useEffect(() => {
    try {
      localStorage.setItem('worshipPlayer.capScale', String(capScale))
    } catch {
      /* not remembered in private mode */
    }
  }, [capScale])

  // Translation engine follows the slide (it stops sending sound to Google while off).
  // Sent when the state changes and again whenever the hub (re)connects.
  const slideNo = useRef(1)
  slideNo.current = index + 1
  useEffect(() => {
    if (deck && hubUp) hub.send({ type: 'control', translate: live, langs, slide: slideNo.current })
  }, [hub, deck, live, langs, hubUp])

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
          void open([...e.dataTransfer.files])
        }}
      >
        <h1>예배 발표기</h1>
        <p>호바트한인교회 · 실시간 번역 자막</p>
        <label className="big-button">
          예배 PPT 열기 (.pptx)
          <input type="file" accept=".pptx,.json" multiple hidden onChange={(e) => void open([...(e.target.files ?? [])])} />
        </label>
        <p className="hint">또는 pptx 파일을 이 창에 끌어다 놓으세요.</p>
        <p className="hint">미리 번역한 자막 파일(.json)이 있으면 pptx와 함께 고르거나 함께 끌어다 놓으세요.</p>
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
        {fixed ? (
          <span className="pill ready" title="자막 파일의 번역을 띄우는 중 (실시간 번역 꺼짐, 비용 없음)">
            준비된 자막
          </span>
        ) : (
          <button className={live ? 'pill on' : 'pill off'} onClick={() => setTranslate((t) => !t)} title="T 키">
            {live ? '번역 켜짐' : '번역 꺼짐'}
          </button>
        )}
        <label className="caption-file" title="미리 번역한 자막 파일(.json)">
          {captions ? `자막 파일: ${captions.title || captions.slides.size + '장'}` : '자막 파일 열기'}
          <input type="file" accept=".json" hidden onChange={(e) => e.target.files?.[0] && void loadCaptions(e.target.files[0], deck)} />
        </label>
        <span className="cap-size" title="프로젝터 자막 글씨 크기 (- / + 키)">
          자막 글씨
          <button onClick={() => handleKey('-')}>A−</button>
          <b>{Math.round(capScale * 100)}%</b>
          <button onClick={() => handleKey('+')}>A+</button>
        </span>
        <span className={hubUp ? 'dot up' : 'dot down'} title="자막 서버 (caption_hub.py)">
          {hubUp ? '자막 서버 연결됨' : '자막 서버 없음'}
        </span>
        {black && <span className="pill black">화면 가림 (B)</span>}
        {(progress || captionWarn) && <span className="warn">{progress || captionWarn}</span>}
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
          <div className="label">{fixed ? '준비된 자막 (이 슬라이드)' : '최근 자막'}</div>
          <div className="last-caption">
            {fixed
              ? langs.filter((c) => fixed[c]).map((c) => <div key={c}>{fixed[c]}</div>)
              : lastCaption.length
                ? lastCaption.map((l, i) => <div key={i}>{l.text}</div>)
                : '(아직 없음)'}
          </div>
          <div className="keys">→ / ← 넘기기 · T 번역 켜기/끄기 · B 화면 가림 · −/+ 자막 글씨 · Home/End 처음/끝</div>
        </aside>
      </main>
      <div className="strip" ref={stripRef}>
        {deck.slides.map((s, i) => (
          <button
            key={i}
            data-i={i}
            className={
              (i === index ? 'thumb current ' : 'thumb ') +
              (captions?.slides.has(s.no) ? 'tr-fixed' : liveTranslation(carried[i]!, markers[i] ?? null, false) ? 'tr-on' : 'tr-off')
            }
            onClick={() => go(i)}
            title={s.title}
          >
            <SlideThumb slide={s.render} images={images} width={144} />
            <span>
              {s.no}
              {captions?.slides.has(s.no) ? ' · 자막' : markers[i] === true ? ' · 번역 ON' : markers[i] === false ? ' · 번역 OFF' : ''}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<Presenter />)
