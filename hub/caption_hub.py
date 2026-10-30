"""Caption hub: broadcasts live caption lines to the slideshow caption band.

Runs on the worship Mac. The IeumOffice slideshow (with the CaptionBar add-on) connects to
ws://localhost:8765 and shows whatever this hub broadcasts.

Usage:
    python3 caption_hub.py            # relay only: rebroadcasts captions sent by other clients
    python3 caption_hub.py --demo     # also plays sample English/Thai captions on a loop

Any client may send {"type": "caption", "lines": [...]} or {"type": "clear"}; the hub forwards
it to every connected client. The translation engine (Gemini/OpenAI) is one such client.

The worship player sends {"type": "control", "translate": true|false, "langs": [...], "slide": n}
when a slide's notes switch translation on or off or the caption languages change. The hub keeps
the merged state, forwards it when something changed, and gives it to every client that connects,
so an engine started later still learns the current state.
"""

import argparse
import asyncio
import json
import logging

import websockets

log = logging.getLogger("caption-hub")
clients = set()
control = {}  # latest translate on/off and caption languages from the worship player

# Sample captions in every language the presenter can pick. The English/Thai lines come from the
# first Gemini Live Translate test (docs/06); the Chinese and Vietnamese lines were written by
# Claude. None of them has been checked by a native speaker.
DEMO = [
    {"en": "Today we are in Genesis chapter 12, verse 1.",
     "zh": "今天我们来看创世记第12章第1节。",
     "th": "วันนี้เราจะมาดูปฐมกาลบทที่ 12 ข้อที่ 1 ด้วยกัน",
     "vi": "Hôm nay chúng ta cùng xem Sáng Thế Ký chương 12, câu 1."},
    {"en": "The Lord said to Abram, “Go from your country, your people, and your father’s household "
           "to the land I will show you.”",
     "zh": "耶和华对亚伯兰说：“你要离开本地、本族、父家，往我所要指示你的地去。”",
     "th": "พระยาห์เวห์ตรัสกับอับรามว่า เจ้าจงออกจากบ้านเกิดเมืองนอนและจากครอบครัวของเจ้า "
           "ไปยังดินแดนที่เราจะแสดงให้เจ้าเห็น",
     "vi": "Đức Giê-hô-va phán với Áp-ram: “Hãy rời quê hương, bà con và nhà cha ngươi, "
           "mà đi đến xứ Ta sẽ chỉ cho.”"},
    {"en": "God is a covenant-making God.",
     "zh": "神是立约的神。",
     "th": "พระเจ้าทรงเป็นผู้ทรงทำพันธสัญญา",
     "vi": "Đức Chúa Trời là Đấng lập giao ước."},
    {"en": "We are justified only by faith.",
     "zh": "我们唯独因信称义。",
     "th": "เราได้รับการนับว่าเป็นผู้ชอบธรรมก็เพราะความเชื่อเท่านั้น",
     "vi": "Chúng ta được xưng công chính chỉ bởi đức tin."},
    {"en": "The Heidelberg Catechism, Question 1, asks: What is your only comfort in life and in death?",
     "zh": "海德堡要理问答第1问：你在生与死中唯一的安慰是什么？",
     "th": "คำสอนไฮเดลเบิร์กข้อที่ 1 ถามว่า ความปลอบใจเดียวของท่านทั้งในชีวิตและในความตายคืออะไร",
     "vi": "Giáo Lý Heidelberg, câu hỏi 1: Niềm an ủi duy nhất của bạn trong sự sống và sự chết là gì?"},
]


async def broadcast(message: str, sender=None) -> None:
    targets = clients - {sender} if sender else clients
    if targets:
        websockets.broadcast(targets, message)


async def handler(ws) -> None:
    clients.add(ws)
    log.info("client connected (%d total)", len(clients))
    try:
        if control:
            await ws.send(json.dumps(control, ensure_ascii=False))
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            kind = msg.get("type")
            if kind in ("caption", "clear"):
                await broadcast(json.dumps(msg, ensure_ascii=False), sender=ws)
            elif kind == "control":
                changed = {k: msg[k] for k in ("translate", "langs") if k in msg and control.get(k) != msg[k]}
                if not changed:
                    continue
                control.update(type="control", slide=msg.get("slide"), **changed)
                log.info("control %s (slide %s)", changed, msg.get("slide"))
                await broadcast(json.dumps(control, ensure_ascii=False), sender=ws)
    except websockets.ConnectionClosed:
        pass  # a screen or the engine went away without saying goodbye; not an error
    finally:
        clients.discard(ws)
        log.info("client disconnected (%d total)", len(clients))


async def demo_loop() -> None:
    """Five captions about 4 s apart, then 12 s of silence so the band's auto-hide is visible.
    Shows the languages chosen on the presenter screen (English until one is chosen)."""
    while True:
        for sample in DEMO:
            langs = control.get("langs") or ["en"]
            lines = [{"lang": c, "text": sample[c]} for c in langs if c in sample]
            msg = {"type": "caption", "lines": lines}
            await broadcast(json.dumps(msg, ensure_ascii=False))
            await asyncio.sleep(4)
        await asyncio.sleep(12)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true", help="play sample captions on a loop")
    args = parser.parse_args()

    # Bind to localhost only: the slideshow runs on the same Mac.
    async with websockets.serve(handler, "localhost", args.port):
        log.info("caption hub listening on ws://localhost:%d%s", args.port, " (demo)" if args.demo else "")
        if args.demo:
            await demo_loop()
        else:
            await asyncio.Future()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
