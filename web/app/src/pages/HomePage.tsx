import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, FileText, Gavel, ShieldCheck, TrendingDown, TrendingUp } from 'lucide-react'
import gsap from 'gsap'

import { HeroScene } from '@/components/hero/HeroScene'
import '@/hooks/useSmoothScroll'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import './home.css'

const CAPABILITIES = [
  {
    index: '01',
    title: '自然语言策略解析',
    text: '把一句策略描述转为结构化规格与可执行代码，字段级校验，解析失败保留原始假设与原因。',
    wide: false,
  },
  {
    index: '02',
    title: '本地沙箱回测',
    text: '事件驱动引擎在隔离沙箱内执行，输出年化、最大回撤、夏普、胜率等指标，并做样本内外切分。',
    wide: false,
  },
  {
    index: '03',
    title: '多空辩论',
    text: '多头、空头、风控核验、最终裁决多轮对抗，逐轮留痕，产出裁决与可回测的修订建议。',
    wide: false,
  },
  {
    index: '04',
    title: '红队对抗审计',
    text: '独立于辩论的审计角色，按逻辑漏洞、过拟合、未来函数、幸存者偏差等类别逐条排查并定级。',
    wide: false,
  },
  {
    index: '05',
    title: '风控分级拦截',
    text: '确定性门控规则，可复现：低、中、高、致命四级，致命风险恒为阻断。',
    wide: false,
  },
  {
    index: '06',
    title: 'Markdown 与 HTML 双报告',
    text: '同源生成归档版 Markdown 与单文件交互 HTML，含 K 线、买卖信号、净值与回撤。',
    wide: true,
  },
]

const PIPELINE = [
  { index: '01', title: '解析', role: 'hypothesis agent', artifact: '策略规格与策略代码' },
  { index: '02', title: '回测', role: 'backtest engine', artifact: '绩效指标与交易明细' },
  { index: '03', title: '辩论', role: 'bull / bear / risk / judge', artifact: '逐轮辩论记录与裁决' },
  { index: '04', title: '审计', role: 'red team / risk', artifact: '审计发现与风险等级' },
  { index: '05', title: '风控', role: 'risk gate', artifact: '门控结论与约束边界' },
  { index: '06', title: '报告', role: 'reviewer', artifact: 'Markdown 与 HTML 报告' },
]

const ROLES = [
  {
    name: '多头',
    sub: 'bull analyst',
    input: '策略规格、回测指标',
    output: '看多论点、乐观情景、收益来源',
    icon: TrendingUp,
  },
  {
    name: '空头',
    sub: 'bear analyst',
    input: '同一份回测与假设',
    output: '看空论点、失效场景、尾部风险',
    icon: TrendingDown,
  },
  {
    name: '风控核验',
    sub: 'risk checker',
    input: '多空草稿与留存论据',
    output: '可证伪性核验、无效论据剔除',
    icon: ShieldCheck,
  },
  {
    name: '裁决',
    sub: 'judge',
    input: '三方材料与核验结论',
    output: '可信度打分、决策与修订建议',
    icon: Gavel,
  },
]

const RISK_SCALE: ReadonlyArray<{
  level: 'low' | 'medium' | 'high' | 'critical'
  label: string
  decisionLabel: string
  tone: string
  width: string
  desc: string
}> = [
  { level: 'low', label: '低', decisionLabel: '采纳', tone: 'bg-success', width: '25%', desc: '风险可控，可进入下一环节。' },
  { level: 'medium', label: '中', decisionLabel: '需修订', tone: 'bg-warning', width: '50%', desc: '存在需修订的问题，列出具体修订项。' },
  { level: 'high', label: '高', decisionLabel: '拒绝', tone: 'bg-danger', width: '75%', desc: '风险显著，说明否决理由。' },
  { level: 'critical', label: '致命', decisionLabel: '阻断', tone: 'bg-critical', width: '100%', desc: '致命风险恒为阻断，并写明约束边界。' },
]

