FROM python:3.12-slim

WORKDIR /app

# 安裝系統依賴（psycopg2 + healthcheck 用 curl）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 建立資料與日誌目錄
RUN mkdir -p data logs

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# 預設啟動 API 伺服器（可在 docker-compose 中覆蓋為 huey worker）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
