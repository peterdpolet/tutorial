/**
 * src/api/auth.js: the calls the account screens make.
 *
 *   POST /api/auth/register/   create an inactive account and email a link
 *   POST /api/auth/verify/     switch the account on, using the token in that link
 *
 * Register returns 201 + {detail}, or 400 + {errors: {field: [reasons]}}.
 * Verify returns 200 + {detail}, or 400 + {errors: {token: [reasons]}}.
 * A 400 becomes a thrown Error whose .fieldErrors says which input to fix.
 *
 * TRACING: sending the header  X-Tracker: 1  asks the server to trace that one
 * request. When it agrees, the response carries  X-Tracker-Run: <id>.  That id
 * comes back as `runId` (on success) or on the thrown error (on a refusal).
 */
import api, { toError } from '@/api/axios'

// Resolves to { detail, runId }. Rejects with an Error (.fieldErrors, .runId).
export const registerAccount = async ({ email, password }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/register/', { email, password }, {
      headers: trace ? { 'X-Tracker': '1' } : {},
    })
    return { detail: res.data.detail, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}

// Resolves to { detail, runId }. Rejects with an Error (.fieldErrors.token, .runId).
export const verifyEmail = async ({ token }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/verify/', { token }, {
      headers: trace ? { 'X-Tracker': '1' } : {},
    })
    return { detail: res.data.detail, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}
