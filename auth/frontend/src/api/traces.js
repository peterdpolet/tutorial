/**
 * src/api/traces.js: reading stored traces back from the tracker app.
 *
 *   GET /api/tracker/runs/         recent traces (summaries)
 *   GET /api/tracker/runs/<id>/    one trace as a nested call tree
 */
import api, { toError } from '@/api/axios'

export const listRuns = async () => {
  try {
    return (await api.get('/tracker/runs/')).data.results
  } catch (err) {
    throw toError(err)
  }
}

export const getRun = async (id) => {
  try {
    return (await api.get(`/tracker/runs/${id}/`)).data
  } catch (err) {
    throw toError(err)
  }
}
