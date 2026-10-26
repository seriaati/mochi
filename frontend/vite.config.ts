import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Installable, with the built app cached so it opens without the network; data still needs
    // the API. src/manifest.ts swaps in the studio's name and logo once they're known.
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Studio',
        short_name: 'Studio',
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
