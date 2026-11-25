import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ExternalLink, Menu, X } from 'lucide-react'

import logo from '@/assets/brand/logo-color.svg'
import { LangSwitch } from '@/components/LangSwitch'
import { Button } from '@/components/ui/button'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'

/** GitHub 官方 octicon（mark-github, 16x16），避免依赖 lucide 已移除的品牌图标 */
function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  )
}

export function SiteHeader() {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const t = useT()

  useEffect(() => {
    setOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const NAV = [
    { href: '/#capability', label: t.navCapability },
    { href: '/#pipeline', label: t.navPipeline },
    { href: '/#debate', label: t.navDebate },
    { href: '/#risk', label: t.navRisk },
    { href: '/#report', label: t.navReport },
  ]

  return (
    <header className="site-header sticky top-0 z-sticky-nav border-b border-rule bg-bg/90 backdrop-blur">
      <div className="shell site-header__inner">
        <a className="brand" href="/">
          <img src={logo} alt="" width={32} height={32} />
          <span className="brand__name">Quant Asst</span>
          <span className="brand__tag">{t.brandTag}</span>
        </a>

        <button
          type="button"
          className="nav-toggle"
          aria-expanded={open}
          aria-controls="site-nav"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="size-5" aria-hidden /> : <Menu className="size-5" aria-hidden />}
          <span className="nav-toggle__label">{open ? t.navClose : t.navMenu}</span>
        </button>

        <nav id="site-nav" className={cn('site-nav', open && 'is-open')} aria-label={t.navLabel}>
          <ul className="site-nav__list">
            {NAV.map((item) => (
              <li key={item.href}>
                <a href={item.href} onClick={() => setOpen(false)}>
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
          <div className="site-nav__actions">
            <LangSwitch />
            <a
              className="site-nav__repo"
              href="https://zyh798-cell.github.io/quant-asst/"
              rel="noopener noreferrer"
            >
              <ExternalLink className="size-4" aria-hidden />
              <span>{t.navDemo}</span>
            </a>
            <a
              className="site-nav__repo"
              href="https://github.com/zyh798-cell/quant-asst"
              rel="noopener noreferrer"
            >
              <GithubMark className="size-4" />
              <span>{t.navRepo}</span>
            </a>
            <Button asChild size="sm">
              <Link to="/studio">{t.navOpenStudio}</Link>
            </Button>
          </div>
        </nav>
      </div>
    </header>
  )
}
