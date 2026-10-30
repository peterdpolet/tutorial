<script setup>
/**
 * App.vue: the tutorial's one screen, with development tools.
 *
 *   Register   the real screen (RegisterView.vue)
 *   Flow       the process map with a saved trace laid over it   (development only)
 *   Traces     saved traces as a call tree                       (development only)
 *
 * The two tools tabs exist only while running `npm run dev` (import.meta.env.DEV)
 * and are left out of a production build, so they cannot reach a live site.
 */
import { ref, defineAsyncComponent } from 'vue'
import RegisterView from '@/views/RegisterView.vue'
import VerifyView from '@/views/VerifyView.vue'

const dev = import.meta.env.DEV

// Loaded only when running `npm run dev`. In a production build `dev` is the
// constant false, so Vite drops these imports and the tools are not shipped.
const FlowView = dev ? defineAsyncComponent(() => import('@/dev/FlowView.vue')) : null
const TraceViewer = dev ? defineAsyncComponent(() => import('@/dev/TraceViewer.vue')) : null
if (dev) import('@/dev/devtools.css')
// The link in the confirmation email opens /verify?token=...; there is no router yet.
const onVerifyPage = window.location.pathname === '/verify'
const tab = ref('register')   // 'register' | 'flow' | 'traces'
</script>

<template>
  <main :class="{ wide: !onVerifyPage && tab !== 'register' }">
    <VerifyView v-if="onVerifyPage" />

    <template v-else>
    <nav v-if="dev" class="tabs">
      <button :class="{ on: tab === 'register' }" @click="tab = 'register'">Register</button>
      <button :class="{ on: tab === 'flow' }" @click="tab = 'flow'">Flow</button>
      <button :class="{ on: tab === 'traces' }" @click="tab = 'traces'">Traces</button>
    </nav>

    <RegisterView v-if="tab === 'register'" />
    <FlowView v-if="dev && tab === 'flow'" />
    <TraceViewer v-if="dev && tab === 'traces'" />
    </template>
  </main>
</template>

<style>
body { font-family: system-ui, sans-serif; margin: 0; background: #f6f7f9; color: #1c2430; }
main { max-width: 26rem; margin: 3rem auto; padding: 0 1rem; }
main.wide { max-width: 1100px; }
.tabs { display: flex; gap: 4px; margin: 0 0 16px; border-bottom: 1px solid #e4e7ec; }
.tabs button { background: none; border: 0; color: #667085; border-radius: 6px 6px 0 0; padding: 8px 14px; font-size: 1rem; cursor: pointer; }
.tabs button.on { color: #1d2433; font-weight: 600; box-shadow: inset 0 -2px 0 #2f5fd0; }
</style>
