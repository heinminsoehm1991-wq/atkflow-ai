"""Private, single-purpose TikTok importer for ATK's authenticated Site route."""

import hmac
import base64
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
                and (parsed.hostname in ("tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be")))
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
        if self.path not in ("/import", "/tts"):
            return self.reply(404, "Not found")
        secret = os.environ.get("ATK_IMPORT_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        secondary = os.environ.get("ATK_RECAP_IMPORT_TOKEN", "")
        if not any(t and hmac.compare_digest(supplied, "Bearer " + t) for t in (secret, secondary)):
            return self.reply(401, "Unauthorized")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, "Invalid request")
        if length < 1 or length > 90000:
            return self.reply(413, "Invalid request size")
        try:
            payload = json.loads(self.rfile.read(length))
            if self.path == "/tts":
                return self.speech(payload)
            url = payload["url"]
        except (ValueError, KeyError, TypeError):
            return self.reply(400, "Invalid JSON")
        if not valid_url(url):
            return self.reply(400, "YouTube or TikTok HTTPS link required")
        if not SLOTS.acquire(blocking=False):
            return self.reply(503, "Importer busy; retry shortly")
        try:
            with tempfile.TemporaryDirectory(prefix="atk-import-") as directory:
                output = str(Path(directory) / "video.%(ext)s")
                command = ["python", "-m", "yt_dlp", "--ignore-config", "--no-playlist",
                           "--no-progress", "--match-filter", "duration <= 600", "--max-filesize", "80M", "--format",
                           "best[ext=mp4]/best", "--merge-output-format", "mp4",
                           "--output", output, "--", url]
                try:
                    result = subprocess.run(command, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.PIPE, text=True, timeout=150, check=False)
                except subprocess.TimeoutExpired:
                    return self.reply(504, "Video download timed out")
                if result.returncode != 0:
                    diagnostic = re.sub(r"https?://[^\s]+", "[URL]", result.stderr or "")
                    diagnostic = diagnostic.replace(secret, "[REDACTED]").replace(secondary, "[REDACTED]")[-4000:]
                    print("ATK_IMPORT_FAILED: " + diagnostic, file=sys.stderr, flush=True)
                    return self.reply(422, ("The video host requires human verification. Upload the video file directly." if "not a bot" in (result.stderr or "").lower() else "Video unavailable for import"))
                videos = list(Path(directory).glob("video.mp4"))
                if not videos:
                    return self.reply(422, "The video host did not provide an MP4")
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


    def speech(self, payload):
        text = payload.get("text")
        voice = payload.get("voice", "my-MM-ThihaNeural")
        if not isinstance(voice, str) or not re.fullmatch(r"(?:my-MM-(?:Thiha|Nilar)|th-TH-(?:Niwat|Premwadee)|en-(?:US|AU|CA|HK|IN|IE|KE|NZ|NG|PH|SG|ZA|TZ|GB)-[A-Za-z]+)Neural", voice):
            return self.reply(400, "Choose a supported Myanmar, Thai, or English voice")
        if not isinstance(text, str) or not text.strip() or len(text) > 20000:
            return self.reply(400, "Enter 1–20000 characters")
        try:
            rate = int(payload.get("rate", 0))
            pitch = int(payload.get("pitch", 0))
            if not -100 <= pitch <= 100:
                raise ValueError()
            if not -50 <= rate <= 100:
                raise ValueError()
        except (ValueError, TypeError):
            return self.reply(400, "Invalid speech rate")
        if not SLOTS.acquire(blocking=False):
            return self.reply(503, "Voice service busy; retry shortly")
        try:
            with tempfile.TemporaryDirectory(prefix="atk-voice-") as directory:
                target = str(Path(directory) / "voice.mp3")
                metadata = str(Path(directory) / "words.jsonl")
                if payload.get("timed"):
                    script = (
                        "import asyncio,json,sys,edge_tts;"
                        "p=json.load(sys.stdin);"
                        "asyncio.run(edge_tts.Communicate(p['text'],p['voice'],"
                        "rate=f\"{p['rate']:+d}%\",pitch=f\"{p['pitch']:+d}Hz\","
                        "boundary='WordBoundary').save(sys.argv[1],sys.argv[2]))"
                    )
                    result = subprocess.run(
                        [sys.executable, "-c", script, target, metadata],
                        input=json.dumps({"text": text, "voice": voice, "rate": rate, "pitch": pitch}).encode(),
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=150)
                else:
                    result = subprocess.run(
                        [sys.executable, "-m", "edge_tts", "--voice", voice, f"--rate={rate:+d}%", f"--pitch={pitch:+d}Hz",
                         "--text", text, "--write-media", target],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=150)
                if result.returncode or not Path(target).is_file():
                    return self.reply(502, "Microsoft voice service could not generate audio")
                data = Path(target).read_bytes()
                content_type = "audio/mpeg"
                if payload.get("timed"):
                    words = []
                    for line in Path(metadata).read_text(encoding="utf-8").splitlines():
                        item = json.loads(line)
                        if item.get("type") == "WordBoundary":
                            words.append({"text": item["text"], "start": item["offset"] / 10000000,
                                          "end": (item["offset"] + item["duration"]) / 10000000})
                    if not words:
                        return self.reply(502, "Voice provider returned no word timings")
                    data = json.dumps({"audio": base64.b64encode(data).decode(), "words": words,
                                       "voice": voice, "rate": rate, "pitch": pitch}).encode()
                    content_type = "application/json"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "private, no-store")
                self.end_headers()
                self.wfile.write(data)
        except subprocess.TimeoutExpired:
            self.reply(504, "Voice generation timed out")
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            SLOTS.release()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
