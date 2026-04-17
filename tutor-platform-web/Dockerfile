# ── Stage 1: Build ──
# MEDIUM-10: pin by @sha256 digest in production — see ./scripts/pin-base-images.sh.
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# 構建時注入 API 位址（由 nginx 反向代理，前端直接用相對路徑）
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# 失敗時讓 build 結束碼非 0，避免上層誤以為 image 構建成功
RUN npm run build

# ── Stage 2: Serve ──
# 改用官方 unprivileged 變體：預設以 nginx (uid 101) 身分執行、監聽 8080，
# 不需要 CAP_NET_BIND_SERVICE 也不會 root；相容 docker-compose 將 8080 對外
# 映射到 host 的 80 埠。
# MEDIUM-10: pin by @sha256 digest in production — see ./scripts/pin-base-images.sh.
FROM nginxinc/nginx-unprivileged:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
