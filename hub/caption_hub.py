"""Caption hub: broadcasts live caption lines to the slideshow caption band.

Runs on the worship Mac. The IeumOffice slideshow (with the CaptionBar add-on) connects to
ws://localhost:8765 and shows whatever this hub broadcasts.

Usage:
    python3 caption_hub.py            # relay only: rebroadcasts captions sent by other clients
    python3 caption_hub.py --demo     # also plays sample English/Thai captions on a loop

Any client may send {"type": "caption", "lines": [...]} or {"type": "clear"}; the hub forwards
it to every connected client. The translation engine (Gemini/OpenAI) is one such client.

The worship player sends {"type": "control", "translate": true|false, "slide": n} when a slide's
notes switch translation on or off; the hub forwards it to the engine and remembers the last
one, so an engine started later still learns the current state.
"""

import argparse
import asyncio
import json
import logging

import websockets

log = logging.getLogger("caption-hub")
clients = set()
last_control = None  # latest translate on/off from the worship player

# Sample captions from the first Gemini Live Translate test (docs/06). The Thai lines are
# machine translations and have not been checked by a Thai speaker.
DEMO = [
    ("Today we are in Genesis chapter 12, verse 1.",
     "วันนี้เราจะมาดูปฐมกาลบทที่ 12 ข้อที่ 1 ด้วยกัน"),
    ("The Lord said to Abram, “Go from your country, your people, and your father’s household "
     "to the land I will show you.”",
     "พระยาห์เวห์ตรัสกับอับรามว่า เจ้าจงออกจากบ้านเกิดเมืองนอนและจากครอบครัวของเจ้า "
     "ไปยังดินแดนที่เราจะแสดงให้เจ้าเห็น"),
    ("God is a covenant-making God.",
     "พระเจ้าทรงเป็นผู้ทรงทำพันธสัญญา"),
    ("We are justified only by faith.",
     "เราได้รับการนับว่าเป็นผู้ชอบธรรมก็เพราะความเชื่อเท่านั้น"),
    ("The Heidelberg Catechism, Question 1, asks: What is your only comfort in life and in death?",
     "คำสอนไฮเดลเบิร์กข้อที่ 1 ถามว่า ความปลอบใจเดียวของท่านทั้งในชีวิตและในความตายคืออะไร"),
]


async def broadcast(message: str, sender=None) -> None:
    targets = clients - {sender} if sender else clients
    if targets:
        websockets.broadcast(targets, message)


async def handler(ws) -> None:
    global last_control
    clients.add(ws)
    log.info("client connected (%d total)", len(clients))
    try:
        if last_control:
            await ws.send(last_control)
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") in ("caption", "clear", "control"):
                out = json.dumps(msg, ensure_ascii=False)
                if msg["type"] == "control":
                    if last_control and json.loads(last_control).get("translate") == msg.get("translate"):
                        continue
                    last_control = out
                    log.info("translation %s (slide %s)", "on" if msg.get("translate") else "off", msg.get("slide"))
                await broadcast(out, sender=ws)
    except websockets.ConnectionClosed:
        pass  # a screen or the engine went away without saying goodbye; not an error
    finally:
        clients.discard(ws)
        log.info("client disconnected (%d total)", len(clients))


async def demo_loop() -> None:
    """Five captions about 4 s apart, then 12 s of silence so the band's auto-hide is visible."""
    while True:
        for en, th in DEMO:
            msg = {"type": "caption", "lines": [{"lang": "en", "text": en}, {"lang": "th", "text": th}]}
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
