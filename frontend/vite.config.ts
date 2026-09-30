import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
  server: {
    // Proxy API calls to the Flask backend so the browser sees same-origin
    // requests regardless of which port Vite ends up on (avoids CORS entirely
    // in dev; the backend's CORS_ORIGINS allowlist only covers localhost:5173).
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
})
