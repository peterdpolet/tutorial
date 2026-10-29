<script setup>
/**
 * FlowView.vue: the code map as a diagram, with one recorded trace laid over it.
 *
 * Two sources, joined here in the browser:
 *   the map     what the code COULD do   (graph API, written by discover/)
 *   the trace   what ONE request DID     (runs API, written by @traced)
 *
 * The join is by name. A traced function keeps its trace name in the map
 * (extra.traced_name), so a call named "Quote.convert_to_po" in the trace lights
 * up the node with that traced_name. The URL route is matched from the recorded
 * method and path. Nodes the request never reached stay dim: that is the point,
 * they are the paths NOT taken.
 */
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import dagre from '@dagrejs/dagre'
import { listProjects, getGraph, getFlow, matchRequest } from '@/api/graph'
import { listRuns, getRun } from '@/api/traces'

const project = ref('')
const flow = ref(null)            // { entities, relations } reachable from `start`
const start = ref('')
const startChoices = ref([])
const runs = ref([])
const runId = ref('')
const calls = ref({})             // trace name -> the call recorded in the trace
const routeIds = ref(new Set())   // url + handler entity ids matched from the request
const chosen = ref(null)          // node clicked, for the detail panel
const error = ref('')
const scroller = ref(null)       // the scrolling frame around the diagram

const NODE_W = 210
const NODE_H = 44

// ---- loading -------------------------------------------------------------

onMounted(async () => {
  try {
    const projects = await listProjects()
    if (!projects.length) {
      error.value = 'No code map loaded yet. Run discover/discover.py, then: python manage.py load_graph <graph.json>'
      return
    }
    project.value = projects[0]
    const all = await getGraph(project.value)
    // The development tools' own buttons are not part of the app being studied.
    startChoices.value = all.entities.filter(
      (e) => ['ui_action', 'url', 'view'].includes(e.kind) && !e.id.includes('/src/dev/'),
    )
    // Default: the user action that sets the most code in motion (the biggest flow).
    const actions = startChoices.value.filter((e) => e.kind === 'ui_action')
    const sizes = await Promise.all(
      actions.map(async (e) => ({ e, n: (await getFlow(project.value, e.id)).entities.length })),
    )
    const wanted = sizes.sort((a, b) => b.n - a.n)[0]?.e ?? startChoices.value[0]
    runs.value = await listRuns()
    if (wanted) start.value = wanted.id
  } catch (err) {
    error.value = err.message
  }
})

watch(start, async (id) => {
  if (!id) return
  chosen.value = null
  try {
    flow.value = await getFlow(project.value, id)
  } catch (err) {
    error.value = err.message
  }
})

watch(runId, async (id) => {
  calls.value = {}
  routeIds.value = new Set()
  chosen.value = null
  if (!id) return
  try {
    const run = await getRun(id)
    const byName = {}
    const walk = (list) => list.forEach((c) => { byName[c.name] = c; walk(c.children) })
    walk(run.calls)
    calls.value = byName
    const found = await matchRequest(project.value, run.method, run.path)
    if (found) routeIds.value = new Set([found.url.id, ...found.handlers])
    await nextTick()
    scrollToFirstRan()
  } catch (err) {
    error.value = err.message
  }
})

// The diagram is wider than the screen, so jump to where the trace starts
function scrollToFirstRan() {
  if (!scroller.value || !layout.value) return
  const first = layout.value.nodes.filter((n) => ran(n.e)).sort((a, b) => a.x - b.x)[0]
  scroller.value.scrollTo({ left: first ? Math.max(first.x - NODE_W, 0) : 0, behavior: 'smooth' })
}

// ---- the diagram -----------------------------------------------------------

const ranCall = (e) => calls.value[e.extra?.traced_name] ?? null
const ran = (e) => !!ranCall(e) || routeIds.value.has(e.id)
const overlayOn = computed(() => !!runId.value)

