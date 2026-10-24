"""Pay-per-job entrypoint. No HTTP listener, polling loop or idle worker."""
from render import Workflows, TaskContext, Retry
import render_jobs

# Retry ownership remains in ATK's durable job/budget records, not two systems.
app = Workflows(default_retry=Retry(max_retries=0, wait_duration_ms=1000), default_timeout=14400, default_plan="flex")

@app.task(name="render_video", retry=Retry(max_retries=0, wait_duration_ms=1000), timeout_seconds=14400, plan="flex")
def render_video(ctx: TaskContext, payload: dict) -> dict:
    render_jobs.validate_payload(payload)
    # Inputs and retained Myanmar narration stay in account-private Site storage.
    # Only the scoped job capability, never video bytes or provider keys, is input.
    quality = render_jobs.run(payload, release_slot=False, raise_errors=True)
    return {"jobId": payload["id"], "quality": quality}

if __name__ == "__main__":
    app.start()
