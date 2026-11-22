import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { SiteFooter } from '@/components/SiteFooter'
import { SiteHeader } from '@/components/SiteHeader'
import { useSmoothScroll } from '@/hooks/useSmoothScroll'
import { HomePage } from '@/pages/HomePage'

// 工具站含 Recharts 等较重依赖，按需分包，避免拖慢首页 LCP
const StudioPage = lazy(() => import('@/pages/StudioPage').then((m) => ({ default: m.StudioPage })))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

export default function App() {
  useSmoothScroll()

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <a className="skip-link" href="#main">
          跳到主内容
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
  )
}
