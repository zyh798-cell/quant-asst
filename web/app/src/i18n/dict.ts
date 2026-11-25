/**
 * 轻量自研 i18n：静态字符串字典 + React Context + `useT()` hook。
 *
 * 设计约束（docs/design/TOKENS.md 9）：
 * - 不引入 react-i18next 等外部方案，字典随首包静态打包，避免拖慢 LCP；
 * - 两种语言（zh / en）字符串一一对应，key 缺失时回退到 zh，保证界面不出现空洞；
 * - 语言选择持久化在 localStorage，首次访问跟随 navigator.language。
 */

export type Lang = 'zh' | 'en'

/** localStorage 键名。集中在常量中，避免测试与实现各自拼写。 */
export const LANG_STORAGE_KEY = 'quant-asst-lang'

export const LANGS: readonly Lang[] = ['zh', 'en']

const ZH = {
  // ---- 顶部导航 ----
  navCapability: '能力',
  navPipeline: '流水线',
  navDebate: '辩论',
  navRisk: '风控',
  navReport: '报告',
  navDemo: '在线演示',
  navRepo: 'GitHub',
  navOpenStudio: '打开工作台',
  navClose: '关闭',
  navMenu: '菜单',
  navLabel: '主导航',
  brandTag: 'LLM Quant Analysis Agent',
  langSwitchLabel: '切换语言',

  // ---- 跳转链接 ----
  skipToMain: '跳到主内容',

  // ---- Hero ----
  heroTitle: '多 Agent 量化研究与风控审计框架',
  heroLede:
    'Quant Asst 把一句策略假设跑成一条可审计的研究流水线：自然语言解析、本地沙箱回测、多空辩论、红队对抗审计、确定性风控分级，最终产出 Markdown 与 HTML 双报告。',
  heroOpenStudio: '打开工作台',
  heroReadGithub: '阅读 GitHub',
  heroNote: '仅用于研究与技术演示，不含实盘下单功能，不构成投资建议。',
  statCapability: '核心能力',
  statRiskLevel: '风险级别',
  statReportFormat: '报告格式',
  statAuditablePipeline: '可审计流水线',

  // ---- 区块标题 ----
  capabilityTitle: '核心能力',
  capabilityLede: '六项能力覆盖从策略输入到报告归档的完整环节，每项都可通过命令行单独调用。',
  pipelineTitle: '流水线',
  pipelineLede: '每一步对应一组角色，前一步的产物是后一步的输入，产物落盘后可单独复查与复跑。',
  debateTitle: '多空辩论',
  debateLede: '四类角色多轮对抗：多头与空头只站自己维度，风控中立核验可证伪性，裁决汇总材料给出结论。',
  riskTitle: '风控分级',
  riskLede: '综合审计发现取最高级别，映射到确定性决策；致命风险恒为阻断，并强制写明约束边界。',
  reportTitle: '双格式报告',
  reportLede: 'Markdown 面向工程归档，HTML 面向研究查阅，两者同源生成，结论一致。',

  // ---- 能力卡片 ----
  cap01Title: '自然语言策略解析',
  cap01Text: '把一句策略描述转为结构化规格与可执行代码，字段级校验，解析失败保留原始假设与原因。',
  cap02Title: '本地沙箱回测',
  cap02Text: '事件驱动引擎在隔离沙箱内执行，输出年化、最大回撤、夏普、胜率等指标，并做样本内外切分。',
  cap03Title: '多空辩论',
  cap03Text: '多头、空头、风控核验、最终裁决多轮对抗，逐轮留痕，产出裁决与可回测的修订建议。',
  cap04Title: '红队对抗审计',
  cap04Text: '独立于辩论的审计角色，按逻辑漏洞、过拟合、未来函数、幸存者偏差等类别逐条排查并定级。',
  cap05Title: '风控分级拦截',
  cap05Text: '确定性门控规则，可复现：低、中、高、致命四级，致命风险恒为阻断。',
  cap06Title: 'Markdown 与 HTML 双报告',
  cap06Text: '同源生成归档版 Markdown 与单文件交互 HTML，含 K 线、买卖信号、净值与回撤。',

  // ---- 流水线步骤 ----
  pipe01Title: '解析',
  pipe01Role: 'hypothesis agent',
  pipe01Artifact: '策略规格与策略代码',
  pipe02Title: '回测',
  pipe02Role: 'backtest engine',
  pipe02Artifact: '绩效指标与交易明细',
  pipe03Title: '辩论',
  pipe03Role: 'bull / bear / risk / judge',
  pipe03Artifact: '逐轮辩论记录与裁决',
  pipe04Title: '审计',
  pipe04Role: 'red team / risk',
  pipe04Artifact: '审计发现与风险等级',
  pipe05Title: '风控',
  pipe05Role: 'risk gate',
  pipe05Artifact: '门控结论与约束边界',
  pipe06Title: '报告',
  pipe06Role: 'reviewer',
  pipe06Artifact: 'Markdown 与 HTML 报告',

  // ---- 辩论角色 ----
  roleBullName: '多头',
  roleBullSub: 'bull analyst',
  roleBullInput: '策略规格、回测指标',
  roleBullOutput: '看多论点、乐观情景、收益来源',
  roleBearName: '空头',
  roleBearSub: 'bear analyst',
  roleBearInput: '同一份回测与假设',
  roleBearOutput: '看空论点、失效场景、尾部风险',
  roleRiskName: '风控核验',
  roleRiskSub: 'risk checker',
  roleRiskInput: '多空草稿与留存论据',
  roleRiskOutput: '可证伪性核验、无效论据剔除',
  roleJudgeName: '裁决',
  roleJudgeSub: 'judge',
  roleJudgeInput: '三方材料与核验结论',
  roleJudgeOutput: '可信度打分、决策与修订建议',
  ioInput: '输入',
  ioOutput: '输出',

  // ---- 风险分级 ----
  riskLowLabel: '低',
  riskLowDecision: '采纳',
  riskLowDesc: '风险可控，可进入下一环节。',
  riskMediumLabel: '中',
  riskMediumDecision: '需修订',
  riskMediumDesc: '存在需修订的问题，列出具体修订项。',
  riskHighLabel: '高',
  riskHighDecision: '拒绝',
  riskHighDesc: '风险显著，说明否决理由。',
  riskCriticalLabel: '致命',
  riskCriticalDecision: '阻断',
  riskCriticalDesc: '致命风险恒为阻断，并写明约束边界。',

  // ---- 报告卡片 ----
  reportMarkdownTitle: 'Markdown',
  reportMarkdownText: '结构化文本，含假设、回测口径、辩论留痕、审计发现与风险声明，便于版本管理与评审。',
  reportHtmlTitle: 'HTML',
  reportHtmlText: '单文件交互式页面，含 K 线、买卖信号、净值与回撤，离线可直接打开。',
  reportMarkdownFigure: 'Markdown 报告版面示意',
  reportHtmlFigure: 'HTML 报告版面示意',

  // ---- 页脚 ----
  footerRiskTitle: '风险声明',
  footerRiskText:
    'Quant Asst 仅用于量化研究与技术演示，不构成任何投资建议，不含实盘下单功能。历史回测结果不代表未来收益。',
  footerLicense: 'MIT License',

  // ---- 风险级别（界面标签；与 core/schemas.py 的 RISK_LEVELS 一一对应）----
  riskLow: '低',
  riskMedium: '中',
  riskHigh: '高',
  riskCritical: '致命',

  // ---- 决策（debate / audit / final 共用）----
  decisionAdopt: '采纳',
  decisionRevise: '需修订',
  decisionReject: '拒绝',
  decisionBlocked: '阻断',

  // ---- 阶段状态 ----
  stagePending: '等待',
  stageRunning: '进行中',
  stageDone: '完成',
  stageFailed: '失败',
  stageSkipped: '跳过',

  // ---- Studio：页面骨架 ----
  studioTitle: '研究工作台',
  studioSub:
    '填写策略假设并运行研究流水线：左侧为纯前端样例（data: sample），关闭 mock 后由本地接口层（server/）接管，逐阶段返回真实产物。',
  studioModeMock: 'mock 离线',
  studioModeReal: '真实模式',
  studioDataSample: 'data: sample',
  studioDataLive: 'data: live',
  studioTaskId: 'task',

  // ---- Studio：策略配置 ----
  configCardTitle: '策略配置',
  fieldStrategy: '策略描述',
  fieldMarket: '市场',
  fieldSymbol: '标的代码',
  fieldSymbolHint: '统一格式 market:code，例如 cn:600519',
  fieldStart: '开始日',
  fieldEnd: '结束日',
  fieldCapital: '初始资金',
  fieldMock: 'mock 离线模式',
  realModeHint:
    '真实模式需本地启动后端（server/：uv run uvicorn server.main:app --port 8000），详见 README。未启动后端时运行会进入失败态。',
  actionRun: '运行策略',
  actionRunning: '运行中',
  actionReset: '重置',

  // ---- Studio：流水线与结果 ----
  pipelineCardTitle: '研究流水线',
  taskFailedTitle: '任务未能完成',
  actionRetry: '重试',
  idleHint: '填写左侧配置并运行，结果将在此处呈现。',
  tabBacktest: '回测结果',
  tabDebate: '辩论审计',
  tabReport: '报告',
  metricAnnualReturn: '年化收益',
  metricMaxDrawdown: '最大回撤',
  metricSharpe: '夏普比率',
  metricWinRate: '按笔胜率',
  metricProfitFactor: '盈亏比',
  metricRangePrefix: '区间',
  metricRangeSuffix: '至',
  chartEquityTitle: '净值曲线',
  chartEquityNote: '买入为向上三角、卖出为向下三角；颜色与形状双通道。',
  chartDrawdownTitle: '回撤曲线',
  chartDrawdownNote: '基线恒为 0，数值为负表示低于历史峰值。',
  chartTradesTitle: '成交记录',
  tradesDate: '日期',
  tradesSide: '方向',
  tradesPrice: '价格',
  tradesShares: '股数',
  tradesAmount: '金额',
  tradesPnl: '盈亏',
  tradeBuy: '买入',
  tradeSell: '卖出',
  debateBullTitle: '多头要点',
  debateBearTitle: '空头要点',
  debateRiskTitle: '风控核验',
  verdictLabel: '裁决',
  credibilityLabel: '可信度',
  auditCardTitle: '红队审计',
  auditOverallRisk: '综合风险',
  auditTradability: '可行性',
  auditColCategory: '类别',
  auditColIssue: '问题',
  auditColSeverity: '级别',
  auditColAdvice: '建议',
  finalCardTitle: '风控综合结论',
  finalDecision: '最终决策',
  finalTradeAdvisory: '交易建议',
  reportCardTitle: 'Markdown 报告',
  reportOpenHtml: '打开 HTML 报告',
  reportDownloadMd: '下载 .md',
  reportLoading: '报告正文加载中…',
  reportEmpty: '报告尚未生成。',
  reportRealNote: '真实模式报告来自本地接口层，落盘于 var/reports/<task_id>/。',

  // ---- 图表 tooltip（组件层）----
  chartNav: '净值',
  chartDrawdown: '回撤',

  // ---- Studio：市场选项 ----
  marketCnStock: 'A 股',
  marketUsStock: '美股',
  marketHkStock: '港股',
  marketFutures: '期货',
  marketCrypto: '加密',

  // ---- Studio：阶段标签与摘要（store 提供 key 与数值）----
  stageParse: '解析',
  stageBacktest: '回测',
  stageDebate: '辩论',
  stageAudit: '审计',
  stageRisk: '风控',
  stageReport: '报告',
  summaryParse: '已解析策略规格：标的、区间、开平仓规则与参数',
  summaryBacktest: '回测完成：{n} 笔成交，{d} 个交易日',
  summaryBacktestFallback: '回测完成',
  summaryDebate: '裁决：{decision}，可信度 {score}/100',
  summaryDebateFallback: '辩论完成',
  summaryAudit: '综合风险：{risk}，{n} 条发现',
  summaryAuditFallback: '审计完成',
  summaryRisk: '决策映射完成，约束边界已写入报告',
  summaryRiskFallback: '风控完成',
  summaryReport: '已生成 Markdown 报告（HTML 报告见真实模式）',
  taskFailed: '任务失败',
  taskRunFailed: '任务执行失败',
}

