<div align="center">

<img src="assets/brand/logo-color.svg" alt="Quant Asst logo" width="96" height="96">

# Quant Asst

**LLM Quant Analysis Agent**

<p>
  <img src="https://img.shields.io/badge/License-MIT-2ea44f" alt="License MIT">
  <img src="https://img.shields.io/badge/Python-%E2%89%A53.11.5-3776ab" alt="Python &gt;= 3.11.5">
  <a href="https://github.com/zyh798-cell/quant-asst/actions/workflows/ci.yml">
    <img src="https://github.com/zyh798-cell/quant-asst/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://github.com/zyh798-cell/quant-asst">
    <img src="https://img.shields.io/badge/zyh798--cell%2Fquant--asst-3776ab" alt="zyh798-cell/quant-asst">
  </a>
  <a href="https://zyh798-cell.github.io/quant-asst/">
    <img src="https://img.shields.io/badge/Live%20Demo-Live-18A67C" alt="Live Demo">
  </a>
</p>

</div>

[中文](README.md) | **English**

Quant Asst is a multi-agent framework for quantitative strategy research and risk-control auditing. It parses a natural-language strategy hypothesis into executable code, runs an event-driven backtest inside a local sandbox, then subjects the result to a bull/bear debate, an independent red-team audit, and a deterministic risk gate before producing an archivable Markdown report plus an interactive HTML report. The project is intended for research and technical demonstration only; it does not provide live order placement and does not constitute investment advice.

**Live demo**: <https://zyh798-cell.github.io/quant-asst/> (GitHub Pages serves the static front end; the workbench defaults to an offline mock mode that can be exercised in full. Real mode requires running `server/` locally.)

## Core Capabilities

- **Natural-language strategy parsing**: turns descriptions such as "dual moving average, buy when the 5-day line crosses above the 20-day line" into a structured hypothesis (symbol, period, entry/exit rules, parameters) and then into contract-compliant strategy code.
- **Sandboxed backtesting**: the event-driven engine executes strategies inside an isolated sandbox and reports total return, annualized return, maximum drawdown, Sharpe ratio, per-trade win rate, trade count and other metrics, with an in-sample / out-of-sample split.
- **Bull/bear debate**: four agent roles - bull, bear, risk checker and judge - argue over multiple rounds with per-round traces, yielding a structured verdict and backtestable revision suggestions.
- **Red-team audit**: an audit agent independent of the debate hunts for logic flaws, overfitting, lookahead functions, survivorship bias, liquidity traps and similar risks, each graded as `low` / `medium` / `high` / `critical`.
- **Deterministic risk gate**: rule-based gating that does not depend on the LLM and is reproducible. Critical findings always block trade advice with decision `blocked`; high severity and above must be annotated with explicit constraint boundaries.
- **Markdown / HTML dual reports**: an engineering-archive Markdown document plus a standalone single-file Plotly interactive HTML report (candlestick chart, buy/sell signals, equity curve, drawdown).
- **Offline mock mode**: no LLM key required and no tokens consumed; the scripted backend returns deterministic samples that satisfy the schema, suited to CI and first-time exploration.
- **Local market-data cache**: daily bars are read from a local Parquet cache first and fetched through the adapter on a miss, so repeated runs do not hit the network again.

## Getting Started

### Requirements

