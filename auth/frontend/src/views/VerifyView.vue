<script setup>
/**
 * VerifyView.vue: where the link in the confirmation email lands.
 *
 *   http://localhost:5273/verify?token=...
 *
 * The page reads the token from the address and waits. Nothing is sent until
 * the person presses the button: that press is the start of the flow.
 */
import { ref } from 'vue'
import { verifyEmail } from '@/api/auth'

const token = new URLSearchParams(window.location.search).get('token') ?? ''
const trace = ref(true)       // ask the server to trace this request
const busy = ref(false)
const done = ref('')
const problem = ref('')
const runId = ref(null)

async function confirm() {
  busy.value = true
  done.value = ''
  problem.value = ''
  runId.value = null
  try {
    const result = await verifyEmail({ token }, { trace: trace.value })
    done.value = result.detail
    runId.value = result.runId
  } catch (err) {
    problem.value = err.fieldErrors?.token?.[0] ?? err.message
    runId.value = err.runId
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section>
    <h1>Confirm your email</h1>

    <p v-if="!token" class="bad">This page needs the link from your email.</p>
    <template v-else>
      <label class="inline">
        <input v-model="trace" type="checkbox" /> Trace this request
      </label>
      <button type="button" :disabled="busy" @click="confirm">
        {{ busy ? 'Working…' : 'Confirm my email' }}
      </button>
    </template>

    <p v-if="done" class="good">{{ done }}</p>
    <p v-if="problem" class="bad">{{ problem }}</p>
    <p v-if="runId" class="hint">
      Traced. In the backend folder run: <code>python manage.py show_trace {{ runId }}</code>
    </p>
  </section>
</template>

<style scoped>
section { display: grid; gap: 1rem; background: #fff; padding: 1.5rem; border-radius: 8px; box-shadow: 0 1px 4px #0002; }
h1 { margin: 0; font-size: 1.3rem; }
label.inline { display: flex; gap: .5rem; align-items: center; font-size: .9rem; }
button { padding: .6rem; font-size: 1rem; cursor: pointer; }
.good { color: #1a7f37; margin: 0; }
.bad { color: #b42318; margin: 0; }
.hint { font-size: .85rem; color: #52606d; margin: 0; }
</style>
