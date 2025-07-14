import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/_inspector/ui/',
  server: {
    proxy: {
      '/_inspector/health': 'http://localhost:7800',
      '/_inspector/sessions': 'http://localhost:7800',
      '/_inspector/trace': {
        target: 'http://localhost:7800',
        changeOrigin: true,
        configure: (proxy, options) => {
          // Log proxy requests for debugging
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('[Vite Proxy] Proxying trace request:', req.url)
          })
        }
      },
      '/_inspector/events': {
        target: 'http://localhost:7800',
        changeOrigin: true,
        // SSE requires special handling
        configure: (proxy, options) => {
          proxy.on('proxyRes', (proxyRes, req, res) => {
            // Ensure SSE headers are preserved
            proxyRes.headers['cache-control'] = 'no-cache'
          })
        }
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  }
})
