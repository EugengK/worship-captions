"""Live caption engine: microphone -> Korean transcript -> translated captions -> caption hub.

    python3 live_engine.py                       # Mac microphone, English + Thai
    python3 live_engine.py --langs en,th,zh      # pick caption languages (first line = first language)
    python3 live_engine.py --file sermon.wav     # replay a recording at real-time speed (for testing)

Pipeline
  1. Audio (16 kHz mono PCM, 100 ms chunks) from the default input device or a WAV file.
  2. A Gemini Live session turns it into Korean text fragments (input transcription).
  3. Fragments are joined into sentences (punctuation, or a pause, or a length cap).
  4. Each sentence is translated by a Gemini text model with the church glossary and the
     previous sentences as context, into every caption language in one call.
  5. The result is sent to the caption hub (ws://localhost:8765), which forwards it to the
     slideshow caption band and any other screen.

Requires GEMINI_API_KEY in the environment. Start caption_hub.py first.
"""

import argparse
import asyncio
import datetime as dt
import json
import logging
import os
import re
import time
import wave
from pathlib import Path

import websockets

log = logging.getLogger("live-engine")

HERE = Path(__file__).resolve().parent
LANG_NAMES = {"en": "English", "th": "Thai", "zh": "Simplified Chinese", "vi": "Vietnamese", "ko": "Korean"}
MAX_LANGS = 4  # every language the engine offers; the projector shows at most 3 of them

# Transcription-only Live model: Korean text, no audio output to pay for (docs/13). The
# live-translate model also works (it returns the Korean input transcription too) but
# generates English speech that the captions do not use.
DEFAULT_STT_MODEL = "gemini-3.5-transcribe-live"
DEFAULT_TRANSLATE_MODEL = "gemini-3.5-flash"

SAMPLE_RATE = 16000
CHUNK_BYTES = SAMPLE_RATE * 2 // 10  # 100 ms of 16-bit mono


# ---------------------------------------------------------------- sentences

class SentenceBuffer:
    """Joins transcript fragments into sentences for captioning.

    A sentence ends at . ? ! (or their full-width forms), after `idle_s` seconds without new
    fragments, or once it grows past `max_chars` (long run-on speech still gets captioned).
    """

    END = re.compile(r"(.+?[.?!。？！])(\s+|$)", re.S)

    SHORT = 6  # a piece this short ("그대로") is usually the start of a sentence still coming

    def __init__(self, idle_s: float = 1.6, max_chars: int = 140, short_idle_s: float = 4.0):
        self.idle_s = idle_s
        self.short_idle_s = short_idle_s
        self.max_chars = max_chars
        self.text = ""
        self.last = 0.0

    def feed(self, fragment: str, now: float) -> list:
        pending = self.text.strip()
        if pending and fragment.strip().startswith(pending):
            # The recogniser re-sent the unfinished sentence in full ("그대로" -> "그대로 있으리라 하시니라.").
            self.text = fragment.lstrip()
        else:
            self.text += fragment
        self.last = now
        out = []
        while True:
            m = self.END.match(self.text)
            if not m:
                break
            out.append(m.group(1).strip())
            self.text = self.text[m.end():]
        if len(self.text) > self.max_chars:
            cut = self.text.rfind(" ", 0, self.max_chars)
            cut = cut if cut > self.max_chars // 2 else self.max_chars
            out.append(self.text[:cut].strip())
            self.text = self.text[cut:]
        return [s for s in out if s]

    def flush_if_idle(self, now: float):
        wait = self.short_idle_s if len(self.text.strip()) < self.SHORT else self.idle_s
        if self.text.strip() and now - self.last >= wait:
            s, self.text = self.text.strip(), ""
            return s
        return None


# ---------------------------------------------------------------- translation

def load_glossary(path: Path) -> list:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("terms", [])
    except FileNotFoundError:
        return []


