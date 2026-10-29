import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The browser talks to Vite (port 5273). Anything under /api is forwarded to
// the Django server (port 8200), so the Vue code uses plain relative URLs and
// there is no CORS to set up. '@' is a shortcut for the src/ folder.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5273,
    proxy: {
      '/api': 'http://127.0.0.1:8200',
    },
  },
})
