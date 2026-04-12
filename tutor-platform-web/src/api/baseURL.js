// 統一的 API baseURL（從 api/index 抽出，避免 stores 與 api 相互 import 形成循環依賴）。
//
// Docker 環境下 VITE_API_BASE_URL="" 為刻意設計：
//   後端所有路由皆以 /api/ 前綴，前端呼叫亦含 /api/，
//   空 baseURL 會送出相對路徑（例如 /api/auth/login），
//   由 nginx 代理至 api:8000。請勿改成 '/api'，否則路徑變成 /api/api/...。
//
// 開發環境（無 env 變數）則回退至 http://localhost:8000。
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
