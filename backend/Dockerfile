# syntax=docker/dockerfile:1
#
# Multi-stage build. Build context MUST be the repo root (see docker-compose:
#   build: { context: ., dockerfile: backend/Dockerfile })
# so the frontend can be built and baked into the image alongside the backend.

# ── Stage 1: build the Vue frontend ───────────────────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # → /frontend/dist

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.11-slim

# System deps:
#   tesseract-ocr(+spa)  OCR engine + Spanish data
#   libzbar0             required by pyzbar (barcode/QR) — image crashed without it
#   libglib2.0-0 libgl1  OpenCV runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-spa \
    libzbar0 \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend lives at /app (so app/main.py resolves the frontend at /frontend/dist).
COPY backend/ /app/

# Built frontend, served by FastAPI's SPA fallback mounted at "/".
COPY --from=frontend /frontend/dist /frontend/dist

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
