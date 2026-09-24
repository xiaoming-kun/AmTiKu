#!/usr/bin/env python3
r"""用**本机 27B** 批量给成品打考点（项目自己的打标入口 `record.tag_point`）。

## 为什么走这条路

题库里既有的 17679 道 `point_source: "llm"` **就是这么打的**——
`amti/record.py:tag_point()` 把 152 条考点清单全量塞进提示词、`temperature=0`、
只允许输出一个合法编号，**认不出就返回空串**（"宁可不打标，也不打错标"）。
所以这不是新引入的口径，是复用工库的那一条。

实测：20/20 命中合法编号，**2.4 秒/题**；9892 题单线程 6.6 小时，
2 并发约 3.3 小时（开更高并发会挤掉别的任务用的同一个模型，故意只开 2）。

## 与 agent 那条路的分工

agent 逐题给 1—3 个考点、会写清主考点，质量更高也贵得多；本脚本只给 1 个。
两边产出都落 `rNNN.json`，由 `补考点成品.py merge` 统一校验、`source` 字段区分。

## 只读不写题库

写出去的就只有 `.tobias/分类/成品/batches/27b/rNNN.json`。
不碰 `题目/*.tex`、不碰成品 JSON、不调 ingest。可随时 Ctrl-C，已写完的批保留。

    python3 脚本/补考点本地模型.py            # 跑还没结果的批
    python3 脚本/补考点本地模型.py --only 120-140   # 只跑这个区间
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from amti import record as RC          # noqa: E402  只用它的 tag_point
from amti import knowledge as KB       # noqa: E402

BATCH = ROOT / ".tobias/分类/成品/batches"
OUT = BATCH / "27b"


def _todo(only: str) -> list[Path]:
    lo = hi = 0
    if only:
        a, _, b = only.partition("-")
        lo, hi = int(a), int(b or a)
    out = []
    for f in sorted(BATCH.glob("b[0-9][0-9][0-9].json")):
        n = int(f.stem[1:])
        if (lo and not (lo <= n <= hi)):
            continue
        if (BATCH / ("r%s.json" % f.stem[1:])).exists() or (OUT / ("r%s.json" % f.stem[1:])).exists():
            continue
        out.append(f)
    return out


def tag_one(it: dict) -> dict | None:
    q = {"stem": it.get("stem"), "type": it.get("type"),
         "options": [[k, v] for k, v in (it.get("opts_by_key") or {}).items()]}
    pid = RC.tag_point(q, timeout=180)
    if not pid or not KB.get(pid):
        return None
    return {"key": it["key"], "points": [pid], "source": "llm"}


def run_batch(f: Path) -> tuple[str, int, int]:
    items = json.loads(f.read_text(encoding="utf-8"))
    opts = []
    for it in items:
        d = {}
        for i, seg in enumerate((it.get("opts") or "").split("；")):
            if seg.strip():
                d[chr(65 + i)] = seg.strip()
        it["opts_by_key"] = d
        opts.append(tag_one(it))
    rows = [r for r in opts if r]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ("r%s.json" % f.stem[1:])).write_text(
        json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return f.stem, len(items), len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑批号在这个区间，如 120-140")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()

    files = _todo(a.only)
    if not files:
        print("没有待跑的批")
        return
    print("待跑 %d 批 / 约 %d 题，%d 并发（占本机 27B）"
          % (len(files), len(files) * 40, a.workers), flush=True)
    t0 = time.time()
    done = hit = tot = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for stem, n, ok in ex.map(run_batch, files):
            done += 1
            tot += n
            hit += ok
            el = time.time() - t0
            left = (len(files) - done) * 40 * el / max(1, tot)
            print("%s %d/%d 批  命中 %d/%d  已用 %.1f 分  约剩 %.1f 分"
                  % (stem, done, len(files), hit, tot, el / 60, left / 60), flush=True)
    print("完成：%d 题打标 %d 题" % (tot, hit))


if __name__ == "__main__":
    main()
