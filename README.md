# TaskFlow — Asynchronous Job Processing System

A background job processing service built with **FastAPI**, **Celery**, and **Redis**. The API accepts a request, hands the real work to a pool of Celery workers, and returns immediately — the client polls a status endpoint to check progress. Everything is containerized with **Docker Compose**, and workers scale horizontally with one command.

## Why this exists

Some work is too slow to do inside a normal request/response cycle — resizing images, generating reports, sending batches of email. Doing it inline blocks the API and makes every client wait on the slowest request. This project offloads that work to a separate pool of workers, coordinated through a Redis queue, so the API stays fast regardless of how long individual jobs take.

## Architecture

```
Client → FastAPI (web) → Redis (broker + result store) → Celery workers (1..N)
                ↑                                              │
                └──────────── poll for status/result ──────────┘
```

- **web** — FastAPI service. Validates requests, hands work to Celery via `.delay()`, returns a task ID immediately. Never does the actual processing itself.
- **redis** — Acts as both the message broker (holds the queue) and the result backend (stores task state and output).
- **worker** — One or more Celery processes pulling jobs off the same Redis queue. Scale this service to add throughput.
- **flower** — Web dashboard for watching tasks move through the queue in real time.

## The three task types

| Task | What it does | Demonstrates |
|---|---|---|
| `process_image` | Resizes + sharpens an uploaded image | CPU-bound background work |
| `generate_report` | Builds a PDF from structured data | File-generation background work |
| `send_email_batch` | Simulates sending a batch of emails | Automatic retry on transient failure (randomly raises `ConnectionError` ~15% of the time to trigger Celery's built-in retry/backoff) |

## Running it

### With Docker (recommended)

```bash
docker compose up --build
```

This starts Redis, the API, one worker, and Flower. Scale workers independently:

```bash
docker compose up --build --scale worker=3
```

- API docs: http://localhost:8000/docs
- Flower dashboard: http://localhost:5555

Processed files land in `./storage/` on your host machine (mounted into both the `web` and `worker` containers), so you can inspect output without shelling into a container.

### Locally, without Docker

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# You need a Redis server running locally — either:
#   apt install redis-server && redis-server --daemonize yes
# or run just the Redis container: docker run -d -p 6379:6379 redis:7-alpine

# Terminal 1
uvicorn app.main:app --reload

# Terminal 2
celery -A app.celery_app worker --loglevel=info

# Terminal 3 (optional monitoring)
celery -A app.celery_app flower
```

## Trying it out

```bash
# Generate a report
curl -X POST http://localhost:8000/tasks/report \
  -H "Content-Type: application/json" \
  -d '{"title": "Weekly Inventory", "rows": [{"item": "Widget", "qty": 12}]}'
# → {"task_id": "...", "status_url": "/tasks/..."}

# Check status (poll this until state is SUCCESS)
curl http://localhost:8000/tasks/<task_id>

# Process an image
curl -X POST "http://localhost:8000/tasks/image?width=300" -F "file=@photo.jpg"

# Trigger a batch email send
curl -X POST http://localhost:8000/tasks/email-batch \
  -H "Content-Type: application/json" \
  -d '{"recipients": ["a@example.com"], "subject": "Hi", "body": "Test"}'
```

Immediately after submitting, the status endpoint will show `PENDING` or `STARTED` — not `SUCCESS` — which is the actual proof the API isn't blocking on the work.

## Project structure

```
taskflow/
├── app/
│   ├── main.py         # FastAPI app and endpoints
│   ├── celery_app.py   # Celery application instance
│   ├── tasks.py        # The three background task definitions
│   ├── config.py        # Centralized settings (env-driven)
│   └── storage/         # Output files (gitignored, volume-mounted in Docker)
├── Dockerfile            # Shared image for web, worker, and flower
├── docker-compose.yml    # Orchestrates redis, web, worker, flower
├── requirements.txt
└── .env.example
```
