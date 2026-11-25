# -*- coding: utf-8 -*-
"""清理示例产物（Step 7）。

一键删除项目根 ``output/`` 目录下由示例生成的报告与临时产物，便于反复演示：

- 报告类：``.md`` / ``.html`` / ``.json``
- 临时类：``.tmp`` / ``.part`` 后缀，以及 ``~`` 开头的编辑器临时副本

安全边界：

- 仅作用于项目根 ``output/`` 目录，绝不触碰 ``var/``（轨迹 / 行情缓存）与源码；
- 删除前打印完整清单；``--dry-run`` 只预览不删除；
- 目录不存在或无可清理文件时友好提示，退出码 0。

运行命令（在项目根目录执行）:

    uv run python examples/clean_examples_output.py            # 一键清理并打印清单
    uv run python examples/clean_examples_output.py --dry-run  # 仅预览将要删除的文件
"""

from __future__ import annotations

import argparse
from pathlib import Path

#: 项目根目录（QuantAsst/）
ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"

#: 报告类后缀（示例产物）
_REPORT_SUFFIXES = {".md", ".html", ".json"}
#: 临时类后缀（半成品 / 断点文件）
_TMP_SUFFIXES = {".tmp", ".part"}


def _is_target(path: Path) -> bool:
    """判断是否为可清理的示例产物。"""
    if path.name.startswith("~"):
        return True
    return path.suffix.lower() in (_REPORT_SUFFIXES | _TMP_SUFFIXES)


def collect(target_dir: Path) -> list[Path]:
    """收集目标目录下所有可清理文件（递归，按路径排序）。"""
    if not target_dir.is_dir():
        return []
    return sorted(p for p in target_dir.rglob("*") if p.is_file() and _is_target(p))


def main() -> int:
    parser = argparse.ArgumentParser(description="清理 examples 演示产物（项目根 output/）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅预览将要删除的文件，不执行删除")
    args = parser.parse_args()

    print("=" * 78)
    print("清理 examples 演示产物")
    print("=" * 78)
    print(f"目标目录 : {OUTPUT_DIR}")

    if not OUTPUT_DIR.is_dir():
        print("目录不存在，无需清理。")
        return 0

    files = collect(OUTPUT_DIR)
    if not files:
        print("未发现可清理的报告或临时产物。")
        return 0

    total = sum(p.stat().st_size for p in files)
    print(f"待清理   : {len(files)} 个文件，合计 {total / 1024:.1f} KB\n")
    for p in files:
        print(f"  - {p.relative_to(ROOT)}")

    if args.dry_run:
        print("\n[dry-run] 仅预览，未执行删除。")
        return 0

    print()
    removed = 0
    for p in files:
        try:
            p.unlink()
            removed += 1
        except OSError as exc:  # noqa: PERF203 —— 逐个容错，失败不影响其余
            print(f"  [失败] {p.relative_to(ROOT)}: {exc}")
    print(f"已删除 {removed}/{len(files)} 个文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
