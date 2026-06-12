# Playwright-Basisimage: enthält Python 3.12, Chromium und alle System-Abhängigkeiten
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs /app/documents/certificates

ENV PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/app/config.json \
    DATABASE_PATH=/app/data/jobs.db \
    LOGS_DIR=/app/logs

EXPOSE 8000

CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