- Python **3.11.5 or newer** (`pyproject.toml` declares `requires-python = ">=3.11.5"`, constrained by akshare's minimum supported version).
- [uv](https://docs.astral.sh/uv/) as the dependency and virtual-environment manager.

### Installation

```bash
git clone https://github.com/zyh798-cell/quant-asst.git
cd quant-asst
uv sync
```

### Configuring keys

```bash
cp .env.example .env    # fill in DEEPSEEK_API_KEY
```

Keys are read from process environment variables following the LiteLLM convention; they never enter configuration objects, run traces or logs. When no key is configured, `debate` / `audit` fall back to offline mock mode automatically.

### Minimal runnable example

```bash
# Run the whole pipeline offline with zero keys (recommended entry point)
uv run python examples/example_4_mock_offline.py

# With a key configured: natural language -> code -> sandboxed backtest
uv run python cli.py run "双均线策略，5日线上穿20日线买入，死叉卖出"
```

`run` uses the Docker sandbox by default (release-grade isolation). For development debugging add `--sandbox local` (weaker isolation, local use only).

### CLI subcommands

| Command | Purpose |
| --- | --- |
| `run` | Runs the full research pipeline from a natural-language hypothesis (parse -> code -> sandboxed backtest). |
| `debate` | Multi-agent bull/bear debate: round-by-round records, risk check, verdict and revision suggestions. |
| `audit` | Red-team audit plus risk synthesis over an existing debate report, producing an audit report and the final quantitative analysis report. |
| `fetch` | Fetches daily bars and writes them to the local Parquet / DuckDB cache. |
| `backtest` | Sends a strategy file into the sandbox engine to verify the link; add `--lookahead-check` for a deterministic lookahead check first (off by default). |
| `doctor` | Environment self-check: configuration, dependencies, Docker, Qdrant, runtime directories. |
| `settings` | Prints the effective configuration (never includes any key). |

## Examples

`examples/` ships five ready-to-run scripts, all defaulting to offline mock mode and requiring no key. Full instructions and a recommended run order live in [`examples/README.md`](examples/README.md).

| Script | Purpose | Key required | Output location |
| --- | --- | --- | --- |
| `example_1_basic_debate.py` | Basic bull/bear debate | No | `output/debate_reports/` |
| `example_2_audit_only.py` | Standalone red-team audit plus risk synthesis | No | `output/audit/` |
| `example_3_full_pipeline.py` | Full pipeline including the HTML report | No | `output/` (three kinds) |
| `example_4_mock_offline.py` | Zero-key offline pipeline (recommended entry point) | No | `output/` (three kinds) |
| `example_5_custom_threshold.py` | Risk-threshold boundary debugging | No | `output/audit/` + terminal |

Examples 03 / 04 fetch data once through AkShare on the first run and write it to `var/market/`; afterwards they run fully offline.

## Repository Layout

```
quant-asst/
├── cli.py               # CLI entry (typer): run / debate / audit / fetch / backtest / doctor / settings
├── core/                # config, state machine (LangGraph), LLM wrapper and mock backend, schemas, risk gate, traces
├── agents/              # hypothesis / bull / bear / risk checker / judge / red team / risk synthesis
├── backtest/            # event-driven engine, performance metrics, market-specific rules
├── tools/               # market-data tools, sandbox executors (docker / local), backtest sandbox
├── data/                # market-data adapters and the local parquet cache layer
├── report/              # report rendering: Markdown / Plotly HTML / data-fetch orchestration
├── audit/               # audit orchestration and report persistence
├── examples/            # example script set (5 demos + strategy templates + validation + cleanup) and shared _common base
├── tests/               # pytest unit tests and example regressions
├── docs/                # architecture, development, brand and front-end design documents
├── assets/              # brand assets (logo) and hero-scene reference art
├── web/app/             # landing page + dynamic studio (Vite + React 19 + TS + Tailwind v4)
├── server/              # FastAPI thin interface layer (Step B: reuses core/backtest/report/audit)
├── var/                 # runtime data (traces / market cache / sandbox workspace, not committed)
└── output/              # deliverables (debate / audit / HTML reports, not committed)
```

Source is organized as flat packages (`core` / `agents` / `tools` / `data` / `backtest` / `report` / `audit`) without a `src/` container.

## Web Application (landing page + studio)

The front end lives in [`web/app/`](web/app/) and is built on **Vite 8 + React 19 + TypeScript + Tailwind CSS v4 + shadcn-style components + Zustand + TanStack Query + Recharts**, with GSAP ScrollTrigger + Lenis driving the scroll narrative. A Chinese / English switcher in the header toggles the site language; the choice is stored in the browser.

- **`/`** landing page: a layered illustrated workbench scene (person, desk, three monitors, screen content and desktop props as independent SVG layers, with the screen area replaceable), a deterministic animation in which candlesticks grow one by one, and five narrative sections covering capabilities, pipeline, bull/bear debate, risk grading and dual-format reports.
- **`/studio`** dynamic studio: strategy configuration -> pipeline status -> backtest metrics with equity / drawdown curves and trade records -> debate and audit views -> Markdown report download. It defaults to a local deterministic mock, so no key is required.

Local preview:

```bash
cd web/app
npm install
npm run dev        # http://localhost:5173
```

Production build:

```bash
cd web/app
npm run build      # output in web/app/dist/
npm run preview
```

### Live demo on GitHub Pages

URL: <https://zyh798-cell.github.io/quant-asst/>

- Deployment is handled by [`.github/workflows/pages.yml`](.github/workflows/pages.yml): after a push to `main`, CI runs `npm ci && npm run build` (with `VITE_BASE=/quant-asst/` for the sub-path), uploads `web/app/dist` as an artifact and calls `deploy-pages`.
- **Only the static front end is deployed**: `server/` and `.env` are not part of the build, so there is no key-exposure surface.
- One-time setup: in the repository go to **Settings -> Pages -> Build and deployment -> Source** and select **GitHub Actions**.
- The workbench on the deployed site defaults to offline mock mode and can be explored in full; real mode requires running `server/` locally (the page states this).
- For a **complete long-window report produced in real mode**, see [`docs/demo/`](docs/demo/) (cn:600519, 2025-01-05 ~ 2026-11-20, with debate, audit, final report and interactive HTML).

### Step B: wiring both ends (interface layer + studio)

The interface layer lives in [`server/`](server/) and is a **thin orchestration layer**: it only handles the HTTP contract, the task state machine and artifact DTO conversion. Strategy logic is reused wholesale from `core` / `agents` / `tools` / `backtest` / `report` / `audit`; it writes no new strategy code and never touches keys.

Startup order (two terminals, backend first):

```bash
# Terminal 1: interface layer
uv run uvicorn server.main:app --reload --port 8000

# Terminal 2: studio
cd web/app
npm run dev        # http://localhost:5173
```

- By default the front end connects directly to `http://localhost:8000`; override with the `VITE_API_BASE` environment variable. Backend CORS already allows `http://localhost:5173` and `http://127.0.0.1:5173`. `vite.config.ts` also sets up a `/api` proxy as a fallback.
- The studio's run mode is switched by configuration: **mock offline** generates deterministic samples in the browser (no key, no backend); **real mode** sends requests to the local interface layer. In real mode the client polls status every 1.5 seconds after creating a task and **renders incrementally as each stage finishes** rather than waiting for the whole run.
- Keys are read from process environment variables following the LiteLLM convention. The interface layer redacts known key values and the `sk-*` / `api_key=` literals, so **keys never appear in any response field, task snapshot or error text** (see the leak assertions in `tests/test_api.py`).

Endpoint overview:

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/analyses` | Creates an analysis task, runs it in the background and returns `201` with the initial status |
| `GET` | `/api/analyses` | Task list ordered by creation time descending (handy for debugging) |
| `GET` | `/api/analyses/{id}` | Task status plus completed stage artifacts (polled by the front end) |
| `GET` | `/api/analyses/{id}/report?format=md\|html` | Report body with `Content-Type` of `text/markdown` or `text/html` |
| `GET` | `/api/health` | Health check returning `{"status":"ok","mode":"mock|real"}` |

Task state machine: `pending -> running -> stage_done -> completed`, with exceptions switching to `failed` and writing a redacted error message. The six stages `parse -> backtest -> debate -> audit -> risk -> report` each record their own `pending / running / done / failed / skipped` status and structured artifacts. Tasks execute serially so that the process-level `QUANT_ASST_LLM_MOCK` / `LITELLM_OFFLINE_MODE` flags cannot cross-contaminate concurrent tasks. Reports are written to `var/reports/<task_id>/` (Markdown + JSON + single-file HTML).

### Asset handling and the broken-image root cause

Hero-scene assets live under `web/app/src/assets/hero/`, named by layer (`person` / `desk` / `monitor-main` / `monitor-side-1` / `monitor-side-2` / `screen-content-*` / `props-desk`); the screen content area is a separate transparent overlay container and can be replaced as a whole.

**Brand assets must always be imported through Vite** (for example `import logo from '@/assets/brand/logo-color.svg'`). Do not write relative paths such as `../../assets/...` in `index.html` or CSS - under GitHub Pages sub-path deployment the server rejects `..` and the logo renders as a broken image. The earlier static landing page was abandoned for exactly this reason; its directory has been removed to avoid two competing home pages.

Visual specification: see [`docs/design/`](docs/design/). Color values, spacing, type sizes, radii, shadows and motion parameters are defined exactly once in `TOKENS.md`; the front end maps them through Tailwind v4's `@theme` (CSS variables) and all page styles reference the tokens.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): layered structure, module responsibilities, data flow and design constraints.
- [`docs/DEVELOP.md`](docs/DEVELOP.md): project bootstrap, conventions for adding agents or examples, test expectations and troubleshooting.
- [`docs/BRAND.md`](docs/BRAND.md): brand name, logo assets, colors and usage conventions.
- [`docs/design/README.md`](docs/design/README.md): front-end design specification index (design tokens, anti-patterns, financial data-product guidelines).
- [`docs/demo/README.md`](docs/demo/README.md): long-window real-mode demo artifacts (cn:600519, 2025-01-05 ~ 2026-11-20) - debate minutes, red-team audit, final report and interactive HTML, including confidence and risk conclusions.
- [`examples/README.md`](examples/README.md): example inventory, recommended run order and artifact notes.

## Disclaimer

**This project is intended for quantitative research and technical demonstration only. It does not constitute investment advice of any kind and provides no live order-placement functionality.**

- All backtest, debate, audit and risk conclusions are based on given assumptions, data definitions and model parameters; **historical backtest results do not represent future returns**.
- Strategy code is generated by an LLM and executed inside a sandbox. The local restricted sandbox (`--sandbox local`) does not provide adequate isolation and is for development debugging only; do not use it in production.
- Risk grading and gating are deterministic rules inside the research workflow, used to expose risks and constraint boundaries; they do not endorse the safety of any asset and are not trade recommendations.
- Users should independently verify the data and conclusions and bear the consequences of their own decisions.

## License

Released under the [MIT License](LICENSE) by [zyh798-cell](https://github.com/zyh798-cell).

Market data comes from [AkShare](https://akshare.akfamily.xyz/) and [CCXT](https://github.com/ccxt/ccxt) for research use only; model calls are routed through [LiteLLM](https://docs.litellm.ai/), the state machine is orchestrated with [LangGraph](https://github.com/langchain-ai/langgraph), and visualization is built on [Plotly](https://plotly.com/python/).
