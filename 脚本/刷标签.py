#!/usr/bin/env python3
r"""把 `数据/录题/待刷标签.jsonl` 攒下的考点/难度**一次**刷进库里那些重复题。

    python3 脚本/刷标签.py --dry      # 只看会动哪几道，不写盘
    python3 脚本/刷标签.py            # 落账：一次 `rewrite_all`，然后把账单归档

为什么要这单独一步：`ingest.commit` 每产出一项升级就要整库重写
（51MB 重写＋52MB 备份），而一批 20 场里有 18 场带升级 ⇒ 每场白搭三十秒。
逐场录入因此走 `--defer-upgrades`（只追加、把该刷的记进 journal），批末走这里。

落账本身仍然由 `ingest.apply_labels()` 跑 `merge_plan`（**只升不降**、考点取并集、
换主考点才重算派生难度），所以重复刷、隔几天再刷都不会把库里已有的东西改坏。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from amti import ingest, store                                   # noqa: E402

PENDING = ROOT / "数据/录题/待刷标签.jsonl"
ARCHIVE = ROOT / "数据/录题/待刷标签.已刷.jsonl"


def load() -> list[dict]:
    if not PENDING.exists():
        return []
    seen, out = set(), []
    for line in PENDING.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        k = (e.get("dup_key"), tuple(e.get("points") or []))
        if k in seen:                 # 同一道被两场重复引用是常态，记一次就够
            continue
        seen.add(k)
        out.append(e)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    entries = load()
    if not entries:
        print("账单是空的（%s）" % PENDING.name)
        return
    n0 = len(store.load_all())
    rep = ingest.apply_labels(entries, dry_run=a.dry)
    print("%s账单 %d 条 → 会动/动了 %d 道，查无此 key %d 道"
          % ("干跑：" if a.dry else "", len(entries), rep["刷了"], rep["查无此key"]))
    for d in rep["明细"]:
        print("   %s ← %s" % (d["key"][:60], "+".join(d["fields"])))
    if a.dry:
        print("（没写盘）")
        return
    n1 = len(store.load_all())
    print("库内题数 %d → %d（刷标签只改元数据，题数必须不变）" % (n0, n1))
    if n0 != n1:
        sys.exit("⛔ 题数变了，立刻停手核查")
    with ARCHIVE.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    PENDING.write_text("", encoding="utf-8")
    print("账单已归档 → %s" % ARCHIVE.name)


if __name__ == "__main__":
    main()
