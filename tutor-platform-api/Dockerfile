# MEDIUM-10: pinned by @sha256 digest for reproducible builds. Refresh with
# `./scripts/pin-base-images.sh` or Renovate (.github/renovate.json).
FROM python:3.12-slim@sha256:401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461

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

# Default entrypoint for the API container (docker-compose overrides to run
# the huey worker instead).
# MEDIUM-2: trust X-Forwarded-For/Proto only from the nginx sidecar.
# uvicorn's ProxyHeadersMiddleware does exact-string IP match (no CIDR), so
# we take the list from the FORWARDED_ALLOW_IPS env var — docker-compose
# pins the web service to a fixed address on a user-defined subnet and
# exports it here. Defaulting to "127.0.0.1" means a mis-deployed container
# (no env var, no nginx in front) refuses to honour spoofed XFF from the
# public internet.
# `exec` replaces the shell with uvicorn so SIGTERM from `docker stop` reaches
# uvicorn directly (otherwise the sh wrapper becomes PID 1 and swallows signals).
# I-01: --timeout-keep-alive bounds idle keep-alive connections so a slow
#   client cannot occupy a worker indefinitely; --timeout-graceful-shutdown
#   gives in-flight requests a deterministic window to finish on SIGTERM
#   before the container is killed by docker stop (default 10s).
# I-02: UVICORN_WORKERS (default 4) matches config.py's db_pool_min=5 so
#   every worker has a DB connection available under load. Override to 1
#   for constrained environments (single-vCPU dev boxes).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\" --workers \"${UVICORN_WORKERS:-4}\" --timeout-keep-alive 30 --timeout-graceful-shutdown 30"]
