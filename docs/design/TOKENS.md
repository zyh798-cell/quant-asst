# Quant Asst 设计令牌

本文件是 Quant Asst 前端视觉规范的唯一事实源（single source of truth）。所有色值、间距、字体、圆角、阴影、动效参数只在此处定义；其他文档与代码一律引用令牌名，不得硬写字面量。

- 产品形态：金融数据研究工具（Operate 模式为主，Persuade 为辅）
- 品牌层：`docs/BRAND.md`
- 禁用项：`docs/design/ANTI_PATTERNS.md`
- 产品准则：`docs/design/GUIDELINES.md`

---

## 1. 色板

### 1.1 基础色

| 令牌 | 色值 | 用途 |
| --- | --- | --- |
| `--color-bg` | `#F0EADC` | 页面底色（暖纸面） |
| `--color-ink` | `#14161A` | 主文字、标题、图标主描边 |
| `--color-body` | `#2A2D33` | 正文 |
| `--color-muted` | `#6B6660` | 次要文字、轴标签、辅助说明 |
| `--color-rule` | `#D9D2C4` | 分隔线、网格线、卡片边框 |
| `--color-accent` | `#18A67C` | 强调色（主行动、关键数据序列） |
| `--color-accent-soft` | `#E4F2EC` | 强调浅底（标签底、选中态底） |
| `--color-surface` | `#FFFFFF` | 卡片、面板、浮层底色 |

### 1.2 中性色阶

由 `--color-ink` 至 `--color-rule` 的明度阶梯，用于填充、禁用态、次级表面。全部在暖纸色相（hue 40 附近）内微调，禁止使用纯中性灰（chroma 0）。

| 令牌 | 色值 | 用途 |
| --- | --- | --- |
| `--color-ink-900` | `#14161A` | 最深，与 `--color-ink` 同值 |
| `--color-ink-800` | `#23262B` | 深色面板底 |
| `--color-ink-700` | `#3A3E45` | 深面板上的次级文字 |
| `--color-ink-500` | `#6B6660` | 与 `--color-muted` 同值 |
| `--color-ink-300` | `#A9A296` | 弱化信息、占位符 |
| `--color-ink-100` | `#E7E1D5` | 浅填充、分区块底 |
| `--color-rule-strong` | `#BFB6A4` | 强分隔线、表头底 |

### 1.3 语义色

风险等级须与 `core/schemas.py` 的 `RISK_LEVELS`（`low` / `medium` / `high` / `critical`）一一对应，界面显示标签用 `RISK_LABELS_ZH`（低 / 中 / 高 / 致命）。

| 令牌 | 色值 | 语义 | 风险等级映射 |
| --- | --- | --- | --- |
| `--color-success` | `#18A67C` | 成功、通过、采纳 | `low` |
| `--color-warning` | `#B8860B` | 警告、需修订 | `medium` |
| `--color-danger` | `#C0392B` | 危险、阻断、拒绝 | `high` |
| `--color-critical` | `#7B1E1A` | 致命错误 | `critical` |
| `--color-info` | `#2F6F8F` | 信息、中性提示 | — |
| `--color-success-soft` | `#E4F2EC` | 成功浅底 | — |
| `--color-warning-soft` | `#F6EEDD` | 警告浅底 | — |
| `--color-danger-soft` | `#F7E7E4` | 危险浅底 | — |
| `--color-info-soft` | `#E7EFF3` | 信息浅底 | — |

决策常量与语义色对应：`adopt` → 成功色、`revise` → 警告色、`reject` → 危险色、`blocked` → 致命色。

### 1.4 语义色墨变体（浅底上的文字色）

语义色与强调色作为**大面积填充**可用，但作为浅底上的**文字色**对比度不足（`--color-accent` 在 `--color-bg` 上仅 2.58:1）。浅底上的文字改用下列深色墨变体：

