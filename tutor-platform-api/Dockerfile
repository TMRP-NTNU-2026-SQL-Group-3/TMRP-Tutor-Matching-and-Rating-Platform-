# MEDIUM-10: production builds must pin this image by @sha256 digest — run
# `./scripts/pin-base-images.sh` from repo root to rewrite the tag into
# `python:3.12-slim@sha256:<digest>`. Renovate (.github/renovate.json) keeps
# the digest current via automated PRs.
FROM python:3.12-slim

WORKDIR /app

# LOW-8: psycopg2-binary ships prebuilt wheels with libpq statically linked,
# so neither gcc nor libpq-dev is needed at build or runtime. curl stays for
# the HEALTHCHECK below. Keeping the image slim cuts ~150 MB and removes a
# compiler from the runtime attack surface.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 建立資料與日誌目錄；改為非 root 之前先把 ownership 給應用使用者，
# 否則 huey sqlite 寫入或 logging file handler 都會被 EACCES。
RUN useradd -m -u 1000 app \
    && mkdir -p data logs \
    && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# SEC-H04: entrypoint reads DB password from Docker secret file and
# constructs DATABASE_URL at runtime, keeping credentials out of env vars.
ENTRYPOINT ["./docker-entrypoint.sh"]

# 預設啟動 API 伺服器（可在 docker-compose 中覆蓋為 huey worker）
# MEDIUM-2: trust X-Forwarded-For/Proto from the in-cluster nginx proxy so
# rate-limiting and audit logs key off the real client IP instead of the
# proxy IP. The forwarded-allow-ips list is intentionally broad ("*") because
# uvicorn only sees traffic inside the compose/overlay network — the outer
# nginx is the single trusted hop, and it overwrites XFF before forwarding
# (see tutor-platform-web/nginx.conf, MEDIUM-3).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
