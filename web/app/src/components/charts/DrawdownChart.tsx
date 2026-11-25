import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useT } from '@/i18n'
import type { EquityPoint } from '@/types'

interface DrawdownChartProps {
  equity: EquityPoint[]
}

function DdTooltip({
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
      <p className="num text-danger-ink">{t.chartDrawdown} {(p.drawdown * 100).toFixed(2)}%</p>
    </div>
  )
}

/** 回撤曲线：基线恒为 0 的单序列面积图，标注口径。 */
export function DrawdownChart({ equity }: DrawdownChartProps) {
  return (
    <div
      className="h-48 w-full"
      role="img"
      aria-label="回撤曲线，基线为 0；数值为负表示低于历史峰值"
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={equity} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12, fill: 'var(--chart-label)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--chart-axis)' }}
            minTickGap={48}
          />
          <YAxis
            tick={{ fontSize: 12, fill: 'var(--chart-label)' }}
            tickLine={false}
            axisLine={false}
            width={52}
            domain={['auto', 0]}
            tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
          />
          <Tooltip content={<DdTooltip />} />
          <Area
            type="monotone"
            dataKey="drawdown"
            stroke="var(--chart-series-2)"
            strokeWidth={2}
            fill="var(--chart-series-2)"
            fillOpacity={0.12}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
