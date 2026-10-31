/**
 * src/api/auth.js: the calls the account screens make.
 *
 *   POST /api/auth/register/   create an inactive account and email a link
 *   POST /api/auth/verify/     switch the account on, using the token in that link
 *   POST /api/auth/login/      check the password, return an access and a refresh token
 *   GET  /api/auth/me/         who does this access token belong to?
 *   POST /api/auth/refresh/    swap a refresh token for a new pair (the old one is retired)
 *   POST /api/auth/logout/     end this login (or every login) on the server
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

// Episode 3. POST /api/auth/login/ returns 200 + {access_token, refresh_token, expires_in},
// or 400/401/403/429 + {detail} (or {errors}) for a refusal.
// Resolves to { accessToken, refreshToken, expiresIn, runId }. Rejects with an Error
// (.status, .fieldErrors, .runId); .status 429 means the address is locked.
export const loginAccount = async ({ email, password }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/login/', { email, password }, {
      headers: trace ? { 'X-Tracker': '1' } : {},
    })
    return {
      accessToken: res.data.access_token,
      refreshToken: res.data.refresh_token,
      expiresIn: res.data.expires_in,
      runId: res.headers['x-tracker-run'] ?? null,
    }
  } catch (err) {
    throw toError(err)
  }
}

// GET /api/auth/me/ with the access token in the Authorization header.
// Resolves to { email, runId }. Rejects with an Error (.status 401 = not logged in / expired).
export const fetchMe = async ({ accessToken }, { trace = false } = {}) => {
  try {
    const res = await api.get('/auth/me/', {
      headers: { Authorization: `Bearer ${accessToken}`, ...(trace ? { 'X-Tracker': '1' } : {}) },
    })
    return { email: res.data.email, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}

// Episode 4. POST /api/auth/refresh/ swaps a refresh token for a NEW pair; the one
// sent is retired. Resolves to { accessToken, refreshToken, expiresIn, runId }.
// Rejects with an Error (.status 401: unknown, expired, or already used; .runId).
export const refreshTokens = async ({ refreshToken }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/refresh/', { refresh_token: refreshToken }, {
      headers: trace ? { 'X-Tracker': '1' } : {},
    })
    return {
      accessToken: res.data.access_token,
      refreshToken: res.data.refresh_token,
      expiresIn: res.data.expires_in,
      runId: res.headers['x-tracker-run'] ?? null,
    }
  } catch (err) {
    throw toError(err)
  }
}

// Episode 5. POST /api/auth/logout/ ends the login the refresh token belongs to
// (or, with everywhere: true, every login of that person). It answers 200 even for
// a token it does not know, so pressing it twice is harmless.
// Resolves to { detail, runId }.
export const logoutAccount = async ({ refreshToken, everywhere = false }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/logout/', { refresh_token: refreshToken, everywhere }, {
      headers: trace ? { 'X-Tracker': '1' } : {},
    })
    return { detail: res.data.detail, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}
