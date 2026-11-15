# EarthTrend AI - production image (Role 6).
# Slim base pinned by digest, non-root user, read-only application code,
# health check, no secret inside the image (keys come from the platform).
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    APP_MODULE=api.server:app \
    MAX_BODY_BYTES=65536 \
    PORT=8000

# Security updates of the Debian base packages (the pinned base image can be
# older than the latest fixes; Trivy fails the pipeline on fixable HIGH/CRITICAL).
RUN apt-get update --error-on=any \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

WORKDIR /app

# Dependencies first: this layer stays cached while only the code changes.
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Code is owned by root, so the running app cannot modify itself.
COPY . .
# The only writable folder: runtime cache (for example NASA CSV files).
RUN mkdir -p /app/data && chown -R app:app /app/data

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=4)"

# --proxy-headers: keeps https:// in generated URLs behind the platform proxy.
# --no-access-log: security.py writes the access log with truncated IPs instead.
# The rate limiter reads the client IP itself (TRUSTED_PROXY_HOPS), see security.py.
CMD ["sh", "-c", "exec uvicorn \"$APP_MODULE\" --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*' --no-server-header --no-access-log"]
