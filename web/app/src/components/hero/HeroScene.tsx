import { useEffect, useState, type CSSProperties } from 'react'

import desk from '@/assets/hero/desk.svg?raw'
import monitorMain from '@/assets/hero/monitor-main.svg?raw'
import monitorSide1 from '@/assets/hero/monitor-side-1.svg?raw'
import monitorSide2 from '@/assets/hero/monitor-side-2.svg?raw'
import person from '@/assets/hero/person.svg?raw'
import propsDesk from '@/assets/hero/props-desk.svg?raw'
import screenMain from '@/assets/hero/screen-content-main.svg?raw'
import screenSide1 from '@/assets/hero/screen-content-side-1.svg?raw'
import screenSide2 from '@/assets/hero/screen-content-side-2.svg?raw'

import { KlineScreen } from './KlineScreen'
import './scene.css'

/** 屏幕开口在 960×640 viewBox 中的百分比定位（与 monitor SVG 一致） */
const SCREEN_POS: Record<'side1' | 'main' | 'side2', CSSProperties> = {
  side1: { left: '7.7083%', top: '29.0625%', width: '24.7917%', height: '25.9375%' },
  main: { left: '36.875%', top: '19.0625%', width: '30.4167%', height: '31.25%' },
  side2: { left: '71.0417%', top: '27.1875%', width: '23.9583%', height: '25.3125%' },
}

function Layer({ raw }: { raw: string }) {
  return <div className="scene__layer" aria-hidden="true" dangerouslySetInnerHTML={{ __html: raw }} />
}

/**
 * 首屏分层动效场景：动漫研究员 + 三屏工作台。
 * - 分层 SVG 全部 inline，填色走 CSS 变量，令牌统一。
 * - 屏幕内容由 canvas 以固定 seed 本地生成，禁止请求行情接口。
 * - prefers-reduced-motion 或窄屏（<768px）退化为静态分层合成帧。
 */
export function HeroScene() {
  const [staticMode, setStaticMode] = useState(false)

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)')
    const narrow = window.matchMedia('(max-width: 768px)')
    const update = () => setStaticMode(reduce.matches || narrow.matches)
    update()
    reduce.addEventListener('change', update)
    narrow.addEventListener('change', update)
    return () => {
      reduce.removeEventListener('change', update)
      narrow.removeEventListener('change', update)
    }
  }, [])

  const animated = !staticMode

  return (
    <div
      className={`scene${staticMode ? ' scene--static' : ''}`}
      role="img"
      aria-label="分层插画场景：一名研究员坐在三屏工作台前，主屏显示 K 线，副屏显示净值曲线与辩论审计状态。"
    >
      <Layer raw={desk} />
      <Layer raw={monitorSide1} />
      <Layer raw={monitorMain} />
      <Layer raw={monitorSide2} />

      {/* 静态降级帧（无 JS / 减少动效 / 移动端） */}
      <div className="scene__screens" aria-hidden="true">
        <Layer raw={screenSide1} />
        <Layer raw={screenMain} />
        <Layer raw={screenSide2} />
      </div>

      {/* 动画画布：桌面端 2 块同时动画，右副屏保持静态帧以控制合成层 */}
      <div className="scene__canvas" style={SCREEN_POS.main}>
        <KlineScreen variant="candles" active={animated} seed={42} interval={320} />
      </div>
      <div className="scene__canvas" style={SCREEN_POS.side1}>
        <KlineScreen variant="equity" active={animated} seed={7} interval={360} />
      </div>

      <Layer raw={propsDesk} />
      <Layer raw={person} />
    </div>
  )
}
