"""Private, single-purpose TikTok importer for ATK's authenticated Site route."""

import hmac
import json
import os
import re
import sys
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlsplit

MAX_BYTES = 80 * 1024 * 1024
SLOTS = BoundedSemaphore(2)


def valid_url(value):
    if not isinstance(value, str) or len(value) > 1000:
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and not parsed.username and not parsed.password
                and parsed.hostname is not None
                and (parsed.hostname == "tiktok.com" or parsed.hostname.endswith(".tiktok.com")))
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, message):
        body = json.dumps({"error": message}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            return self.reply(404, "Not found")
        return self.reply(200, "ok")

    def do_POST(self):
        if self.path != "/import":
            return self.reply(404, "Not found")
        secret = os.environ.get("ATK_IMPORT_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        if not secret or not hmac.compare_digest(supplied, "Bearer " + secret):
            return self.reply(401, "Unauthorized")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, "Invalid request")
        if length < 1 or length > 2048:
            return self.reply(413, "Invalid request size")
        try:
            url = json.loads(self.rfile.read(length))["url"]
        except (ValueError, KeyError, TypeError):
            return self.reply(400, "Invalid JSON")
        if not valid_url(url):
            return self.reply(400, "TikTok HTTPS link required")
        if not SLOTS.acquire(blocking=False):
            return self.reply(503, "Importer busy; retry shortly")
        try:
            with tempfile.TemporaryDirectory(prefix="atk-import-") as directory:
                output = str(Path(directory) / "video.%(ext)s")
                command = ["python", "-m", "yt_dlp", "--ignore-config", "--no-playlist",
                           "--no-progress", "--max-filesize", "80M", "--format",
                           "best[ext=mp4]/best", "--merge-output-format", "mp4",
                           "--output", output, "--", url]
                try:
                    result = subprocess.run(command, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.PIPE, text=True, timeout=150, check=False)
                except subprocess.TimeoutExpired:
                    return self.reply(504, "TikTok download timed out")
                if result.returncode != 0:
                    diagnostic = re.sub(r"https?://[^\s]+", "[URL]", result.stderr or "")
                    diagnostic = diagnostic.replace(secret, "[REDACTED]")[-4000:]
                    print("ATK_IMPORT_FAILED: " + diagnostic, file=sys.stderr, flush=True)
                    return self.reply(422, "TikTok video unavailable for import")
                videos = list(Path(directory).glob("video.mp4"))
                if not videos:
                    return self.reply(422, "TikTok did not provide an MP4")
                video = videos[0]
                size = video.stat().st_size
                if not 0 < size <= MAX_BYTES:
                    return self.reply(413, "Video must be under 80 MB")
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "private, no-store")
                self.end_headers()
                with video.open("rb") as stream:
                    while chunk := stream.read(256 * 1024):
                        self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            SLOTS.release()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
