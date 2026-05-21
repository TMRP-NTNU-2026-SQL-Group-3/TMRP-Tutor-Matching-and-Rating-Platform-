import api from './index'

// The /api/stats/income and /api/stats/expense endpoints are asynchronous:
// each enqueues a Huey background job and returns only a { task_id }. The
// computed figures must be polled from /api/stats/tasks/{task_id} until the
// job reports status === 'complete'. These helpers hide that two-step flow
// so callers receive the final result object directly.
const POLL_INTERVAL_MS = 700
const MAX_POLL_ATTEMPTS = 30 // ~21s ceiling before giving up

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function pollTaskResult(taskId) {
  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
    const res = await api.get(`/api/stats/tasks/${taskId}`)
    if (res?.status === 'complete') {
      const result = res.result || {}
      // The worker reports business failures (e.g. bad month, missing
      // tutor record) as an { error } field inside an otherwise complete
      // task — surface it as a rejection so views show it like any error.
      if (result.error) throw new Error(result.error)
      return result
    }
    await sleep(POLL_INTERVAL_MS)
  }
  throw new Error('統計計算逾時，請稍後再試')
}

async function runStatsJob(path, params) {
  const queued = await api.get(path, { params })
  const taskId = queued?.task_id
  if (!taskId) throw new Error('統計任務建立失敗，請稍後再試')
  return pollTaskResult(taskId)
}

export const statsApi = {
  getIncome(params) {
    return runStatsJob('/api/stats/income', params)
  },
  getExpense(params) {
    return runStatsJob('/api/stats/expense', params)
  },
}
