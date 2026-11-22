/**
 * 确定性伪随机行情生成：固定 seed，禁止运行时请求真实行情接口。
 * 仅用于首屏场景屏幕内容填充，不构成任何行情数据。
 */

export interface Candle {
  o: number
  h: number
  l: number
  c: number
}

/** mulberry32：小巧的确定性 PRNG，同 seed 同序列。 */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** 生成一段带趋势与波动率的 OHLC 序列（几何随机游走）。 */
export function makeCandles(seed: number, count: number, start = 100): Candle[] {
  const rand = mulberry32(seed)
  const out: Candle[] = []
  let price = start
  let drift = 0
  for (let i = 0; i < count; i += 1) {
    // 缓慢变化的趋势项 + 日内波动
    drift = drift * 0.9 + (rand() - 0.48) * 1.4
    const vol = 1.2 + rand() * 2.4
    const open = price
    const close = Math.max(5, open + drift + (rand() - 0.5) * vol * 2)
    const high = Math.max(open, close) + rand() * vol
    const low = Math.min(open, close) - rand() * vol
    out.push({ o: open, h: high, l: low, c: close })
    price = close
  }
  return out
}

/** 净值曲线（累计收益，起点 1）。 */
export function makeEquity(seed: number, count: number): number[] {
  const rand = mulberry32(seed)
  const out: number[] = [1]
  let v = 1
  let drift = 0
  for (let i = 1; i < count; i += 1) {
    drift = drift * 0.92 + (rand() - 0.47) * 0.012
    v = Math.max(0.6, v * (1 + drift))
    out.push(v)
  }
  return out
}

/** 从 CSS 变量读取图表配色，保证 canvas 与全站一致。 */
export function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}
