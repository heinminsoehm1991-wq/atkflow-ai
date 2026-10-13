# ATK AI FLOW backend (integration scaffold)
Isolated branch for ATK AI FLOW. Existing Render services are untouched.
Run: npm install && npm start
Required Render environment: FAL_KEY, SCENE_IMAGE_MODEL_ID, SCENE_VIDEO_MODEL_ID.
GET /api/health checks configuration. POST /api/generate accepts multipart fields kind=image|video, image, prompt. GET /api/jobs/:id polls result.
IMPORTANT: This is not production-ready. Select fal.ai models that actually accept prompt + image_url and verify output schema. No final MP4 merge yet. Configure authentication, quotas, persistence and provider cost controls before public deployment.
