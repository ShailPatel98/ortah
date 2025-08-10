# ===== Base =====
FROM python:3.11-slim

WORKDIR /app

# System deps (optional but nice for curl/debug)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY server ./server
COPY web ./web
COPY scraper ./scraper
COPY indexer ./indexer

# Ensure data dir exists at runtime (scraper writes here)
RUN mkdir -p /app/data

EXPOSE 8000

# Start server
CMD ["python", "server/app.py"]
