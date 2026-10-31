"""Tests for the caption engine plumbing. No Gemini calls: transcriber and translator are stubs."""

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import websockets

HUB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB_DIR))

from live_engine import Engine, HubClient, SentenceBuffer, build_prompt, load_glossary  # noqa: E402


def test_sentence_buffer_splits_on_punctuation():
    b = SentenceBuffer()
    assert b.feed("오늘 우리는 창세기 12장을", 0) == []
    assert b.feed(" 봅니다. 하나님은 언약을", 0.5) == ["오늘 우리는 창세기 12장을 봅니다."]
    assert b.feed(" 맺으십니다? 아멘", 1.0) == ["하나님은 언약을 맺으십니다?"]
    assert b.text.strip() == "아멘"


def test_sentence_buffer_flushes_after_pause():
    b = SentenceBuffer(idle_s=1.6)
    b.feed("마침표 없이 끝나는 말", 10.0)
    assert b.flush_if_idle(11.0) is None
    assert b.flush_if_idle(11.7) == "마침표 없이 끝나는 말"
    assert b.flush_if_idle(20.0) is None


def test_sentence_buffer_caps_run_on_speech():
    b = SentenceBuffer(max_chars=20)
    out = b.feed("아주 긴 문장이 마침표 없이 계속 이어지고 있습니다 그리고 또", 0)
    assert out and all(len(s) <= 20 for s in out)


def test_prompt_includes_only_glossary_terms_in_sentence():
    glossary = load_glossary(HUB_DIR / "glossary.json")
    prompt = build_prompt("하이델베르크 요리문답 제1문을 봅시다.", ["이전 문장."], glossary, ["en", "th"])
    assert "the Heidelberg Catechism" in prompt
    assert "covenant" not in prompt  # 언약 is not in the sentence
    assert "이전 문장." in prompt
    assert prompt.rstrip().endswith("하이델베르크 요리문답 제1문을 봅시다.")


class StubTranscriber:
    def __init__(self, fragments):
        self.fragments = fragments

    async def run(self, queue, on_text):
        for f in self.fragments:
            await on_text(f)
            await asyncio.sleep(0.05)


class StubTranslator:
    async def translate(self, sentence, context):
        return {"en": f"EN<{sentence}>", "th": f"TH<{sentence}>"}


def free_port():
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


