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
import { decisionLabel, interpolate, riskLabel, type Dict } from '@/i18n/dict'
import { useT } from '@/i18n'
import type { StageId, StageStatus, SummaryKey } from '@/types'
import './studio.css'

/** 阶段状态 -> 徽章色（沿用原有映射）。 */
const STATUS_VARIANT: Record<StageStatus, 'neutral' | 'low' | 'info' | 'high'> = {
  pending: 'neutral',
  running: 'info',
  done: 'low',
  failed: 'high',
  skipped: 'neutral',
}

const STAGE_LABEL_KEYS: Record<StageId, string> = {
  parse: 'stageParse',
  backtest: 'stageBacktest',
  debate: 'stageDebate',
  audit: 'stageAudit',
  risk: 'stageRisk',
  report: 'stageReport',
} as const

function stageLabel(t: Dict, id: StageId): string {
  return t[STAGE_LABEL_KEYS[id] as keyof typeof t] as string
}

function statusLabel(t: Dict, status: StageStatus): string {
  switch (status) {
    case 'pending':
      return t.stagePending
    case 'running':
      return t.stageRunning
    case 'done':
      return t.stageDone
    case 'failed':
      return t.stageFailed
    case 'skipped':
      return t.stageSkipped
    default:
      return status
  }
}

