# ATK AI Documentary Studio — low-cost roadmap

## Product decision
Default: **Original Documentary**. YouTube URL is a reference, never an unconditional download/republish input. User supplies their own or commercially licensed media for rendering.

## MVP already running
- Browser login via Render ATK_PASSWORD (Basic Auth)
- Myanmar male speech preview via Edge TTS (availability/commercial usage terms need review)
- Multiple uploaded clips, equal-time scene sequencing, optional BGM
- Separate SRT download, 1080p MP4 encoding
- Trial limit: 2 minutes, 12 clips, 70MB each; no semantic AI scene selection

## Phase 1: YouTube Reference (next)
1. URL field with validation for youtube.com and youtu.be and explicit 'reference only' labeling.
2. Fetch public video metadata via supported provider; transcript only where authorized/available. Do not assume all links provide captions.
3. Let user paste their own notes/transcript when automated retrieval is blocked.
4. Generate an *original* Burmese outline and draft from supplied notes; fact-check and require user approval before voice generation. LLM integration optional and requires separately configured key.
5. Keep all references and license/attribution notes; never auto-reuse original footage without documented permission.

## Phase 2: usable editor
- Scene list with per-scene script, media asset, in/out and narration durations
- SRT timing based on TTS speech marks or alignment, not equal line splitting
- Burn-in captions with Myanmar Unicode font; optional separate SRT
- User-supplied licensed BGM, ducking under voice
- 1080p export with progress/jobs and retries

## Phase 3: production
- Durable storage, queued FFmpeg workers, upload limits, cleanup, cost caps, no public sharing by default
- Test 5 minutes, 15 minutes, then 60 minutes; Render Free is not a reliable one-hour render target
- Authentication improvements and rate limiting, secure keys
- Verify TTS licensing, reliability, copyright/monetization policies

## Acceptance tests
- Browser login with secret
- 10-second Burmese male voice audible
- Two licensed 10-second clips + script -> 1080p MP4 with synced voice
- BGM quiet enough, downloadable SRT
- Clear error for unsupported YouTube link or missing transcript
- No change to existing ATKFLOW main branch or atk-video-import service

## Important
Current code does NOT accept YouTube URLs, create original scripts, burn in captions, or semantically analyze scenes. Do not present these as deployed features.
