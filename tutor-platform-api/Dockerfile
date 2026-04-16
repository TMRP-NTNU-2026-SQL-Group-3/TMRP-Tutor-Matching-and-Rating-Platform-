FROM python:3.12-slim

WORKDIR /app

# 安裝系統依賴（psycopg2 + healthcheck 用 curl）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
