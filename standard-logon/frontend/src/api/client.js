import axios from 'axios'

// Every call goes to /api/..., which Vite forwards to Django while developing
// and Nginx forwards on a real server. The same code runs in both places.
const client = axios.create({ baseURL: '/api' })

// toError() turns a failed request into an ordinary Error that carries the
// server's own reason ({detail: "..."}) and, when the request was traced, the
// id of the saved trace (response header X-Tracker-Run).
export function toError(err) {
  const status = err.response?.status
  const out = new Error(err.response?.data?.detail ?? `Request failed (${status ?? 'no response'})`)
  out.status = status
  out.runId = err.response?.headers?.['x-tracker-run'] ?? null
  return out
}

export default client
