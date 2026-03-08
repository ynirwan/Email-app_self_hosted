import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5000,
    allowedHosts: true,
  },
  define: {
    // Expose environment variables to client
    __VITE_API_BASE_URL__: JSON.stringify(process.env.VITE_API_BASE_URL || 'http://localhost:8000/api'),
    __VITE_FALLBACK_API_URL__: JSON.stringify(process.env.VITE_FALLBACK_API_URL || 'http://localhost:8000/api'),
  },
})
