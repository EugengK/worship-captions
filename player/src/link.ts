/**
 * Connections of the worship player:
 *  - the caption hub (ws://localhost:8765): caption lines in, translation on/off out
 *  - a BroadcastChannel between the presenter window and the audience window
 */

export interface CaptionLine {
  lang: string
  text: string
}

export type HubMessage =
  | { type: 'caption'; lines: CaptionLine[] }
  | { type: 'clear' }
  | { type: 'control'; translate?: boolean; langs?: string[]; slide?: number }

/** Presenter ⇄ audience messages. */
export type ShowMessage =
  | { type: 'hello' }
  | { type: 'deck' }
  | {
      type: 'state'
      index: number
      /** Live translation on this slide */
      translate: boolean
      black: boolean
      langs: string[]
      /** Prepared captions for this slide (language → text), shown instead of live ones */
      fixed: Record<string, string> | null
      /** Caption text size, 1 = default */
      scale: number
    }
  | { type: 'key'; key: string }

export const CHANNEL = 'worship-player'

/** Caption languages the presenter can pick. English is always on; at most MAX_LANGS lines. */
export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'zh', label: '中文' },
  { code: 'th', label: 'ไทย' },
  { code: 'vi', label: 'Tiếng Việt' },
]
export const MAX_LANGS = 3

/** Adds or removes a language, keeping English and the order of LANGUAGES. */
export function toggleLang(langs: string[], code: string): string[] {
  if (code === 'en') return langs
  const on = langs.includes(code)
  if (!on && langs.length >= MAX_LANGS) return langs
  const next = on ? langs.filter((c) => c !== code) : [...langs, code]
  return LANGUAGES.map((l) => l.code).filter((c) => c === 'en' || next.includes(c))
}
export const HUB_URL = (() => {
  try {
    return new URLSearchParams(location.search).get('hub') || localStorage.getItem('worshipCaptions.url') || 'ws://localhost:8765'
  } catch {
    return 'ws://localhost:8765'
  }
})()

/** Keeps a websocket to the hub open, reconnecting every 3 s. */
export class Hub {
  private ws: WebSocket | null = null
  private retry: number | undefined
  private closed = false
  private queued: HubMessage | null = null

  constructor(
    private onMessage: (msg: HubMessage) => void,
    private onStatus: (connected: boolean) => void = () => {},
  ) {
    this.connect()
  }

  private connect(): void {
    if (this.closed) return
    try {
      this.ws = new WebSocket(HUB_URL)
    } catch {
      this.retry = window.setTimeout(() => this.connect(), 3000)
      return
    }
    this.ws.onopen = () => {
      this.onStatus(true)
      if (this.queued) this.send(this.queued)
    }
    this.ws.onmessage = (ev) => {
      try {
        this.onMessage(JSON.parse(String(ev.data)))
      } catch {
        /* not JSON: ignore */
      }
    }
    this.ws.onclose = () => {
      this.ws = null
      this.onStatus(false)
      if (!this.closed) this.retry = window.setTimeout(() => this.connect(), 3000)
    }
  }

  /** Sends now, or as soon as the hub is reachable (only the latest unsent message is kept). */
  send(msg: HubMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
      this.queued = null
    } else {
      this.queued = msg
    }
  }

  close(): void {
    this.closed = true
    window.clearTimeout(this.retry)
    this.ws?.close()
  }
}

/** Keys a presentation clicker or keyboard uses to move between slides. */
export const NEXT_KEYS = new Set(['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter', 'n', 'N'])
export const PREV_KEYS = new Set(['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace', 'p', 'P'])
