import { mulberry32 } from '@/lib/kline'

import type {
  AuditBrief,
  BacktestResult,
  DebateBrief,
  EquityPoint,
  ReportBrief,
  RunConfig,
  Trade,
} from '@/types'

/**
 * 样例数据：固定 seed 的确定性生成，仅用于 Step A 骨架演示。
 * 页面所有引用处必须标注 data: sample（GUIDELINES.md 1.6）。
 */

const TRADE_DATES = (start: string, count: number): string[] => {
  const out: string[] = []
  const d = new Date(`${start}T00:00:00Z`)
  let added = 0
  while (added < count) {
    const day = d.getUTCDay()
    if (day !== 0 && day !== 6) {
      out.push(d.toISOString().slice(0, 10))
      added += 1
    }
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return out
}

export function buildMockBacktest(config: RunConfig): BacktestResult {
  const rand = mulberry32(20261122)
  const days = 126
  const dates = TRADE_DATES(config.periodStart, days)
  const equity: EquityPoint[] = []
  let nav = 1
  let peak = 1
  let price = 100
  // 直接对日收益建模：日均约 +0.05%（年化 ~21%）、日波动约 1.7%（年化 ~27%），
  // 叠加约 44 日周期项让 MA 交叉自然产生盈亏混合，避免“夸张收益 + 100% 胜率”的失真实样例
  for (let i = 0; i < days; i += 1) {
    if (i > 0) {
      const r = (rand() - 0.5) * 0.03 + 0.0005 + 0.006 * Math.sin(i / 7)
      price = Math.max(20, price * (1 + r))
      nav = price / 100
    }
    peak = Math.max(peak, nav)
    equity.push({ date: dates[i], nav, drawdown: (nav - peak) / peak })
  }
  const totalReturn = nav - 1
  const annualReturn = totalReturn * (252 / days)
  let maxDd = 0
  for (const p of equity) maxDd = Math.min(maxDd, p.drawdown)
  const rets = equity.slice(1).map((p, i) => p.nav / equity[i].nav - 1)
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length
  const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length) || 1e-9
  const sharpe = (mean / sd) * Math.sqrt(252)

  const trades: Trade[] = []
  let position = 0
  let cash = config.initialCapital
  let wins = 0
  let losses = 0
  let winSum = 0
  let lossSum = 0
  const STOP_LOSS = 0.97 // 固定止损 -3%，让样例包含亏损笔，避免“全胜”失真
  const FAST = 5
  const SLOW = 20
  const ma = (i: number, n: number): number =>
    100 * equity.slice(Math.max(0, i - n + 1), i + 1).reduce((a, b) => a + b.nav, 0) / Math.min(n, i + 1)
  const close = (i: number, price: number) => {
    const entry = trades[trades.length - 1].price
    cash += position * price
    const pnl = position * (price - entry)
    if (pnl >= 0) {
      wins += 1
      winSum += pnl
    } else {
      losses += 1
      lossSum += -pnl
    }
    trades.push({ date: dates[i], side: 'sell', price, shares: position, amount: position * price, pnl })
    position = 0
  }
  for (let i = 2; i < days - 2; i += 1) {
    const price = 100 * equity[i].nav
    const fast = ma(i, FAST)
    const slow = ma(i, SLOW)
    const prevFast = ma(i - 1, FAST)
    const prevSlow = ma(i - 1, SLOW)
    const entry = trades.length > 0 ? trades[trades.length - 1].price : null
    const crossedUp = prevFast <= prevSlow && fast > slow
    const crossedDown = prevFast >= prevSlow && fast < slow
    if (position === 0 && crossedUp) {
      position = Math.floor(cash / price)
      cash -= position * price
      trades.push({ date: dates[i], side: 'buy', price, shares: position, amount: position * price, pnl: null })
    } else if (position > 0 && entry !== null && (crossedDown || price <= entry * STOP_LOSS)) {
      close(i, price)
    }
  }
  const nTrades = trades.length
  const winRate = wins + losses > 0 ? wins / (wins + losses) : null
  const profitFactor = lossSum > 0 ? winSum / lossSum : null

  return {
    symbol: config.symbol,
    market: config.market,
    period_start: config.periodStart,
    period_end: config.periodEnd,
    metrics: {
      total_return: totalReturn,
      annual_return: annualReturn,
      max_drawdown: maxDd,
      sharpe,
      win_rate: winRate,
      profit_factor: profitFactor,
      n_trades: nTrades,
      n_days: days,
    },
    equity,
    trades,
    sample: true,
  }
}

export function buildMockDebate(): DebateBrief {
  return {
    credibility_score: 68,
    decision: 'revise',
    consensus: ['趋势样本内有效', '回撤可控'],
    disagreements: ['参数敏感性', '样本外衰减幅度'],
    bull_points: ['样本内年化优于基准', '回撤集中于少数交易日'],
    bear_points: ['参数窗口敏感', '样本外收益衰减明显'],
    risk_findings: ['过度依赖单一参数窗口', '未计入冲击成本'],
    rationale: '方向性证据成立，但参数稳健性不足，建议收缩窗口并复核成本假设。',
  }
}

export function buildMockAudit(): AuditBrief {
  return {
    overall_risk_level: 'medium',
    risk_grade_label: '中',
    tradability: 'restricted',
    findings: [
      { category: 'overfitting', title: '参数窗口过拟合', severity: 'medium', recommendation: '做窗口敏感性扫描' },
      { category: 'lookahead', title: '信号确认滞后未计入', severity: 'low', recommendation: '补一日执行延迟' },
      { category: 'liquidity_trap', title: '小市值标的冲击成本', severity: 'medium', recommendation: '加入成交量过滤' },
    ],
  }
}

export function buildMockReport(result: BacktestResult, debate: DebateBrief, audit: AuditBrief): ReportBrief {
  const md = [
    `# 量化研究报告（样例）`,
    '',
    `标的：${result.symbol}　区间：${result.period_start} 至 ${result.period_end}`,
    '',
    `## 回测指标`,
    `- 年化收益：${(result.metrics.annual_return ?? 0).toFixed(2)}%`,
    `- 最大回撤：${(result.metrics.max_drawdown * 100).toFixed(2)}%`,
    `- 夏普比率：${(result.metrics.sharpe ?? 0).toFixed(2)}`,
    `- 按笔胜率：${((result.metrics.win_rate ?? 0) * 100).toFixed(1)}%`,
    `- 成交笔数：${result.metrics.n_trades}`,
    '',
    `## 裁决`,
    `- 可信度：${debate.credibility_score}/100`,
    `- 决策：${debate.decision}`,
    `- 综合风险：${audit.risk_grade_label}`,
    '',
    `> 样例数据，仅用于演示，不构成投资建议。`,
  ].join('\n')
  return { markdown: md, html_url: null }
}
