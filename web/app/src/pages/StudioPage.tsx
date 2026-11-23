import {
  AlertTriangle,
  Check,
  Download,
  FileText,
  Loader2,
  Play,
  RotateCcw,
  X,
} from 'lucide-react'

import { DrawdownChart } from '@/components/charts/DrawdownChart'
import { EquityChart } from '@/components/charts/EquityChart'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { useStudioStore } from '@/store/studio'
import type { StageStatus } from '@/types'
import './studio.css'

const STATUS_META: Record<StageStatus, { label: string; variant: 'neutral' | 'low' | 'info' | 'high' }> = {
  pending: { label: '等待', variant: 'neutral' },
  running: { label: '进行中', variant: 'info' },
  done: { label: '完成', variant: 'low' },
  failed: { label: '失败', variant: 'high' },
  skipped: { label: '跳过', variant: 'neutral' },
}

function StageIcon({ status }: { status: StageStatus }) {
  if (status === 'running') return <Loader2 className="size-3.5 animate-spin" aria-hidden />
  if (status === 'done') return <Check className="size-3.5" aria-hidden />
  if (status === 'failed') return <X className="size-3.5" aria-hidden />
  return <span className="size-2 rounded-pill bg-ink-300" aria-hidden />
}

const pct = (v: number | null, digits = 2) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`)
const num = (v: number | null, digits = 2) => (v == null ? '—' : v.toFixed(digits))

export function StudioPage() {
  const {
    config,
    setConfig,
    stages,
    phase,
    error,
    backend,
    taskId,
    notice,
    result,
    debate,
    audit,
    final,
    report,
    run,
    reset,
  } = useStudioStore()

  const running = phase === 'running'

  const downloadReport = () => {
    if (!report) return
    const blob = new Blob([report.markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'quant-asst-report.md'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="studio">
      <div className="shell">
        <header className="studio__head">
          <h1 className="studio__title">研究工作台</h1>
          <p className="studio__sub">
            填写策略假设并运行研究流水线：左侧为纯前端样例（data: sample），
            关闭 mock 后由本地接口层（server/）接管，逐阶段返回真实产物。
          </p>
          <div className="flex flex-wrap gap-2">
            <Badge variant={config.mock ? 'low' : 'info'}>
              {config.mock ? 'mock 离线' : '真实模式'}
            </Badge>
            <Badge variant="outline">{config.mock ? 'data: sample' : 'data: live'}</Badge>
            {backend === 'remote' && taskId && (
              <Badge variant="outline">task {taskId}</Badge>
            )}
          </div>
          {notice && (
            <p className="mt-2 text-caption text-warning-ink" role="status">
              {notice}
            </p>
          )}
        </header>

        <div className="studio__grid">
          {/* ---- 策略配置 ---- */}
          <aside className="studio__aside">
            <Card>
              <CardHeader>
                <CardTitle>策略配置</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="form-field">
                  <Label htmlFor="strategy">策略描述</Label>
                  <Textarea
                    id="strategy"
                    value={config.strategy}
                    onChange={(e) => setConfig({ strategy: e.target.value })}
                    disabled={running}
                  />
                </div>

                <div className="form-field">
                  <Label htmlFor="market">市场</Label>
                  <Select value={config.market} onValueChange={(v) => setConfig({ market: v })} disabled={running}>
                    <SelectTrigger id="market">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cn_stock">A 股</SelectItem>
                      <SelectItem value="us_stock">美股</SelectItem>
                      <SelectItem value="hk_stock">港股</SelectItem>
                      <SelectItem value="futures">期货</SelectItem>
                      <SelectItem value="crypto">加密</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="form-field">
                  <Label htmlFor="symbol">标的代码</Label>
                  <Input
                    id="symbol"
                    value={config.symbol}
                    onChange={(e) => setConfig({ symbol: e.target.value })}
                    disabled={running}
                  />
                  <p className="form-field__hint">统一格式 market:code，例如 cn:600519</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="form-field">
                    <Label htmlFor="start">开始日</Label>
                    <Input
                      id="start"
                      type="date"
                      value={config.periodStart}
                      onChange={(e) => setConfig({ periodStart: e.target.value })}
                      disabled={running}
                    />
                  </div>
                  <div className="form-field">
                    <Label htmlFor="end">结束日</Label>
                    <Input
                      id="end"
                      type="date"
                      value={config.periodEnd}
                      onChange={(e) => setConfig({ periodEnd: e.target.value })}
                      disabled={running}
                    />
                  </div>
                </div>

                <div className="form-field">
                  <Label htmlFor="capital">初始资金</Label>
                  <Input
                    id="capital"
                    type="number"
                    min={1000}
                    value={config.initialCapital}
                    onChange={(e) => setConfig({ initialCapital: Number(e.target.value) })}
                    disabled={running}
                  />
                </div>

                <div className="switch-row">
                  <Label htmlFor="mock">mock 离线模式</Label>
                  <button
                    id="mock"
                    type="button"
                    role="switch"
                    aria-checked={config.mock}
                    className="switch"
                    data-checked={config.mock}
                    onClick={() => setConfig({ mock: !config.mock })}
                    disabled={running}
                  >
                    <span className="switch__thumb" data-checked={config.mock} />
                  </button>
                </div>
                {!config.mock && (
                  <p className="form-field__hint" role="note">
                    真实模式需本地启动后端（<code>server/</code>：
                    <code>uv run uvicorn server.main:app --port 8000</code>），详见 README。
                    未启动后端时运行会进入失败态。
                  </p>
                )}

                <div className="flex gap-2">
                  <Button type="button" onClick={() => void run()} disabled={running} className="flex-1">
                    {running ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Play aria-hidden />}
                    {running ? '运行中' : '运行策略'}
                  </Button>
                  <Button type="button" variant="secondary" onClick={reset} disabled={running}>
                    <RotateCcw aria-hidden />
                    重置
                  </Button>
                </div>
              </CardContent>
            </Card>
          </aside>

          {/* ---- 流水线与结果 ---- */}
          <section className="flex min-w-0 flex-col gap-4">
            <Card>
              <CardHeader>
                <CardTitle>研究流水线</CardTitle>
              </CardHeader>
              <CardContent>
                {error ? (
                  <div className="flex items-start gap-3 rounded-md border border-danger/40 bg-danger-soft p-4" role="alert">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger-ink" aria-hidden />
                    <div>
                      <p className="text-label font-medium text-danger-ink">任务未能完成</p>
                      <p className="mt-1 text-caption text-body">{error}</p>
                      <Button type="button" variant="secondary" size="sm" className="mt-3" onClick={() => void run()}>
                        重试
                      </Button>
                    </div>
                  </div>
                ) : (
                  <ol className="stage-list">
                    {stages.map((s) => (
                      <li key={s.id} className={`stage stage--${s.status}`}>
                        <span className="stage__icon">
                          <StageIcon status={s.status} />
                        </span>
                        <div className="stage__body">
                          <p className="stage__label">{s.label}</p>
                          {s.summary && <p className="stage__summary">{s.summary}</p>}
                        </div>
                        <Badge variant={STATUS_META[s.status].variant}>{STATUS_META[s.status].label}</Badge>
                      </li>
                    ))}
                  </ol>
                )}
              </CardContent>
            </Card>

            {phase === 'idle' && (
              <Card>
                <CardContent className="py-10 text-center text-label text-muted">
                  填写左侧配置并运行，结果将在此处呈现。
                </CardContent>
              </Card>
            )}

            {result && (
              <Tabs defaultValue="backtest">
                <TabsList>
                  <TabsTrigger value="backtest">回测结果</TabsTrigger>
                  <TabsTrigger value="debate">辩论审计</TabsTrigger>
                  <TabsTrigger value="report">报告</TabsTrigger>
                </TabsList>

                <TabsContent value="backtest" className="flex flex-col gap-4">
                  <div className="metric-grid">
                    {[
                      { label: '年化收益', value: pct(result.metrics.annual_return) },
                      { label: '最大回撤', value: pct(result.metrics.max_drawdown) },
                      { label: '夏普比率', value: num(result.metrics.sharpe) },
                      { label: '按笔胜率', value: pct(result.metrics.win_rate, 1) },
                      { label: '盈亏比', value: num(result.metrics.profit_factor) },
                    ].map((m) => (
                      <div key={m.label} className="metric">
                        <p className="metric__label">{m.label}</p>
                        <p className="metric__value">{m.value}</p>
                        <p className="metric__note">区间 {result.period_start} 至 {result.period_end}</p>
                      </div>
                    ))}
                  </div>

                  <div className="chart-card">
                    <h3 className="chart-card__title">净值曲线</h3>
                    <p className="chart-card__note">买入为向上三角、卖出为向下三角；颜色与形状双通道。</p>
                    <EquityChart equity={result.equity} trades={result.trades} />
                  </div>

                  <div className="chart-card">
                    <h3 className="chart-card__title">回撤曲线</h3>
                    <p className="chart-card__note">基线恒为 0，数值为负表示低于历史峰值。</p>
                    <DrawdownChart equity={result.equity} />
                  </div>

                  <div className="chart-card">
                    <h3 className="chart-card__title">成交记录</h3>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>日期</TableHead>
                          <TableHead>方向</TableHead>
                          <TableHead className="text-right">价格</TableHead>
                          <TableHead className="text-right">股数</TableHead>
                          <TableHead className="text-right">金额</TableHead>
                          <TableHead className="text-right">盈亏</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {result.trades.map((t, i) => (
                          <TableRow key={`${t.date}-${i}`}>
                            <TableCell className="num">{t.date}</TableCell>
                            <TableCell>
                              <span className={t.side === 'buy' ? 'text-danger-ink' : 'text-success-ink'}>
                                {t.side === 'buy' ? '买入' : '卖出'}
                              </span>
                            </TableCell>
                            <TableCell className="num text-right">{t.price.toFixed(2)}</TableCell>
                            <TableCell className="num text-right">{t.shares}</TableCell>
                            <TableCell className="num text-right">{t.amount.toFixed(2)}</TableCell>
                            <TableCell className="num text-right">
                              {t.pnl == null ? '—' : t.pnl.toFixed(2)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </TabsContent>

                <TabsContent value="debate" className="flex flex-col gap-4">
                  {debate && (
                    <>
                      <div className="debate-cols">
                        <Card>
                          <CardHeader>
                            <CardTitle>多头要点</CardTitle>
                          </CardHeader>
                          <CardContent>
                            <ul className="list-disc space-y-1 pl-5 text-label text-body">
                              {debate.bull_points.map((p, i) => (
                                <li key={`${i}-${p}`}>{p}</li>
                              ))}
                            </ul>
                          </CardContent>
                        </Card>
                        <Card>
                          <CardHeader>
                            <CardTitle>空头要点</CardTitle>
                          </CardHeader>
                          <CardContent>
                            <ul className="list-disc space-y-1 pl-5 text-label text-body">
                              {debate.bear_points.map((p, i) => (
                                <li key={`${i}-${p}`}>{p}</li>
                              ))}
                            </ul>
                          </CardContent>
                        </Card>
                      </div>

                      <Card>
                        <CardHeader>
                          <CardTitle>风控核验</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ul className="list-disc space-y-1 pl-5 text-label text-body">
                            {debate.risk_findings.map((f, i) => (
                              <li key={`${i}-${f}`}>{f}</li>
                            ))}
                          </ul>
                          <div className="verdict">
                            <div>
                              <p className="text-label font-medium text-ink">裁决：{debate.decision}</p>
                              <p className="mt-1 text-caption text-muted">{debate.rationale}</p>
                            </div>
                            <Badge variant="info">可信度 {debate.credibility_score}/100</Badge>
                          </div>
                        </CardContent>
                      </Card>
                    </>
                  )}

                  {audit && (
                    <Card>
                      <CardHeader>
                        <CardTitle>红队审计</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="mb-3 flex gap-2">
                          <Badge variant={audit.overall_risk_level}>综合风险：{audit.risk_grade_label}</Badge>
                          <Badge variant="outline">可行性：{audit.tradability}</Badge>
                        </div>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>类别</TableHead>
                              <TableHead>问题</TableHead>
                              <TableHead>级别</TableHead>
                              <TableHead>建议</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {audit.findings.map((f, i) => (
                              <TableRow key={`${i}-${f.title}`}>
                                <TableCell>{f.category}</TableCell>
                                <TableCell>{f.title}</TableCell>
                                <TableCell>
                                  <Badge variant={f.severity}>{f.severity}</Badge>
                                </TableCell>
                                <TableCell>{f.recommendation}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                  )}

                  {final && (
                    <Card>
                      <CardHeader>
                        <CardTitle>风控综合结论</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="mb-3 flex flex-wrap gap-2">
                          <Badge variant={final.overall_risk_level}>
                            综合风险：{final.overall_risk_level}
                          </Badge>
                          <Badge variant="info">最终决策：{final.final_decision}</Badge>
                          <Badge variant="outline">可信度 {final.credibility_score}/100</Badge>
                        </div>
                        {final.risk_banner && (
                          <p className="mb-2 text-label text-danger-ink">{final.risk_banner}</p>
                        )}
                        <p className="text-label text-body">{final.executive_summary}</p>
                        {final.trade_advisory && (
                          <p className="mt-2 text-caption text-muted">
                            交易建议：{final.trade_advisory}
                          </p>
                        )}
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>

                <TabsContent value="report" className="flex flex-col gap-4">
                  {report ? (
                    <Card>
                      <CardHeader className="flex-row items-center justify-between">
                        <CardTitle>Markdown 报告</CardTitle>
                        <div className="flex gap-2">
                          {report.html_url && (
                            <Button
                              type="button"
                              variant="secondary"
                              size="sm"
                              asChild
                            >
                              <a href={report.html_url} target="_blank" rel="noreferrer">
                                <FileText aria-hidden />
                                打开 HTML 报告
                              </a>
                            </Button>
                          )}
                          <Button type="button" variant="secondary" size="sm" onClick={downloadReport}>
                            <Download aria-hidden />
                            下载 .md
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <pre className="overflow-x-auto rounded-md border border-rule bg-ink-100/40 p-4 text-caption text-body">
                          {report.markdown || '报告正文加载中…'}
                        </pre>
                        {!config.mock && (
                          <p className="mt-3 text-micro text-muted">
                            真实模式报告来自本地接口层，落盘于 var/reports/&lt;task_id&gt;/。
                          </p>
                        )}
                      </CardContent>
                    </Card>
                  ) : (
                    <CardContent className="py-10 text-center text-label text-muted">
                      <FileText className="mx-auto mb-2 size-5 text-muted" aria-hidden />
                      报告尚未生成。
                    </CardContent>
                  )}
                </TabsContent>
              </Tabs>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
