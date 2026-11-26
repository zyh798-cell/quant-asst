import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Plugin } from 'vite'

// 三层解耦：web/app（前端）→ /api（server/ 薄接口层）→ 现有 Python 后端模块
// 开发态前端 5173，接口层 8000；/api 代理避免开发期跨域。
//
// base 默认 '/'：本地 dev / preview 走根路径。部署到 GitHub Pages 子路径时
// （如 https://<user>.github.io/quant-asst/）用 VITE_BASE 覆盖为 '/quant-asst/'，
// 否则 index.html 会去站点根找资源导致 404。

/**
 * GitHub Pages 没有 SPA fallback：未知路径不会回落到 index.html，而是返回 404。
 * 它会把站点根下的 404.html 当作自定义错误页来服务，因此把同一份 index.html
 * 复制成 404.html 即可让 /studio 这类直链在服务端拿到 SPA 外壳，
 * 再由 react-router（basename = BASE_URL）接管成干净 URL。
 *
 * 产物与 index.html 字节一致：资源引用全部带 base 前缀（/quant-asst/assets/...），
 * 不存在相对路径解析差异，所以不需要改写内容。
 */
function spaFallback(): Plugin {
  const INDEX = fileURLToPath(new URL('./dist/index.html', import.meta.url))
  return {
    name: 'spa-fallback-404',
    apply: 'build',
    enforce: 'post',
    async closeBundle() {
      const html = await readFile(INDEX, 'utf8')
      const target = fileURLToPath(new URL('./dist/404.html', import.meta.url))
      await mkdir(dirname(target), { recursive: true })
      await writeFile(target, html)
    },
  }
}

export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [react(), tailwindcss(), spaFallback()],
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
