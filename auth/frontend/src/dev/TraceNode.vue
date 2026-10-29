<script setup>
/**
 * TraceNode.vue: one traced function call, drawn as a card.
 *
 * It draws itself again for each child call, which is how the whole nested
 * tree appears. Inside a card, the checkpoints (the decisions made in this
 * function) and the child calls are shown in the order they happened.
 *
 * The coloured bar under the name is this call's share of the whole
 * request's time.
 */
import { computed, ref } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  totalMs: { type: Number, required: true },
  depth: { type: Number, default: 0 },
})

const open = ref(true)
const showArgs = ref(false)

const items = computed(() =>
  [
    ...props.node.checkpoints.map((c) => ({ kind: 'checkpoint', seq: c.seq, data: c })),
    ...props.node.children.map((c) => ({ kind: 'call', seq: c.seq, data: c })),
  ].sort((a, b) => a.seq - b.seq),
)

const argEntries = computed(() => Object.entries(props.node.args ?? {}))
const failed = computed(() => !!props.node.exception)
const barWidth = computed(() =>
  `${Math.max(1.5, Math.min(100, (props.node.elapsed_ms / (props.totalMs || 1)) * 100))}%`,
)
const ms = (v) => (v < 1 ? v.toFixed(2) : v.toFixed(1)) + ' ms'
</script>

<template>
  <div class="call" :class="{ failed }">
    <div class="head">
      <button
        v-if="items.length"
        class="twisty"
        :aria-label="open ? 'Collapse' : 'Expand'"
        @click="open = !open"
      >{{ open ? '▾' : '▸' }}</button>
      <span v-else class="twisty spacer"></span>

      <span class="name">{{ node.name }}</span>
      <span class="time">{{ ms(node.elapsed_ms) }}</span>

      <span v-if="failed" class="badge bad" :title="node.exception">raised: {{ node.exception }}</span>
      <span v-else-if="node.returned && node.returned !== 'None'" class="badge ok" :title="node.returned">
        → {{ node.returned }}
      </span>

      <button v-if="argEntries.length" class="link" @click="showArgs = !showArgs">
        {{ showArgs ? 'hide inputs' : `inputs (${argEntries.length})` }}
      </button>
    </div>

    <div class="bar"><div class="fill" :style="{ width: barWidth }"></div></div>

    <dl v-if="showArgs" class="kv">
      <template v-for="[k, v] in argEntries" :key="k">
        <dt>{{ k }}</dt>
        <dd>{{ v }}</dd>
      </template>
    </dl>

    <div v-if="open && items.length" class="body">
      <template v-for="item in items" :key="item.seq">
        <div v-if="item.kind === 'checkpoint'" class="checkpoint">
          <div class="cp-label">◆ {{ item.data.label }}</div>
          <dl class="kv">
            <template v-for="(v, k) in item.data.values" :key="k">
              <dt>{{ k }}</dt>
              <dd>{{ v }}</dd>
            </template>
          </dl>
        </div>
        <TraceNode v-else :node="item.data" :total-ms="totalMs" :depth="depth + 1" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.call {
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  border-radius: 8px;
  background: var(--card);
  padding: 10px 12px 8px;
  margin: 8px 0;
}
.call.failed { border-left-color: var(--bad); }
.head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.twisty { width: 18px; padding: 0; border: 0; background: none; color: var(--muted); font-size: 14px; cursor: pointer; }
.spacer { display: inline-block; }
.name { font: 600 14px ui-monospace, SFMono-Regular, Menlo, monospace; }
.time { color: var(--muted); font-size: 12px; margin-left: auto; }
.badge {
  font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
  padding: 2px 8px; border-radius: 999px;
  max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.badge.ok { background: var(--ok-bg); color: var(--ok); }
.badge.bad { background: var(--bad-bg); color: var(--bad); }
.link { border: 0; background: none; color: var(--accent); padding: 0; text-decoration: underline; font-size: 12px; cursor: pointer; }
.bar { height: 3px; background: var(--grey-bg); border-radius: 2px; margin: 8px 0 4px 28px; }
.fill { height: 100%; background: var(--accent); border-radius: 2px; opacity: .55; }
.failed .fill { background: var(--bad); }
.body { margin-left: 22px; }
.kv {
  display: grid; grid-template-columns: max-content 1fr; gap: 2px 12px;
  margin: 4px 0 4px 28px; font: 12.5px ui-monospace, SFMono-Regular, Menlo, monospace;
}
.kv dt { color: var(--muted); }
.kv dd { margin: 0; word-break: break-word; }
.checkpoint {
  border-left: 3px solid #d29922; background: #fdf6e3;
  border-radius: 4px; padding: 6px 10px; margin: 6px 0 6px 6px;
}
.checkpoint .kv { margin-left: 0; }
.cp-label { font-weight: 600; font-size: 13px; color: #8a6500; }
</style>
