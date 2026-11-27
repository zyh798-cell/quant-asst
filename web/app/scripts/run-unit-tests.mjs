// 零依赖前端单测运行器：rolldown（vite 自带）把 TS 测试入口打成单文件后交给 Node。
// 不引入 vitest / playwright，避免为一条用例扩依赖树。
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

import { rolldown } from 'rolldown'

const root = resolve(import.meta.dirname, '..')

// 所有测试入口在此登记；打包成单一 bundle 以共享 testkit 的计数与汇总状态。
const entries = [
  'src/i18n/__tests__/i18n.test.ts',
  'src/lib/__tests__/api.test.ts',
]
const outFile = resolve(root, '.test-dist/all-tests.mjs')

const VIRTUAL_ID = 'quant-asst-all-tests'
const virtualSource = entries
  .map((rel) => `import ${JSON.stringify(resolve(root, rel))}`)
  .join('\n')

const bundle = await rolldown({
  input: VIRTUAL_ID,
  plugins: [
    {
      name: 'virtual-test-entry',
      resolveId(id) {
        return id === VIRTUAL_ID ? id : null
      },
      load(id) {
        return id === VIRTUAL_ID ? virtualSource : null
      },
    },
  ],
  resolve: {
    alias: { '@': resolve(root, 'src') + '/' },
  },
})

await bundle.write({
  file: outFile,
  format: 'esm',
})

await import(pathToFileURL(outFile).href)
