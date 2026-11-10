<script setup>
import { menuItems } from '@/router.js'
</script>

<template>
  <header class="app-header">
    <div class="inner">
      <span class="brand">Standard logon</span>
      <nav>
        <RouterLink v-for="item in menuItems" :key="item.name" :to="item.path">
          {{ item.label }}
        </RouterLink>
      </nav>
    </div>
  </header>

  <main>
    <RouterView />
  </main>

  <footer class="app-footer">
    A tutorial template: a main menu and stub pages that each episode fills in.
  </footer>
</template>
