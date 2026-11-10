<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <section class="card">
    <h1>{{ route.meta.title }}</h1>
    <p><span class="tag">stub</span></p>
    <p>
      This page is a placeholder in the template. The real page is built in:
      <strong>{{ route.meta.episode }}</strong>.
    </p>
  </section>
</template>
