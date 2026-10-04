#!/usr/bin/env python3
r"""逐题审阅 · 终审台（把各路报来的「错」一条条摊开，供**人/模型自己重算**）。

只读，不写题库、不写台账。合并脚本只信这个台子筛过的条目。

    python3 脚本/题库审阅终审.py list              # 队列概览
    python3 脚本/题库审阅终审.py show 3            # 摊开第 3 条（题库现值 + agent 的说法）
    python3 脚本/题库审阅终审.py verdict 3 ok|对|否 "依据"   # 记一条终审结论
    python3 脚本/题库审阅终审.py status            # 已终审到哪、各结论多少

结论落在 `数据/题库审阅/终审.jsonl`：`pass`＝agent 说对了、可以落账；
`reject`＝agent 判错（题库本来就对，或它的算法不成立）；`hold`＝还没算明白。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store                                   # noqa: E402
from amti.paths import ROOT as RROOT                     # noqa: E402

DIR = RROOT / "数据" / "题库审阅"
BATCH = DIR / "批次"
OUT = DIR / "终审.jsonl"

# 已终审落盘的批次（agentA/B/C/F 那 14 条已经进过题库，不再重复摊）
LANDED = {"agentA", "agentB", "agentC", "agentF"}


def queue() -> list[dict]:
    r"""待终审队列：**所有**批次里 verdict=错 的条目，稳定排序。

    ⚠️ 队列**不随签字收缩**——早先版本把已签字的剔掉，于是 `verdict 2` 之后
    原来的第 3 条就变成第 2 条，我在同一批命令里把三条结论记到了错的题上。
    现在序号恒定，签字状态只在 `list` 里标出来；寻址也支持直接给题号关键字。
    """
    done = judged()
    rows = []
    for p in sorted((BATCH).glob("*.jsonl")) + sorted((BATCH).glob("*-待核.hold")):
        for ln in p.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r.get("verdict") != "错" or not r.get("key"):
                continue
            r["_batch"] = p.stem
            rows.append(r)
    rows.sort(key=lambda r: (r["_batch"], r["key"]))
    for i, r in enumerate(rows):
        r["_idx"] = i + 1
        r["_done"] = done.get(r["key"])
    return rows


def resolve(rows: list[dict], arg: str) -> dict | None:
    """按序号或题号关键字（唯一命中）定位一条。"""
    if arg.isdigit():
        return next((r for r in rows if r["_idx"] == int(arg)), None)
    hit = [r for r in rows if arg in r["key"]]
    if len(hit) != 1:
        print(f"「{arg}」命中 {len(hit)} 条，要更具体的关键字：")
        for r in hit[:12]:
            print("   ", r["key"])
        return None
    return hit[0]


def judged() -> dict[str, dict]:
    out = {}
    if OUT.exists():
        for ln in OUT.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                out[r["key"]] = r
    return out


def record(key: str, result: str, note: str) -> None:
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"key": key, "result": result, "note": note,
                            "at": "2026-10-03"}, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "show", "verdict", "status"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    rows = queue()

    if a.cmd == "list":
        done = judged()
        for r in rows:
            j = done.get(r["key"])
            mark = (j["result"] if j else "··")
            print(f"{r['_idx']:>3} [{mark:>6}] {r['_batch']:<12} {r['axis']:<8} {r['key']}")
        print(f"\n共 {len(rows)} 条，已终审 {len([r for r in rows if r['key'] in done])} 条")
        return 0

    if a.cmd == "status":
        done = judged()
        from collections import Counter
        print(Counter(j["result"] for j in done.values()))
        for r in rows:
            j = done.get(r["key"])
            if j:
                print(f"  [{j['result']}] {r['key']} — {j['note'][:70]}")
        return 0

    hit = resolve(rows, a.args[0])
    if hit is None:
        print(f"队列里定位不到「{a.args[0]}」（共 {len(rows)} 条）")
        return 1
    n = hit["_idx"]

    if a.cmd == "show":
        q = store.find(hit["key"])
        if q is None:
            print("⚠️ 题库里找不到这道题")
        else:
            print("=" * 78)
            print(f"#{n}  {hit['key']}  [{hit['_batch']} / {hit['axis']}]")
            print("-" * 78)
            print("【题干】", (q.stem or "").strip()[:1800])
            print("-" * 78)
            for op in q.options:
                print(f"  {op.label}. {op.text}")
            print("【答案】", q.answer)
            print("【题型】", q.type, "| 难度", q.difficulty, "| 考点", q.points)
            print("-" * 78)
            print("【解析】", (q.solution or "")[:2200])
            print("=" * 78)
            print(f"agent 说：{hit.get('problem','')}")
            print(f"agent 算：{hit.get('proof','')}")
            if hit.get("fix"):
                print(f"agent 建议：{json.dumps(hit['fix'], ensure_ascii=False)[:2500]}")
            if hit.get("note"):
                print(f"agent 备注：{hit['note']}")
        return 0

    # verdict
    result, note = a.args[1], (a.args[2] if len(a.args) > 2 else "")
    alias = {"对": "pass", "ok": "pass", "pass": "pass", "否": "reject", "reject": "reject",
             "挂": "hold", "hold": "hold"}
    if result not in alias:
        print("结论只认 pass/对、reject/否、hold/挂")
        return 1
    record(hit["key"], alias[result], note or hit.get("problem", ""))
    # 把题号回显出来：早先只回显序号，记错题看不出来（真记错过 3 条）
    print(f"已记 #{n} {hit['key']} → {alias[result]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
