# ATK AI FLOW
Isolated application on branch `atk-ai-flow-workflow`; no changes to other services.

Run `npm ci && npm start` in this directory. Render build: `cd atk-ai-flow && npm install`; start: `cd atk-ai-flow && npm start`.

Required secrets: `FAL_KEY`, `ADMIN_TOKEN`. Credentials remain server-side. The administrator enters ADMIN_TOKEN into the session-only password field. Paid generation requires explicit charge confirmation.

All scenes are numbered and shown individually on one scrollable canvas, with automatic node scaling and a 25–150% zoom slider. No scene pagination.

Connected product → prompt → image → video → final graph. Scene chains can be disconnected and excluded from execution. Scene prompts are an editable local shot template; the local prompt planning button does not call an AI language model. Long prompt plans are split into batches of 60 scenes. Generate AI prompts uses openrouter/router through fal.ai, with google/gemini-2.5-flash by default (PROMPT_MODEL_ID can override it). Image/video generation uses fal.ai. Verified adapters: FLUX Kontext dev/pro, Wan 2.2 5B, Kling 2.6 Pro. Model selectors use supported defaults if old environment IDs are unsupported.

2 minute / 3 minute / custom targets from 1 second up to 60 minutes; maximum 720 scenes. Wan clips are limited to 5 seconds in the planner. Kling accepts 5 or 10 seconds. Final rendering normalizes each clip to its scene duration by trimming or holding its last frame. Output is silent H.264, 24 FPS, 16:9 / 9:16 / 1:1. The FFmpeg executable is installed via ffmpeg-static.

POST /api/render accepts completed video job IDs, not arbitrary URLs. Server verifies target total, serializes renders, and provides authenticated status/download endpoints. Completed outputs expire after 1 hour. Provider job metadata lives in memory and is lost on server restart; browser layouts persist but saved output URLs cannot be used as authenticated jobs after restart. This is a single-admin beta, not durable multi-user hosting.

Tests: `npm test` (schemas, duration validation, actual mixed-resolution MP4 merge).


## Direct Google Gemini provider

The editor defaults to `google/gemini-3.1-flash-image` for images and
`google/veo-3.1-fast-generate-preview` for video. Add `GEMINI_API_KEY` to
the existing **atk-ai-flow-backend** Render service, alongside its existing
`ADMIN_TOKEN`. Keys stay on the server. No fal balance is needed for Google
models. `GEMINI_PROMPT_MODEL` optionally overrides `gemini-2.5-flash`.

Use **Check Gemini key (no generation)** after entering the Admin token.
This checks model visibility, not billing eligibility. Google image and video
generation require appropriate model access and billing. Veo supports 16:9
and 9:16, with 4/6/8-second generated clips. Five-second scenes generate six
seconds and are trimmed by the renderer, so billable duration can exceed
final duration. Veo's audio is removed by the existing silent MP4 renderer.

Google outputs are downloaded server-side and expire after 24 hours or a
server restart. Media links use unguessable job IDs; treat them as private
share links. Final MP4 download expires after one hour. Google model versions
can retire; check Google's model deprecation page and update the allowlist
when moving to a replacement. fal models remain optional, explicitly selected.

Validation: `npm test` includes mocked Google reference inputs, provider
failures and download behavior, plus real FFmpeg merge/duration checks.
Mock tests do not establish live Google generation or billing access.
