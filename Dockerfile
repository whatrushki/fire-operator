# Multi-stage Dockerfile для Fire-Operator

# Stage 1: Сборка React фронтенда
FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python бэкенд и инференс среда
FROM python:3.11-slim

# Установка системных зависимостей для GDAL / PROJ / C-библиотек
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    libspatialindex-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка зависимостей Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода, весов моделей и собранного фронтенда
COPY ml/ ./ml/
COPY backend/ ./backend/
COPY weights/ ./weights/
COPY --from=frontend-builder /build/dist ./frontend/dist
COPY inference.py .
COPY README.md .

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/backend

EXPOSE 8000

# По умолчанию запускается REST API сервис
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

