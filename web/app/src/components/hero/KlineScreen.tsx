import { useEffect, useRef } from 'react'

import { cssVar, makeCandles, makeEquity } from '@/lib/kline'

interface KlineScreenProps {
  variant: 'candles' | 'equity'
  /** false 时只画一帧静态（降级 / 减少动效） */
  active: boolean
  seed: number
  /** 逐根生长间隔 ms（200~400 区间） */
  interval?: number
  className?: string
}

const WINDOW = 18
const PAD = 10

/**
 * 单块屏幕画布：主屏 K 线蜡烛逐根生长滚动，左副屏净值曲线滚动。
 * 数据来自固定 seed 的本地确定性伪随机，不请求任何行情接口。
 */
export function KlineScreen({ variant, active, seed, interval = 320, className }: KlineScreenProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef({
    idx: WINDOW,
    progress: 0,
    candles: makeCandles(seed, 500),
    equity: makeEquity(seed, 600),
  })

  useEffect(() => {
    stateRef.current = {
      idx: WINDOW,
      progress: 0,
      candles: makeCandles(seed, 500),
      equity: makeEquity(seed, 600),
    }
  }, [seed])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let raf = 0
    let last = performance.now()

    const draw = (now: number) => {
      const dt = Math.min(64, now - last)
      last = now
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      if (w === 0 || h === 0) return
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr)
        canvas.height = Math.round(h * dpr)
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)

      if (variant === 'candles') drawCandles(ctx, w, h, dt)
      else drawEquity(ctx, w, h, dt)
    }

    const drawCandles = (ctx: CanvasRenderingContext2D, w: number, h: number, dt: number) => {
      const s = stateRef.current
      s.progress += dt / interval
      if (s.progress >= 1) {
        s.progress = 0
        s.idx = Math.min(s.idx + 1, s.candles.length - 1)
      }
      const buy = cssVar('--chart-buy', '#c0392b')
      const sell = cssVar('--chart-sell', '#18a67c')
      const grid = cssVar('--chart-grid', '#d9d2c4')
      const start = Math.max(0, s.idx - WINDOW + 1)
      const slice = s.candles.slice(start, s.idx + 1)
      const hi = Math.max(...slice.map((c) => c.h))
      const lo = Math.min(...slice.map((c) => c.l))
      const span = Math.max(1e-6, hi - lo)
      const y = (v: number) => PAD + ((hi - v) / span) * (h - PAD * 2)
      const step = (w - PAD * 2) / WINDOW
      const latestX = w - PAD - step * 0.5

      // 网格 3 条水平实线
      ctx.strokeStyle = grid
      ctx.globalAlpha = 0.4
      ctx.lineWidth = 1
      for (let g = 0; g < 3; g += 1) {
        const gy = PAD + ((h - PAD * 2) * (g + 0.5)) / 3
        ctx.beginPath()
        ctx.moveTo(PAD, gy)
        ctx.lineTo(w - PAD, gy)
        ctx.stroke()
      }
      ctx.globalAlpha = 1

      slice.forEach((c, i) => {
        const isLast = start + i === s.idx
        const grow = isLast ? s.progress : 1
        const close = c.o + (c.c - c.o) * grow
        const x = latestX - (s.idx - (start + i)) * step - s.progress * step
        const up = close >= c.o
        const color = up ? buy : sell
        ctx.strokeStyle = color
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.moveTo(x, y(c.h))
        ctx.lineTo(x, y(c.l))
        ctx.stroke()
        const top = y(Math.max(c.o, close))
        const bottom = y(Math.min(c.o, close))
        ctx.fillStyle = color
        ctx.fillRect(x - step * 0.28, top, step * 0.56, Math.max(2, bottom - top))
      })
    }

    const drawEquity = (ctx: CanvasRenderingContext2D, w: number, h: number, dt: number) => {
      const s = stateRef.current
      s.progress += dt / (interval + 80)
      if (s.progress >= 1) {
        s.progress = 0
        s.idx = Math.min(s.idx + 1, s.equity.length - 1)
      }
      const series = cssVar('--chart-series-1', '#18a67c')
      const grid = cssVar('--chart-grid', '#d9d2c4')
      const start = Math.max(0, s.idx - 60 + 1)
      const slice = s.equity.slice(start, s.idx + 1)
      const hi = Math.max(...slice)
      const lo = Math.min(...slice)
      const span = Math.max(1e-6, hi - lo)
      const y = (v: number) => PAD + ((hi - v) / span) * (h - PAD * 2)
      const step = (w - PAD * 2) / 60
      const latestX = w - PAD

      ctx.strokeStyle = grid
      ctx.globalAlpha = 0.4
      ctx.lineWidth = 1
      for (let g = 0; g < 3; g += 1) {
        const gy = PAD + ((h - PAD * 2) * (g + 0.5)) / 3
        ctx.beginPath()
        ctx.moveTo(PAD, gy)
        ctx.lineTo(w - PAD, gy)
        ctx.stroke()
      }
      ctx.globalAlpha = 1

      ctx.strokeStyle = series
      ctx.lineWidth = 2
      ctx.lineJoin = 'round'
      ctx.beginPath()
      slice.forEach((v, i) => {
        const x = latestX - (s.idx - (start + i)) * step - s.progress * step
        const py = y(v)
        if (i === 0) ctx.moveTo(x, py)
        else ctx.lineTo(x, py)
      })
      ctx.stroke()
      const lastV = slice[slice.length - 1]
      const lastX = latestX - s.progress * step
      ctx.fillStyle = series
      ctx.beginPath()
      ctx.arc(lastX, y(lastV), 3.5, 0, Math.PI * 2)
      ctx.fill()
    }

    const tick = (now: number) => {
      draw(now)
      raf = requestAnimationFrame(tick)
    }

    if (active) {
      raf = requestAnimationFrame(tick)
    } else {
      draw(performance.now())
    }
    return () => cancelAnimationFrame(raf)
  }, [active, variant, interval])

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />
}