| 令牌 | 色值 | 用途 | 对比度 |
| --- | --- | --- | --- |
| `--color-accent-ink` | `#0E6B50` | 强调色底上的文字、强调链接文字 | 5.41:1（对 `--color-bg`） |
| `--color-success-ink` | `#0E6B50` | 成功浅底上的文字 | 5.62:1（对 `--color-success-soft`） |
| `--color-warning-ink` | `#7A5300` | 警告浅底上的文字 | 5.94:1（对 `--color-warning-soft`） |
| `--color-danger-ink` | `#A32A1E` | 危险浅底上的文字 | 6.02:1（对 `--color-danger-soft`） |
| `--color-critical-ink` | `#6B1915` | 致命浅底上的文字 | 9.86:1（对 `--color-danger-soft`） |
| `--color-info-ink` | `#255A75` | 信息浅底上的文字 | 6.45:1（对 `--color-info-soft`） |
| `--color-ink-300` | `#8C857A` | 极弱化文字（占位、禁用） | 3.04:1（对 `--color-bg`），仅用于非文字元素 |

规则：

- 强调色作为**填充**（按钮底、图表标记、进度条）时用 `--color-accent`，配对文字用 `--color-ink`（对比度 5.85:1）。
- 强调色作为**文字**时改用 `--color-accent-ink`，不用 `--color-accent`。
- 徽章、状态标签、提示条一律「浅底 + 墨变体文字」，不用「饱和底 + 白字」（`--color-accent` 上的白字仅 3.10:1）。

### 1.5 深色模式

深色模式为独立编排，不是浅色模式机械反相。

| 令牌 | 色值 |
| --- | --- |
| `--color-bg` | `#14161A` |
| `--color-surface` | `#1C1F24` |
| `--color-ink` | `#F0EADC` |
| `--color-body` | `#D9D2C4` |
| `--color-muted` | `#9B9488` |
| `--color-rule` | `#333840` |
| `--color-accent` | `#2BBE90`（深底上提亮，chroma 略降） |
| `--color-accent-soft` | `#173A31` |

### 1.6 色彩使用比例

强调色在一个视口内的占比不超过 8%（金融数据面板取密集档，上限 5%）。强调色用于承载信息，不用于装饰。

**禁用**：紫粉渐变、彩虹多色分类、青紫蓝渐变文字、框架默认调色板（Tailwind indigo/violet/slate 等）作为令牌。

### 1.7 场景插画辅助色

首屏工作台插画为分层 SVG / canvas 场景，除基础色与中性色阶外，仅需少量非数据色承载人物质感。这类颜色只用于插画填充，不进入数据图表与状态语义。

| 令牌 | 色值 | 用途 |
| --- | --- | --- |
| `--color-scene-skin` | `#F2D8C0` | 人物皮肤 |
| `--color-scene-blush` | `#E8A894` | 人物腮红（低透明度叠加） |

场景其余部件（头发 / 椅背 / 桌腿 / 显示器边框）复用 `--color-ink-*` 中性色阶，屏幕面板复用 `--color-ink-900`。场景层填色统一写作 `fill="var(--color-xxx, #fallback)"`：内联 SVG 层直接吃 CSS 变量；`<img>` 降级时回退到括号内字面量。

---

## 2. 字体

### 2.1 字体栈

| 角色 | 令牌 | 字体栈 |
| --- | --- | --- |
| 正文 | `--font-body` | `"Inter", "Source Han Sans SC", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif` |
| 标题 | `--font-display` | `"Inter Tight", "Source Han Sans SC", "Noto Sans SC", "PingFang SC", system-ui, sans-serif` |
| 数据 | `--font-mono` | `"JetBrains Mono", "IBM Plex Mono", "SFMono-Regular", Consolas, monospace` |
| 中文回退 | `--font-cjk` | `"Source Han Sans SC", "Noto Sans SC", "PingFang SC", "Microsoft YaHei"` |

约束：

- 全站最多三套字体族（标题 / 正文 / 等宽），不做第四套。
- 等宽字体仅用于代码、行情代码、指标数字与度量值；不用于普通标签、表头、导航文案。
- 禁用 Inter / Roboto / Open Sans / Poppins / Lato 作为展示标题（`--font-display`）；正文字体族可保留 Inter。
- 展示标题禁用斜体；标题内不单独把某个词染成强调色（accented word）。

### 2.2 字号层级

以 4px 为基数，等比递进。密集数据面板取偏小一档。

