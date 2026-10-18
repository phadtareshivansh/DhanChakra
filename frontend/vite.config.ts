import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: Number(env.VITE_PORT) || 5173,
      proxy: {
        '/api': {
          target: env.VITE_PROXY_TARGET || 'http://api:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
