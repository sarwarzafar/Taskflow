"""
The FastAPI web service. This is the "main application thread" that stays
fast and responsive because it never does heavy work itself — it only
validates the request, hands it to Celery, and immediately returns a
task ID. The actual work happens in a separate worker process.
"""
import os
import shutil
import uuid

from celery.result import AsyncResult
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.config import settings
from app.tasks import generate_report, process_image, send_email_batch

app = FastAPI(
    title="TaskFlow",
    description="Asynchronous job processing system built with FastAPI, Celery, and Redis.",
    version="1.0.0",
)

os.makedirs(settings.upload_dir, exist_ok=True)


class ReportRequest(BaseModel):
    title: str = Field(..., examples=["Monthly Inventory"])
    rows: list[dict] = Field(..., examples=[[{"item": "Widget", "qty": 5}]])


class EmailBatchRequest(BaseModel):
    recipients: list[str] = Field(..., examples=[["a@example.com", "b@example.com"]])
    subject: str
    body: str


@app.get("/health")
def health_check():
    """Confirms the API is up. Doesn't check Redis/Celery — see /health/full for that."""
    return {"status": "ok"}


@app.get("/health/full")
def health_check_full():
    """Confirms the API AND its connection to the Redis broker are both alive."""
    try:
        celery_app.backend.client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {"api": "ok", "redis": "ok" if redis_ok else "unreachable"}


@app.post("/tasks/image")
async def submit_image_task(file: UploadFile = File(...), width: int = 400):
    """
    Accepts an image upload, saves it, and hands off resizing/sharpening
    to a Celery worker. Returns immediately with a task ID — this endpoint
    does NOT wait for processing to finish.
    """
    ext = os.path.splitext(file.filename)[1]
    safe_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(settings.upload_dir, safe_name)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    task = process_image.delay(save_path, safe_name, width)
    return {"task_id": task.id, "status_url": f"/tasks/{task.id}"}


@app.post("/tasks/report")
async def submit_report_task(payload: ReportRequest):
    """Triggers PDF report generation as a background job."""
    task = generate_report.delay(payload.title, payload.rows)
    return {"task_id": task.id, "status_url": f"/tasks/{task.id}"}


@app.post("/tasks/email-batch")
async def submit_email_batch_task(payload: EmailBatchRequest):
    """Triggers a simulated batch email send as a background job."""
    task = send_email_batch.delay(payload.recipients, payload.subject, payload.body)
    return {"task_id": task.id, "status_url": f"/tasks/{task.id}"}


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """
    Poll this endpoint with a task ID to check progress.
    State moves through PENDING -> STARTED -> SUCCESS (or FAILURE, with retries in between).
    """
    result = AsyncResult(task_id, app=celery_app)

    if not result.id:
        raise HTTPException(status_code=404, detail="Task not found")

    response = {"task_id": task_id, "state": result.state}

    if result.state == "PENDING":
        response["info"] = "Task not found or not yet started"
    elif result.state == "STARTED":
        response["info"] = result.info
    elif result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.info)
        response["retries"] = result.info.get("retries") if isinstance(result.info, dict) else None
    else:
        response["info"] = str(result.info)

    return response
