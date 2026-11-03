<script setup>
/**
 * AdminView.vue: the list of accounts, and buttons to change a role.
 *
 * Read this with one rule in mind: HIDING a button is a courtesy, not security.
 * This page shows the table to anyone who presses "Load accounts" and lets the
 * SERVER decide. A member who presses it gets a 403, and that refusal is the
 * rule. If the buttons were the only thing standing in the way, anyone could
 * send the same request from a terminal and skip them.
 *
 * You must be logged in first (Log in tab). The login is kept in memory by
 * api/session.js, so switching tabs does not lose it.
 */
import { ref } from 'vue'
import { listAccounts, changeRole, session } from '@/api/session'

const trace = ref(true)
const busy = ref(false)
const users = ref(null)         // null = not loaded yet
const problem = ref('')
const note = ref('')
const runs = ref([])            // newest first: { label, id }
const tryId = ref('')           // "send the request yourself": what a script would send
const tryRole = ref('admin')

function remember(label, id) {
  if (id) runs.value.unshift({ label, id })
}

async function load() {
  busy.value = true
  problem.value = ''
  note.value = ''
  try {
    const result = await listAccounts({ trace: trace.value })
    users.value = result.users
    remember('list', result.runId)
  } catch (err) {
    users.value = null
    problem.value = explain(err)
    remember('list (refused)', err.runId)
  } finally {
    busy.value = false
  }
}

async function setRole(user, role) {
  busy.value = true
  problem.value = ''
  note.value = ''
  try {
    const result = await changeRole({ userId: user.id, role, trace: trace.value })
    remember('change role', result.runId)
    note.value = `${user.email} is now ${role}.`
    try {
      const fresh = await listAccounts({ trace: trace.value })     // refresh the table, if we may see it
      users.value = fresh.users
    } catch {
      /* not allowed to see the table: the change itself still stands */
    }
  } catch (err) {
    problem.value = explain(err)
    remember('change role (refused)', err.runId)
  } finally {
    busy.value = false
  }
}

// The same request the buttons send, without the table. A member has no table and no buttons,
// but a script does not need them: this is what a script does. The server must still say no.
async function sendYourself() {
  const id = tryId.value.trim() === '' ? null : Number(tryId.value)
  const userId = Number.isInteger(id) ? id : tryId.value          // let a bad id reach the server as typed
  await setRole({ id: userId, email: `account ${tryId.value}` }, tryRole.value)
}

// The status tells you WHICH question the server said no to.
function explain(err) {
  if (!session.signedIn) return 'Log in first (Log in tab). Then come back here.'
  if (err.status === 401) return `Not logged in (401): ${err.message}`
  if (err.status === 403) return `Refused (403): you are logged in, but you are not an admin.`
  return `${err.message} (${err.status})`
}
</script>

<template>
  <section>
    <h1>Accounts</h1>
    <p class="hint">
      Admins only. Anyone can press the button; the server decides. Make the first admin
      in a terminal: <code>python manage.py make_admin --email you@example.com</code>
    </p>

    <label class="inline">
      <input v-model="trace" type="checkbox" /> Trace these requests
    </label>
    <button type="button" :disabled="busy" @click="load">{{ busy ? 'Working…' : 'Load accounts' }}</button>

    <p v-if="problem" class="bad">{{ problem }}</p>
    <p v-if="note" class="good">{{ note }}</p>

    <table v-if="users">
      <thead><tr><th>Id</th><th>Account</th><th>Role</th><th></th></tr></thead>
      <tbody>
        <tr v-for="u in users" :key="u.id">
          <td>{{ u.id }}</td>
          <td>{{ u.email }}<span v-if="!u.active" class="off"> (switched off)</span></td>
          <td><b>{{ u.role }}</b></td>
          <td>
            <button v-if="u.role !== 'admin'" type="button" :disabled="busy" @click="setRole(u, 'admin')">Make admin</button>
            <button v-else type="button" class="quiet" :disabled="busy" @click="setRole(u, 'member')">Make member</button>
          </td>
        </tr>
      </tbody>
    </table>

    <form class="direct" @submit.prevent="sendYourself">
      <h2>Send the request yourself</h2>
      <p class="hint">
        What a script would do, with no table and no buttons. Try it as a member: the
        buttons are not the rule, the server is.
      </p>
      <label>Account id <input v-model="tryId" type="text" autocomplete="off" /></label>
      <label>Role <input v-model="tryRole" type="text" autocomplete="off" /></label>
      <button type="submit" :disabled="busy">Send</button>
    </form>

    <ul v-if="runs.length" class="runs">
      <li v-for="(r, i) in runs.slice(0, 6)" :key="runs.length - i">
        {{ r.label }}: <code>python manage.py show_trace {{ r.id }}</code>
      </li>
    </ul>
  </section>
</template>

<style scoped>
section { display: grid; gap: 1rem; background: #fff; padding: 1.5rem; border-radius: 8px; box-shadow: 0 1px 4px #0002; }
h1 { margin: 0; font-size: 1.3rem; }
h2 { margin: 0; font-size: 1rem; }
.direct { display: grid; gap: .6rem; border-top: 1px solid #e4e7ec; padding-top: 1rem; }
.direct label { display: grid; gap: .2rem; font-size: .9rem; }
.direct input { padding: .4rem; font-size: 1rem; }
label.inline { display: flex; gap: .5rem; align-items: center; font-size: .9rem; }
button { padding: .5rem .8rem; font-size: .95rem; cursor: pointer; }
.quiet { background: none; border: 1px solid #d0d5dd; color: #52606d; }
table { border-collapse: collapse; font-size: .9rem; width: 100%; }
th, td { text-align: left; padding: .4rem .3rem; border-bottom: 1px solid #e4e7ec; }
td:nth-child(2) { word-break: break-all; }     /* only the address may break anywhere */
td:nth-child(1), td:nth-child(3), td button { white-space: nowrap; }
.off { color: #b42318; font-size: .8rem; }
.good { color: #1a7f37; margin: 0; }
.bad { color: #b42318; margin: 0; }
.hint { font-size: .85rem; color: #52606d; margin: 0; }
.runs { list-style: none; margin: 0; padding: 0; display: grid; gap: .4rem; font-size: .8rem; color: #52606d; word-break: break-all; }
</style>
