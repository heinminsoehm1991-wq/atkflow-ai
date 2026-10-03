# ATK English Studio processing server

This repository now contains the genuine processing service required by the
hosted editor. The Sites frontend alone cannot run Python, native FFmpeg or
MediaPipe. Deploy this container to Render or a comparable persistent CPU service.
It has **not** been connected to a live provider or deployed until its configuration
and external hosting are supplied.

## Deploy

Build from the repository root using `backend/Dockerfile`. Use Python 3.11 and
the pinned MediaPipe/OpenCV dependencies. `render.yaml` contains a deployment
template; a single instance and a persistent `/data` disk are required. Choose a
service with at least 2 GB RAM for the first video trial, then measure usage.
The repository must be accessible to the host; Sites' Git endpoint is not a public
GitHub repository, so the Render plugin must be checked for its source-deployment
capabilities after connection. No live service or hosting bill has been created.

Required environment:

- `ADMIN_TOKEN`: random string at least 32 characters. Do not publish it.
- `ALLOWED_ORIGINS`: `https://atk-english-studio.wint44954.chatgpt.site`.
- `DATA_DIR`: a persistent private volume, normally `/data`.
- `GEMINI_API_KEY` and `ELEVENLABS_API_KEY`: provider secrets. Alternatively,
  after deploying, enter them in the editor Settings: `/v1/settings` saves them
  server-side in a private file with mode `0600`. Environment values take priority.
- `GEMINI_MODEL` default `gemini-2.5-flash`; configurable if unavailable on account.
- `ELEVENLABS_MODEL` default `eleven_multilingual_v2`.
- `MAX_VIDEO_SECONDS` default `1800` (30 minutes), configurable. No 60-second cap.

Run locally with `python backend/server.py` after installing requirements and
FFmpeg. Production must use an HTTPS reverse proxy; do not expose plain HTTP or
provider secrets to the browser. The backend access token remains only in the
browser session; its URL can be saved as a device preference.

## Real workflow

1. Validate YouTube/TikTok video link and use yt-dlp to retrieve it. No bypass of
   private/login restrictions is implemented. Platforms may refuse a download.
2. Extract 90-second audio chunks, ask Gemini for faithful, concise English
   translation with start/end timestamps, and reject invalid/overlapping cues.
3. Review the generated timed script, or use One Click with the selected voice.
4. Get actual voices from the ElevenLabs account with pagination and gender labels.
5. Generate the selected voice per timed segment. Modestly speed it up when needed
   (at most 1.35× beyond the selected rate), and insert it at its source timestamp.
   Do not truncate intelligible speech. Too-long segments fail with a review request.
6. Build a mono 24 kHz WAV of the full source duration, keeping the silence gaps.
7. Decode the source frames; use MediaPipe person masks when person/background
   color adjustments are requested. Apply whole/person/background/left/right
   controls; encode up to 720 px on the longer side with H.264/AAC and optional ASS
   subtitles. Fonts are mapped to installed Liberation/DejaVu/Noto families.
8. Check final duration before marking successful. Return signed, expiring
   WAV/SRT/ASS/MP4 links, supporting range playback.

Original audio is muted by default; optional volume mixes the entire original
audio back in. This is not dialogue/music source separation. Segmentation is a
selfie/person model; crowded scenes, motion blur and fine hair can need adjustment.
Translation timestamps are AI estimates and should be reviewed for important work.
Changing script during review preserves timestamp boundaries; captions update to
the edited script. Lip sync is not generated.

## Reliability and access

- All settings, jobs and voice routes require the server owner token.
- Provider secrets are excluded from responses, logs and Git.
- Reject unknown URL hosts, arbitrary path access and shell interpolation.
- `X-Request-ID` makes a retried identical job request idempotent.
- One active processor, at most two queued/running jobs.
- Persistent SQLite records progress. Restart marks interrupted jobs failed instead
  of silently making paid API requests again.
- Jobs and outputs remain on the disk until the owner deletes them. Monitor disk
  space and provider quota. This first implementation is single-owner; do not rent
  it to multiple users without per-user auth, quotas and storage isolation.

## Testing

`python -m unittest discover -s backend/tests -v` verifies URL validation,
timestamp bounds, scene audio insertion using mocked provider speech, native
FFmpeg duration, SRT/ASS output, authorization, signed range-download handling and
job-request idempotency. Mocked provider tests do not prove live API behavior.
Run a licensed short video through the actual deployed service after adding keys.
Local JavaScript/HTTP tests do not replace a mobile browser playback test.