def build_prompt(sentence: str, context: list, glossary: list, langs: list, notes: str = "", hint: str = "") -> str:
    """Prompt for one sentence. Only glossary terms that occur in the sentence are included."""
    used = [t for t in glossary if t.get("ko") and t["ko"] in sentence]
    lines = [
        "Translate the Korean sentence from a live church sermon into captions.",
        "Return JSON with exactly these keys: " + ", ".join(langs) + ".",
        "Each value is a natural, faithful translation of the sentence only, short enough for a projector caption.",
        "Do not add explanations. For Bible quotations, translate directly from the Korean in your own words; "
        "do not reproduce the wording of any published Bible translation.",
        "The Korean comes from live speech recognition and may have recognition errors (odd spacing, misheard names); "
        "translate what the preacher meant.",
    ]
    for code in langs:
        lines.append(f'- "{code}": {LANG_NAMES.get(code, code)}')
    if used:
        lines.append("Use these church terms exactly:")
        for t in used:
            lines.append("  " + t["ko"] + " = " + "; ".join(f"{c}: {t[c]}" for c in langs if t.get(c)))
    if notes:
        lines.append("Notes about today's sermon (use them to resolve misheard names and terms): " + notes)
        lines.append("If the sentence names a Bible book, chapter or person that conflicts with these notes, "
                     "it is almost certainly a speech-recognition error: translate it as the notes say.")
    if hint:
        lines.append("The preacher is following a manuscript. The matching manuscript passage and its prepared "
                     "translation:")
        lines.extend("  " + h for h in hint.splitlines())
        lines.append("If the spoken sentence means the same as the manuscript, return the prepared translation "
                     "unchanged (only the part that was actually said, if it is a partial sentence). If anything "
                     "differs in meaning (numbers, negation, names, added or missing parts), translate what was "
                     "actually said, reusing the prepared wording where it still fits.")
    if context:
        lines.append("Previous sentences (context only, do not translate):")
        lines.extend("  " + c for c in context)
    lines.append("Sentence to translate:")
    lines.append(sentence)
    return "\n".join(lines)


class GeminiTranslator:
    def __init__(self, langs: list, glossary: list, model: str = DEFAULT_TRANSLATE_MODEL, think_budget: int = 0,
                 notes: str = ""):
        from google import genai
        from google.genai import types
        self.types = types
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.langs, self.glossary, self.model = langs, glossary, model
        # Thinking off: measured ~1.1 s per sentence instead of ~5.4 s with the same output quality.
        self.think_budget = think_budget
        self.notes = notes

    async def translate(self, sentence: str, context: list, hint: str = "") -> dict:
        prompt = build_prompt(sentence, context, self.glossary, self.langs, self.notes, hint)
        problem = ""
        # Long Bible quotations are sometimes blocked as RECITATION (too close to a copyrighted Bible
        # translation); a second try with more varied wording usually gets through.
        for temperature in (0.2, 0.8):
            config = self.types.GenerateContentConfig(
                response_mime_type="application/json", temperature=temperature,
                thinking_config=self.types.ThinkingConfig(thinking_budget=self.think_budget))
            resp = await self.client.aio.models.generate_content(model=self.model, contents=prompt, config=config)
            try:
                data = json.loads(resp.text or "")
                return {c: str(data.get(c, "")).strip() for c in self.langs}
            except ValueError:
                cand = resp.candidates[0] if resp.candidates else None
                problem = f"empty or invalid reply (finish_reason={getattr(cand, 'finish_reason', None)})"
        raise RuntimeError(problem)


# ---------------------------------------------------------------- audio sources

def level(chunk: bytes) -> int:
    """Loudness of a 16-bit PCM chunk, 0-100 (rough; for the on-screen meter only)."""
    import numpy as np
    pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
    if pcm.size == 0:
        return 0
    rms = float(np.sqrt(np.mean(pcm * pcm)))
    return min(100, int(rms / 50))  # ~5000 RMS (loud speech) -> 100


