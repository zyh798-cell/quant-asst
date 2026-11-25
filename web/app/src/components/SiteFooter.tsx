import logo from '@/assets/brand/logo-color.svg'
import { useT } from '@/i18n'

export function SiteFooter() {
  const t = useT()

  return (
    <footer className="site-footer">
      <div className="shell site-footer__inner">
        <div className="site-footer__risk">
          <p className="site-footer__risk-title">{t.footerRiskTitle}</p>
          <p className="site-footer__risk-text">{t.footerRiskText}</p>
        </div>
        <div className="site-footer__meta">
          <p className="site-footer__brand">
            <img src={logo} alt="" width={24} height={24} />
            <span>Quant Asst</span>
          </p>
          <p className="site-footer__legal">
            <span>{t.footerLicense}</span>
            <a href="https://github.com/zyh798-cell/quant-asst" rel="noopener noreferrer">
              zyh798-cell/quant-asst
            </a>
          </p>
        </div>
      </div>
    </footer>
  )
}
