FROM python:3.12-slim

WORKDIR /app

# Exact versions (requirements.lock) so every build installs what the tests ran against
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .
RUN mkdir -p data logs

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# Default: FastAPI server. SERVICE_ROLE=recorder runs the options recorder scheduler instead
# (Railway service "recorder"). CLI: docker compose run tradingagents RELIANCE.NS
CMD if [ "$SERVICE_ROLE" = "recorder" ]; then exec python -m options.daemon;     else exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}; fi
