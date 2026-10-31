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

Congregation phones (--lan-port, e.g. 8000): http://<this Mac>:<port>/ serves web/listener.html,
which receives captions over ws://<this Mac>:<port>/ws and reads them aloud with the phone's own
voice. A phone only says which language it listens to ({"type": "listen", "lang": "th"}); the
engine is then asked to translate into that language too, even if the projector does not show
it. Phones cannot send captions. /qr shows a QR code of the address for the projector.
"""

import argparse
import asyncio
import json
import logging

from pathlib import Path

import websockets
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

log = logging.getLogger("caption-hub")
HERE = Path(__file__).resolve().parent
LISTENER_PAGE = HERE.parent / "web" / "listener.html"
LANG_ORDER = ["en", "zh", "th", "vi"]  # languages the engine can translate into

clients = set()     # this Mac: the engine and the worship player windows
listeners = {}      # congregation phones -> the language each one listens to
control = {}        # latest translate on/off, slide and projector languages from the worship player
last_control = ""   # last control message sent to the engine, to skip repeats

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
    targets = (clients | set(listeners)) - {sender}
    if targets:
        websockets.broadcast(targets, message)


def engine_langs() -> list:
    """Projector languages plus every language a phone is listening to."""
    want = set(control.get("screen_langs") or ["en"]) | {l for l in listeners.values() if l}
    return [c for c in LANG_ORDER if c in want] or ["en"]


def control_message() -> str:
    msg = {"type": "control", "slide": control.get("slide"), "langs": engine_langs()}
    if "translate" in control:
        msg["translate"] = control["translate"]
    return json.dumps(msg, ensure_ascii=False)


async def send_control(sender=None) -> None:
    """Tells the engine (and the player) the current state, if it changed."""
    global last_control
    msg = control_message()
    if msg == last_control:
        return
    last_control = msg
    targets = clients - {sender}
    if targets:
        websockets.broadcast(targets, msg)


async def handler(ws) -> None:
    clients.add(ws)
    log.info("client connected (%d total)", len(clients))
    try:
        if control or listeners:
            await ws.send(control_message())
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            kind = msg.get("type")
            if kind in ("caption", "clear"):
                await broadcast(json.dumps(msg, ensure_ascii=False), sender=ws)
            elif kind == "control":
                before = control_message()
                if isinstance(msg.get("translate"), bool):
                    control["translate"] = msg["translate"]
                if isinstance(msg.get("langs"), list):
                    control["screen_langs"] = msg["langs"]
                control["slide"] = msg.get("slide")
                if json.loads(before) | {"slide": None} == json.loads(control_message()) | {"slide": None}:
                    continue
                log.info("control %s (slide %s)", {k: v for k, v in json.loads(control_message()).items()
                                                   if k in ("translate", "langs")}, msg.get("slide"))
                await send_control(sender=ws)
    except websockets.ConnectionClosed:
        pass  # a screen or the engine went away without saying goodbye; not an error
    finally:
        clients.discard(ws)
        log.info("client disconnected (%d total)", len(clients))


# ---------------------------------------------------------------- congregation phones

def listener_counts() -> str:
    counts = {}
    for l in listeners.values():
        counts[l or "?"] = counts.get(l or "?", 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "없음"


async def listener_handler(ws) -> None:
    listeners[ws] = None
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "listen":
                lang = msg.get("lang")
                listeners[ws] = lang if lang in LANG_ORDER or lang == "ko" else None
                log.info("휴대폰 청취자: %s", listener_counts())
                await send_control()
    except websockets.ConnectionClosed:
        pass
    finally:
        listeners.pop(ws, None)
        log.info("휴대폰 청취자: %s", listener_counts())
        await send_control()


def page(body: bytes, ctype: str = "text/html; charset=utf-8") -> Response:
    return Response(200, "OK", Headers([("Content-Type", ctype), ("Content-Length", str(len(body))),
                                        ("Cache-Control", "no-store")]), body)


def qr_page(url: str) -> bytes:
    import segno
    svg = segno.make(url, error="m").svg_inline(scale=12, dark="#000", light="#fff")
    return f"""<!doctype html><meta charset="utf-8"><title>통역 듣기 QR</title>
<body style="margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
background:#fff;font:28px -apple-system,'Apple SD Gothic Neo',sans-serif;gap:24px;text-align:center">
<div style="font-size:40px;font-weight:700">실시간 통역 · Live interpretation</div>
{svg}
<div>{url}</div>
<div style="font-size:22px;color:#555">교회 Wi-Fi에 연결한 뒤 휴대폰 카메라로 찍으세요 · Connect to the church Wi-Fi, then scan</div>
</body>""".encode("utf-8")


def make_router(url: str):
    def route(connection, request):
        if request.path.startswith("/ws"):
            return None
        if request.path.split("?")[0] in ("/", "/index.html"):
            return page(LISTENER_PAGE.read_bytes())
        if request.path == "/qr":
            return page(qr_page(url))
        if request.path == "/ca":
            # This Mac's own certificate authority, for the preacher's phone (phone_mic.py)
            from phone_mic import ensure_ca
            ca_file, _ = ensure_ca()
            resp = page(ca_file.read_bytes(), "application/x-x509-ca-cert")
            resp.headers["Content-Disposition"] = 'attachment; filename="worship-mac.crt"'
            return resp
        return connection.respond(404, "not found\n")
    return route


async def demo_loop() -> None:
    """Five captions about 4 s apart, then 12 s of silence so the band's auto-hide is visible.
    Shows the languages chosen on the presenter screen (English until one is chosen)."""
    while True:
        for sample in DEMO:
            langs = engine_langs()
            lines = [{"lang": c, "text": sample[c]} for c in langs if c in sample]
            msg = {"type": "caption", "lines": lines}
            await broadcast(json.dumps(msg, ensure_ascii=False))
            await asyncio.sleep(4)
        await asyncio.sleep(12)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true", help="play sample captions on a loop")
    parser.add_argument("--lan-port", type=int, default=0,
                        help="also serve the congregation phone page on this port over Wi-Fi (e.g. 8000)")
    args = parser.parse_args()

    # The engine and the slideshow are on this Mac: their port stays on localhost.
    async with serve(handler, "localhost", args.port):
        log.info("caption hub listening on ws://localhost:%d%s", args.port, " (demo)" if args.demo else "")
        if args.lan_port:
            from phone_mic import lan_ip
            url = f"http://{lan_ip()}:{args.lan_port}/"
            await serve(listener_handler, "0.0.0.0", args.lan_port, process_request=make_router(url))
            log.info("성도 휴대폰 통역 페이지: %s   (QR 화면: %sqr)", url, url)
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
