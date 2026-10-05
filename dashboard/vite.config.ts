/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// During development the dashboard (http://localhost:5173) forwards /api to the FastAPI
// server, so the browser sees ONE address: no CORS, and the HttpOnly login cookie works.
// In production both are served from the same domain by the load balancer (Phase 18).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Form tests type a lot; on a busy machine (or with --coverage) 5 s is too tight.
    testTimeout: 15_000,
    coverage: { include: ['src/**/*.{ts,tsx}'], exclude: ['src/**/*.test.tsx', 'src/test/**', 'src/main.tsx'] },
  },
})
