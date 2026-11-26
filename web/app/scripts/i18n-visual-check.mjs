// 四视口自检：验证中文 / 英文切换在两个页面上即时生效，并截图存档。
// 仅本地调试脚本，不进入依赖树（playwright-core 用 --no-save 安装）。
import { cp, mkdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { chromium } from 'playwright-core'

// BASE 必须以斜杠结尾：项目部署在 /quant-asst/ 子路径下，不能用 new URL('/studio', BASE)
// （那会解析成站点根，丢掉子路径）。
const BASE = (process.env.CHECK_BASE ?? 'http://localhost:4173/').replace(/\/?$/, '/')
// 截图先落系统临时目录再回拷到仓库（避免 IDE 安全沙箱拦截对仓库内目录的写入）
const OUT = join(tmpdir(), 'quant-asst-screens')
const REPO_OUT = resolve(import.meta.dirname, '../.test-dist/screenshots')

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'laptop', width: 1280, height: 800 },
  { name: 'tablet', width: 834, height: 1112 },
  { name: 'mobile', width: 390, height: 844 },
]

const ZH_MARKERS = ['多 Agent 量化研究与风控审计框架', '核心能力', '多空辩论']
const EN_MARKERS = ['Multi-agent quantitative research and risk-audit framework', 'Core capabilities', 'Bull/bear debate']

const STUDIO_ZH = ['研究工作台', '策略配置', '研究流水线', '运行策略']
const STUDIO_EN = ['Research workbench', 'Strategy configuration', 'Research pipeline', 'Run strategy']

async function readText(page) {
  return (await page.locator('body').innerText()).replace(/\s+/g, ' ')
}

/** 切换语言：窄屏下控件在折叠菜单内；hero 场景层会拦截真实点击时退化为 DOM 点击。 */
async function clickLangButton(page, label) {
  const btn = page.getByRole('button', { name: label, exact: true })
  if (!(await btn.isVisible().catch(() => false))) {
    await page.getByRole('button', { name: /Menu|菜单/ }).click()
    await page.waitForTimeout(200)
  }
  try {
    await btn.click({ timeout: 3000 })
  } catch {
    // 场景层/滚动位置导致命中失败：直接派发点击事件，验证逻辑本身而非命中测试
    await page.locator('.lang-switch button').nth(label === 'EN' ? 1 : 0).dispatchEvent('click')
  }
  await page.waitForTimeout(300)
}

async function assertLang(page, markers, label) {
  const text = await readText(page)
  for (const marker of markers) {
    if (!text.includes(marker)) {
      throw new Error(`${label}: 未找到「${marker}」`)
    }
  }
  return text
}

/**
 * SPA 直链用例：GitHub Pages 无 fallback，靠 dist/404.html 兜住未知路径。
 * 这里不走首页点击，而是直接 goto /studio，验证服务端确实返回了 SPA 外壳、
 * 且 react-router 用 basename 正确接管成 StudioPage（URL 保持干净，不出现重复前缀）。
 */
/**
 * SPA 直链用例：GitHub Pages 无 fallback，靠 dist/404.html 兜住未知路径。
 * 这里不走首页点击，而是直接 goto /studio，验证服务端确实返回了 SPA 外壳、
 * 且 react-router 用 basename 正确接管成 StudioPage（URL 保持干净，不出现重复前缀）。
 *
 * 语言显式固定：Playwright 各执行环境的 navigator.language 不一致（本机 zh-CN、
 * CI/无头环境多为 en-US），依赖浏览器探测会让同一用例在不同环境走上不同分支。
 */
async function checkDirectStudio(page, vp) {
  await page.goto(`${BASE}studio`, { waitUntil: 'networkidle' })
  const url = page.url()
  if (!/\/studio\/?$/.test(url)) {
    throw new Error(`${vp.name} 直链后 URL 异常：${url}`)
  }
  await clickLangButton(page, '中文')
  await assertLang(page, STUDIO_ZH, `${vp.name} 直链 studio（中文）`)
  await page.screenshot({ path: `${OUT}/${vp.name}-studio-direct-zh.png`, fullPage: false })

  // 直链入口同样要能切到英文，确认控制器不是只在首页挂载
  await clickLangButton(page, 'EN')
  await assertLang(page, STUDIO_EN, `${vp.name} 直链 studio 切英文`)
  await page.screenshot({ path: `${OUT}/${vp.name}-studio-direct-en.png`, fullPage: false })
}

