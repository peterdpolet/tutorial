<script setup>
/**
 * TwoFactorPanel.vue: turn two-factor on, from the logged-in screen (episode 7).
 *
 *   1. "Set up two-factor"   the server makes a secret and shows it ONCE
 *   2. type it into an authenticator app (or use the dev command, below)
 *   3. type the code the app shows   -> it switches on, and recovery codes appear ONCE
 *
 * An authenticator app normally reads a QR code. The tutorial has no QR code
 * library, so type the secret in by hand ("enter a setup key").
 */
import { ref } from 'vue'
import { setUpTwoFactor, confirmTwoFactor } from '@/api/session'

const stage = ref('idle')       // 'idle' | 'pending' | 'on'
const secret = ref('')
const code = ref('')
const recoveryCodes = ref([])
const trace = ref(true)
const busy = ref(false)
const problem = ref('')
const runIds = ref([])

async function start() {
  busy.value = true
  problem.value = ''
  runIds.value = []
  try {
    const result = await setUpTwoFactor({ trace: trace.value })
    secret.value = result.secret
    stage.value = 'pending'
    if (result.runId) runIds.value.push({ label: 'setup', id: result.runId })
  } catch (err) {
    problem.value = err.message
    if (err.runId) runIds.value.push({ label: 'setup', id: err.runId })
  } finally {
    busy.value = false
  }
}

async function confirm() {
  busy.value = true
  problem.value = ''
  try {
    const result = await confirmTwoFactor({ code: code.value, trace: trace.value })
    recoveryCodes.value = result.recoveryCodes
    stage.value = 'on'
    secret.value = ''
    code.value = ''
    if (result.runId) runIds.value.push({ label: 'confirm', id: result.runId })
  } catch (err) {
    problem.value = err.message
    if (err.runId) runIds.value.push({ label: 'confirm', id: err.runId })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="box">
    <h2>Two-factor</h2>

    <template v-if="stage === 'idle'">
      <p class="hint">Ask for a code from an authenticator app every time you log in.</p>
      <button type="button" :disabled="busy" @click="start">Set up two-factor</button>
    </template>

    <template v-else-if="stage === 'pending'">
      <p class="hint">
        Add an account in your authenticator app, choose "enter a setup key", and type this key
        (spaces do not matter). It is shown once.
      </p>
      <code class="secret">{{ secret }}</code>
      <p class="hint">
        No phone handy? In the backend folder run
        <code>python manage.py show_code --email you@example.com</code>
      </p>
      <label>
        The code the app shows now
        <input v-model="code" type="text" inputmode="numeric" autocomplete="off" />
      </label>
      <button type="button" :disabled="busy" @click="confirm">Switch it on</button>
    </template>

    <template v-else>
      <p class="good">Two-factor is on. Your next login will ask for a code.</p>
      <p class="hint">
        Keep these recovery codes somewhere safe. Each works once, if you lose your phone. They
        are shown now and never again.
      </p>
      <ul class="codes">
        <li v-for="c in recoveryCodes" :key="c"><code>{{ c }}</code></li>
      </ul>
    </template>

    <label class="inline"><input v-model="trace" type="checkbox" /> Trace these requests</label>
    <p v-if="problem" class="bad">{{ problem }}</p>
    <p v-for="r in runIds" :key="r.id" class="hint">
      {{ r.label }}: <code>python manage.py show_trace {{ r.id }}</code>
    </p>
  </div>
</template>

<style scoped>
.box { display: grid; gap: .6rem; border-top: 1px solid #e4e7ec; padding-top: 1rem; }
h2 { margin: 0; font-size: 1.05rem; }
label { display: grid; gap: .25rem; font-size: .9rem; }
label.inline { display: flex; gap: .5rem; align-items: center; }
input[type='text'] { padding: .5rem; font-size: 1rem; }
button { padding: .6rem; font-size: 1rem; cursor: pointer; }
.secret { display: block; padding: .6rem; background: #f2f4f7; border-radius: 6px; word-break: break-all; font-size: 1rem; }
.codes { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: 1fr 1fr; gap: .25rem; }
.good { color: #1a7f37; margin: 0; }
.bad { color: #b42318; margin: 0; }
.hint { font-size: .85rem; color: #52606d; margin: 0; word-break: break-word; }
</style>
