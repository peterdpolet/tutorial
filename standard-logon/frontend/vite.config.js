import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The browser talks to Vite (port 5274). Anything under /api is forwarded to
// the Django server (port 8201), so the Vue code uses plain relative URLs and
// there is no CORS to set up. '@' is a shortcut for the src/ folder.
//
// strictPort: if 5274 is busy, fail loudly instead of quietly moving to
// another port, because Django builds the links in its emails from
// FRONTEND_URL (http://localhost:5274).
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5274,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8201',
    },
  },
})
