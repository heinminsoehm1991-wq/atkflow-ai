# ATK AI FLOW
Isolated application on branch `atk-ai-flow-workflow`; no changes to other services.

Run `npm ci && npm start` in this directory. Render build: `cd atk-ai-flow && npm install`; start: `cd atk-ai-flow && npm start`.

Required secrets: `FAL_KEY`, `ADMIN_TOKEN`. Credentials remain server-side. The administrator enters ADMIN_TOKEN into the session-only password field. Paid generation requires explicit charge confirmation.

Connected product → prompt → image → video → final graph. Scene chains can be disconnected and excluded from execution. Scene prompts are an editable local shot template; the prompt planning button does not call an AI language model. Image/video generation uses fal.ai. Verified adapters: FLUX Kontext dev/pro, Wan 2.2 5B, Kling 2.6 Pro. Model selectors use supported defaults if old environment IDs are unsupported.

2 minute / 3 minute / custom targets up to 10 minutes; maximum 120 scenes. Wan clips are limited to 5 seconds in the planner. Kling accepts 5 or 10 seconds. Final rendering normalizes each clip to its scene duration by trimming or holding its last frame. Output is silent H.264, 24 FPS, 16:9 / 9:16 / 1:1. The FFmpeg executable is installed via ffmpeg-static.

POST /api/render accepts completed video job IDs, not arbitrary URLs. Server verifies target total, serializes renders, and provides authenticated status/download endpoints. Completed outputs expire after 1 hour. Provider job metadata lives in memory and is lost on server restart; browser layouts persist but saved output URLs cannot be used as authenticated jobs after restart. This is a single-admin beta, not durable multi-user hosting.

Tests: `npm test` (schemas, duration validation, actual mixed-resolution MP4 merge).
