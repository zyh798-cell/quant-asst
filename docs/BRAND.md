# Quant Asst 品牌规范

本文档定义 Quant Asst 仓库的品牌资产与使用约定，确保 README、文档与示例中的呈现一致。

## 名称与副标题

- 项目名：**Quant Asst**
- 副标题：**LLM Quant Analysis Agent**
- 仓库：`zyh798-cell/quant-asst`
- 代码包名：`quant_asst`（`pyproject.toml`；v0.1.0 起由 `quantsentinel` 统一改名）

## Logo 资产

| 资产 | 路径 | 用途 |
| --- | --- | --- |
| 彩色 Logo | `assets/brand/logo-color.svg` | README 头部、文档站点、演示材料 |

Logo 构成：墨黑（`#14161A`）开放 Q 形环（开口朝右）与青绿（`#18A67C`）向上趋势折线，画布 96 x 96。SVG 为矢量格式，可按需缩放；不要位图化或改色后对外发布。

## 色彩

| 用途 | 色值 |
| --- | --- |
| 主色（图形 / 文字） | `#14161A` |
| 强调色（趋势 / 交互） | `#18A67C` |

风险等级与决策术语（`low` / `medium` / `high` / `critical`；`adopt` / `revise` / `reject` / `blocked`）以 `core/schemas.py` 为准。

## 元数据行

README 头部固定一行元数据：License MIT、Python ≥3.11、测试状态、仓库链接。测试状态在 CI 就绪前使用 `pending` 占位。

## 使用约定

- 品牌名统一为 Quant Asst；代码包名、配置前缀（`QUANT_ASST_`）、logger 名与状态类型统一使用 `quant_asst` / `QuantAsst`。
- 文档保持工程化文风：无 emoji、无口语化表述、无营销话术。
- 术语（风险等级、决策值、指标名）与 `core/schemas.py` 严格一致。
