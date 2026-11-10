<script setup>
import { onMounted, ref } from 'vue'
import client from '@/api/client.js'

const result = ref(null)
const failure = ref('')
const loading = ref(false)

async function check() {
  loading.value = true
  failure.value = ''
  try {
    const response = await client.get('/health/')
    result.value = response.data
  } catch (error) {
    // A 503 still carries the service's answer ("degraded"); show it.
    // No response at all means the back end is not reachable.
    if (error.response && error.response.data && error.response.data.status) {
      result.value = error.response.data
    } else {
      result.value = null
      failure.value = 'The back end did not answer. Is Django running on port 8201?'
    }
  } finally {
    loading.value = false
  }
}

onMounted(check)
</script>

<template>
  <section class="card">
    <h1>Health</h1>
    <p v-if="loading">Checking...</p>
    <template v-else>
      <p v-if="failure" class="bad">{{ failure }}</p>
      <template v-else-if="result">
        <p>
          Status:
          <strong :class="result.status === 'ok' ? 'ok' : 'bad'">{{ result.status }}</strong>
        </p>
        <p>Database: <code>{{ result.database }}</code></p>
      </template>
    </template>
    <button :disabled="loading" @click="check">Check again</button>
  </section>
</template>
