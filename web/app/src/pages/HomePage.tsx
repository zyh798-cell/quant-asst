import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, FileText, Gavel, ShieldCheck, TrendingDown, TrendingUp } from 'lucide-react'
import gsap from 'gsap'

import { HeroScene } from '@/components/hero/HeroScene'
import '@/hooks/useSmoothScroll'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useT } from '@/i18n'
import type { Dict } from '@/i18n/dict'
import './home.css'

/** 能力卡片：文案取自语言字典，结构（index / wide）保持静态，避免 GSAP 选择器受影响。 */
function capabilities(t: Dict) {
  return [
    { index: '01', title: t.cap01Title, text: t.cap01Text, wide: false },
    { index: '02', title: t.cap02Title, text: t.cap02Text, wide: false },
    { index: '03', title: t.cap03Title, text: t.cap03Text, wide: false },
    { index: '04', title: t.cap04Title, text: t.cap04Text, wide: false },
    { index: '05', title: t.cap05Title, text: t.cap05Text, wide: false },
    { index: '06', title: t.cap06Title, text: t.cap06Text, wide: true },
  ]
}

function pipeline(t: Dict) {
  return [
    { index: '01', title: t.pipe01Title, role: t.pipe01Role, artifact: t.pipe01Artifact },
    { index: '02', title: t.pipe02Title, role: t.pipe02Role, artifact: t.pipe02Artifact },
    { index: '03', title: t.pipe03Title, role: t.pipe03Role, artifact: t.pipe03Artifact },
    { index: '04', title: t.pipe04Title, role: t.pipe04Role, artifact: t.pipe04Artifact },
    { index: '05', title: t.pipe05Title, role: t.pipe05Role, artifact: t.pipe05Artifact },
    { index: '06', title: t.pipe06Title, role: t.pipe06Role, artifact: t.pipe06Artifact },
  ]
}

function roles(t: Dict) {
  return [
    { name: t.roleBullName, sub: t.roleBullSub, input: t.roleBullInput, output: t.roleBullOutput, icon: TrendingUp },
    { name: t.roleBearName, sub: t.roleBearSub, input: t.roleBearInput, output: t.roleBearOutput, icon: TrendingDown },
    { name: t.roleRiskName, sub: t.roleRiskSub, input: t.roleRiskInput, output: t.roleRiskOutput, icon: ShieldCheck },
    { name: t.roleJudgeName, sub: t.roleJudgeSub, input: t.roleJudgeInput, output: t.roleJudgeOutput, icon: Gavel },
  ]
}

/** 风险分级：level / tone / width 为语义与视觉常量，仅 label / decisionLabel / desc 随语言变化。 */
function riskScale(t: Dict) {
  return [
    { level: 'low' as const, label: t.riskLowLabel, decisionLabel: t.riskLowDecision, tone: 'bg-success', width: '25%', desc: t.riskLowDesc },
    { level: 'medium' as const, label: t.riskMediumLabel, decisionLabel: t.riskMediumDecision, tone: 'bg-warning', width: '50%', desc: t.riskMediumDesc },
    { level: 'high' as const, label: t.riskHighLabel, decisionLabel: t.riskHighDecision, tone: 'bg-danger', width: '75%', desc: t.riskHighDesc },
    { level: 'critical' as const, label: t.riskCriticalLabel, decisionLabel: t.riskCriticalDecision, tone: 'bg-critical', width: '100%', desc: t.riskCriticalDesc },
  ]
}

export function HomePage() {
  const root = useRef<HTMLDivElement>(null)
  const t = useT()
  const CAPABILITIES = capabilities(t)
  const PIPELINE = pipeline(t)
  const ROLES = roles(t)
  const RISK_SCALE = riskScale(t)

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
            <h1 className="hero__title">{t.heroTitle}</h1>
            <p className="hero__lede">{t.heroLede}</p>
            <div className="hero__actions">
              <Button asChild size="lg">
                <Link to="/studio">
                  {t.heroOpenStudio}
                  <ArrowRight aria-hidden />
                </Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <a href="https://github.com/zyh798-cell/quant-asst" rel="noopener noreferrer">
                  {t.heroReadGithub}
                </a>
              </Button>
            </div>
            <p className="hero__note">{t.heroNote}</p>
            <dl className="hero__stats">
              {[
                { end: 6, label: t.statCapability },
                { end: 4, label: t.statRiskLevel },
                { end: 2, label: t.statReportFormat },
                { end: 1, label: t.statAuditablePipeline },
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
            <h2 className="section__title">{t.capabilityTitle}</h2>
            <p className="section__lede">{t.capabilityLede}</p>
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
            <h2 className="section__title">{t.pipelineTitle}</h2>
            <p className="section__lede">{t.pipelineLede}</p>
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
            <h2 className="section__title">{t.debateTitle}</h2>
            <p className="section__lede">{t.debateLede}</p>
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
                  <dt>{t.ioInput}</dt>
                  <dd>{r.input}</dd>
                  <dt>{t.ioOutput}</dt>
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
            <h2 className="section__title">{t.riskTitle}</h2>
            <p className="section__lede">{t.riskLede}</p>
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
            <h2 className="section__title">{t.reportTitle}</h2>
            <p className="section__lede">{t.reportLede}</p>
          </div>
          <ul className="report-grid">
            <li className="report-card reveal">
              <div className="flex items-center gap-2">
                <FileText className="size-4 text-accent-ink" aria-hidden />
                <h3 className="report-card__title">{t.reportMarkdownTitle}</h3>
              </div>
              <p className="report-card__text">{t.reportMarkdownText}</p>
              <div className="report-card__frame">
                <svg viewBox="0 0 320 120" role="img" aria-label={t.reportMarkdownFigure}>
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
                <h3 className="report-card__title">{t.reportHtmlTitle}</h3>
              </div>
              <p className="report-card__text">{t.reportHtmlText}</p>
              <div className="report-card__frame">
                <svg viewBox="0 0 320 120" role="img" aria-label={t.reportHtmlFigure}>
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
