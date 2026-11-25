// 四视口自检：验证中文 / 英文切换在两个页面上即时生效，并截图存档。
// 仅本地调试脚本，不进入依赖树（playwright-core 用 --no-save 安装）。
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

// BASE 必须以斜杠结尾：项目部署在 /quant-asst/ 子路径下，不能用 new URL('/studio', BASE)
// （那会解析成站点根，丢掉子路径）。
const BASE = (process.env.CHECK_BASE ?? 'http://localhost:4173/').replace(/\/?$/, '/')
const OUT = resolve(import.meta.dirname, '../.test-dist/screenshots')

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
      await assertLang(page, ZH_MARKERS, `${vp.name} 首页默认中文`)
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

    // ---- 工作台 ----
    try {
      // GitHub Pages 无 SPA fallback，/studio 直链会 404；改走真实用户路径：首页点「打开工作台」。
      await page.goto(`${BASE}`, { waitUntil: 'networkidle' })
      const openLabel = (await page.locator('body').innerText()).includes('打开工作台')
        ? /打开工作台/
        : /Open studio/
      await page.getByRole('link', { name: openLabel }).first().click()
      await page.waitForTimeout(900)
      await assertLang(page, STUDIO_EN, `${vp.name} studio 沿用英文`)
      await page.screenshot({ path: `${OUT}/${vp.name}-studio-en.png`, fullPage: false })

      await clickLangButton(page, '中文')
      await assertLang(page, STUDIO_ZH, `${vp.name} studio 切回中文`)
      await page.screenshot({ path: `${OUT}/${vp.name}-studio-zh.png`, fullPage: false })

      const htmlLang = await page.evaluate(() => document.documentElement.lang)
      if (htmlLang !== 'zh-CN') throw new Error(`<html lang> 应为 zh-CN，实际 ${htmlLang}`)

      // 运行 mock 流程，确认阶段标签与状态徽章随语言切换
      await clickLangButton(page, 'EN')
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

  console.log(`\n截图目录：${OUT}`)
  if (failed > 0) {
    console.log(`\n失败 ${failed} 项：`)
    for (const p of problems) console.log(` - ${p}`)
    process.exitCode = 1
  } else {
    console.log('\n四视口 × 两页面 × 两语言：全部通过')
  }
}

await main()
