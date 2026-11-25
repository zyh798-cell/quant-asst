import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useT } from '@/i18n'
import type { EquityPoint, Trade } from '@/types'

interface EquityChartProps {
  equity: EquityPoint[]
  trades: Trade[]
}

interface Point {
  date: string
  nav: number
}

function BuyShape(props: { cx?: number; cy?: number }) {
  const { cx = 0, cy = 0 } = props
  return (
    <path
      d={`M ${cx} ${cy + 9} L ${cx - 5} ${cy + 17} L ${cx + 5} ${cy + 17} Z`}
      fill="var(--chart-buy)"
    />
  )
}

function SellShape(props: { cx?: number; cy?: number }) {
  const { cx = 0, cy = 0 } = props
  return (
    <path
      d={`M ${cx} ${cy - 9} L ${cx - 5} ${cy - 17} L ${cx + 5} ${cy - 17} Z`}
      fill="var(--chart-sell)"
    />
  )
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: EquityPoint }>
}) {
  const t = useT()
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="rounded-md border border-rule bg-surface px-3 py-2 text-caption shadow-md">
      <p className="text-muted">{p.date}</p>
      <p className="num text-body">{t.chartNav} {p.nav.toFixed(4)}</p>
      <p className="num text-danger-ink">{t.chartDrawdown} {(p.drawdown * 100).toFixed(2)}%</p>
    </div>
  )
}

/** 净值曲线：单序列折线 + 买卖信号双通道（颜色 + 形状）。 */
export function EquityChart({ equity, trades }: EquityChartProps) {
  const navByDate = new Map(equity.map((p) => [p.date, p.nav]))
  const buys: Point[] = trades
    .filter((t) => t.side === 'buy')
    .map((t) => ({ date: t.date, nav: navByDate.get(t.date) ?? 0 }))
  const sells: Point[] = trades
    .filter((t) => t.side === 'sell')
    .map((t) => ({ date: t.date, nav: navByDate.get(t.date) ?? 0 }))

  return (
    <div
      className="h-72 w-full"
      role="img"
      aria-label="净值曲线，含买入与卖出信号标记；等价数据见下方成交记录表"
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={equity} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12, fill: 'var(--chart-label)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--chart-axis)' }}
            minTickGap={48}
          />
          <YAxis
            dataKey="nav"
            tick={{ fontSize: 12, fill: 'var(--chart-label)' }}
            tickLine={false}
            axisLine={false}
            width={52}
            domain={['auto', 'auto']}
            tickFormatter={(v: number) => v.toFixed(2)}
          />
          <Tooltip content={<ChartTooltip />} />
          <Line
            type="monotone"
            dataKey="nav"
            stroke="var(--chart-series-1)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Scatter data={buys} shape={<BuyShape />} isAnimationActive={false} />
          <Scatter data={sells} shape={<SellShape />} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
