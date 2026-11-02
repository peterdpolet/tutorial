<script setup>
/**
 * ForgotView.vue: "I forgot my password". Asks for a reset link.
 *
 * The server answers with the same sentence whether or not the address has an
 * account, so this screen can never tell you which it was. Look in the backend
 * terminal (the console email backend prints the email there) to see whether a
 * link was really sent.
 */
import { ref } from 'vue'
import { forgotPassword } from '@/api/auth'

const email = ref('')
const trace = ref(true)       // ask the server to trace this request
const busy = ref(false)
const done = ref('')
const problem = ref('')
const runId = ref(null)

async function submit() {
  busy.value = true
  done.value = ''
  problem.value = ''
  runId.value = null
  try {
    const result = await forgotPassword({ email: email.value }, { trace: trace.value })
    done.value = result.detail
    runId.value = result.runId
  } catch (err) {
    problem.value = err.fieldErrors?.email?.[0] ?? err.message
    runId.value = err.runId
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form @submit.prevent="submit">
    <h1>Forgot your password?</h1>
    <p class="hint">Type your email and we will send a link to choose a new one.</p>

    <label>
      Email
      <input v-model="email" type="text" autocomplete="off" />
    </label>

    <label class="inline">
      <input v-model="trace" type="checkbox" /> Trace this request
    </label>

    <button type="submit" :disabled="busy">{{ busy ? 'Working…' : 'Send me a link' }}</button>

    <p v-if="done" class="good">{{ done }}</p>
    <p v-if="problem" class="bad">{{ problem }}</p>
    <p v-if="runId" class="hint">
      Traced. In the backend folder run: <code>python manage.py show_trace {{ runId }}</code>
    </p>
  </form>
</template>

<style scoped>
form { display: grid; gap: 1rem; background: #fff; padding: 1.5rem; border-radius: 8px; box-shadow: 0 1px 4px #0002; }
h1 { margin: 0; font-size: 1.3rem; }
label { display: grid; gap: .25rem; font-size: .9rem; }
label.inline { display: flex; gap: .5rem; align-items: center; }
input[type='text'] { padding: .5rem; font-size: 1rem; }
button { padding: .6rem; font-size: 1rem; cursor: pointer; }
.good { color: #1a7f37; margin: 0; }
.bad { color: #b42318; margin: 0; }
.hint { font-size: .85rem; color: #52606d; margin: 0; }
</style>
