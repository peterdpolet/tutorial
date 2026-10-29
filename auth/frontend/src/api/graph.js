/**
 * src/api/graph.js: reading the code map (what the discoverer found).
 *
 *   GET /api/tracker/graph/                       projects loaded
 *   GET /api/tracker/graph/<p>/flow/?start=<id>   everything reachable from one entity
 *   GET /api/tracker/graph/<p>/                   the whole graph
 *   GET /api/tracker/graph/<p>/match/?method&path which route + view handled a request
 */
import api, { toError } from '@/api/axios'

const get = async (url, params) => {
  try {
    return (await api.get(url, { params })).data
  } catch (err) {
    throw toError(err)
  }
}

export const listProjects = async () => (await get('/tracker/graph/')).projects
export const getGraph = (project) => get(`/tracker/graph/${project}/`)
export const getFlow = (project, start) => get(`/tracker/graph/${project}/flow/`, { start })

// A request the code map has no route for answers 404; that is "no match", not a failure.
export const matchRequest = async (project, method, path) => {
  try {
    return await get(`/tracker/graph/${project}/match/`, { method, path })
  } catch (err) {
    if (err.status === 404) return null
    throw err
  }
}
