import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: proxy the API to the FastAPI server. Production: FastAPI serves the build (same origin).
// __BUILD_TIME__ is stamped into the bundle so the footer shows which build you are looking at.
export default defineConfig({
  plugins: [react()],
  define: { __BUILD_TIME__: JSON.stringify(new Date().toISOString()) },
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000' } },
})
