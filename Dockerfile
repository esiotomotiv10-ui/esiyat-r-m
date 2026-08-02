# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Bağımlılıkları önce kur (katman önbelleği için).
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# Güvenlik: kök olmayan kullanıcı ile çalıştır.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# Paper trading zorunlu; canlı emir kapalı.
ENV TRADING_MODE=paper \
    LIVE_TRADING_DISABLED=true \
    KILL_SWITCH=false \
    ENABLE_KILL_SWITCH_ENDPOINT=false

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
