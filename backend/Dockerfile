FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    tesseract-ocr libtesseract-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/src

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY schemas/ schemas/
COPY packages/ packages/

ENV PYTHONPATH=/opt/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["sh", "-c", "cd /opt/src && alembic -c backend/alembic.ini upgrade head 2>&1 || echo 'Migration warning (non-fatal)' && uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8001} --workers ${WEB_CONCURRENCY:-4} --timeout-keep-alive 30"]
