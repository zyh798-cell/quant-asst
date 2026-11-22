# Quant Asst 设计规范

前端视觉规范入口。当前只完成规范层与技能接入自检，未落地具体页面与面板。

## 文档结构

| 文件 | 内容 |
| --- | --- |
| [TOKENS.md](TOKENS.md) | 设计令牌：色板、中性色阶、语义色、字体栈、字号层级、间距栅格、圆角、边框、阴影、动效、层级、图表色、浏览器原生表面 |
| [ANTI_PATTERNS.md](ANTI_PATTERNS.md) | 禁用清单：按颜色、字体、布局、文案、动效、资产、金融数据专项分组，每条注明替代做法 |
| [GUIDELINES.md](GUIDELINES.md) | 金融数据产品准则：图表形式与构造、买卖信号标记、控件状态、决策与风险展示、响应式降级、可访问性、面板骨架 |

约定：

- 色值、间距、字体、圆角、阴影、动效参数只在 `TOKENS.md` 定义一次，其余文件引用令牌名。
- `ANTI_PATTERNS.md` 判定「该不该用」，`TOKENS.md` 判定「用哪个值」，两者冲突时以 `TOKENS.md` 的具体数值为准。
- 风险等级与决策常量以 `core/schemas.py` 为准：`low` / `medium` / `high` / `critical`，`adopt` / `revise` / `reject` / `blocked`。
- 品牌资产与名称规范见 `../BRAND.md`。

## 规则来源

本规范的规则提炼自三个开源技能：

| 技能 | 仓库 | 提炼内容 |
| --- | --- | --- |
| impeccable | https://github.com/pbakaus/impeccable | 设计质量底线与绝对禁令；排版层级、行宽、字距规则；色彩应用与深色模式编排；动效时长与缓动曲线；a11y / 性能 / 主题 / 响应式审计维度 |
| hallmark | https://github.com/Nutlope/hallmark | slop 检测闸门（Floor / Reflex / Finish / Ledger 分级）；卡片结构、模板标点、眉标、装饰插画等具体禁用项；`references/data-viz.md` 的数据可视化构造与配色规则 |
| ui-ux-pro-max | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | 按产品类型选型的配色与字体搭配、图表类型匹配、UX 准则优先级（可访问性、触控、性能、图表数据） |

未接入：threeui（不引入 Three.js / WebGL 3D 组件）。

规则为提炼与重组，非原文复制；具体数值的最终依据是本目录三份文件。

## 技能接入状态

当前环境支持外部 Agent Skill 加载，三个技能均已以项目级方式落到仓库内：

```
.agents/skills/
├── hallmark/          # SKILL.md + references/（含 gates.md、data-viz.md）
├── impeccable/        # SKILL.md + reference/ + agents/ + scripts/
└── ui-ux-pro-max/     # SKILL.md + references/ + data/ + scripts/

.codebuddy/skills/     # 同上三者的 CodeBuddy 目录副本
skills-lock.json       # skills CLI 的安装锁文件
```

安装方式与来源：

- `hallmark`：`npx skills add nutlope/hallmark -y --copy`（GitHub 克隆）
- `impeccable`：官方 CLI 因 TLS 握手失败不可用，改从已克隆仓库的 `.agents/skills/impeccable` 直接复制
- `ui-ux-pro-max`：从仓库的 `.claude/skills/ui-ux-pro-max` 直接复制

技能目录体积约 42MB，属第三方技能包本体，已在 `.gitignore` 中排除，不入库。规则提炼物（`docs/design/`）入库。重新安装后目录结构保持一致即可。

上游仓库的本地克隆位于 `D:\github\`（`impeccable`、`hallmark`、`ui-ux-pro-max-skill`），不在本仓库内。

若后续环境网络恢复，可重新执行官方安装命令覆盖项目级目录：

```bash
npx impeccable skills install -y --scope=project
npx skills add nutlope/hallmark -y --copy
npx skills add nextlevelbuilder/ui-ux-pro-max-skill -y --copy
```

## 本轮范围

- 仅规范层与技能接入自检。
- 未编写落地页或面板。
- 未引入 React / Vue / Three.js 构建链；前端形态（原生 HTML/CSS/JS 或 Streamlit）待后续单独决策。
- 未改动 `core` / `agents` / `backtest` / `report` 后端业务代码。
