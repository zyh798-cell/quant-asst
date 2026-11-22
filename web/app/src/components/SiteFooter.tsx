import logo from '@/assets/brand/logo-color.svg'

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell site-footer__inner">
        <div className="site-footer__risk">
          <p className="site-footer__risk-title">风险声明</p>
          <p className="site-footer__risk-text">
            Quant Asst 仅用于量化研究与技术演示，不构成任何投资建议，不含实盘下单功能。历史回测结果不代表未来收益。
          </p>
        </div>
        <div className="site-footer__meta">
          <p className="site-footer__brand">
            <img src={logo} alt="" width={24} height={24} />
            <span>Quant Asst</span>
          </p>
          <p className="site-footer__legal">
            <span>MIT License</span>
            <a href="https://github.com/zyh798-cell/quant-asst" rel="noopener noreferrer">
              zyh798-cell/quant-asst
            </a>
          </p>
        </div>
      </div>
    </footer>
  )
}
