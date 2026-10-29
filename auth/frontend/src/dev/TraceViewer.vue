<script setup>
/**
 * TraceViewer.vue: recent traces on the left, the chosen one drawn as a tree
 * of calls on the right.
 *
 * Everything shown here was read back from the database through the tracker
 * API; nothing is carried over from the page that triggered the request.
 */
import { ref, computed, watch, onMounted } from 'vue'
import { listRuns, getRun } from '@/api/traces'
import TraceNode from './TraceNode.vue'

const props = defineProps({ runId: { type: String, default: null } })

const runs = ref([])
const selected = ref(null)       // the full tree of the chosen run
const loading = ref(false)
const error = ref('')

const totalMs = computed(() =>
  selected.value ? Math.max(...selected.value.calls.map((c) => c.elapsed_ms), 0.001) : 1,
)

async function loadRuns() {
  try {
    runs.value = await listRuns()
  } catch (err) {
    error.value = `Could not load traces: ${err.message}`
  }
}

async function open(id) {
  loading.value = true
  error.value = ''
  try {
    selected.value = await getRun(id)
  } catch (err) {
    error.value = `Could not load that trace: ${err.message}`
  } finally {
    loading.value = false
  }
}

const when = (iso) => new Date(iso).toLocaleTimeString()

onMounted(async () => {
  await loadRuns()
  const first = props.runId ?? runs.value[0]?.id
  if (first) await open(first)
})
watch(() => props.runId, async (id) => {
  if (id) {
    await loadRuns()
    await open(id)
  }
})
</script>

<template>
  <div class="viewer">
    <aside>
      <h2>Recent traces</h2>
      <p v-if="!runs.length" class="muted small">
        None yet. Register with “Trace this request” ticked, then come back.
      </p>
      <button
        v-for="r in runs"
        :key="r.id"
        class="run"
        :class="{ on: selected?.id === r.id }"
        @click="open(r.id)"
      >
        <span class="path">{{ r.method }} {{ r.path }}</span>
        <span class="meta">
          <span class="status" :class="r.status_code < 400 ? 'good' : 'bad'">{{ r.status_code }}</span>
          {{ when(r.started_at) }} · {{ r.duration_ms.toFixed(0) }} ms
        </span>
      </button>
    </aside>

    <section>
      <p v-if="error" class="panel refused">{{ error }}</p>
      <p v-else-if="loading" class="muted">Loading…</p>
      <template v-else-if="selected">
        <h2>
          {{ selected.method }} {{ selected.path }}
          <span class="status" :class="selected.status_code < 400 ? 'good' : 'bad'">{{ selected.status_code }}</span>
        </h2>
        <p class="muted small">
          {{ selected.duration_ms.toFixed(1) }} ms in total · {{ selected.event_count }} recorded events.
          Each card is one traced function; amber boxes are the decisions it made, with the values behind them.
        </p>
        <TraceNode v-for="c in selected.calls" :key="c.seq" :node="c" :total-ms="totalMs" />
      </template>
      <p v-else class="muted">Pick a trace on the left.</p>
    </section>
  </div>
</template>

<style scoped>
.viewer { display: grid; grid-template-columns: 280px 1fr; gap: 24px; align-items: start; }
@media (max-width: 800px) { .viewer { grid-template-columns: 1fr; } }
h2 { font-size: 16px; margin: 0 0 10px; }
.muted { color: var(--muted); }
.small { font-size: 13px; }
aside { display: flex; flex-direction: column; gap: 6px; }
.run {
  text-align: left; background: var(--card); color: var(--ink);
  border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; cursor: pointer;
  display: flex; flex-direction: column; gap: 2px;
}
.run.on { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.path { font: 600 13px ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; }
.meta { font-size: 12px; color: var(--muted); }
.status { font-size: 12px; padding: 1px 7px; border-radius: 999px; }
.status.good { background: var(--ok-bg); color: var(--ok); }
.status.bad { background: var(--bad-bg); color: var(--bad); }
.panel { padding: 12px 14px; border-radius: 8px; border: 1px solid var(--line); }
.panel.refused { background: var(--bad-bg); border-color: #f5c2bd; }
</style>
