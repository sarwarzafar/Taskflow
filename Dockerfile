# One image, two roles. The web service and the worker service run the
# exact same codebase and dependencies — only the startup command differs,
# which docker-compose.yml overrides per-service. This mirrors exactly how
# the app was tested locally (same code, same requirements, run two ways).

FROM python:3.12-slim

WORKDIR /code

# Install dependencies first so Docker's layer cache skips this step
# on rebuilds where only application code changed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Default command runs the API. docker-compose.yml overrides this
# for the worker and flower services.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
