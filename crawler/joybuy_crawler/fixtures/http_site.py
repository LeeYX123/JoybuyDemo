"""A local fixture HTTP server for crawler base verification.

Only ever bound to localhost with an ephemeral port and used from tests —
the crawler never touches the real Joybuy site in this work package.

Routes:
- ``/ok``                 -> 200 static page
- ``/flaky?fails=N``      -> 429 with ``Retry-After: 1`` for the first N hits, then 200
- ``/boom?fails=N``       -> 500 for the first N hits, then 200
- ``/echo``               -> 200 JSON of the received request headers
- ``/js``                 -> 200 page whose body text is set by JavaScript
- ``/image``              -> 200 small PNG with EXIF metadata
- ``/video``              -> 200 tiny MP4 (written by tests via ``write_video_payload``)
- ``/missing-media``      -> 404
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def make_exif_png(width=64, height=48) -> bytes:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (width, height), (12, 200, 90))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_exif_jpeg(width=64, height=48) -> bytes:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (width, height), (200, 90, 12))
    exif = image.getexif()
    exif[0x010F] = "FixtureCam"  # Make
    exif[0x0110] = "Model X100"  # Model
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def write_video_payload(path, *, seconds: float = 0.5) -> None:
    """Generate a tiny test MP4 with FFmpeg (skipped in environments without it)."""

    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is not available")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={seconds}:size=64x64:rate=5",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        check=True,
    )


# Registered by tests: route -> bytes provider.
_MEDIA_ROUTES: dict[str, bytes] = {}
_MEDIA_MIMES: dict[str, str] = {}


def register_media_route(path: str, payload: bytes, *, mime_type: str):
    _MEDIA_ROUTES[path] = payload
    _MEDIA_MIMES[path] = mime_type


def unregister_media_route(path: str):
    _MEDIA_ROUTES.pop(path, None)
    _MEDIA_MIMES.pop(path, None)


JS_PAGE = """<!DOCTYPE html>
<html><head><title>JS fixture</title></head>
<body><div id="content">empty</div>
<script>document.getElementById('content').textContent = 'rendered-by-chromium';</script>
</body></html>"""


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "JoybuyFixture/1.0"

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        return  # keep test output clean

    def _send(self, status: int, body: bytes, headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        route = parsed.path
        counter: dict = self.server.hit_counts  # type: ignore[attr-defined]

        if route == "/ok":
            self._send(200, b"<html><body>static-ok</body></html>")
        elif route == "/flaky":
            fails = int(query.get("fails", "2"))
            counter[route] = counter.get(route, 0) + 1
            if counter[route] <= fails:
                self._send(429, b"slow down", headers={"Retry-After": "1"})
            else:
                self._send(200, b"<html><body>flaky-ok</body></html>")
        elif route == "/boom":
            fails = int(query.get("fails", "2"))
            counter[route] = counter.get(route, 0) + 1
            if counter[route] <= fails:
                self._send(500, b"boom")
            else:
                self._send(200, b"<html><body>boom-ok</body></html>")
        elif route == "/echo":
            payload = json.dumps(
                {"headers": {key: value for key, value in self.headers.items()}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif route == "/js":
            self._send(200, JS_PAGE.encode())
        elif route in _MEDIA_ROUTES:
            payload = _MEDIA_ROUTES[route]
            mime = _MEDIA_MIMES.get(route, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif route == "/missing-media":
            self._send(404, b"no such media")
        else:
            self._send(404, b"not found")


class CrawlerFixtureServer:
    """Threaded localhost server; ``start`` returns the base URL."""

    def __init__(self):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self._server.hit_counts = {}
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def reset_counters(self):
        self._server.hit_counts.clear()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
