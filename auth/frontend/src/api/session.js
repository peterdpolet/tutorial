/**
 * src/api/session.js: the logged-in session, kept in memory.
 *
 * Holds the two tokens and does the one clever thing episode 4 adds: when the
 * server answers 401 to a request that carried the access token, quietly swap
 * the refresh token for a new pair and try the request once more. The person
 * never sees the expiry.
 *
 * The tokens live in variables, not in localStorage: a page reload logs you
 * out. Where tokens are kept in a browser is a security decision of its own;
 * this is the simplest honest choice for a tutorial.
 *
 * ONE refresh at a time. Rotation retires the refresh token when it is used. If
 * two requests both hit a 401 and both refreshed, the second would send an
 * already-retired token, and the server would read that as theft and end the
 * whole login. So every caller shares the single refresh in flight.
 */
import { reactive } from 'vue'
import { loginAccount, fetchMe, refreshTokens } from '@/api/auth'

let accessToken = null
let refreshToken = null
let previousRefreshToken = null   // kept only so the demo can "replay" it
let refreshing = null             // the refresh in flight, shared by every caller

// What the screen needs to know (reactive so buttons enable and disable).
export const session = reactive({ signedIn: false, canReplay: false })

function setTokens(next, { rotated }) {
  if (rotated) previousRefreshToken = refreshToken
  accessToken = next.accessToken
  refreshToken = next.refreshToken
  session.signedIn = true
  session.canReplay = previousRefreshToken !== null
}

function endSession() {
  accessToken = refreshToken = previousRefreshToken = null
  session.signedIn = false
  session.canReplay = false
}

// Log in. Resolves to { runId }.
export async function startSession({ email, password }, { trace = false } = {}) {
  previousRefreshToken = null
  const result = await loginAccount({ email, password }, { trace })
  setTokens(result, { rotated: false })
  return { runId: result.runId }
}

// Swap the refresh token for a new pair. Shares one in-flight refresh. Resolves to { runId }.
export function refreshNow({ trace = false } = {}) {
  if (!refreshing) {
    refreshing = refreshTokens({ refreshToken }, { trace })
      .then((result) => {
        setTokens(result, { rotated: true })
        return { runId: result.runId }
      })
      .catch((err) => {
        endSession()              // the server ended the login: nothing left to try
        throw err
      })
      .finally(() => { refreshing = null })
  }
  return refreshing
}

// Ask the server who we are. On a 401, refresh once and retry.
// Resolves to { email, refreshed, runs: [{ label, id }] }.
export async function whoAmI({ trace = false } = {}) {
  const runs = []
  const note = (label, id) => { if (id) runs.push({ label, id }) }
  try {
    const me = await fetchMe({ accessToken }, { trace })
    note('/me', me.runId)
    return { email: me.email, refreshed: false, runs }
  } catch (err) {
    note('/me (refused)', err.runId)
    if (err.status !== 401) throw Object.assign(err, { runs })
  }
  try {
    const renewed = await refreshNow({ trace })
    note('refresh', renewed.runId)
    const me = await fetchMe({ accessToken }, { trace })
    note('/me (retry)', me.runId)
    return { email: me.email, refreshed: true, runs }
  } catch (err) {
    note('refresh (refused)', err.runId)
    throw Object.assign(err, { runs })
  }
}

// DEMO: make the access token invalid, as if its 15 minutes had run out.
export function breakAccessToken() {
  accessToken = `${accessToken}x`
}

// DEMO: send the PREVIOUS refresh token, as a thief holding a stolen copy would.
// Does not change our own tokens. Rejects with the server's refusal.
export async function replayOldToken({ trace = false } = {}) {
  try {
    await refreshTokens({ refreshToken: previousRefreshToken }, { trace })
  } catch (err) {
    throw Object.assign(err, { runs: err.runId ? [{ label: 'replay', id: err.runId }] : [] })
  }
}

export function forgetSession() {
  endSession()
}
