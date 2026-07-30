"""
The three task types this project demonstrates:

1. process_image   - CPU-bound image processing (resize + filter)
2. generate_report - builds a PDF from structured data
3. send_email_batch - simulates dispatching a batch of emails, with
                       automatic retry on (simulated) transient failure

Each is deliberately made to take a few seconds, so it's visibly obvious
that the FastAPI endpoint returns immediately while the real work happens
here, in a separate worker process.
"""
import os
import random
import time
from datetime import datetime, timezone

from PIL import Image, ImageFilter
from fpdf import FPDF, XPos, YPos

from app.celery_app import celery_app
from app.config import settings

os.makedirs(settings.processed_dir, exist_ok=True)
os.makedirs(settings.reports_dir, exist_ok=True)
os.makedirs(settings.logs_dir, exist_ok=True)


@celery_app.task(bind=True, name="tasks.process_image")
def process_image(self, upload_path: str, filename: str, width: int = 400):
    """
    Resize an uploaded image and apply a sharpen filter.
    Simulates real processing cost with a short sleep so you can watch
    the task sit in 'STARTED' state before completing.
    """
    self.update_state(state="STARTED", meta={"step": "opening image"})
    img = Image.open(upload_path)

    self.update_state(state="STARTED", meta={"step": "resizing"})
    ratio = width / float(img.width)
    height = int(img.height * ratio)
    img = img.resize((width, height))
    img = img.filter(ImageFilter.SHARPEN)

    time.sleep(3)  # stand-in for heavier real-world processing

    out_path = os.path.join(settings.processed_dir, f"processed_{filename}")
    img.save(out_path)

    return {
        "status": "completed",
        "output_path": out_path,
        "dimensions": f"{width}x{height}",
    }


@celery_app.task(bind=True, name="tasks.generate_report")
def generate_report(self, title: str, rows: list[dict]):
    """
    Build a simple PDF report from a list of dict rows.
    e.g. rows = [{"item": "Widget", "qty": 5}, {"item": "Gadget", "qty": 2}]
    """
    self.update_state(state="STARTED", meta={"step": "building PDF"})

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Generated {datetime.now(timezone.utc).isoformat()}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    for row in rows:
        line = ", ".join(f"{k}: {v}" for k, v in row.items())
        # new_x/new_y must be set explicitly here too, or the cursor is left
        # at the right margin and the *next* multi_cell call has zero width.
        pdf.multi_cell(0, 8, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    time.sleep(2)  # stand-in for heavier report-building logic

    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    out_path = os.path.join(settings.reports_dir, f"{safe_title or 'report'}_{int(time.time())}.pdf")
    pdf.output(out_path)

    return {"status": "completed", "output_path": out_path, "row_count": len(rows)}


@celery_app.task(
    bind=True,
    name="tasks.send_email_batch",
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    retry_backoff_max=30,
    max_retries=3,
)
def send_email_batch(self, recipients: list[str], subject: str, body: str):
    """
    Simulates sending a batch of emails (no real SMTP calls — this is a
    demo project, and you don't want to accidentally spam real addresses).

    Randomly raises ConnectionError ~15% of the time to demonstrate Celery's
    automatic retry behavior, which you can watch happen live in the worker
    logs and in Flower.
    """
    self.update_state(state="STARTED", meta={"step": f"sending to {len(recipients)} recipients"})

    if random.random() < 0.15:
        raise ConnectionError("Simulated transient mail-server failure")

    time.sleep(1.5)

    log_path = os.path.join(settings.logs_dir, f"batch_{int(time.time())}.log")
    with open(log_path, "w") as f:
        f.write(f"Subject: {subject}\n")
        f.write(f"Body: {body}\n")
        f.write(f"Sent at: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Recipients ({len(recipients)}):\n")
        f.write("\n".join(recipients))

    return {"status": "completed", "sent_count": len(recipients), "log_path": log_path}
