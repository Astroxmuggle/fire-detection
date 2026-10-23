# syntax=docker/dockerfile:1
#
# CPU-only image. The application itself is unchanged: it reads its paths from
# environment variables, so all state lives in the /data volume.
#
#   docker build -t firewatch-ai .
#   docker run --rm -p 5000:5000 -v firewatch-data:/data firewatch-ai
#
# NOTE: a webcam device cannot be passed through Docker Desktop on Windows.
# Use an RTSP URL (CAMERA_SOURCE=rtsp://...) instead of a device index.

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=5000 \
    DATABASE_PATH=/data/fire_detection.db \
    EVIDENCE_DIR=/data/snapshots \
    LOG_DIR=/data/logs

# Runtime libraries required by the OpenCV GUI build and by FFMPEG video/RTSP.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the CPU build of torch first, then everything else. requirements.txt
# pins torch==2.6.0; installing from PyPI would pull the multi-gigabyte CUDA
# wheel, so the torch lines are filtered out of the second install.
COPY requirements.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.6.0 torchvision==0.21.0 \
    && grep -v -E '^(torch|torchvision)==' requirements.txt > /tmp/requirements-server.txt \
    && pip install -r /tmp/requirements-server.txt \
    && pip install "gunicorn==23.0.0"

COPY . .

RUN useradd --create-home --uid 10001 firewatch \
    && mkdir -p /data/snapshots /data/logs \
    && chown -R firewatch:firewatch /app /data

USER firewatch

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3).status == 200 else 1)"

# gthread keeps the long-lived MJPEG response from blocking the status API.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "8", \
     "--worker-class", "gthread", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "app:app"]