const layout = computed(() => {
  if (!flow.value) return null
  const g = new dagre.graphlib.Graph({ multigraph: true })
  g.setGraph({ rankdir: 'LR', nodesep: 14, ranksep: 44, marginx: 12, marginy: 12 })
    flow.value.entities.forEach((e) => g.setNode(e.id, { width: NODE_W, height: NODE_H }))
  flow.value.relations.forEach((r) => g.setEdge(r.source_id, r.target_id, {}, r.relation_type))
  dagre.layout(g)
  const nodes = flow.value.entities.map((e) => ({ e, ...g.node(e.id) }))
  const edges = flow.value.relations.map((r) => ({
    r,
    points: g.edge({ v: r.source_id, w: r.target_id, name: r.relation_type }).points,
  }))
  const { width, height } = g.graph()
  return { nodes, edges, width, height }
})

const ms = (v) => Number(v).toFixed(2)
const path = (pts) => pts.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' ')
const label = (e) => (e.name.length > 32 ? e.name.slice(0, 31) + '…' : e.name)
const layerOf = (e) =>
  e.kind === 'url' ? 'route'
  : e.language === 'python' ? 'django'
  : 'vue'

const edgeLit = (ed) => {
  const s = layout.value.nodes.find((n) => n.e.id === ed.r.source_id)
  const t = layout.value.nodes.find((n) => n.e.id === ed.r.target_id)
  return overlayOn.value && s && t && ran(s.e) && ran(t.e)
}
const ranCount = computed(() => (layout.value ? layout.value.nodes.filter((n) => ran(n.e)).length : 0))
</script>

<template>
  <section>
    <p class="muted">
      The code map: everything reachable from one starting point. Pick a trace to
      light up what that request ran. A dim box was not run by it, or is not marked
      <code>@traced</code> so the trace cannot see it.
    </p>
    <p v-if="error" class="bad">{{ error }}</p>

    <div class="flow-controls">
      <label>Start from
        <select v-model="start">
          <option v-for="e in startChoices" :key="e.id" :value="e.id">{{ e.kind }}: {{ e.name }} ({{ e.file.split('/').pop() }})</option>
        </select>
      </label>
      <label>Overlay trace
        <select v-model="runId">
          <option value="">(none)</option>
          <option v-for="r in runs" :key="r.id" :value="r.id">
            {{ r.method }} {{ r.path }} · {{ r.status_code }} · {{ new Date(r.started_at).toLocaleTimeString() }}
          </option>
        </select>
      </label>
      <span v-if="overlayOn" class="muted">{{ ranCount }} of {{ layout?.nodes.length }} boxes ran</span>
    </div>

    <div class="flow-legend">
      <span class="sw vue"></span>Vue <span class="sw route"></span>Route <span class="sw django"></span>Django
      <span class="sw lit"></span>ran in this trace <span class="muted">· dashed arrow = inferred link</span>
    </div>

    <div v-if="layout" class="flow-wrap">
      <div class="flow-scroll" ref="scroller">
        <svg class="flow-svg" :width="layout.width" :height="layout.height" :viewBox="`0 0 ${layout.width} ${layout.height}`">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#98a2b3" />
            </marker>
            <marker id="arrow-lit" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#2f5fd0" />
            </marker>
          </defs>
          <path v-for="(ed, i) in layout.edges" :key="i" :d="path(ed.points)" fill="none"
                :class="['edge', { lit: edgeLit(ed), dim: overlayOn && !edgeLit(ed), inferred: ed.r.extra?.inferred }]"
                :marker-end="edgeLit(ed) ? 'url(#arrow-lit)' : 'url(#arrow)'">
            <title>{{ ed.r.relation_type }}{{ ed.r.extra?.inferred ? ' (inferred)' : '' }}</title>
          </path>
          <g v-for="n in layout.nodes" :key="n.e.id"
             :class="['node', layerOf(n.e), { lit: overlayOn && ran(n.e), dim: overlayOn && !ran(n.e), chosen: chosen?.id === n.e.id }]"
             :transform="`translate(${n.x - NODE_W / 2},${n.y - NODE_H / 2})`" @click="chosen = n.e">
            <rect :width="NODE_W" :height="NODE_H" rx="8" />
            <text x="10" y="19" class="name">{{ label(n.e) }}</text>
            <text x="10" y="35" class="sub">
              {{ n.e.kind }}<template v-if="ranCall(n.e)"> · {{ ms(ranCall(n.e).elapsed_ms) }} ms</template>
            </text>
            <title>{{ n.e.name }}</title>
          </g>
        </svg>
      </div>

      <aside class="flow-detail">
        <p v-if="!chosen" class="muted">Click a box.</p>
        <template v-else>
          <h3>{{ chosen.name }}</h3>
          <p class="muted">{{ chosen.kind }} · {{ chosen.file }}<template v-if="chosen.line">:{{ chosen.line }}</template></p>
          <p v-if="chosen.docstring">{{ chosen.docstring }}</p>
          <p v-if="chosen.extra?.traced_name" class="muted">Trace name: <code>{{ chosen.extra.traced_name }}</code></p>
          <template v-if="ranCall(chosen)">
            <h4>In this trace</h4>
            <p class="muted">{{ ms(ranCall(chosen).elapsed_ms) }} ms</p>
            <pre v-if="Object.keys(ranCall(chosen).args || {}).length">{{ JSON.stringify(ranCall(chosen).args, null, 1) }}</pre>
            <p v-if="ranCall(chosen).returned">Returned <code>{{ ranCall(chosen).returned }}</code></p>
            <p v-if="ranCall(chosen).exception" class="bad">Raised {{ ranCall(chosen).exception }}</p>
            <div v-for="(cp, i) in ranCall(chosen).checkpoints" :key="i" class="cp">
              <strong>{{ cp.label }}</strong>
              <div v-for="(v, k) in cp.values" :key="k"><span class="muted">{{ k }}</span> {{ v }}</div>
            </div>
          </template>
          <p v-else-if="overlayOn" class="muted">Not run by this trace.</p>
        </template>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.flow-svg { display: block; }
