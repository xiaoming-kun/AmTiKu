#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片目录清理：删可再生成的 TikZ 缓存，归档真正没引用的图。

`图片/` 是**内容寻址的源图目录**，不该混缓存：
  · `tikz-<hash>.pdf/.png` 是 `amti/tikzfig.py` 的渲染产物，删了会按需重画；
  · 其余 `[0-9a-f]{16}.png` 如果全仓没有任何引用，归档（**不删**）到
    `归档/图片_未引用_<日期>/`，并写一份 CSV 清单。

引用来源：题目 figures，以及仓库里的 .tex/.json/.md/.py/.ts
（不算 `变更记录/`、`记录/`、`归档/` 这些历史材料）。

用法：
    python3 脚本/清理图片缓存.py          # 干跑
    python3 脚本/清理图片缓存.py --apply  # 执行
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store  # noqa: E402

IMG = ROOT / "图片"
SKIP_DIRS = {"图片", ".git", "node_modules", "dist", "归档", "记录",
             "变更记录", "__pycache__", ".venv", ".pytest_cache"}
EXTS = {".py", ".ts", ".tsx", ".json", ".tex", ".md", ".csv", ".txt", ".mjs", ".js"}
NAME_RE = re.compile(r"[\w-]+\.(?:png|jpg|jpeg|pdf)")


def used_names() -> set[str]:
    used = {f.id for q in store.load_all() for f in q.figures}
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fn:
            p = Path(dp) / f
            if p.suffix.lower() not in EXTS:
                continue
            try:
                used.update(NAME_RE.findall(p.read_text(encoding="utf-8")))
            except Exception:                                # noqa: BLE001
                pass
    return used


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    used = used_names()
    files = {p.name: p for p in IMG.iterdir() if p.is_file()}
    orphans = [p for n, p in files.items()
               if n not in used and n != "来源清单.json"]
    tikz = [p for p in orphans if p.name.startswith("tikz-")]
    rest = [p for p in orphans if not p.name.startswith("tikz-")]
    print("图片 %d 个；未引用 %d 个（TikZ 缓存 %d，其余 %d）"
          % (len(files), len(orphans), len(tikz), len(rest)))
    print("其余未引用：%.1f MB" % (sum(p.stat().st_size for p in rest) / 1e6))
    if not a.apply:
        print("\n干跑结束；加 --apply 执行。")
        return 0

    for p in tikz:
        p.unlink()
    if rest:
        dest = ROOT / "归档" / ("图片_未引用_%s" % _dt.datetime.now().strftime("%Y%m%d"))
        dest.mkdir(parents=True, exist_ok=True)
        with (dest / "清单.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["文件", "字节"])
            for p in rest:
                w.writerow([p.name, p.stat().st_size])
                shutil.move(str(p), str(dest / p.name))
        print("归档到 %s" % dest.relative_to(ROOT))
    print("删除 TikZ 缓存 %d 个，归档 %d 个" % (len(tikz), len(rest)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