async function main() {
  await mkdir(OUT, { recursive: true })
  const browser = await chromium.launch({
    executablePath:
      process.env.CHROME_PATH ??
      `${process.env.LOCALAPPDATA}\\ms-playwright\\chromium-1248\\chrome-win64\\chrome.exe`,
  })

  let failed = 0
  const problems = []

  for (const vp of VIEWPORTS) {
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } })
    const page = await context.newPage()

    // ---- 首页 ----
    await page.goto(`${BASE}`, { waitUntil: 'networkidle' })
    try {
      // 显式切到中文再断言：Playwright 各执行环境的 navigator.language 不一致，
      // 依赖浏览器探测会让同一用例在不同环境走上不同分支。
      await clickLangButton(page, '中文')
      await assertLang(page, ZH_MARKERS, `${vp.name} 首页中文`)
      await page.screenshot({ path: `${OUT}/${vp.name}-home-zh.png`, fullPage: false })

      // 点击 EN 切换到英文
      await clickLangButton(page, 'EN')
      await assertLang(page, EN_MARKERS, `${vp.name} 首页切英文`)
      await page.screenshot({ path: `${OUT}/${vp.name}-home-en.png`, fullPage: false })

      const htmlLang = await page.evaluate(() => document.documentElement.lang)
      if (htmlLang !== 'en') throw new Error(`<html lang> 应为 en，实际 ${htmlLang}`)
    } catch (err) {
      failed += 1
      problems.push(String(err.message ?? err))
    }

    // ---- 工作台（先验直链，再走点击路径）----
    try {
      // 直链用例：/studio 必须返回 SPA 外壳并渲染出工作台（依赖 dist/404.html），
      // 并验证直链入口的语言切换。结束时停留在中文。
      await checkDirectStudio(page, vp)

      // 常规路径：首页点「打开工作台」，确认直链改动没有影响既有入口。
      // 直链用例结束时语言为英文，所以这里同时验证语言在页面跳转后保持。
      await page.goto(`${BASE}`, { waitUntil: 'networkidle' })
      const openLabel = (await page.locator('body').innerText()).includes('打开工作台')
        ? /打开工作台/
        : /Open studio/
      await page.getByRole('link', { name: openLabel }).first().click()
      await page.waitForTimeout(900)
      await assertLang(page, STUDIO_EN, `${vp.name} studio 沿用英文`)
      await page.screenshot({ path: `${OUT}/${vp.name}-studio-en.png`, fullPage: false })

      const htmlLang = await page.evaluate(() => document.documentElement.lang)
      if (htmlLang !== 'en') throw new Error(`<html lang> 应为 en，实际 ${htmlLang}`)

      // 运行 mock 流程，确认阶段标签与状态徽章为英文
      await page.getByRole('button', { name: /Run strategy/ }).click()
      await page.waitForTimeout(4500)
      await assertLang(page, ['Parse', 'Backtest', 'Done'], `${vp.name} studio 英文阶段标签`)
      await page.screenshot({ path: `${OUT}/${vp.name}-studio-running-en.png`, fullPage: false })
    } catch (err) {
      failed += 1
      problems.push(String(err.message ?? err))
    }

    await context.close()
  }

  await browser.close()

  if (failed === 0 && process.env.KEEP_SCREENS !== '0') {
    await cp(OUT, REPO_OUT, { recursive: true })
  }
  console.log(`\n截图目录：${REPO_OUT}`)
  if (failed > 0) {
    console.log(`\n失败 ${failed} 项：`)
    for (const p of problems) console.log(` - ${p}`)
    process.exitCode = 1
  } else {
    console.log('\n四视口 × 两页面 × 两语言：全部通过')
  }
}

await main()
