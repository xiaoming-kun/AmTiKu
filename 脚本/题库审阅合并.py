#!/usr/bin/env python3
r"""逐题审阅 · 合并各路的判定（**唯一写数据的人**）。

并行审阅时每一路只准写自己的 `数据/题库审阅/批次/agentN.jsonl`，
**不碰题库、不碰台账**；本脚本把批次判定收上来，做三件事：

1. 判「ok」的写进 `逐题进度.json`（游标，续跑时跳过）；
2. 判「错」且给了 `fix` 的，转成 `数据/订正台账.json` 的一条账
   ——`expect` 一律**现读题库当前值**（写死旧值会被漂移护栏整批拒掉），
   改答案时**题干 `\paren[…]` / `\fillin[…]` 同步改**（ENTRY 期规则只在录入时同步，
   只改字段的话卷面仍印旧答案）；
3. 判「待裁决」的进 `待裁决.md`，考点/难度类建议进 `标签建议.jsonl`
   （考点 `points` 不在 fixups 可改字段里，得走标签那条线，别在这里硬写）。

    python3 脚本/题库审阅合并.py            # 干跑：只报会落哪些账
    python3 脚本/题库审阅合并.py --yes      # 落账 + 跑 fixups + 更新游标
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store                                   # noqa: E402
from amti.paths import ROOT as RROOT                     # noqa: E402

DIR = RROOT / "数据" / "题库审阅"
CURSOR = DIR / "逐题进度.json"
LEDGER = RROOT / "数据" / "订正台账.json"


def set_blank(stem: str, ans: str) -> str:
    r"""把题干里**最后一个**作答位的空填成答案（\paren 与 \fillin 两种写法）。"""
    hits = list(re.finditer(r"\\(?:paren|fillin)\s*\[[^\]]*\]", stem))
    if not hits:
        return stem
    m = hits[-1]
    return stem[:m.start()] + "\\" + m.group(0)[1:].split("[")[0] + "[" + ans + "]" + stem[m.end():]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--only", default="",
                    help="只合并这些批次（逗号分隔的文件名主干，如 agentA,agentB）")
    a = ap.parse_args()
    files = sorted((DIR / "批次").glob("*.jsonl"))
    keep = {x.strip() for x in a.only.split(",") if x.strip()}
    if keep:
        skipped = [f.name for f in files if f.stem not in keep]
        files = [f for f in files if f.stem in keep]
        print(f"只合并 {keep}；本轮暂不放进来 {len(skipped)} 个批次：", skipped)
    if not files:
        print("没有批次文件：", DIR / "批次")
        return 1
    rows, badline = [], []
    for f in files:
        for ln in f.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                rows.append(json.loads(ln))
            except ValueError:
                badline.append((f.name, ln[:60]))
    cnt = Counter(r.get("verdict", "?") for r in rows)
    print(f"收 {len(files)} 个批次、{len(rows)} 条判定：", dict(cnt))
    if badline:
        print("  ⚠️ 读不懂的行：", badline[:3])

    by_key = {q.key: q for q in store.load_cached()}
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    idx = {p["key"]: i for i, p in enumerate(led["patches"])}
    new, upd = [], 0
    labels, undecided = [], []
    for r in rows:
        key = r.get("key") or ""
        q = by_key.get(key)
        if q is None:
            print("  ⚠️ 题库里没有这道，丢弃：", key)
            continue
        v = r.get("verdict")
        if v == "待裁决":
            undecided.append(r)
            continue
        if v != "错":
            continue
        fix = r.get("fix") or {}
        st, se = {}, {}
        if fix.get("answer") and fix["answer"].strip() != (q.answer or "").strip():
            se["answer"] = fix["answer"].strip()
            st["answer"] = q.answer
            ns = set_blank(q.stem, se["answer"])
            if ns != q.stem:
                se["stem"] = ns
                st["stem"] = q.stem
        if fix.get("solution") and fix["solution"].strip() != (q.solution or "").strip():
            se["solution"] = fix["solution"]
            st["solution"] = q.solution
        if fix.get("difficulty"):
            se["meta"] = {"difficulty": fix["difficulty"]}
            st["meta"] = {"difficulty": (q.meta or {}).get("difficulty", "")}
        if fix.get("points"):
            labels.append({"key": key, "points": fix["points"],
                           "why": r.get("proof") or r.get("problem", "")})
        if not se:
            continue
        ent = {"key": key, "why": (r.get("problem") or "逐题审阅判为错")[:120],
               "src": r.get("proof") or "审阅者独立复算", "expect": st, "set": se}
        if key in idx:
            led["patches"][idx[key]] = ent
            upd += 1
        else:
            new.append(ent)
    print(f"要落账：新增 {len(new)} 条、覆盖 {upd} 条；考点建议 {len(labels)} 条；"
          f"待裁决 {len(undecided)} 条")
    for e in new[:6] + [x for x in led["patches"] if x in new][:0]:
        print("  ·", e["key"], "→", list(e["set"]))
    if not a.yes:
        print("（干跑。加 --yes 落账）")
        return 0

    led["patches"].extend(new)
    LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    cur = json.loads(CURSOR.read_text(encoding="utf-8")) if CURSOR.exists() else {"判定": {}}
    for r in rows:
        if r.get("key") in by_key:
            cur["判定"][r["key"]] = r.get("verdict", "?")
    cur["审到"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur["keys"] = list(cur["判定"])
    CURSOR.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    if labels:
        with (DIR / "标签建议.jsonl").open("a", encoding="utf-8") as f:
            for x in labels:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    if undecided:
        with (DIR / "待裁决.md").open("a", encoding="utf-8") as f:
            f.write(f"\n## 批次合并 {cur['审到']}\n\n")
            for r in undecided:
                f.write(f"- `{r['key']}` ｜ {r.get('problem', '')} ｜ {r.get('proof', '')}\n")
    print(f"已落账，游标 {len(cur['判定'])} 道。接下来跑：python3 -m amti.fixups --yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
