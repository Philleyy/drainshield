import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run dev` serves the site on http://localhost:5173 and forwards /api to the Python server on :8000.
// `npm run build` writes the finished site into ../server/static, which the Python server serves.
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../server/static', emptyOutDir: true },
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