class MicMeter:
    """Prints the mic level every few seconds and warns once if nothing is coming in.

    macOS hands silent audio to apps that were refused microphone access, so silence is the
    only sign of a missing permission or a wrong input device.
    """

    MAC_HINT = ("① 시스템 설정 > 개인정보 보호 및 보안 > 마이크 에서 '터미널' 켜기 (켠 뒤 터미널을 완전히 종료 후 다시 실행) "
                "② 시스템 설정 > 사운드 > 입력 에서 올바른 마이크 선택")
    PHONE_HINT = "휴대폰 페이지의 소리 막대가 움직이는지, Safari 마이크 허용이 켜져 있는지 보세요"

    def __init__(self, every_s: float = 5.0, silent_after_s: float = 10.0, hint: str = MAC_HINT):
        self.every_s, self.silent_after_s, self.hint = every_s, silent_after_s, hint
        self.peak, self.started, self.last_report, self.heard, self.warned = 0, None, 0.0, False, False

    def feed(self, chunk: bytes, now: float) -> None:
        if self.started is None:
            self.started = self.last_report = now
        lv = level(chunk)
        self.peak = max(self.peak, lv)
        if lv >= 3:
            self.heard = True
        if now - self.last_report >= self.every_s:
            log.info("마이크 소리 크기: %s %d", "▮" * (self.peak // 10) or "·", self.peak)
            self.peak, self.last_report = 0, now
        if not self.heard and not self.warned and now - self.started >= self.silent_after_s:
            self.warned = True
            log.warning("마이크에서 소리가 들어오지 않습니다. 확인하세요: %s", self.hint)


async def mic_chunks(queue: asyncio.Queue) -> None:
    import sounddevice as sd  # imported here so --file tests do not need PortAudio
    loop = asyncio.get_running_loop()
    meter = MicMeter()

    def callback(indata, frames, t, status):
        chunk = bytes(indata)
        loop.call_soon_threadsafe(queue.put_nowait, chunk)
        meter.feed(chunk, time.monotonic())

    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                           blocksize=CHUNK_BYTES // 2, callback=callback):
        try:
            name = sd.query_devices(kind="input")["name"]
        except Exception:
            name = "?"
        log.info("마이크로 듣는 중: %s", name)
        await asyncio.Future()


async def file_chunks(queue: asyncio.Queue, path: str) -> None:
    """Replays a 16-bit WAV at real-time speed (resampled to 16 kHz mono), then 3 s of silence."""
    import numpy as np
    with wave.open(path) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)
    n = int(len(pcm) * SAMPLE_RATE / sr)
    pcm = np.interp(np.linspace(0, len(pcm) - 1, n), np.arange(len(pcm)), pcm).astype(np.int16).tobytes()
    pcm += b"\0" * SAMPLE_RATE * 2 * 3
    for i in range(0, len(pcm), CHUNK_BYTES):
        await queue.put(pcm[i:i + CHUNK_BYTES])
        await asyncio.sleep(0.1)
    await queue.put(None)


# ---------------------------------------------------------------- errors

class FatalError(Exception):
    """Retrying cannot help (bad key, no credit): stop and tell the person what to fix."""


FATAL_HINTS = ("api key", "api_key", "x-goog-api-key", "credits are depleted", "spending cap",
               "permission_denied", "unauthenticated", "billing")


def is_fatal(message: str) -> bool:
    m = message.lower()
    return any(h in m for h in FATAL_HINTS)


def redact(text: str) -> str:
    """Never print the API key, even when an error message echoes it."""
    key = os.environ.get("GEMINI_API_KEY", "")
    return text.replace(key, "***") if key else text


# ---------------------------------------------------------------- transcription

class GeminiTranscriber:
    """Streams audio into a Gemini Live session and reports Korean transcript fragments.

    Live sessions have a time limit, so the session is reopened whenever it closes; audio that
    queued up during a reconnect is dropped beyond the last 2 s so captions stay current.
    """

    def __init__(self, model: str = DEFAULT_STT_MODEL):
        from google import genai
        from google.genai import types
        self.types = types
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.model = model

    def _config(self):
        t = self.types
        modality = "TEXT" if "transcribe" in self.model else "AUDIO"
        cfg = dict(response_modalities=[modality], input_audio_transcription=t.AudioTranscriptionConfig())
        if "translate" in self.model:
            cfg["translation_config"] = t.TranslationConfig(target_language_code="en")
        else:
            # Default end-of-speech detection waits for long pauses and delivered sermon text up
            # to ~20 s late in bursts; high sensitivity returns each sentence ~0.5-1 s after it ends.
            cfg["realtime_input_config"] = t.RealtimeInputConfig(
                automatic_activity_detection=t.AutomaticActivityDetection(
                    end_of_speech_sensitivity=t.EndSensitivity.END_SENSITIVITY_HIGH, silence_duration_ms=200))
        return t.LiveConnectConfig(**cfg)

    async def run(self, queue: asyncio.Queue, on_text) -> None:
        done = False
        while not done:
            # Google closes a session that gets no sound for about a minute. Waiting for sound
            # before (re)opening avoids a new session every minute while the mic is silent or
            # translation is off.
            first = await queue.get()
            if first is None:
                return
            try:
                async with self.client.aio.live.connect(model=self.model, config=self._config()) as s:
                    log.info("transcription session open (%s)", self.model)
                    while queue.qsize() > 20:
                        queue.get_nowait()

                    async def send():
                        nonlocal done
                        await s.send_realtime_input(
                            audio=self.types.Blob(data=first, mime_type=f"audio/pcm;rate={SAMPLE_RATE}"))
                        while True:
                            chunk = await queue.get()
                            if chunk is None:
                                done = True
                                await asyncio.sleep(6)  # let the last words come back
                                return
                            await s.send_realtime_input(
                                audio=self.types.Blob(data=chunk, mime_type=f"audio/pcm;rate={SAMPLE_RATE}"))

                    async def recv():
                        async for m in s.receive():
                            sc = m.server_content
                            if sc and sc.input_transcription and sc.input_transcription.text:
                                await on_text(sc.input_transcription.text)

                    sender, receiver = asyncio.create_task(send()), asyncio.create_task(recv())
                    await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
                    for task in (sender, receiver):
                        task.cancel()
            except Exception as e:  # network drop, session limit, quota
                msg = redact(str(e))
                if is_fatal(msg):
                    raise FatalError(msg) from None
                log.warning("transcription session ended, reconnecting: %s", msg)
                await asyncio.sleep(1)


# ---------------------------------------------------------------- hub output

class HubClient:
    def __init__(self, url: str):
        self.url, self.ws = url, None

    async def send(self, msg: dict) -> None:
        for _ in range(2):
            try:
                if self.ws is None:
                    self.ws = await websockets.connect(self.url)
                await self.ws.send(json.dumps(msg, ensure_ascii=False))
                return
            except Exception as e:
                log.warning("caption hub not reachable (%s): %s", self.url, e)
                self.ws = None

    async def listen(self, on_control) -> None:
        """Follows {"type": "control", "translate": bool, "langs": [...]} from the worship player, reconnecting."""
        while True:
            try:
                async with websockets.connect(self.url) as ws:
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        if msg.get("type") == "control":
                            on_control(msg)
            except (OSError, websockets.WebSocketException):
                pass
            await asyncio.sleep(3)


class GatedQueue(asyncio.Queue):
    """Audio queue that drops sound while translation is off, so nothing is sent to Google."""

    def __init__(self, is_open):
        super().__init__()
        self.is_open = is_open

    def put_nowait(self, item) -> None:
        if item is None or self.is_open():  # None ends a file replay and always passes
            super().put_nowait(item)


# ---------------------------------------------------------------- engine

class Engine:
    def __init__(self, transcriber, translator, hub, langs: list, logfile: Path = None, script=None):
        self.transcriber, self.translator, self.hub, self.langs = transcriber, translator, hub, langs
        self.script = script  # ScriptFollower: prepared sermon translations (script_follow.py), or None
        self.buffer = SentenceBuffer()
        self.context = []
        self.logfile = logfile
        self.pending = asyncio.Queue()
        self.translating = True  # the worship player switches this per slide; without it, always on

    def on_control(self, msg: dict) -> None:
        """Applies a control message from the worship player: languages first, then on/off."""
        if isinstance(msg.get("langs"), list):
            self.set_langs(msg["langs"])
        if isinstance(msg.get("translate"), bool):
            self.set_translating(msg["translate"], msg.get("slide"))

    def set_langs(self, langs: list) -> None:
        """Caption languages chosen on the presenter screen (at most 3, Korean excluded)."""
        wanted = [c for c in dict.fromkeys(langs) if c in LANG_NAMES and c != "ko"][:MAX_LANGS]
        if not wanted or wanted == self.langs:
            return
        self.langs = wanted
        if hasattr(self.translator, "langs"):
            self.translator.langs = wanted
        log.info("자막 언어: %s", ", ".join(LANG_NAMES[c] for c in wanted))

    def set_translating(self, on: bool, slide=None) -> None:
        if on == self.translating:
            return
        self.translating = on
        where = f" (슬라이드 {slide})" if slide else ""
        if on:
            log.info("번역 켜짐%s", where)
        else:
            log.info("번역 꺼짐%s: 마이크 소리를 보내지 않습니다", where)
            rest = self.buffer.text.strip()  # finish the sentence that was being spoken
            if rest:
                self.buffer.text = ""
                self._start(rest)

    async def on_text(self, fragment: str) -> None:
        log.info("인식: %s", fragment.strip())
        for sentence in self.buffer.feed(fragment, time.monotonic()):
            self._start(sentence)

    def _start(self, sentence: str) -> None:
        """Starts translating at once (sentences overlap) but keeps them in spoken order.

        With a sermon script: a sentence said exactly as written takes its prepared translation
        (no translation call); a similar one is translated with the manuscript as a hint, so a
        changed number or negation is followed; one already shown is skipped; the rest is live."""
        hint = ""
        if self.script is not None:
            m = self.script.match(sentence)
            where = f"원고 {m.index + 1}" + (f"~{m.index + m.count}" if m.count > 1 else "") + "번"
            if m.kind == "repeat":
                log.info("%s 문장 (이미 표시함)", where)
                self.context.append(sentence)
                return
            if m.exact and (out := self.script.translation(m, self.langs)) is not None:
                log.info("%s 문장 그대로 → 준비된 번역", where)
                task = asyncio.create_task(self._prepared({**out, "_src": f"script:{m.index + 1}"}))
                self.context.append(sentence)
                self.pending.put_nowait((sentence, task))
                return
            if m.kind in ("match", "fragment"):
                log.info("%s 문장과 비슷함 (%.2f/%.2f) → 원고를 참고해 번역", where, m.precision, m.recall)
                hint = self.script.hint(m, self.langs)
            else:
                log.info("원고에 없음 → 즉석 번역")
        if hint:
            task = asyncio.create_task(self.translator.translate(sentence, self.context[-3:], hint=hint))
            self.context.append(sentence)
            self.pending.put_nowait((sentence, task))
            return
        task = asyncio.create_task(self.translator.translate(sentence, self.context[-3:]))
        self.context.append(sentence)
        self.pending.put_nowait((sentence, task))

    @staticmethod
    async def _prepared(out: dict) -> dict:
        return out

    async def _idle_flusher(self) -> None:
        while True:
            await asyncio.sleep(0.3)
            s = self.buffer.flush_if_idle(time.monotonic())
            if s:
                self._start(s)

    async def _translate_loop(self) -> None:
        while True:
            sentence, task = await self.pending.get()
            try:
                out = await task
            except Exception as e:
                msg = redact(str(e))
                if is_fatal(msg):
                    raise FatalError(msg) from None
                log.warning("translation failed: %s", msg)
                self.pending.task_done()
                continue
            lines = [{"lang": c, "text": out[c]} for c in self.langs if out.get(c)]
            # The Korean as heard, for the congregation phones' "한국어 자막" (the projector ignores it)
            lines.append({"lang": "ko", "text": sentence})
            if lines:
                await self.hub.send({"type": "caption", "lines": lines})
            log.info("%s -> %s", sentence, " | ".join(l["text"] for l in lines))
            if self.logfile:
                with self.logfile.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": dt.datetime.now().isoformat(timespec="seconds"),
                                        "ko": sentence, **out}, ensure_ascii=False) + "\n")
            self.pending.task_done()

    async def run(self, audio_task_factory) -> None:
        audio = GatedQueue(lambda: self.translating)
        translator = asyncio.create_task(self._translate_loop())
        tasks = [asyncio.create_task(self._idle_flusher()), translator,
                 asyncio.create_task(audio_task_factory(audio))]
        if hasattr(self.hub, "listen"):
            tasks.append(asyncio.create_task(self.hub.listen(self.on_control)))
        try:
            listener = asyncio.create_task(self.transcriber.run(audio, self.on_text))
            await asyncio.wait({listener, translator}, return_when=asyncio.FIRST_COMPLETED)
            if translator.done():  # only ends early on a fatal error
                listener.cancel()
                translator.result()
            await listener
            rest = self.buffer.text.strip()  # words still waiting for a full stop
            if rest:
                self.buffer.text = ""
                self._start(rest)
            await self.pending.join()  # finish the last sentences after a file replay
        finally:
            if self.script is not None:
                st = self.script.stats
                log.info("원고 따라가기 결과: 원고 문장 %d, 일부 %d, 반복 %d, 원고에 없음(즉석 번역) %d",
                         st["match"], st["fragment"], st["repeat"], st["none"])
            if getattr(self.hub, "ws", None) is not None:
                await self.hub.ws.close()
            for t in tasks:
                t.cancel()


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--langs", default="en", help="caption languages, in display order (default en; the worship player can change them)")
    p.add_argument("--file", help="replay this WAV instead of using the microphone")
    p.add_argument("--phone", action="store_true",
                   help="use a phone as the microphone: it opens an https page served by this Mac (phone_mic.py)")
    p.add_argument("--phone-port", type=int, default=8443)
    p.add_argument("--script", help="sermon script with prepared translations (JSON, see script_follow.py)")
    p.add_argument("--hub", default="ws://localhost:8765")
    p.add_argument("--glossary", default=str(HERE / "glossary.json"))
    p.add_argument("--stt-model", default=DEFAULT_STT_MODEL)
    p.add_argument("--translate-model", default=DEFAULT_TRANSLATE_MODEL)
    p.add_argument("--notes", default="", help='today\'s passage and names, e.g. "창세기 12:1-9. 이 본문에서는 아브람(Abram)"')
    p.add_argument("--think-budget", type=int, default=0, help="translation model thinking budget (0 = off, fastest)")
    args = p.parse_args()

    langs = [c.strip() for c in args.langs.split(",") if c.strip()]
    logdir = HERE / "logs"
    logdir.mkdir(exist_ok=True)
    logfile = logdir / dt.datetime.now().strftime("%Y%m%d-%H%M.jsonl")

    script = None
    if args.script:
        from script_follow import ScriptFollower
        script = ScriptFollower.load(Path(args.script))
        have = [c for c in langs if all(x.get(c) for x in script.sentences)]
        log.info("설교 원고: %s (%d문장, 준비된 언어: %s)", script.title or args.script, len(script.sentences),
                 ", ".join(have) or "없음")

    engine = Engine(GeminiTranscriber(args.stt_model),
                    GeminiTranslator(langs, load_glossary(Path(args.glossary)), args.translate_model, args.think_budget,
                                     args.notes),
                    HubClient(args.hub), langs, logfile, script)
    if args.file:
        source = lambda q: file_chunks(q, args.file)
    elif args.phone:
        from phone_mic import PhoneMic
        phone = PhoneMic(args.phone_port, status=lambda: {"translating": engine.translating})
        source = lambda q: phone.run(q, MicMeter(hint=MicMeter.PHONE_HINT))
    else:
        source = mic_chunks
    log.info("captions: %s, transcript log: %s", ",".join(langs), logfile)
    await engine.run(source)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    # Per-request lines from the HTTP and Gemini libraries bury the captions on screen.
    for noisy in ("httpx", "google_genai", "google_genai.models", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except FatalError as e:
        print("\n중단: Gemini가 요청을 거절했습니다. 다시 시도해도 해결되지 않는 문제입니다.")
        print("  - 키 문제라면: bash start-mac.sh reset-key 로 키를 다시 넣으세요.")
        print("  - 크레딧·지출 한도 문제라면: https://ai.studio/spend 에서 한도와 결제를 확인하세요.")
        print("  원래 오류:", str(e)[:300])
        raise SystemExit(1)
