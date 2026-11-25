import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { SiteFooter } from '@/components/SiteFooter'
import { SiteHeader } from '@/components/SiteHeader'
import { useSmoothScroll } from '@/hooks/useSmoothScroll'
import { I18nContext, useI18nProvider } from '@/i18n'
import { HomePage } from '@/pages/HomePage'

// Vite base（'/' 或 '/quant-asst/'）必须同步给路由，否则子路径部署时
// /studio 会因 location.pathname 含前缀而匹配不到，落到 '*' -> 首页。
const basename = import.meta.env.BASE_URL || '/'

// 工具站含 Recharts 等较重依赖，按需分包，避免拖慢首页 LCP
const StudioPage = lazy(() => import('@/pages/StudioPage').then((m) => ({ default: m.StudioPage })))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

export default function App() {
  useSmoothScroll()
  const i18n = useI18nProvider()

  return (
    <I18nContext.Provider value={i18n}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename={basename}>
          <a className="skip-link" href="#main">
            {i18n.t.skipToMain}
          </a>
          <SiteHeader />
          <main id="main">
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route
                path="/studio"
                element={
                  <Suspense fallback={<div className="shell studio" aria-busy="true" />}>
                    <StudioPage />
                  </Suspense>
                }
              />
              <Route path="*" element={<HomePage />} />
            </Routes>
          </main>
          <SiteFooter />
        </BrowserRouter>
      </QueryClientProvider>
    </I18nContext.Provider>
  )
}