@pytest.fixture
def hub():
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(HUB_DIR / "caption_hub.py"), "--port", str(port)])
    for _ in range(50):
        try:
            socket.create_connection(("localhost", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"ws://localhost:{port}"
    proc.terminate()
    proc.wait()


def test_engine_sends_captions_through_hub(hub, tmp_path):
    async def scenario():
        received = []
        async with websockets.connect(hub) as screen:  # stands in for the slideshow caption band
            engine = Engine(StubTranscriber(["하나님은 언약을", " 맺으십니다. ", "아멘"]), StubTranslator(),
                            HubClient(hub), ["en", "th"], tmp_path / "log.jsonl")

            async def no_audio(q):
                await asyncio.Future()

            await engine.run(no_audio)  # returns after the stub transcript plus the idle flush
            try:
                while True:
                    received.append(json.loads(await asyncio.wait_for(screen.recv(), 1.0)))
            except asyncio.TimeoutError:
                pass
        return received

    msgs = asyncio.run(scenario())
    assert msgs[0] == {"type": "caption", "lines": [
        {"lang": "en", "text": "EN<하나님은 언약을 맺으십니다.>"},
        {"lang": "th", "text": "TH<하나님은 언약을 맺으십니다.>"},
        {"lang": "ko", "text": "하나님은 언약을 맺으십니다."}]}  # Korean as heard, for the phones
    assert msgs[1]["lines"][0]["text"] == "EN<아멘>"  # no full stop: flushed when speech ends
    log = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [entry["ko"] for entry in log] == ["하나님은 언약을 맺으십니다.", "아멘"]


class SlowFirstTranslator:
    """First sentence takes longest, so concurrent translations finish out of order."""

    def __init__(self):
        self.n = 0

    async def translate(self, sentence, context):
        self.n += 1
        await asyncio.sleep(0.4 if self.n == 1 else 0.05)
        return {"en": sentence, "th": sentence}


def test_captions_keep_spoken_order_when_translations_overlap(hub, tmp_path):
    async def scenario():
        async with websockets.connect(hub) as screen:
            engine = Engine(StubTranscriber(["첫째. ", "둘째. ", "셋째. "]), SlowFirstTranslator(),
                            HubClient(hub), ["en"], None)

            async def no_audio(q):
                await asyncio.Future()

            await engine.run(no_audio)
            return [json.loads(await asyncio.wait_for(screen.recv(), 1.0))["lines"][0]["text"] for _ in range(3)]

    assert asyncio.run(scenario()) == ["첫째.", "둘째.", "셋째."]


def test_fatal_errors_are_recognised_and_key_is_redacted(monkeypatch):
    from live_engine import is_fatal, redact
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET123")
    assert is_fatal("1007 invalid x-goog-api-key")
    assert is_fatal("Your project has exceeded its monthly spending cap.")
    assert not is_fatal("keepalive ping timeout")
    assert redact("bad key SECRET123 rejected") == "bad key *** rejected"


def test_mic_meter_warns_only_when_nothing_is_heard(caplog):
    import logging
    from live_engine import MicMeter
    silent, loud = b"\0\0" * 1600, (b"\x10\x27" * 1600)  # 0 and 10000 as int16
    m = MicMeter(every_s=100, silent_after_s=10)
    with caplog.at_level(logging.WARNING, logger="live-engine"):
        for i in range(120):
            m.feed(silent, i * 0.1)
    assert "들어오지 않습니다" in caplog.text
    caplog.clear()
    m = MicMeter(every_s=100, silent_after_s=10)
    with caplog.at_level(logging.WARNING, logger="live-engine"):
        m.feed(loud, 0)
        for i in range(1, 120):
            m.feed(silent, i * 0.1)
    assert "들어오지 않습니다" not in caplog.text


def test_sentence_buffer_replaces_resent_start_of_sentence():
    b = SentenceBuffer()
    assert b.feed("그대로", 0) == []
    assert b.flush_if_idle(3.0) is None  # too short to flush after a 3 s pause
    assert b.feed("그대로 있으리라 하시니라.", 3.0) == ["그대로 있으리라 하시니라."]


def test_prompt_tells_translator_to_trust_notes_over_misheard_passage():
    prompt = build_prompt("사도행전 20장 19절에서 23절의 말씀입니다.", [], [], ["en"], "오늘 본문: 요한복음 20:19-23")
    assert "요한복음 20:19-23" in prompt and "speech-recognition error" in prompt


def test_audio_is_dropped_while_translation_is_off():
    from live_engine import GatedQueue
    state = {"on": True}
    q = GatedQueue(lambda: state["on"])
    q.put_nowait(b"a")
    state["on"] = False
    q.put_nowait(b"b")
    q.put_nowait(None)  # end of a file replay still gets through
    assert [q.get_nowait() for _ in range(q.qsize())] == [b"a", None]


def test_switching_off_finishes_the_sentence_in_progress(tmp_path):
    async def scenario():
        engine = Engine(None, StubTranslator(), None, ["en"], None)
        engine.buffer.feed("마침표 없이 하던 말", 0)
        engine.set_translating(False, 74)
        sentence, task = engine.pending.get_nowait()
        return engine.translating, sentence, (await task)["en"]

    assert asyncio.run(scenario()) == (False, "마침표 없이 하던 말", "EN<마침표 없이 하던 말>")


def test_hub_forwards_control_and_replays_it_to_late_clients(hub):
    async def scenario():
        async with websockets.connect(hub) as player, websockets.connect(hub) as engine:
            await player.send(json.dumps({"type": "control", "translate": False, "slide": 3}))
            first = json.loads(await asyncio.wait_for(engine.recv(), 1.0))
            await player.send(json.dumps({"type": "control", "translate": False, "slide": 4}))  # no change
            async with websockets.connect(hub) as late:
                replay = json.loads(await asyncio.wait_for(late.recv(), 1.0))
            try:
                extra = await asyncio.wait_for(engine.recv(), 0.3)
            except asyncio.TimeoutError:
                extra = None
            return first, replay, extra

    first, replay, extra = asyncio.run(scenario())
    assert first["translate"] is False and first["slide"] == 3
    assert replay["translate"] is False and extra is None


def test_engine_follows_control_from_hub(hub):
    async def scenario():
        engine = Engine(None, StubTranslator(), HubClient(hub), ["en"], None)
        listener = asyncio.create_task(engine.hub.listen(engine.on_control))
        await asyncio.sleep(0.3)
        async with websockets.connect(hub) as player:
            await player.send(json.dumps({"type": "control", "translate": False, "slide": 56}))
            await asyncio.sleep(0.3)
            off = engine.translating
            await player.send(json.dumps({"type": "control", "translate": True, "slide": 73}))
            await asyncio.sleep(0.3)
        listener.cancel()
        return off, engine.translating

    assert asyncio.run(scenario()) == (False, True)


def test_presenter_language_choice_reaches_translator(hub):
    class Langs(StubTranslator):
        langs = ["en"]

    async def scenario():
        engine = Engine(None, Langs(), HubClient(hub), ["en"], None)
        listener = asyncio.create_task(engine.hub.listen(engine.on_control))
        await asyncio.sleep(0.3)
        async with websockets.connect(hub) as player:
            await player.send(json.dumps({"type": "control", "langs": ["en", "th", "ko", "xx", "zh", "vi"]}))
            await asyncio.sleep(0.3)
        listener.cancel()
        return engine.langs, engine.translator.langs, engine.translating

    # Korean and unknown codes are dropped; on/off is untouched
    assert asyncio.run(scenario()) == (["en", "zh", "th", "vi"], ["en", "zh", "th", "vi"], True)


def test_phone_mic_serves_page_and_queues_audio(tmp_path, monkeypatch):
    import ssl
    import urllib.request
    import phone_mic
    monkeypatch.setattr(phone_mic, "CERT_DIR", tmp_path)
    port = free_port()

    async def scenario():
        q = asyncio.Queue()
        mic = phone_mic.PhoneMic(port, status=lambda: {"translating": False})
        server = asyncio.create_task(mic.run(q))
        await asyncio.sleep(1.0)
        insecure = ssl.create_default_context()
        insecure.check_hostname, insecure.verify_mode = False, ssl.CERT_NONE
        page = await asyncio.to_thread(
            lambda: urllib.request.urlopen(f"https://localhost:{port}/", context=insecure).read().decode())
        async with websockets.connect(f"wss://localhost:{port}/ws", ssl=insecure) as ws:
            status = json.loads(await asyncio.wait_for(ws.recv(), 3))
            await ws.send(b"\x01\x00" * 1600)
            chunk = await asyncio.wait_for(q.get(), 3)
        server.cancel()
        return page, status, chunk

    page, status, chunk = asyncio.run(scenario())
    assert "설교 마이크" in page
    assert status == {"translating": False}
    assert len(chunk) == 3200
    assert (tmp_path / "phone-mic.crt").exists() and (tmp_path / "phone-mic.key").stat().st_mode & 0o077 == 0


def test_phones_add_their_language_and_cannot_send_captions():
    port, lan = free_port(), free_port()
    proc = subprocess.Popen([sys.executable, str(HUB_DIR / "caption_hub.py"), "--port", str(port), "--lan-port", str(lan)])
    try:
        for _ in range(50):
            try:
                socket.create_connection(("localhost", lan), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.1)

        async def scenario():
            import urllib.request
            page = await asyncio.to_thread(lambda: urllib.request.urlopen(f"http://localhost:{lan}/").read().decode())
            qr = await asyncio.to_thread(lambda: urllib.request.urlopen(f"http://localhost:{lan}/qr").read().decode())
            async with websockets.connect(f"ws://localhost:{port}") as engine, \
                    websockets.connect(f"ws://localhost:{lan}/ws") as phone:
                await phone.send(json.dumps({"type": "listen", "lang": "th"}))
                ctl = json.loads(await asyncio.wait_for(engine.recv(), 2))
                await phone.send(json.dumps({"type": "caption", "lines": [{"lang": "th", "text": "spoof"}]}))
                await engine.send(json.dumps({"type": "caption", "lines": [{"lang": "th", "text": "สวัสดี"}]}))
                got = json.loads(await asyncio.wait_for(phone.recv(), 2))
                try:
                    spoof = await asyncio.wait_for(engine.recv(), 0.5)
                except asyncio.TimeoutError:
                    spoof = None
            return page, qr, ctl, got, spoof

        page, qr, ctl, got, spoof = asyncio.run(scenario())
        assert "Hobart Korean Church" in page and "<svg" in qr
        assert ctl["langs"] == ["en", "th"]  # projector default English + the phone's Thai
        assert got["lines"][0]["text"] == "สวัสดี"
        assert spoof is None  # a phone cannot put captions on the screen
    finally:
        proc.terminate()
        proc.wait()


def test_phone_mic_certificate_is_trusted_through_the_mac_ca(tmp_path, monkeypatch):
    import ssl
    import phone_mic
    monkeypatch.setattr(phone_mic, "CERT_DIR", tmp_path)
    port = free_port()

    async def scenario():
        server = asyncio.create_task(phone_mic.PhoneMic(port).run(asyncio.Queue()))
        await asyncio.sleep(1.0)
        ctx = ssl.create_default_context(cafile=str(tmp_path / "ca.crt"))  # a phone that installed the CA
        async with websockets.connect(f"wss://localhost:{port}/ws", ssl=ctx) as ws:
            ok = ws.state.name == "OPEN"
        server.cancel()
        return ok

    assert asyncio.run(scenario())
    ca_before = (tmp_path / "ca.crt").read_bytes()
    phone_mic.ensure_cert("10.1.2.3", "other.local")  # new Wi-Fi address: new page certificate, same CA
    assert (tmp_path / "ca.crt").read_bytes() == ca_before
