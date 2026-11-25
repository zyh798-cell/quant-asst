// 零依赖前端单测运行器：rolldown（vite 自带）把 TS 测试入口打成单文件后交给 Node。
// 不引入 vitest / playwright，避免为一条用例扩依赖树。
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

import { rolldown } from 'rolldown'

const root = resolve(import.meta.dirname, '..')
const entry = resolve(root, 'src/i18n/__tests__/i18n.test.ts')
const outFile = resolve(root, '.test-dist/i18n.test.mjs')

const bundle = await rolldown({
  input: entry,
  resolve: {
    alias: { '@': resolve(root, 'src') + '/' },
  },
})

await bundle.write({
  file: outFile,
  format: 'esm',
})

await import(pathToFileURL(outFile).href)
