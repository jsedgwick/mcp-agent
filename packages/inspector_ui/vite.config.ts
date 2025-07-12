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
      '/_inspector/trace': 'http://localhost:7800',
      '/_inspector/events': 'http://localhost:7800',
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  }
})
