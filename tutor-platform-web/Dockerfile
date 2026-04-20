# ── Stage 1: Build ──
# MEDIUM-10: pin by @sha256 digest in production — see ./scripts/pin-base-images.sh.
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS build

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
FROM nginxinc/nginx-unprivileged:alpine@sha256:72cd9a222d01fdf47bd47ad8dc50b0221a768742b84a66c5e0b94ed13bcc6c72

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Place security-headers snippet OUTSIDE conf.d so nginx's top-level
# `include /etc/nginx/conf.d/*.conf` (http scope) does not try to load these
# add_header directives at http scope, which would fail to start nginx.
COPY nginx-security-headers.conf /etc/nginx/snippets/security-headers.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
