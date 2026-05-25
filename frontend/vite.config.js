import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/auth':     'http://localhost:8000',
      '/data':     'http://localhost:8000',
      '/pipeline': 'http://localhost:8000',
      '/analysis': 'http://localhost:8000',
      '/stocks':   'http://localhost:8000',
      '/posts':    'http://localhost:8000',
    }
  }
})