.flow-controls { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; margin: 12px 0 8px; }
.flow-controls select { margin-left: 6px; padding: 4px 6px; max-width: 340px; }
.flow-legend { display: flex; gap: 6px; align-items: center; font-size: 13px; color: var(--muted); margin-bottom: 10px; }
.sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; margin-left: 10px; border: 1.5px solid; }
.sw.vue { background: #e6f6ee; border-color: #4aa57a; }
.sw.route { background: #fdf0e1; border-color: #d9903d; }
.sw.django { background: #e8eefc; border-color: #6b87d6; }
.sw.lit { background: #fff; border-color: var(--accent); border-width: 3px; }
.flow-wrap { display: grid; grid-template-columns: 1fr; gap: 14px; }
.flow-scroll { overflow: auto; background: var(--card); border: 1px solid var(--line); border-radius: 10px; }
.flow-detail { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; font-size: 14px; }
.flow-detail h3 { margin: 0 0 4px; font-size: 15px; word-break: break-word; }
.flow-detail h4 { margin: 12px 0 2px; }
.flow-detail pre { background: var(--grey-bg); padding: 6px; border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-word; }
.cp { background: #fdf5e1; border-left: 3px solid #d9a53d; padding: 4px 8px; margin: 6px 0; font-size: 13px; }
.edge { stroke: #98a2b3; stroke-width: 1.4; }
.edge.inferred { stroke-dasharray: 5 4; }
.edge.lit { stroke: var(--accent); stroke-width: 2.4; }
.edge.dim { opacity: 0.25; }
.node { cursor: pointer; }
.node rect { stroke-width: 1.5; }
.node.vue rect { fill: #e6f6ee; stroke: #4aa57a; }
.node.route rect { fill: #fdf0e1; stroke: #d9903d; }
.node.django rect { fill: #e8eefc; stroke: #6b87d6; }
.node.lit rect { stroke: var(--accent); stroke-width: 3.5; }
.node.dim { opacity: 0.35; }
.node.chosen rect { stroke-dasharray: 4 2; }
.node .name { font: 600 12px system-ui, sans-serif; fill: var(--ink); }
.node .sub { font: 11px system-ui, sans-serif; fill: var(--muted); }
.bad { color: var(--bad); }
.muted { color: var(--muted); }
</style>
