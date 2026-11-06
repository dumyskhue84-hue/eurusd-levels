import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'EURUSD Daily Levels',
        short_name: 'Levels',
        start_url: '/',
        display: 'standalone',
        background_color: '#0f1419',
        theme_color: '#0f1419',
        description: 'EURUSD daily adaptive levels for Android',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,json,png,svg}'],
      },
      injectManifest: false,
    }),
  ],
})
