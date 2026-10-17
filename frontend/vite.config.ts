import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The FastAPI backend (uv run uvicorn app.main:app --reload, in backend/).
    // 127.0.0.1 rather than localhost: on Windows, localhost tries IPv6 first.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
