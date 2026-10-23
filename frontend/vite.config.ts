import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Keeps the browser's Host header, so the API sees requests from this page as same-origin
      // (its cross-site write check compares Origin with it).
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
})
