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
 * GitHub Pages 的静态托管限制与对策：
 *
 * 1. 未知路径不会回落到 index.html，只会返回 404。站点根下的 404.html 会被当作
 *    自定义错误页提供（状态码仍为 404），供拼写错误的路径渲染 SPA 外壳。
 * 2. 预渲染路由目录：把同一份 index.html 复制成 studio/index.html，让
 *    /quant-asst/studio/ 作为真实存在的静态文件被服务，从而得到真 200。
 *
 * 两份产物都与 index.html 字节一致：资源引用全部带 base 前缀
 * （/quant-asst/assets/...），不存在相对路径解析差异，无需改写内容。
 */
const PRE_RENDERED_ROUTES = ['studio']

function spaFallback(): Plugin {
  const INDEX = fileURLToPath(new URL('./dist/index.html', import.meta.url))
  const DIST = fileURLToPath(new URL('./dist/', import.meta.url))
  return {
    name: 'spa-fallback-404',
    apply: 'build',
    enforce: 'post',
    async closeBundle() {
      const html = await readFile(INDEX, 'utf8')

      // 未知路径兜底（状态码 404，页面仍可渲染）
      const notFound = `${DIST}404.html`
      await mkdir(dirname(notFound), { recursive: true })
      await writeFile(notFound, html)

      // 预渲染路由目录：真 200
      for (const route of PRE_RENDERED_ROUTES) {
        const target = `${DIST}${route}/index.html`
        await mkdir(dirname(target), { recursive: true })
        await writeFile(target, html)
      }
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
