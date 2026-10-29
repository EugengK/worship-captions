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
        {"lang": "th", "text": "TH<하나님은 언약을 맺으십니다.>"}]}
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