export type Dict = typeof ZH

const EN: Dict = {
  // ---- header ----
  navCapability: 'Capabilities',
  navPipeline: 'Pipeline',
  navDebate: 'Debate',
  navRisk: 'Risk control',
  navReport: 'Reports',
  navDemo: 'Live demo',
  navRepo: 'GitHub',
  navOpenStudio: 'Open studio',
  navClose: 'Close',
  navMenu: 'Menu',
  navLabel: 'Primary navigation',
  brandTag: 'LLM Quant Analysis Agent',
  langSwitchLabel: 'Switch language',

  // ---- skip link ----
  skipToMain: 'Skip to main content',

  // ---- Hero ----
  heroTitle: 'Multi-agent quantitative research and risk-audit framework',
  heroLede:
    'Quant Asst turns one strategy hypothesis into an auditable research pipeline: natural-language parsing, sandboxed backtesting, a bull/bear debate, red-team auditing, deterministic risk grading, and finally dual reports in Markdown and HTML.',
  heroOpenStudio: 'Open studio',
  heroReadGithub: 'View on GitHub',
  heroNote:
    'For research and technical demonstration only. No live order placement; not investment advice.',
  statCapability: 'Core capabilities',
  statRiskLevel: 'Risk levels',
  statReportFormat: 'Report formats',
  statAuditablePipeline: 'Auditable pipelines',

  // ---- sections ----
  capabilityTitle: 'Core capabilities',
  capabilityLede:
    'Six capabilities cover the full path from strategy input to report archiving, each callable on its own from the CLI.',
  pipelineTitle: 'Pipeline',
  pipelineLede:
    'Each step maps to a set of roles; the artifact of one step is the input of the next, and every artifact is persisted so it can be reviewed or re-run independently.',
  debateTitle: 'Bull/bear debate',
  debateLede:
    'Four roles argue over multiple rounds: bull and bear hold their own dimension, risk checking neutrally tests falsifiability, and the judge summarizes the material into a verdict.',
  riskTitle: 'Risk grading',
  riskLede:
    'The highest severity across audit findings maps to a deterministic decision; critical risks always block and must state their constraint boundaries.',
  reportTitle: 'Dual-format reports',
  reportLede:
    'Markdown serves engineering archiving, HTML serves research review; both are generated from the same source and reach the same conclusion.',

  // ---- capability cards ----
  cap01Title: 'Natural-language strategy parsing',
  cap01Text:
    'Turns a plain-language strategy description into a structured spec and executable code with field-level validation; a failed parse keeps the original hypothesis and the reason.',
  cap02Title: 'Sandboxed backtesting',
  cap02Text:
    'An event-driven engine runs inside an isolated sandbox and reports annualized return, maximum drawdown, Sharpe, win rate and more, with an in-sample / out-of-sample split.',
  cap03Title: 'Bull/bear debate',
  cap03Text:
    'Bull, bear, risk checker and judge argue over multiple rounds with per-round traces, producing a verdict and backtestable revision suggestions.',
  cap04Title: 'Red-team audit',
  cap04Text:
    'An audit role independent of the debate checks logic flaws, overfitting, lookahead functions, survivorship bias and similar categories item by item, assigning a severity grade.',
  cap05Title: 'Deterministic risk gate',
  cap05Text:
    'Reproducible rule-based gating across four grades - low, medium, high and critical; critical always blocks.',
  cap06Title: 'Markdown and HTML dual reports',
  cap06Text:
    'Generated from one source into an archival Markdown document and a single-file interactive HTML page with candlesticks, signals, equity and drawdown.',

  // ---- pipeline steps ----
  pipe01Title: 'Parse',
  pipe01Role: 'hypothesis agent',
  pipe01Artifact: 'Strategy spec and strategy code',
  pipe02Title: 'Backtest',
  pipe02Role: 'backtest engine',
  pipe02Artifact: 'Performance metrics and trade records',
  pipe03Title: 'Debate',
  pipe03Role: 'bull / bear / risk / judge',
  pipe03Artifact: 'Round-by-round records and verdict',
  pipe04Title: 'Audit',
  pipe04Role: 'red team / risk',
  pipe04Artifact: 'Audit findings and risk grade',
  pipe05Title: 'Risk gate',
  pipe05Role: 'risk gate',
  pipe05Artifact: 'Gate conclusion and constraint boundaries',
  pipe06Title: 'Report',
  pipe06Role: 'reviewer',
  pipe06Artifact: 'Markdown and HTML reports',

  // ---- debate roles ----
  roleBullName: 'Bull',
  roleBullSub: 'bull analyst',
  roleBullInput: 'Strategy spec, backtest metrics',
  roleBullOutput: 'Bull case, optimistic scenario, source of returns',
  roleBearName: 'Bear',
  roleBearSub: 'bear analyst',
  roleBearInput: 'Same backtest and hypothesis',
  roleBearOutput: 'Bear case, failure scenarios, tail risk',
  roleRiskName: 'Risk check',
  roleRiskSub: 'risk checker',
  roleRiskInput: 'Bull and bear drafts with retained evidence',
  roleRiskOutput: 'Falsifiability checks, invalid arguments removed',
  roleJudgeName: 'Judge',
  roleJudgeSub: 'judge',
  roleJudgeInput: 'Material from three parties plus check conclusions',
  roleJudgeOutput: 'Credibility score, decision and revision suggestions',
  ioInput: 'Input',
  ioOutput: 'Output',

  // ---- risk grading ----
  riskLowLabel: 'Low',
  riskLowDecision: 'Adopt',
  riskLowDesc: 'Risk is manageable; the workflow may proceed to the next step.',
  riskMediumLabel: 'Medium',
  riskMediumDecision: 'Revise',
  riskMediumDesc: 'Issues require revision; list the specific items to change.',
  riskHighLabel: 'High',
  riskHighDecision: 'Reject',
  riskHighDesc: 'Risk is significant; state the reason for rejection.',
  riskCriticalLabel: 'Critical',
  riskCriticalDecision: 'Blocked',
  riskCriticalDesc: 'A critical risk is always blocked, with its constraint boundaries written out.',

  // ---- report cards ----
  reportMarkdownTitle: 'Markdown',
  reportMarkdownText:
    'Structured text covering the hypothesis, backtest conventions, debate traces, audit findings and the risk disclaimer - suited to version control and review.',
  reportHtmlTitle: 'HTML',
  reportHtmlText:
    'A standalone interactive page with candlesticks, buy/sell signals, equity and drawdown, openable offline.',
  reportMarkdownFigure: 'Markdown report layout preview',
  reportHtmlFigure: 'HTML report layout preview',

  // ---- footer ----
  footerRiskTitle: 'Disclaimer',
  footerRiskText:
    'Quant Asst is for quantitative research and technical demonstration only. It does not constitute investment advice and provides no live order placement. Historical backtest results do not represent future returns.',
  footerLicense: 'MIT License',

  // ---- risk levels (mirror core/schemas.py RISK_LEVELS) ----
  riskLow: 'Low',
  riskMedium: 'Medium',
  riskHigh: 'High',
  riskCritical: 'Critical',

  // ---- decisions ----
  decisionAdopt: 'Adopt',
  decisionRevise: 'Revise',
  decisionReject: 'Reject',
  decisionBlocked: 'Blocked',

  // ---- stage status ----
  stagePending: 'Pending',
  stageRunning: 'Running',
  stageDone: 'Done',
  stageFailed: 'Failed',
  stageSkipped: 'Skipped',

  // ---- studio shell ----
  studioTitle: 'Research workbench',
  studioSub:
    'Describe a strategy hypothesis and run the research pipeline. The left panel uses pure front-end samples (data: sample); turn mock off to hand over to the local interface layer (server/) which returns real artifacts stage by stage.',
  studioModeMock: 'mock offline',
  studioModeReal: 'real mode',
  studioDataSample: 'data: sample',
  studioDataLive: 'data: live',
  studioTaskId: 'task',

  // ---- configuration form ----
  configCardTitle: 'Strategy configuration',
  fieldStrategy: 'Strategy description',
  fieldMarket: 'Market',
  fieldSymbol: 'Symbol',
  fieldSymbolHint: 'Use market:code, for example cn:600519',
  fieldStart: 'Start date',
  fieldEnd: 'End date',
  fieldCapital: 'Initial capital',
  fieldMock: 'mock offline mode',
  realModeHint:
    'Real mode requires the backend running locally (server/: uv run uvicorn server.main:app --port 8000), see README. Running without it moves the task to a failed state.',
  actionRun: 'Run strategy',
  actionRunning: 'Running',
  actionReset: 'Reset',

  // ---- pipeline and results ----
  pipelineCardTitle: 'Research pipeline',
  taskFailedTitle: 'Task did not complete',
  actionRetry: 'Retry',
  idleHint: 'Fill in the configuration on the left and run; results appear here.',
  tabBacktest: 'Backtest',
  tabDebate: 'Debate and audit',
  tabReport: 'Report',
  metricAnnualReturn: 'Annualized return',
  metricMaxDrawdown: 'Maximum drawdown',
  metricSharpe: 'Sharpe ratio',
  metricWinRate: 'Win rate per trade',
  metricProfitFactor: 'Profit factor',
  metricRangePrefix: 'Period',
  metricRangeSuffix: 'to',
  chartEquityTitle: 'Equity curve',
  chartEquityNote: 'Buy is an upward triangle and sell a downward triangle; colour and shape carry the same channel.',
  chartDrawdownTitle: 'Drawdown',
  chartDrawdownNote: 'The baseline is always 0; negative values sit below the historical peak.',
  chartTradesTitle: 'Trade records',
  tradesDate: 'Date',
  tradesSide: 'Side',
  tradesPrice: 'Price',
  tradesShares: 'Shares',
  tradesAmount: 'Amount',
  tradesPnl: 'PnL',
  tradeBuy: 'Buy',
  tradeSell: 'Sell',
  debateBullTitle: 'Bull points',
  debateBearTitle: 'Bear points',
  debateRiskTitle: 'Risk check',
  verdictLabel: 'Verdict',
  credibilityLabel: 'Credibility',
  auditCardTitle: 'Red-team audit',
  auditOverallRisk: 'Overall risk',
  auditTradability: 'Tradability',
  auditColCategory: 'Category',
  auditColIssue: 'Issue',
  auditColSeverity: 'Severity',
  auditColAdvice: 'Advice',
  finalCardTitle: 'Final risk conclusion',
  finalDecision: 'Final decision',
  finalTradeAdvisory: 'Trade advisory',
  reportCardTitle: 'Markdown report',
  reportOpenHtml: 'Open HTML report',
  reportDownloadMd: 'Download .md',
  reportLoading: 'Loading report body…',
  reportEmpty: 'No report yet.',
  reportRealNote: 'In real mode reports come from the local interface layer and are written to var/reports/<task_id>/.',

  // ---- chart tooltips ----
  chartNav: 'NAV',
  chartDrawdown: 'Drawdown',

  // ---- market options ----
  marketCnStock: 'A-shares',
  marketUsStock: 'US stocks',
  marketHkStock: 'Hong Kong stocks',
  marketFutures: 'Futures',
  marketCrypto: 'Crypto',

  // ---- stage labels and summaries ----
  stageParse: 'Parse',
  stageBacktest: 'Backtest',
  stageDebate: 'Debate',
  stageAudit: 'Audit',
  stageRisk: 'Risk gate',
  stageReport: 'Report',
  summaryParse: 'Parsed the strategy spec: symbol, period, entry/exit rules and parameters',
  summaryBacktest: 'Backtest done: {n} trades over {d} trading days',
  summaryBacktestFallback: 'Backtest done',
  summaryDebate: 'Verdict: {decision}, credibility {score}/100',
  summaryDebateFallback: 'Debate done',
  summaryAudit: 'Overall risk: {risk}, {n} findings',
  summaryAuditFallback: 'Audit done',
  summaryRisk: 'Decision mapping done; constraint boundaries written into the report',
  summaryRiskFallback: 'Risk gate done',
  summaryReport: 'Markdown report generated (see real mode for the HTML report)',
  taskFailed: 'Task failed',
  taskRunFailed: 'Task execution failed',
}

export const DICTS: Record<Lang, Dict> = { zh: ZH, en: EN }

/**
 * 替换模板中的 `{key}` 占位符（用于阶段摘要等由 store 计算数值的文案）。
 * 未提供的键保留原占位符，避免出现空洞。
 */
export function interpolate(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in vars ? String(vars[key]) : match,
  )
}

/** 风险级别 -> 展示标签（界面层不直接信任后端返回的原始枚举值）。 */
export function riskLabel(dict: Dict, level: string): string {
  switch (level) {
    case 'low':
      return dict.riskLow
    case 'medium':
      return dict.riskMedium
    case 'high':
      return dict.riskHigh
    case 'critical':
      return dict.riskCritical
    default:
      // fail-safe：未知级别不静默降级，原样显示以便排查
      return level
  }
}

/** 决策 -> 展示标签。 */
export function decisionLabel(dict: Dict, decision: string): string {
  switch (decision) {
    case 'adopt':
      return dict.decisionAdopt
    case 'revise':
      return dict.decisionRevise
    case 'reject':
      return dict.decisionReject
    case 'blocked':
      return dict.decisionBlocked
    default:
      return decision
  }
}
