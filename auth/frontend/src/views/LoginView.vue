<script setup>
import { ref } from 'vue'
import { startSession, whoAmI, refreshNow, breakAccessToken, replayOldToken, logOutOnServer, forgetSession, session } from '@/api/session'

const email = ref('')
const password = ref('')
const trace = ref(true)       // ask the server to trace these requests
const busy = ref(false)
const problem = ref('')
const fieldErrors = ref({})
const log = ref([])           // newest first: what the buttons did, with trace ids

function say(text, { bad = false, runs = [] } = {}) {
  log.value.unshift({ text, bad, runs })
}

async function run(action) {
  busy.value = true
  try {
    await action()
  } finally {
    busy.value = false
  }
}

function onLogin() {
  return run(async () => {
    problem.value = ''
    fieldErrors.value = {}
    log.value = []
    try {
      const result = await startSession({ email: email.value, password: password.value }, { trace: trace.value })
      password.value = ''
      say('Logged in. Two tokens are held in memory (not shown).', { runs: [{ label: 'login', id: result.runId }] })
      await askWho()
    } catch (err) {
      problem.value = err.message
      fieldErrors.value = err.fieldErrors
      if (err.runId) say(problem.value, { bad: true, runs: [{ label: 'login', id: err.runId }] })
    }
  })
}

async function askWho() {
  try {
    const me = await whoAmI({ trace: trace.value })
    say(
      me.refreshed
        ? `Access token was refused, so the page refreshed it automatically and tried again. Logged in as ${me.email}.`
        : `Logged in as ${me.email}.`,
      { runs: me.runs },
    )
  } catch (err) {
    say(err.message, { bad: true, runs: err.runs ?? [] })
    sessionOver(err)
  }
}

// If the server has ended the login, the page is back at the form: say why there.
function sessionOver(err) {
  if (!session.signedIn) problem.value = err.message
}

const onWho = () => run(askWho)

const onRefresh = () => run(async () => {
  try {
    const r = await refreshNow({ trace: trace.value })
    say('Refreshed. The old refresh token is now retired.', { runs: [{ label: 'refresh', id: r.runId }] })
  } catch (err) {
    say(err.message, { bad: true, runs: err.runId ? [{ label: 'refresh', id: err.runId }] : [] })
    sessionOver(err)
  }
})

const onBreak = () => {
  breakAccessToken()
  say('Access token damaged, as if its 15 minutes were up. Press "Who am I?" to see it refresh by itself.')
}

const onReplay = () => run(async () => {
  try {
    await replayOldToken({ trace: trace.value })
    say('The server accepted a retired token. That should never happen.', { bad: true })
  } catch (err) {
    say(`Replaying the previous refresh token: ${err.message}`, { bad: true, runs: err.runs ?? [] })
  }
})

const onLogout = (everywhere) => run(async () => {
  try {
    const r = await logOutOnServer({ everywhere, trace: trace.value })
    say(
      everywhere
        ? 'Logged out everywhere: every login of this account has been ended on the server.'
        : 'Logged out: this login has been ended on the server.',
      { runs: [{ label: 'logout', id: r.runId }] },
    )
  } catch (err) {
    say(err.message, { bad: true, runs: err.runId ? [{ label: 'logout', id: err.runId }] : [] })
  }
})

const onLeave = () => { forgetSession(); log.value = [] }
</script>

<template>
  <form v-if="!session.signedIn" @submit.prevent="onLogin">
    <h1>Log in</h1>

    <label>
      Email
      <input v-model="email" type="text" autocomplete="off" />
      <small v-for="m in fieldErrors.email" :key="m" class="bad">{{ m }}</small>
    </label>

    <label>
      Password
      <input v-model="password" type="password" autocomplete="off" />
      <small v-for="m in fieldErrors.password" :key="m" class="bad">{{ m }}</small>
    </label>

    <label class="inline">
      <input v-model="trace" type="checkbox" /> Trace these requests
    </label>

    <button type="submit" :disabled="busy">{{ busy ? 'Working…' : 'Log in' }}</button>

    <p v-if="problem" class="bad">{{ problem }}</p>
    <p v-for="(item, i) in log.slice(0, 1)" :key="i" class="hint">
      <template v-for="r in item.runs" :key="r.id">
        {{ r.label }}: <code>python manage.py show_trace {{ r.id }}</code><br />
      </template>
    </p>
  </form>

  <section v-else class="panel">
    <h1>Logged in</h1>
    <label class="inline">
      <input v-model="trace" type="checkbox" /> Trace these requests
    </label>

    <div class="buttons">
      <button :disabled="busy" @click="onWho">Who am I?</button>
      <button :disabled="busy" @click="onBreak">Break my access token</button>
      <button :disabled="busy" @click="onRefresh">Refresh now</button>
      <button :disabled="busy" @click="onLogout(false)">Log out</button>
      <button :disabled="busy" @click="onLogout(true)">Log out everywhere</button>
      <button :disabled="busy || !session.canReplay" @click="onReplay">Replay the previous refresh token</button>
      <button :disabled="busy" class="quiet" @click="onLeave">Forget the session (this page only)</button>
    </div>
    <p v-if="session.loggedOut" class="notice">
      You are logged out on the server. This page still holds the old tokens, so try
      <b>Who am I?</b> (the access token still answers until its 15 minutes are up) and
      <b>Refresh now</b> (the refresh token is dead).
    </p>
    <p class="hint">
      "Replay" plays a thief holding a stolen copy of the previous refresh token. It needs one
      "Refresh now" first, so that there is a previous token to replay.
    </p>

    <ul class="log">
      <li v-for="(item, i) in log" :key="log.length - i" :class="{ bad: item.bad }">
        {{ item.text }}
        <span v-for="r in item.runs" :key="r.id" class="run">
          {{ r.label }}: <code>show_trace {{ r.id }}</code>
        </span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
form, .panel { display: grid; gap: 1rem; background: #fff; padding: 1.5rem; border-radius: 8px; box-shadow: 0 1px 4px #0002; }
h1 { margin: 0; font-size: 1.3rem; }
label { display: grid; gap: .25rem; font-size: .9rem; }
label.inline { display: flex; gap: .5rem; align-items: center; }
input[type='text'], input[type='password'] { padding: .5rem; font-size: 1rem; }
button { padding: .6rem; font-size: 1rem; cursor: pointer; }
.buttons { display: grid; gap: .5rem; }
.quiet { background: none; border: 1px solid #d0d5dd; color: #52606d; }
.notice { margin: 0; padding: .6rem .8rem; background: #fff7e6; border: 1px solid #f0d9a8; border-radius: 6px; font-size: .9rem; }
.bad { color: #b42318; }
p.bad { margin: 0; }
.hint { font-size: .85rem; color: #52606d; margin: 0; }
.log { list-style: none; margin: 0; padding: 0; display: grid; gap: .5rem; font-size: .9rem; }
.log li { color: #1a7f37; }
.log li.bad { color: #b42318; }
.run { display: block; font-size: .8rem; color: #52606d; word-break: break-all; }
</style>
