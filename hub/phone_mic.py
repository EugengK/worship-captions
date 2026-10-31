"""Phone microphone: a phone browser streams its microphone to this Mac over Wi-Fi.

For Macs that cannot use an iPhone as a microphone directly (Continuity needs macOS 13+), e.g.
the church MacBook Air on macOS 11. The engine serves a small page over HTTPS; the preacher's
phone opens it, taps start, and sends 16 kHz 16-bit mono PCM back over a secure websocket.

Phone browsers only allow the microphone on https pages, so a self-signed certificate is made
for this Mac's name and Wi-Fi address (hub/certs, not committed). The phone shows a warning the
first time, which has to be accepted once.

    python3 live_engine.py --phone          # engine with the phone as microphone
    python3 phone_mic.py                    # page and level meter only, no Gemini (for testing)
"""

import asyncio
import datetime as dt
import ipaddress
import json
import logging
import socket
import ssl
import time
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

log = logging.getLogger("live-engine")

HERE = Path(__file__).resolve().parent
PAGE = HERE / "phone_mic.html"
CERT_DIR = HERE / "certs"
DEFAULT_PORT = 8443


def lan_ip() -> str:
    """This Mac's address on the Wi-Fi (no packet is sent; the OS just picks the route)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def local_name() -> str:
    """Bonjour name phones can use instead of the address, e.g. Hobarts-Air.local."""
    name = socket.gethostname().split(".")[0]
    return f"{name}.local"


CA_NAME = "Hobart Korean Church worship Mac (local only)"
# The CA may only vouch for local addresses: if its key ever leaked, it could not impersonate
# real websites on a phone that trusts it.
LOCAL_NETWORKS = ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "127.0.0.0/8"]


def _x509():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    return x509, hashes, serialization, ec, NameOID


def _write_key(path: Path, key) -> None:
    _, _, serialization, _, _ = _x509()
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    path.chmod(0o600)


def ensure_ca() -> tuple[Path, Path]:
    """This Mac's own certificate authority. Installed once on the preacher's phone, it makes the
    microphone page trusted (no warning) even when the Wi-Fi address changes."""
    x509, hashes, serialization, ec, NameOID = _x509()
    CERT_DIR.mkdir(exist_ok=True)
    ca_file, ca_key = CERT_DIR / "ca.crt", CERT_DIR / "ca.key"
    if ca_file.exists() and ca_key.exists():
        return ca_file, ca_key
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, CA_NAME)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                     crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.NameConstraints(
            permitted_subtrees=[x509.DNSName("local"), x509.DNSName("localhost")]
            + [x509.IPAddress(ipaddress.ip_network(n)) for n in LOCAL_NETWORKS],
            excluded_subtrees=None), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_key(ca_key, key)
    ca_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return ca_file, ca_key


def ensure_cert(ip: str, name: str) -> tuple[Path, Path]:
    """Certificate for this Mac's page, signed by its own CA; remade when the Wi-Fi address changes."""
    x509, hashes, serialization, ec, NameOID = _x509()
    ca_file, ca_key_file = ensure_ca()
    # The CA may only vouch for local addresses (see LOCAL_NETWORKS); any other address is left out
    local = any(ipaddress.ip_address(ip) in ipaddress.ip_network(n) for n in LOCAL_NETWORKS)
    ca = x509.load_pem_x509_certificate(ca_file.read_bytes())
    cert_file, key_file = CERT_DIR / "phone-mic.crt", CERT_DIR / "phone-mic.key"
    if cert_file.exists() and key_file.exists():
        cert = x509.load_pem_x509_certificate(cert_file.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        still_valid = cert.not_valid_after_utc > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)
        if still_valid and cert.issuer == ca.subject \
                and (not local or ipaddress.ip_address(ip) in san.get_values_for_type(x509.IPAddress)) \
                and name in san.get_values_for_type(x509.DNSName):
            return cert_file, key_file

    ca_key = serialization.load_pem_private_key(ca_key_file.read_bytes(), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=800))  # Apple refuses server certificates over 825 days
        .add_extension(x509.SubjectAlternativeName(
            [x509.DNSName(name), x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            + ([x509.IPAddress(ipaddress.ip_address(ip))] if local else [])), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(key_file, key)
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_file, key_file


class PhoneMic:
    """Serves the phone page and puts the phone's audio chunks on the engine's queue.

    One phone at a time: a new connection (for example after the page is reloaded) replaces
    the old one, so two streams are never mixed.
    """

    def __init__(self, port: int = DEFAULT_PORT, status=lambda: {}):
        self.port, self.status = port, status
        self.active = None

    def _page(self, connection, request):
        if request.path.startswith("/ws"):
            return None  # websocket upgrade
        if request.path in ("/", "/index.html"):
            body = PAGE.read_bytes()
            headers = Headers([("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body))),
                               ("Cache-Control", "no-store")])
            return Response(200, "OK", headers, body)
        return connection.respond(404, "not found\n")

    async def run(self, queue: asyncio.Queue, meter=None) -> None:
        ip, name = lan_ip(), local_name()
        cert, key = ensure_cert(ip, name)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)

        async def handler(ws):
            if self.active is not None:
                await self.active.close(1000, "replaced by a newer connection")
            self.active = ws
            log.info("휴대폰 마이크 연결됨 (%s)", ws.remote_address[0] if ws.remote_address else "?")

            async def report():
                while True:
                    await ws.send(json.dumps(self.status()))
                    await asyncio.sleep(2)

            reporter = asyncio.create_task(report())
            try:
                async for msg in ws:
                    if isinstance(msg, bytes) and msg and len(msg) % 2 == 0:
                        queue.put_nowait(msg)
                        if meter:
                            meter.feed(msg, time.monotonic())
            except ConnectionClosed:
                pass
            finally:
                reporter.cancel()
                if self.active is ws:
                    self.active = None
                    log.warning("휴대폰 마이크 연결이 끊겼습니다. 휴대폰 화면을 켜고 페이지에서 다시 '시작'을 누르세요.")

        async with serve(handler, "0.0.0.0", self.port, ssl=ctx, process_request=self._page, max_size=1 << 20):
            log.info("휴대폰으로 이 주소를 여세요 (같은 Wi-Fi): https://%s:%d   또는  https://%s:%d",
                     ip, self.port, name, self.port)
            log.info("경고('비공개 연결이 아닙니다')가 뜨면: '자세히 보기' → '이 웹 사이트 방문'. "
                     "아예 안 뜨게 하려면 아이폰에서 http://%s:8000/ca 를 열어 인증서를 한 번 설치하세요 "
                     "(맥에서 예배 모드가 켜져 있을 때).", ip)
            await asyncio.Future()


if __name__ == "__main__":
    import argparse

    from live_engine import MicMeter

    p = argparse.ArgumentParser(description="Phone microphone page and level meter only (no translation).")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("websockets").setLevel(logging.WARNING)

    async def main():
        q = asyncio.Queue()

        async def drain():
            while True:
                await q.get()

        asyncio.create_task(drain())
        await PhoneMic(args.port, status=lambda: {"translating": True, "test": True}).run(q, MicMeter())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
