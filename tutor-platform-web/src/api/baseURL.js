// Single source of truth for the API baseURL (split out from api/index so
// stores ↔ api can't form an import cycle).
//
// Docker 環境下 VITE_API_BASE_URL="" 為刻意設計：
//   後端所有路由皆以 /api/ 前綴，前端呼叫亦含 /api/，空 baseURL 會送出
//   相對路徑（例如 /api/auth/login），由 nginx 代理至 api:8000。請勿改成
//   '/api'，否則路徑會重複成 /api/api/...。
//
// Dev / prod URLs are supplied by `.env.development` / `.env.production`.
// The empty-string check below is important: an explicit VITE_API_BASE_URL=""
// (Docker prod) must survive as "" and NOT fall through to the dev default.
const envValue = import.meta.env.VITE_API_BASE_URL

export const API_BASE_URL = envValue !== undefined
  ? envValue
  // Dev-only safety net. If you hit this in production, something is wrong
  // with your build-time env injection — fix the build rather than relying
  // on this branch, so misconfigured prod deploys fail loudly in one place.
  : (import.meta.env.DEV
      ? 'http://localhost:8000'
      : (() => { throw new Error('VITE_API_BASE_URL is not set in this build') })())