| 令牌 | 字号 | 行高 | 用途 |
| --- | --- | --- | --- |
| `--text-hero` | 48px | 1.05 | 落地页首屏主标题 |
| `--text-display` | 40px | 1.05 | 大标题（面板主视觉） |
| `--text-section-lg` | 40px | 1.15 | 落地页区块标题 |
| `--text-section` | 28px | 1.15 | 区块标题（应用界面） |
| `--text-title` | 20px | 1.30 | 卡片 / 面板标题 |
| `--text-body` | 16px | 1.55 | 正文 |
| `--text-label` | 14px | 1.45 | 控件标签、表头 |
| `--text-caption` | 13px | 1.45 | 辅助说明、坐标轴标签 |
| `--text-micro` | 12px | 1.40 | 数据角标、时间戳 |

窄屏（≤640px）下 `--text-hero` 降为 32px、`--text-section-lg` 降为 26px，通过覆写令牌实现，组件内不写断点字号。

约束：

- 正文不得小于 12px，功能性文字不得小于 11px。
- 展示标题 `letter-spacing` 不低于 -0.04em；常规取 -0.02em 至 -0.03em。
- 15px 及以下的标签、说明、表头、导航项一律用正文字体、正常字重、句首大写、零字距；禁止全大写（`text-transform: uppercase`）与大于 0.03em 的字距。
- 所有数字表面（指标卡、表格、回测数值、坐标轴）使用 `font-variant-numeric: tabular-nums`。
- 正文行宽 `max-width: 65ch`（45ch 至 75ch 区间内）。

---

## 3. 间距

4px 基数栅格，仅允许使用以下令牌。

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--space-1` | 4px | 图标与文字间隙、徽标内边距 |
| `--space-2` | 8px | 紧凑控件内元素间隙 |
| `--space-3` | 12px | 控件内边距（垂直）、标签组间隙 |
| `--space-4` | 16px | 卡片内边距（密集）、表单行间距 |
| `--space-5` | 20px | 标准内边距 |
| `--space-6` | 24px | 卡片内边距（宽松）、区块内元素间距 |
| `--space-8` | 32px | 面板内边距 |
| `--space-10` | 40px | 区块间距（密集档） |
| `--space-12` | 48px | 区块间距（标准档） |
| `--space-16` | 64px | 区块间距（宽松档） |
| `--space-20` | 80px | 落地页章节间距（密集） |
| `--space-24` | 96px | 落地页章节间距（标准） |
| `--space-32` | 128px | 落地页章节间距（宽松）、Hero 上下留白 |

规则：

- 禁止在 `padding` / `margin` / `gap` 中书写裸长度，必须使用 `--space-*` 令牌。
- 区块间距在同一页面中不得全部相同，需按信息层级变化。
- 卡片与相邻内容间距 16px；卡片内元素间距 12px 至 16px。

---

## 4. 圆角、边框、阴影

### 4.1 圆角

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--radius-sm` | 4px | 输入框、按钮、标签 |
| `--radius-md` | 8px | 卡片、次级面板 |
| `--radius-lg` | 12px | 大面板、浮层 |
| `--radius-pill` | 999px | 状态徽章、芯片（仅限小控件） |

卡片圆角统一 12px（8px 至 16px 区间内）；不使用大圆角药丸卡片。

### 4.2 边框

| 令牌 | 值 |
| --- | --- |
| `--border-hairline` | `1px solid var(--color-rule)` |
| `--border-strong` | `1px solid var(--color-rule-strong)` |
| `--border-focus` | `2px solid var(--color-ink)` + `outline-offset: 2px` |

聚焦环不得用 `border` 实现（会导致尺寸跳动），使用 `outline`；聚焦环与底色对比度不低于 3:1，出现必须是瞬时（无淡入）。

聚焦环用 `--color-ink` 而非 `--color-accent`：`--color-accent` 对 `--color-bg` 仅 2.58:1，低于 3:1 门槛；`--color-ink` 为 15.1:1。强调色可通过外圈或图标补充识别，但不能替代聚焦环本身。

### 4.3 阴影

