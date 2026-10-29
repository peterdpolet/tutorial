/**
 * src/api/axios.js
 *
 * The one HTTP client for the whole app. Every request goes to /api/... (Vite
 * forwards /api to the Django server while developing), so the rest of the
 * code writes paths relative to that: api.post('/auth/register/', ...).
 *
 * toError() turns a failed request into an ordinary Error that carries:
 *   .status       the HTTP status
 *   .fieldErrors  {field: [messages]} when the server said which input is wrong
 *   .runId        the id of the saved trace, when the request was traced
 *                 (response header X-Tracker-Run)
 */
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export function toError(err) {
  const status = err.response?.status
  const data = err.response?.data
  const out = new Error(data?.detail ?? (data?.errors ? 'Please fix the highlighted fields.' : `Request failed (${status ?? 'no response'})`))
  out.status = status
  out.fieldErrors = data?.errors ?? {}
  out.runId = err.response?.headers?.['x-tracker-run'] ?? null
  return out
}

export default api
