import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发服务器把 /api 代理到 FastAPI(8000)，前端专注 5173，无跨域烦恼
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8008',
        changeOrigin: true,
      },
    },
  },
})
