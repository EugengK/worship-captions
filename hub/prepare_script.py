"""Turns a sermon manuscript into a script file for live_engine.py --script.

    python3 prepare_script.py 설교원고.docx -o sermon.json            # split only (Korean)
    python3 prepare_script.py 설교원고.txt -o sermon.json --translate en,th   # also translate with Gemini

Reads .txt, .md or .docx. Splits into sentences the way they are preached; headings, Bible
references on their own line and very short lines are kept too (they rarely match and cost
nothing). Translations can also be filled in by hand or by Claude, as long as each sentence
keeps its "ko" text.
"""

import argparse
import json
import re
import zipfile
from pathlib import Path

# End of a sentence: its punctuation, any closing quote or bracket, then a space
SENTENCE_END = re.compile(r"([.?!。？！…]+[\"'”’)\]]*)\s+")


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        paras = []
        for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
            text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
            paras.append(text)
        import html
        return "\n".join(html.unescape(t) for t in paras)
    return path.read_text(encoding="utf-8")


def split_sentences(text: str) -> list[str]:
    out = []
    for para in text.splitlines():
        para = re.sub(r"^[#>*\-\s]+", "", para).strip()  # markdown headings, bullets
        if not para:
            continue
        out.extend(s.strip() for s in SENTENCE_END.sub(r"\1\n", para).split("\n") if s.strip())
    return out


def translate_all(sentences: list[str], langs: list[str], model: str, notes: str) -> list[dict]:
    """Batch translation with Gemini, 30 sentences per request, with the neighbours as context."""
    import os

    from google import genai
    from google.genai import types

    from live_engine import LANG_NAMES

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    rows = [{"ko": s} for s in sentences]
    for start in range(0, len(sentences), 30):
        batch = sentences[start:start + 30]
        prompt = "\n".join([
            "Translate each numbered Korean sentence from a church sermon manuscript for projector captions.",
            "Return a JSON list with one object per sentence, in order, each with keys: "
            + ", ".join(f'"{c}" ({LANG_NAMES.get(c, c)})' for c in langs) + ".",
            "Translate faithfully and naturally, one sentence for one sentence. For Bible quotations translate "
            "directly from the Korean; do not reproduce a published Bible translation.",
            ("Notes: " + notes) if notes else "",
            "Sentences:",
            *[f"{i + 1}. {s}" for i, s in enumerate(batch)],
        ])
        resp = client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2,
                                               thinking_config=types.ThinkingConfig(thinking_budget=0)))
        data = json.loads(resp.text)
        if len(data) != len(batch):
            raise RuntimeError(f"expected {len(batch)} translations, got {len(data)} (sentences {start + 1}~)")
        for row, tr in zip(rows[start:start + 30], data):
            row.update({c: str(tr.get(c, "")).strip() for c in langs})
        print(f"번역 {min(start + 30, len(sentences))}/{len(sentences)}")
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("manuscript")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--translate", default="", help="languages to translate into with Gemini, e.g. en,th")
    p.add_argument("--model", default="gemini-3.5-flash")
    p.add_argument("--notes", default="")
    args = p.parse_args()

    src = Path(args.manuscript)
    sentences = split_sentences(read_text(src))
    langs = [c.strip() for c in args.translate.split(",") if c.strip()]
    rows = translate_all(sentences, langs, args.model, args.notes) if langs else [{"ko": s} for s in sentences]
    Path(args.out).write_text(json.dumps({"title": args.title or src.stem, "sentences": rows},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)}문장 → {args.out}")


if __name__ == "__main__":
    main()
