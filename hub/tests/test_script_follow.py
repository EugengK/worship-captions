"""Manuscript following with recognizer-style variations. No Gemini calls."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from script_follow import ScriptFollower  # noqa: E402

SCRIPT = [
    {"ko": "오늘 우리는 레위기 4장의 속죄제를 함께 살펴보겠습니다.", "en": "Today we look at the sin offering in Leviticus 4."},
    {"ko": "속죄제는 부지중에 지은 죄를 위한 제사였습니다.", "en": "The sin offering was for sins committed unintentionally."},
    {"ko": "하나님은 우리가 알지 못하고 지은 죄까지도 다루십니다.", "en": "God deals even with the sins we commit without knowing."},
    {"ko": "제사장은 그 피를 성소의 휘장 앞에 일곱 번 뿌렸습니다.", "en": "The priest sprinkled the blood seven times before the curtain."},
    {"ko": "이것은 그리스도의 피를 가리킵니다.", "en": "This points to the blood of Christ."},
    {"ko": "그러므로 우리는 담대히 은혜의 보좌 앞에 나아갈 수 있습니다.", "en": "Therefore we can boldly approach the throne of grace."},
    {"ko": "기도하겠습니다.", "en": "Let us pray."},
]


def follower():
    return ScriptFollower(json.loads(json.dumps(SCRIPT)), "레위기 4장")


def test_exact_and_spacing_variations_match_in_order():
    f = follower()
    m = f.match("오늘 우리는 레위기 4장의 속죄제를 함께 살펴 보겠습니다")
    assert (m.kind, m.index) == ("match", 0)
    m = f.match("속죄 제는 부지 중에 지은 죄를 위한 제사였습니다.")
    assert (m.kind, m.index) == ("match", 1)
    assert f.translation(m, ["en"]) == {"en": "The sin offering was for sins committed unintentionally."}


def test_misheard_syllables_still_match():
    f = follower()
    f.pos = 3
    m = f.match("제사장은 그 피를 성서의 휘장 앞에 일곱 번 뿌렸습니다.")  # 성소 -> 성서
    assert (m.kind, m.index, m.exact) == ("match", 3, False)  # found, but checked by the translator


def test_changed_number_or_negation_is_never_exact():
    f = follower()
    f.pos = 2
    m = f.match("하나님은 우리가 알고 지은 죄만 다루십니다.")
    assert not m.exact
    f.pos = 3
    m = f.match("제사장은 그 피를 성소의 휘장 앞에 세 번 뿌렸습니다.")
    assert m.kind == "match" and not m.exact
    assert "일곱 번" in f.hint(m, ["en"]) and "seven times" in f.hint(m, ["en"])


def test_fragments_are_followed_and_a_shown_sentence_is_not_repeated():
    f = follower()
    f.pos = 2
    m1 = f.match("하나님은 우리가 알지 못하고")
    assert (m1.kind, m1.index) == ("fragment", 2)
    m2 = f.match("지은 죄까지도 다루십니다.")
    assert (m2.kind, m2.index) == ("fragment", 2)  # each piece is captioned as it is said


def test_two_sentences_said_at_once():
    f = follower()
    f.pos = 3
    m = f.match("제사장은 그 피를 성소의 휘장 앞에 일곱 번 뿌렸습니다 이것은 그리스도의 피를 가리킵니다")
    assert (m.kind, m.index, m.count) == ("match", 3, 2)
    assert f.translation(m, ["en"])["en"].startswith("The priest") and "Christ" in f.translation(m, ["en"])["en"]


def test_ad_lib_and_changed_meaning_go_live():
    f = follower()
    f.pos = 1
    assert f.match("여러분 오늘 날씨가 참 좋지요?").kind == "none"
    # Same topic, different claim: must not be captioned with the manuscript's sentence
    assert f.match("속죄제는 일부러 지은 죄를 위한 제사가 아니었습니다.").kind == "none"


def test_jump_ahead_only_on_a_clear_match():
    f = follower()
    m = f.match("그러므로 우리는 담대히 은혜의 보좌 앞에 나아갈 수 있습니다.")
    assert (m.kind, m.index) == ("match", 5)
    assert f.match("기도").kind == "none"  # too short to jump on
    assert f.match("그러므로 우리는 담대히 은혜의 보좌 앞에 나아갈 수 있습니다").kind == "repeat"


def test_missing_language_falls_back_to_live():
    f = follower()
    m = f.match("오늘 우리는 레위기 4장의 속죄제를 함께 살펴보겠습니다.")
    assert f.translation(m, ["en", "th"]) is None


def test_engine_uses_script_and_translates_the_rest(tmp_path):
    from live_engine import Engine

    class Hub:
        def __init__(self):
            self.sent = []

        async def send(self, msg):
            self.sent.append(msg)

    class Translator:
        langs = ["en"]

        def __init__(self):
            self.calls = []

        async def translate(self, sentence, context, hint=""):
            self.calls.append((sentence, hint))
            return {"en": f"LIVE<{sentence}>"}

    async def scenario():
        hub, tr = Hub(), Translator()
        engine = Engine(None, tr, hub, ["en"], tmp_path / "log.jsonl", follower())
        loop = asyncio.create_task(engine._translate_loop())
        for s in ["오늘 우리는 레위기 4장의 속죄제를 함께 살펴보겠습니다.", "여러분 오늘 날씨가 참 좋지요?",
                  "속죄제는 부지중에 지은 죄를 위한 제사였습니다.", "속죄제는 부지중에 지은 죄를 위한 제사였습니다.",
                  "하나님은 우리가 알고 지은 죄만 다루십니다."]:
            engine._start(s)
        await engine.pending.join()
        loop.cancel()
        return hub.sent, tr.calls

    sent, calls = asyncio.run(scenario())
    assert [m["lines"][0]["text"] for m in sent] == [
        "Today we look at the sin offering in Leviticus 4.",
        "LIVE<여러분 오늘 날씨가 참 좋지요?>",
        "The sin offering was for sins committed unintentionally.",
        "LIVE<하나님은 우리가 알고 지은 죄만 다루십니다.>",
    ]
    assert calls[0] == ("여러분 오늘 날씨가 참 좋지요?", "")
    assert calls[1][0] == "하나님은 우리가 알고 지은 죄만 다루십니다." and "알지 못하고" in calls[1][1]


def test_prompt_carries_the_manuscript_hint():
    from live_engine import build_prompt
    p = build_prompt("세 번 뿌렸습니다.", [], [], ["en"], hint="Manuscript Korean: 일곱 번 뿌렸습니다.\nPrepared \"en\": seven times")
    assert "일곱 번" in p and "translate what was actually said" in p


def test_manuscript_is_split_into_preached_sentences(tmp_path):
    from prepare_script import read_text, split_sentences
    md = tmp_path / "s.md"
    md.write_text("# 속죄제\n\n오늘은 레위기 4장입니다. 함께 보시죠! 왜 그럴까요?\n“이것이 피니라.” 아멘.\n", encoding="utf-8")
    assert split_sentences(read_text(md)) == ["속죄제", "오늘은 레위기 4장입니다.", "함께 보시죠!", "왜 그럴까요?",
                                              "“이것이 피니라.”", "아멘."]