阴影必须同时带偏移与柔和模糊；零偏移纯色光晕视为装饰，禁止使用。

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--shadow-sm` | `0 1px 2px rgba(20, 22, 26, 0.06)` | 卡片静态 |
| `--shadow-md` | `0 4px 12px rgba(20, 22, 26, 0.08)` | 浮层、下拉 |
| `--shadow-lg` | `0 12px 32px rgba(20, 22, 26, 0.12)` | 模态、抽屉 |

同一元素不得同时使用 1px 边框与 24px 以上模糊的宽软阴影（幽灵卡片）。

---

## 5. 动效

### 5.1 缓动曲线

| 令牌 | 曲线 | 用途 |
| --- | --- | --- |
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | 进入、展开 |
| `--ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | 位移、循环 |
| `--ease-linear` | `linear` | 进度条、连续数据 |

禁用弹跳、回弹、橡皮筋曲线（`cubic-bezier` 中出现负值或大于 1 的过冲）。

### 5.2 时长

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--duration-fast` | 120ms | 即时反馈（hover、按下） |
| `--duration-base` | 200ms | 常规状态切换 |
| `--duration-slow` | 320ms | 面板展开、视图切换 |
| `--duration-entrance` | 500ms | 刻意编排的入场（落地页仅一处） |

退场时长约为入场的 60%，不慢于 200ms。

### 5.3 动效规则

- 禁止 `transition: all`；必须逐属性声明，只动 `transform` 与 `opacity`。
- 禁止对 `width` / `height` / `top` / `left` / `margin` / `padding` 做过渡；改用 transform 或 grid 方案。
- 每个可交互元素只允许一种 hover 信号，且作用在容器上（不做图片缩放、旋转）。
- 所有动效必须提供 `prefers-reduced-motion: reduce` 分支：减少空间位移，保留状态与颜色的变化。
- 焦点环、提示气泡等状态反馈不做入场动画，直接出现。

---

## 6. 层级（z-index）

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--z-base` | 0 | 常规内容 |
| `--z-sticky` | 100 | 表头吸顶 |
| `--z-sticky-nav` | 200 | 导航吸顶（高于 sticky） |
| `--z-dropdown` | 300 | 下拉、悬浮面板 |
| `--z-modal` | 400 | 模态 |
| `--z-toast` | 500 | 提示条 |

同一层级不得出现两个 `position: sticky; top: 0` 元素（会发生遮挡）。

---

## 7. 图表令牌

图表遵循「一图一论点」，详细规则见 `docs/design/GUIDELINES.md`。

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--chart-series-1` | `#18A67C` | 主序列（强调色） |
| `--chart-series-2` | `#2F6F8F` | 次序列（同色相明度阶） |
| `--chart-series-3` | `#4A8FA8` | 第三序列 |
| `--chart-series-4` | `#6B6660` | 上下文 / 参考序列 |
| `--chart-grid` | `#D9D2C4` | 网格线（1px 实线） |
| `--chart-axis` | `#A9A296` | 轴线、刻度 |
| `--chart-label` | `#6B6660` | 轴标签、图例文字 |
| `--chart-buy` | `#C0392B` | 买入信号标记 |
| `--chart-sell` | `#18A67C` | 卖出信号标记 |

规则：

- 单一序列图只用 `--chart-series-1`。
- 多序列图在同一色相上做明度阶（L 步进 12% 至 15%，chroma 保持不变），按固定顺序分配，不循环复用。
- 文字永远不穿数据色；序列靠色块 + 文字标签识别。
- 禁止双 Y 轴；单位不同则拆成两张小图。
- 网格线 3 至 5 条水平线，实线，不虚线；柱状图基线恒为 0。
- 禁止 3D、标记阴影、渐变填充（sparkline 的渐隐填充除外）。

---

## 8. 浏览器原生表面

以下属于产品外观的一部分，必须显式设定，不得留默认：

```css
::selection { background: var(--color-accent-soft); color: var(--color-ink); }
:root { caret-color: var(--color-accent); scrollbar-color: var(--color-rule-strong) var(--color-bg); }
```

---

## 9. 使用约定

- 组件中禁止出现裸色值与裸 `font-family`，一律引用本文令牌。
- 深色模式通过覆写令牌实现，不在组件内写 `[data-theme="dark"]` 分支。
- 新增令牌必须先写入本文件，再在代码中使用。
- 语义色不用于装饰，仅表达状态；风险等级色按 1.3 的映射使用，不得挪用。
