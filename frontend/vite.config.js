import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, /api and /ws go to the local backend (uvicorn on :8000).
// `npm run demo` (mode "demo") needs no backend at all: see src/demo/.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  test: { environment: 'node', include: ['src/**/*.test.js'] },
})
