/**
 * src/api/auth.js: the calls the account screens make.
 *
 *   POST /api/auth/register/   create an inactive account and email a link
 *   POST /api/auth/verify/     switch the account on, using the token in that link
 *   POST /api/auth/login/      check the password, return an access and a refresh token
 *   GET  /api/auth/me/         who does this access token belong to?
 *   POST /api/auth/refresh/    swap a refresh token for a new pair (the old one is retired)
 *   POST /api/auth/logout/     end this login (or every login) on the server
 *   POST /api/auth/forgot/     ask for a password-reset link (always the same answer)
 *   POST /api/auth/reset/      set a new password, using the token in that link
 *   POST /api/auth/2fa/setup/    (logged in) make an authenticator secret
 *   POST /api/auth/2fa/confirm/  (logged in) prove the app works; get recovery codes
 *   POST /api/auth/2fa/login/    finish a login with the six-digit code (or a recovery code)
 *   GET  /api/auth/admin/users/  (admin only) every account with its role
 *   POST /api/auth/admin/role/   (admin only) change an account's role
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
// Resolves to { accessToken, refreshToken, expiresIn, runId }, or (episode 7, when the
// account uses two-factor) to { mfaRequired: true, mfaToken, runId }: the password was
// right but the tokens come only after the code. Rejects with an Error
// (.status, .fieldErrors, .runId); .status 429 means the address is locked.
export const loginAccount = async ({ email, password }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/login/', { email, password }, {
      headers: trace ? { 'X-Tracker': '1' } : {},
    })
    if (res.data.mfa_required) {
      return { mfaRequired: true, mfaToken: res.data.mfa_token, runId: res.headers['x-tracker-run'] ?? null }
    }
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
// Resolves to { email, role, runId }. Rejects with an Error (.status 401 = not logged in / expired).
export const fetchMe = async ({ accessToken }, { trace = false } = {}) => {
  try {
    const res = await api.get('/auth/me/', {
      headers: { Authorization: `Bearer ${accessToken}`, ...(trace ? { 'X-Tracker': '1' } : {}) },
    })
    return { email: res.data.email, role: res.data.role, runId: res.headers['x-tracker-run'] ?? null }
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

// Episode 6. POST /api/auth/forgot/ always answers 200 with the same sentence, whether
// or not the address has an account, so the form cannot be used to find out.
// Resolves to { detail, runId }.
export const forgotPassword = async ({ email }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/forgot/', { email }, {
      headers: trace ? { 'X-Tracker': '1' } : {},
    })
    return { detail: res.data.detail, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}

// Episode 6. POST /api/auth/reset/ sets the new password and ends every login.
// Resolves to { detail, runId }. Rejects with an Error (.fieldErrors.token or
// .fieldErrors.password; a weak password does NOT use up the link; .runId).
export const resetPassword = async ({ token, password }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/reset/', { token, password }, {
      headers: trace ? { 'X-Tracker': '1' } : {},
    })
    return { detail: res.data.detail, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}

// Episode 7. Everything below needs a login except twoFactorLogin.

// POST /api/auth/2fa/setup/ -> { secret, otpauthUri, runId }. 409 if it is already on.
export const twoFactorSetup = async ({ accessToken }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/2fa/setup/', {}, {
      headers: { Authorization: `Bearer ${accessToken}`, ...(trace ? { 'X-Tracker': '1' } : {}) },
    })
    return { secret: res.data.secret, otpauthUri: res.data.otpauth_uri, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}

// POST /api/auth/2fa/confirm/ -> { recoveryCodes, runId }. The codes are shown once.
export const twoFactorConfirm = async ({ accessToken, code }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/2fa/confirm/', { code }, {
      headers: { Authorization: `Bearer ${accessToken}`, ...(trace ? { 'X-Tracker': '1' } : {}) },
    })
    return { recoveryCodes: res.data.recovery_codes, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}

// POST /api/auth/2fa/login/ -> the same { accessToken, refreshToken, expiresIn, runId } as a plain
// login. `code` is the six-digit code or a recovery code. Rejects with an Error (.status 401, 429).
export const twoFactorLogin = async ({ mfaToken, code }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/2fa/login/', { mfa_token: mfaToken, code }, {
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

// Episode 8. Both need a login AND the admin role.
// 401 = not logged in, 403 = logged in but not an admin.

// GET /api/auth/admin/users/ -> { users: [{ id, email, role, active }], runId }
export const adminUsers = async ({ accessToken }, { trace = false } = {}) => {
  try {
    const res = await api.get('/auth/admin/users/', {
      headers: { Authorization: `Bearer ${accessToken}`, ...(trace ? { 'X-Tracker': '1' } : {}) },
    })
    return { users: res.data.users, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}

// POST /api/auth/admin/role/ -> { detail, runId }. 403 not an admin, 404 no such account,
// 409 that would leave no admin, 400 the request itself made no sense.
export const adminSetRole = async ({ accessToken, userId, role }, { trace = false } = {}) => {
  try {
    const res = await api.post('/auth/admin/role/', { user_id: userId, role }, {
      headers: { Authorization: `Bearer ${accessToken}`, ...(trace ? { 'X-Tracker': '1' } : {}) },
    })
    return { detail: res.data.detail, runId: res.headers['x-tracker-run'] ?? null }
  } catch (err) {
    throw toError(err)
  }
}