/** 摘要：优先按结构化 key + 当前语言插值，否则回落到后端原文。 */
export function summaryText(
  t: Dict,
  stage: { summary?: string; summaryKey?: SummaryKey; summaryVars?: Record<string, string | number> },
): string {
  if (stage.summaryKey) {
    const template = t[stage.summaryKey as keyof Dict]
    if (typeof template === 'string') {
      return interpolate(template, stage.summaryVars ?? {})
    }
  }
  return stage.summary ?? ''
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
  const t = useT()
  const {
    config,
    setConfig,
    toggleMock,
    probeBackend,
    backendReady,
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
  // 真实模式下后端不可达：禁用运行并给出启动指引，替代裸抛网络错误
  const backendMissing = !config.mock && backendReady === false
  const errorTitle =
    error?.kind === 'http'
      ? t.errorHttpTitle
      : error?.kind === 'task'
        ? t.errorTaskTitle
        : error?.kind === 'offline'
          ? t.backendOfflineTitle
          : t.errorNetworkTitle

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
          <h1 className="studio__title">{t.studioTitle}</h1>
          <p className="studio__sub">{t.studioSub}</p>
          <div className="flex flex-wrap gap-2">
            <Badge variant={config.mock ? 'low' : 'info'}>
              {config.mock ? t.studioModeMock : t.studioModeReal}
            </Badge>
            <Badge variant="outline">{config.mock ? t.studioDataSample : t.studioDataLive}</Badge>
            {backend === 'remote' && taskId && (
              <Badge variant="outline">{t.studioTaskId} {taskId}</Badge>
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
                <CardTitle>{t.configCardTitle}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="form-field">
                  <Label htmlFor="strategy">{t.fieldStrategy}</Label>
                  <Textarea
                    id="strategy"
                    value={config.strategy}
                    onChange={(e) => setConfig({ strategy: e.target.value })}
                    disabled={running}
                  />
                </div>

                <div className="form-field">
                  <Label htmlFor="market">{t.fieldMarket}</Label>
                  <Select value={config.market} onValueChange={(v) => setConfig({ market: v })} disabled={running}>
                    <SelectTrigger id="market">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cn_stock">{t.marketCnStock}</SelectItem>
                      <SelectItem value="us_stock">{t.marketUsStock}</SelectItem>
                      <SelectItem value="hk_stock">{t.marketHkStock}</SelectItem>
                      <SelectItem value="futures">{t.marketFutures}</SelectItem>
                      <SelectItem value="crypto">{t.marketCrypto}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="form-field">
                  <Label htmlFor="symbol">{t.fieldSymbol}</Label>
                  <Input
                    id="symbol"
                    value={config.symbol}
                    onChange={(e) => setConfig({ symbol: e.target.value })}
                    disabled={running}
                  />
                  <p className="form-field__hint">{t.fieldSymbolHint}</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="form-field">
                    <Label htmlFor="start">{t.fieldStart}</Label>
                    <Input
                      id="start"
                      type="date"
                      value={config.periodStart}
                      onChange={(e) => setConfig({ periodStart: e.target.value })}
                      disabled={running}
                    />
                  </div>
                  <div className="form-field">
                    <Label htmlFor="end">{t.fieldEnd}</Label>
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
                  <Label htmlFor="capital">{t.fieldCapital}</Label>
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
                  <Label htmlFor="mock">{t.fieldMock}</Label>
                  <button
                    id="mock"
                    type="button"
                    role="switch"
                    aria-checked={config.mock}
                    className="switch"
                    data-checked={config.mock}
                    onClick={() => void toggleMock()}
                    disabled={running}
                  >
                    <span className="switch__thumb" data-checked={config.mock} />
                  </button>
                </div>
                {!config.mock && (
                  <p className="form-field__hint" role="note">
                    {t.realModeHint}
                  </p>
                )}
                {!config.mock && backendReady === null && (
                  <p className="form-field__hint" role="status">
                    {t.backendProbing}
                  </p>
                )}
                {backendMissing && (
                  <div
                    className="rounded-sm border border-warning/40 bg-warning-soft p-3"
                    role="alert"
                  >
                    <p className="text-label font-medium text-warning-ink">
                      {t.backendOfflineTitle}
                    </p>
                    <p className="mt-1 text-caption text-body">{t.backendOfflineHint}</p>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="mt-2"
                      onClick={() => void probeBackend()}
                    >
                      {t.backendRecheck}
                    </Button>
                  </div>
                )}

                <div className="flex gap-2">
                  <Button
                    type="button"
                    onClick={() => void run()}
                    disabled={running || backendMissing}
                    className="flex-1"
                  >
                    {running ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Play aria-hidden />}
                    {running ? t.actionRunning : t.actionRun}
                  </Button>
                  <Button type="button" variant="secondary" onClick={reset} disabled={running}>
                    <RotateCcw aria-hidden />
                    {t.actionReset}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </aside>

          {/* ---- 流水线与结果 ---- */}
          <section className="flex min-w-0 flex-col gap-4">
            <Card>
              <CardHeader>
                <CardTitle>{t.pipelineCardTitle}</CardTitle>
              </CardHeader>
              <CardContent>
                {error ? (
                  <div className="flex items-start gap-3 rounded-md border border-danger/40 bg-danger-soft p-4" role="alert">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger-ink" aria-hidden />
                    <div>
                      <p className="text-label font-medium text-danger-ink">{errorTitle}</p>
                      {/* 保留具体原因（超时 / 网络错误 / 后端返回体），便于定位 */}
                      <p className="mt-1 text-caption text-body">
                        <span className="sr-only">{t.errorDetailLabel}: </span>
                        {error.detail}
                      </p>
                      <Button type="button" variant="secondary" size="sm" className="mt-3" onClick={() => void run()}>
                        {t.actionRetry}
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
                          <p className="stage__label">{stageLabel(t, s.id)}</p>
                          {summaryText(t, s) && <p className="stage__summary">{summaryText(t, s)}</p>}
                        </div>
                        <Badge variant={STATUS_VARIANT[s.status]}>{statusLabel(t, s.status)}</Badge>
                      </li>
                    ))}
                  </ol>
                )}
              </CardContent>
            </Card>

            {phase === 'idle' && (
              <Card>
                <CardContent className="py-10 text-center text-label text-muted">{t.idleHint}</CardContent>
              </Card>
            )}

            {result && (
              <Tabs defaultValue="backtest">
                <TabsList>
                  <TabsTrigger value="backtest">{t.tabBacktest}</TabsTrigger>
                  <TabsTrigger value="debate">{t.tabDebate}</TabsTrigger>
                  <TabsTrigger value="report">{t.tabReport}</TabsTrigger>
                </TabsList>

                <TabsContent value="backtest" className="flex flex-col gap-4">
                  <div className="metric-grid">
                    {[
                      { label: t.metricAnnualReturn, value: pct(result.metrics.annual_return) },
                      { label: t.metricMaxDrawdown, value: pct(result.metrics.max_drawdown) },
                      { label: t.metricSharpe, value: num(result.metrics.sharpe) },
                      { label: t.metricWinRate, value: pct(result.metrics.win_rate, 1) },
                      { label: t.metricProfitFactor, value: num(result.metrics.profit_factor) },
                    ].map((m) => (
                      <div key={m.label} className="metric">
                        <p className="metric__label">{m.label}</p>
                        <p className="metric__value">{m.value}</p>
                        <p className="metric__note">
                          {t.metricRangePrefix} {result.period_start} {t.metricRangeSuffix} {result.period_end}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="chart-card">
                    <h3 className="chart-card__title">{t.chartEquityTitle}</h3>
                    <p className="chart-card__note">{t.chartEquityNote}</p>
                    <EquityChart equity={result.equity} trades={result.trades} />
                  </div>

                  <div className="chart-card">
                    <h3 className="chart-card__title">{t.chartDrawdownTitle}</h3>
                    <p className="chart-card__note">{t.chartDrawdownNote}</p>
                    <DrawdownChart equity={result.equity} />
                  </div>

                  <div className="chart-card">
                    <h3 className="chart-card__title">{t.chartTradesTitle}</h3>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>{t.tradesDate}</TableHead>
                          <TableHead>{t.tradesSide}</TableHead>
                          <TableHead className="text-right">{t.tradesPrice}</TableHead>
                          <TableHead className="text-right">{t.tradesShares}</TableHead>
                          <TableHead className="text-right">{t.tradesAmount}</TableHead>
                          <TableHead className="text-right">{t.tradesPnl}</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {result.trades.map((tr, i) => (
                          <TableRow key={`${tr.date}-${i}`}>
                            <TableCell className="num">{tr.date}</TableCell>
                            <TableCell>
                              <span className={tr.side === 'buy' ? 'text-danger-ink' : 'text-success-ink'}>
                                {tr.side === 'buy' ? t.tradeBuy : t.tradeSell}
                              </span>
                            </TableCell>
                            <TableCell className="num text-right">{tr.price.toFixed(2)}</TableCell>
                            <TableCell className="num text-right">{tr.shares}</TableCell>
                            <TableCell className="num text-right">{tr.amount.toFixed(2)}</TableCell>
                            <TableCell className="num text-right">
                              {tr.pnl == null ? '—' : tr.pnl.toFixed(2)}
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
                            <CardTitle>{t.debateBullTitle}</CardTitle>
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
                            <CardTitle>{t.debateBearTitle}</CardTitle>
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
                          <CardTitle>{t.debateRiskTitle}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ul className="list-disc space-y-1 pl-5 text-label text-body">
                            {debate.risk_findings.map((f, i) => (
                              <li key={`${i}-${f}`}>{f}</li>
                            ))}
                          </ul>
                          <div className="verdict">
                            <div>
                              <p className="text-label font-medium text-ink">
                                {t.verdictLabel}：{decisionLabel(t, debate.decision)}
                              </p>
                              <p className="mt-1 text-caption text-muted">{debate.rationale}</p>
                            </div>
                            <Badge variant="info">
                              {t.credibilityLabel} {debate.credibility_score}/100
                            </Badge>
                          </div>
                        </CardContent>
                      </Card>
                    </>
                  )}

                  {audit && (
                    <Card>
                      <CardHeader>
                        <CardTitle>{t.auditCardTitle}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="mb-3 flex gap-2">
                          <Badge variant={audit.overall_risk_level}>
                            {t.auditOverallRisk}：{riskLabel(t, audit.overall_risk_level)}
                          </Badge>
                          <Badge variant="outline">{t.auditTradability}：{audit.tradability}</Badge>
                        </div>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>{t.auditColCategory}</TableHead>
                              <TableHead>{t.auditColIssue}</TableHead>
                              <TableHead>{t.auditColSeverity}</TableHead>
                              <TableHead>{t.auditColAdvice}</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {audit.findings.map((f, i) => (
                              <TableRow key={`${i}-${f.title}`}>
                                <TableCell>{f.category}</TableCell>
                                <TableCell>{f.title}</TableCell>
                                <TableCell>
                                  <Badge variant={f.severity}>{riskLabel(t, f.severity)}</Badge>
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
                        <CardTitle>{t.finalCardTitle}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="mb-3 flex flex-wrap gap-2">
                          <Badge variant={final.overall_risk_level}>
                            {t.auditOverallRisk}：{riskLabel(t, final.overall_risk_level)}
                          </Badge>
                          <Badge variant="info">
                            {t.finalDecision}：{decisionLabel(t, final.final_decision)}
                          </Badge>
                          <Badge variant="outline">
                            {t.credibilityLabel} {final.credibility_score}/100
                          </Badge>
                        </div>
                        {final.risk_banner && (
                          <p className="mb-2 text-label text-danger-ink">{final.risk_banner}</p>
                        )}
                        <p className="text-label text-body">{final.executive_summary}</p>
                        {final.trade_advisory && (
                          <p className="mt-2 text-caption text-muted">
                            {t.finalTradeAdvisory}：{final.trade_advisory}
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
                        <CardTitle>{t.reportCardTitle}</CardTitle>
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
                                {t.reportOpenHtml}
                              </a>
                            </Button>
                          )}
                          <Button type="button" variant="secondary" size="sm" onClick={downloadReport}>
                            <Download aria-hidden />
                            {t.reportDownloadMd}
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <pre className="overflow-x-auto rounded-md border border-rule bg-ink-100/40 p-4 text-caption text-body">
                          {report.markdown || t.reportLoading}
                        </pre>
                        {!config.mock && (
                          <p className="mt-3 text-micro text-muted">{t.reportRealNote}</p>
                        )}
                      </CardContent>
                    </Card>
                  ) : (
                    <CardContent className="py-10 text-center text-label text-muted">
                      <FileText className="mx-auto mb-2 size-5 text-muted" aria-hidden />
                      {t.reportEmpty}
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
