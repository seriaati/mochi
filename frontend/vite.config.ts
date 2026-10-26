import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Installable as Mochi, with the built app cached so it opens without the network; data
    // still needs the API. The manifest is a fixed file, not made in the page: Chrome
    // on Android only installs a real app (a WebAPK) from a manifest and icons at https URLs, and
    // falls back to a home screen shortcut otherwise.
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Mochi',
        short_name: 'Mochi',
        start_url: '/',
        display: 'standalone',
        background_color: '#efeeea',
        theme_color: '#efeeea',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: { navigateFallbackDenylist: [/^\/api\//] },
    }),
  ],
  server: {
    proxy: {
      // Keeps the browser's Host header, so the API sees requests from this page as same-origin
      // (its cross-site write check compares Origin with it).
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
})
