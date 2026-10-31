"""Sermon script following: shows the prepared translation of the manuscript sentence being preached.

Before the service the manuscript is split into sentences and each one is translated
(prepare_script.py, or by Claude). During the sermon every Korean sentence the speech
recognizer hears is looked up in the manuscript, near the place reached so far:

    exact match → the prepared translation is shown at once (no translation call)
    near match  → translated live, with the manuscript sentence and its prepared translation as
                  a hint: the translator keeps the prepared wording when the meaning is the same,
                  and follows what was said when it is not (a number, a negation, a name...)
    fragment    → part of a manuscript sentence: translated live with the same hint
    repeat      → a sentence already shown in full: nothing new is shown
    none        → an ad-lib: translated live as before

Character overlap cannot tell "일곱 번" from "세 번", so only an exact match skips the
translator; a changed sentence is never captioned with the manuscript's wording.

Script file (JSON):
    {"title": "...", "sentences": [{"ko": "...", "en": "...", "th": "..."}, ...]}
"""

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

_DROP = re.compile(r"[^0-9A-Za-z가-힣]")

# Thresholds, tuned on recognizer-style variations (spacing, a few misheard syllables).
EXACT = 0.97           # both precision and recall: the manuscript sentence as written
FULL_PRECISION = 0.80   # share of what was said that is in the manuscript sentence
FULL_RECALL = 0.60      # share of the manuscript sentence that was said
FRAGMENT_PRECISION = 0.85
FRAGMENT_MIN_CHARS = 8
JUMP_PRECISION, JUMP_RECALL, JUMP_MIN_CHARS = 0.90, 0.80, 12  # matches far from the current place
WINDOW_BACK, WINDOW_AHEAD = 3, 15


def norm(text: str) -> str:
    """Letters and digits only: recognizers differ from manuscripts in spacing and punctuation."""
    return _DROP.sub("", text)


def overlap(said: str, written: str) -> tuple[float, float]:
    """(precision, recall) of the characters the two strings share in order."""
    if not said or not written:
        return 0.0, 0.0
    m = sum(b.size for b in SequenceMatcher(None, said, written, autojunk=False).get_matching_blocks())
    return m / len(said), m / len(written)


@dataclass
class Match:
    kind: str                 # "match" | "fragment" | "repeat" | "none"
    index: int = -1           # manuscript sentence (0-based); for two sentences said at once, the first
    count: int = 1            # how many manuscript sentences the match covers (1 or 2)
    precision: float = 0.0
    recall: float = 0.0

    @property
    def exact(self) -> bool:
        return self.kind == "match" and self.precision >= EXACT and self.recall >= EXACT


class ScriptFollower:
    def __init__(self, sentences: list[dict], title: str = ""):
        self.sentences = [s for s in sentences if norm(s.get("ko", ""))]
        self.keys = [norm(s["ko"]) for s in self.sentences]
        self.title = title
        self.pos = 0             # next sentence expected
        self.shown: set[int] = set()
        self.stats = {"match": 0, "fragment": 0, "repeat": 0, "none": 0}

    @classmethod
    def load(cls, path: Path) -> "ScriptFollower":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data.get("sentences", []), data.get("title", ""))

    def _candidates(self, lo: int, hi: int):
        lo, hi = max(0, lo), min(len(self.keys), hi)
        for i in range(lo, hi):
            yield i, 1, self.keys[i]
            if i + 1 < len(self.keys):
                yield i, 2, self.keys[i] + self.keys[i + 1]

    def _best(self, said: str, lo: int, hi: int):
        best = None
        for i, n, key in self._candidates(lo, hi):
            p, r = overlap(said, key)
            # Prefer the reading that explains most of what was said, then the nearest one
            score = (round(p, 2), round(r, 2), -abs(i - self.pos))
            if best is None or score > best[0]:
                best = (score, i, n, p, r)
        return best

    def match(self, sentence: str) -> Match:
        said = norm(sentence)
        if not said or not self.keys:
            self.stats["none"] += 1
            return Match("none")
        best = self._best(said, self.pos - WINDOW_BACK, self.pos + WINDOW_AHEAD)
        kind = None
        if best:
            _, i, n, p, r = best
            if p >= FULL_PRECISION and r >= FULL_RECALL:
                kind = "match"
            elif p >= FRAGMENT_PRECISION and len(said) >= FRAGMENT_MIN_CHARS and n == 1:
                kind = "fragment"
        if kind is None:
            # The preacher may have skipped ahead or gone back: accept only a very clear match
            far = self._best(said, 0, len(self.keys))
            if far:
                _, i, n, p, r = far
                if p >= JUMP_PRECISION and r >= JUMP_RECALL and len(said) >= JUMP_MIN_CHARS:
                    kind = "match"
        if kind is None:
            self.stats["none"] += 1
            return Match("none", precision=best[3] if best else 0.0, recall=best[4] if best else 0.0)
        covered = set(range(i, i + n))
        if kind == "match" and covered <= self.shown:
            kind = "repeat"
        if kind == "match":
            self.shown |= covered  # fragments are captioned piece by piece, so not counted as shown
        self.pos = max(self.pos, i + n)
        self.stats[kind] += 1
        return Match(kind, i, n, p, r)

    def hint(self, m: Match, langs: list[str]) -> str:
        """The manuscript sentence and its prepared translation, for the live translator."""
        parts = self.sentences[m.index:m.index + m.count]
        lines = ["Manuscript Korean: " + " ".join(s["ko"] for s in parts)]
        for c in langs:
            texts = [s.get(c, "").strip() for s in parts]
            if all(texts):
                lines.append(f'Prepared "{c}": ' + " ".join(texts))
        return "\n".join(lines)

    def translation(self, m: Match, langs: list[str]):
        """Prepared captions for a match, or None when the script lacks one of the languages."""
        parts = self.sentences[m.index:m.index + m.count]
        out = {}
        for c in langs:
            texts = [s.get(c, "").strip() for s in parts]
            if not all(texts):
                return None
            out[c] = " ".join(texts)
        return out