export function HomePage() {
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const ctx = gsap.context(() => {
      gsap
        .timeline({ defaults: { ease: 'power3.out' } })
        .from('.hero__title', { opacity: 0, y: 24, duration: 0.6 })
        .from('.hero__lede', { opacity: 0, y: 16, duration: 0.5 }, '-=0.35')
        .from('.hero__actions', { opacity: 0, y: 12, duration: 0.45 }, '-=0.3')
        .from('.hero__note', { opacity: 0, duration: 0.4 }, '-=0.2')
        .from('.hero__stats', { opacity: 0, duration: 0.4 }, '-=0.2')
        .from('.hero__figure', { opacity: 0, y: 20, duration: 0.6 }, '-=0.5')

      gsap.utils.toArray<HTMLElement>('.reveal').forEach((el) => {
        gsap.from(el, {
          opacity: 0,
          y: 16,
          duration: 0.55,
          ease: 'power3.out',
          scrollTrigger: { trigger: el, start: 'top 88%' },
        })
      })

      gsap.utils.toArray<HTMLElement>('.pipeline__step').forEach((el, i) => {
        gsap.from(el, {
          opacity: 0,
          y: 16,
          duration: 0.5,
          delay: i * 0.06,
          scrollTrigger: { trigger: '.pipeline', start: 'top 82%' },
        })
      })
      gsap.from('.pipeline__arrow', {
        scaleX: 0,
        duration: 0.45,
        stagger: 0.1,
        ease: 'power2.out',
        scrollTrigger: { trigger: '.pipeline', start: 'top 82%' },
      })

      gsap.utils.toArray<HTMLElement>('.num-count').forEach((el) => {
        const end = Number(el.dataset.end ?? 0)
        const obj = { v: 0 }
        gsap.to(obj, {
          v: end,
          duration: 1.2,
          ease: 'power2.out',
          scrollTrigger: { trigger: el, start: 'top 88%' },
          onUpdate: () => {
            el.textContent = String(Math.round(obj.v))
          },
        })
      })
    }, root)
    return () => ctx.revert()
  }, [])

  return (
    <div ref={root}>
      {/* ---- Hero：左侧文案 + 右侧分层动效场景 ---- */}
      <section className="hero">
        <div className="shell hero__inner">
          <div className="hero__copy">
            <h1 className="hero__title">多 Agent 量化研究与风控审计框架</h1>
            <p className="hero__lede">
              Quant Asst 把一句策略假设跑成一条可审计的研究流水线：自然语言解析、本地沙箱回测、
              多空辩论、红队对抗审计、确定性风控分级，最终产出 Markdown 与 HTML 双报告。
            </p>
            <div className="hero__actions">
              <Button asChild size="lg">
                <Link to="/studio">
                  打开工作台
                  <ArrowRight aria-hidden />
                </Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <a href="https://github.com/zyh798-cell/quant-asst" rel="noopener noreferrer">
                  阅读 GitHub
                </a>
              </Button>
            </div>
            <p className="hero__note">仅用于研究与技术演示，不含实盘下单功能，不构成投资建议。</p>
            <dl className="hero__stats">
              {[
                { end: 6, label: '核心能力' },
                { end: 4, label: '风险级别' },
                { end: 2, label: '报告格式' },
                { end: 1, label: '可审计流水线' },
              ].map((s) => (
                <div key={s.label} className="hero__stat">
                  <dd className="num hero__stat-num">
                    <span className="num-count" data-end={s.end}>
                      0
                    </span>
                  </dd>
                  <dt className="hero__stat-label">{s.label}</dt>
                </div>
              ))}
            </dl>
          </div>

          <figure className="hero__figure">
            <HeroScene />
          </figure>
        </div>
      </section>

      {/* ---- 能力 ---- */}
      <section className="section" id="capability">
        <div className="shell">
          <div className="section__head reveal">
            <h2 className="section__title">核心能力</h2>
            <p className="section__lede">
              六项能力覆盖从策略输入到报告归档的完整环节，每项都可通过命令行单独调用。
            </p>
          </div>
          <ul className="capability-grid">
            {CAPABILITIES.map((c) => (
              <li key={c.index} className={`capability reveal${c.wide ? ' capability--wide' : ''}`}>
                <p className="capability__index">{c.index}</p>
                <h3 className="capability__title">{c.title}</h3>
                <p className="capability__text">{c.text}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ---- 流水线 ---- */}
      <section className="section section--tight" id="pipeline">
        <div className="shell">
          <div className="section__head reveal">
            <h2 className="section__title">流水线</h2>
            <p className="section__lede">
              每一步对应一组角色，前一步的产物是后一步的输入，产物落盘后可单独复查与复跑。
            </p>
          </div>
          <ol className="pipeline">
            {PIPELINE.map((s) => (
              <li key={s.index} className="pipeline__step">
                <span className="pipeline__arrow" aria-hidden="true" />
                <p className="pipeline__index">{s.index}</p>
                <h3 className="pipeline__title">{s.title}</h3>
                <p className="pipeline__meta">{s.role}</p>
                <p className="pipeline__meta">{s.artifact}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---- 多空辩论 ---- */}
      <section className="section" id="debate">
        <div className="shell">
          <div className="section__head reveal">
            <h2 className="section__title">多空辩论</h2>
            <p className="section__lede">
              四类角色多轮对抗：多头与空头只站自己维度，风控中立核验可证伪性，裁决汇总材料给出结论。
            </p>
          </div>
          <ul className="debate-grid">
            {ROLES.map((r) => (
              <li key={r.name} className="role-card reveal">
                <div className="role-card__head">
                  <span className="role-card__avatar" aria-hidden="true">
                    <r.icon className="size-5" />
                  </span>
                  <div>
                    <h3 className="role-card__title">{r.name}</h3>
                    <p className="role-card__sub">{r.sub}</p>
                  </div>
                </div>
                <dl className="role-card__io">
                  <dt>输入</dt>
                  <dd>{r.input}</dd>
                  <dt>输出</dt>
                  <dd>{r.output}</dd>
                </dl>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ---- 风控分级 ---- */}
      <section className="section section--tight" id="risk">
        <div className="shell">
          <div className="section__head reveal">
            <h2 className="section__title">风控分级</h2>
            <p className="section__lede">
              综合审计发现取最高级别，映射到确定性决策；致命风险恒为阻断，并强制写明约束边界。
            </p>
          </div>
          <ul className="risk-scale">
            {RISK_SCALE.map((r) => (
              <li key={r.level} className="risk-cell reveal">
                <div className="risk-cell__bar">
                  <span className={r.tone} style={{ width: r.width }} />
                </div>
                <h3 className="risk-cell__title">{r.label}</h3>
                <p className="risk-cell__desc">{r.desc}</p>
                <p className="risk-cell__decision">
                  <Badge variant={r.level}>{r.decisionLabel}</Badge>
                </p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ---- 报告 ---- */}
      <section className="section" id="report">
        <div className="shell">
          <div className="section__head reveal">
            <h2 className="section__title">双格式报告</h2>
            <p className="section__lede">
              Markdown 面向工程归档，HTML 面向研究查阅，两者同源生成，结论一致。
            </p>
          </div>
          <ul className="report-grid">
            <li className="report-card reveal">
              <div className="flex items-center gap-2">
                <FileText className="size-4 text-accent-ink" aria-hidden />
                <h3 className="report-card__title">Markdown</h3>
              </div>
              <p className="report-card__text">
                结构化文本，含假设、回测口径、辩论留痕、审计发现与风险声明，便于版本管理与评审。
              </p>
              <div className="report-card__frame">
                <svg viewBox="0 0 320 120" role="img" aria-label="Markdown 报告版面示意">
                  <g fill="var(--color-ink-300)">
                    <rect x="20" y="16" width="120" height="10" rx="2" />
                    <rect x="20" y="36" width="260" height="6" rx="2" />
                    <rect x="20" y="48" width="220" height="6" rx="2" />
                    <rect x="20" y="60" width="240" height="6" rx="2" />
                    <rect x="20" y="80" width="90" height="8" rx="2" />
                    <rect x="20" y="96" width="260" height="6" rx="2" />
                  </g>
                </svg>
              </div>
            </li>
            <li className="report-card reveal">
              <div className="flex items-center gap-2">
                <FileText className="size-4 text-accent-ink" aria-hidden />
                <h3 className="report-card__title">HTML</h3>
              </div>
              <p className="report-card__text">
                单文件交互式页面，含 K 线、买卖信号、净值与回撤，离线可直接打开。
              </p>
              <div className="report-card__frame">
                <svg viewBox="0 0 320 120" role="img" aria-label="HTML 报告版面示意">
                  <g stroke="var(--color-ink-300)" strokeWidth="1">
                    <line x1="20" y1="20" x2="20" y2="100" />
                    <line x1="20" y1="100" x2="300" y2="100" />
                  </g>
                  <path d="M20 84 L70 72 L120 78 L170 50 L220 58 L270 34 L300 40" fill="none" stroke="var(--chart-series-1)" strokeWidth="2.5" />
                </svg>
              </div>
            </li>
          </ul>
        </div>
      </section>
    </div>
  )
}
