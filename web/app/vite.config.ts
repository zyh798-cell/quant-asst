import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'

// 三层解耦：web/app（前端）→ /api（server/ 薄接口层）→ 现有 Python 后端模块
// 开发态前端 5173，接口层 8000；/api 代理避免开发期跨域。
//
// base 默认 '/'：本地 dev / preview 走根路径。部署到 GitHub Pages 子路径时
// （如 https://<user>.github.io/quant-asst/）用 VITE_BASE 覆盖为 '/quant-asst/'，
// 否则 index.html 会去站点根找资源导致 404。
export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
