FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data logs

EXPOSE 8000

# Default: FastAPI server. CLI: docker compose run tradingagents RELIANCE.NS
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
