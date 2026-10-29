<script setup>
import { ref } from 'vue'
import { registerAccount } from '@/api/auth'

const email = ref('')
const password = ref('')
const trace = ref(true)       // ask the server to trace this request
const busy = ref(false)
const done = ref('')
const problem = ref('')
const fieldErrors = ref({})
const runId = ref(null)

async function submit() {
  busy.value = true
  done.value = ''
  problem.value = ''
  fieldErrors.value = {}
  runId.value = null
  try {
    const result = await registerAccount(
      { email: email.value, password: password.value },
      { trace: trace.value },
    )
    done.value = result.detail
    runId.value = result.runId
    password.value = ''
  } catch (err) {
    problem.value = err.message
    fieldErrors.value = err.fieldErrors
    runId.value = err.runId
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form @submit.prevent="submit">
    <h1>Create an account</h1>

    <label>
      Email
      <input v-model="email" type="text" autocomplete="off" />
      <small v-for="m in fieldErrors.email" :key="m" class="bad">{{ m }}</small>
    </label>

    <label>
      Password
      <input v-model="password" type="password" autocomplete="new-password" />
      <small v-for="m in fieldErrors.password" :key="m" class="bad">{{ m }}</small>
    </label>

    <label class="inline">
      <input v-model="trace" type="checkbox" /> Trace this request
    </label>

    <button type="submit" :disabled="busy">{{ busy ? 'Working…' : 'Register' }}</button>

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
input[type='text'], input[type='password'] { padding: .5rem; font-size: 1rem; }
button { padding: .6rem; font-size: 1rem; cursor: pointer; }
.good { color: #1a7f37; margin: 0; }
.bad { color: #b42318; }
p.bad { margin: 0; }
.hint { font-size: .85rem; color: #52606d; margin: 0; }
</style>
