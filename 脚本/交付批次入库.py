#!/usr/bin/env python3
r"""交付批次入库：一批「五样交付」目录 → preview → commit（走 ingest 唯一入口）。

    python3 脚本/交付批次入库.py ~/Desktop/初中数学项目/交付/*/        # 干跑
    python3 脚本/交付批次入库.py ~/Desktop/初中数学项目/交付/*/ --yes  # 入库

每个目录要有：
    <卷名>.tex        题目块（question/question+problem 均可）
    图/               题图（可空）
    录入参数.txt      book=… label=… year=… region=…
    考点标签.json     [{"block":1,"points":["c71.1.5"],"difficulty":"简单题","note":"…"}, …]
                      block **1 基**（与 .tex 的块序一致）；points 第一条是主考点。

为什么考点/难度在**入库时**一起带走，而不是入库后再补：
    `points` 不参与 content_hash，`commit` 时一并写入是零风险的；
    补标签要走 `store.rewrite_all()` 全库重写。

干跑只读：解析、查图、查重、规范复核、字段校验，什么都不写。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import ingest as ig          # noqa: E402


def read_params(d: Path) -> dict:
    """`录入参数.txt` 是这批的唯一真相（目录名只兜底）。"""
    pf = d / "录入参数.txt"
    if not pf.exists():
        raise SystemExit(f"✗ {d.name}：没有 录入参数.txt")
    kv = dict(re.findall(r"(\w+)=([^\s]*)", pf.read_text(encoding="utf-8")))
    if not kv.get("label"):
        raise SystemExit(f"✗ {d.name}：录入参数缺 label")
    if not kv.get("year"):
        raise SystemExit(f"✗ {d.name}：录入参数缺 year")
    return kv


def read_tags(d: Path, n_blocks: int) -> list[dict]:
    tf = d / "考点标签.json"
    if not tf.exists():
        raise SystemExit(f"✗ {d.name}：没有 考点标签.json（难度/考点由录入方给）")
    rows = json.loads(tf.read_text(encoding="utf-8"))
    if len(rows) != n_blocks:
        raise SystemExit(f"✗ {d.name}：考点标签 {len(rows)} 条 ≠ 块数 {n_blocks}")
    seen = set()
    for r in rows:
        b = int(r["block"])
        if b in seen:
            raise SystemExit(f"✗ {d.name}：块号重复 {b}")
        seen.add(b)
        if not r.get("points"):
            raise SystemExit(f"✗ {d.name}：第 {b} 块没有考点")
        if r.get("difficulty") not in ("简单题", "中档题", "难题"):
            raise SystemExit(f"✗ {d.name}：第 {b} 块难度非法 {r.get('difficulty')!r}")
    if seen != set(range(1, n_blocks + 1)):
        raise SystemExit(f"✗ {d.name}：块号不是 1..{n_blocks}")
    return rows


def items_of(rows: list[dict]) -> list[dict]:
    """`考点标签.json`（1 基块号）→ `ingest` 的逐题覆盖（0 基块号）。"""
    out = []
    for r in rows:
        b = int(r["block"])
        out.append({
            "block": b - 1,
            "points": list(r["points"]),
            "difficulty": r["difficulty"],
            "source_no": str(b),
            "point_source": r.get("source") or "llm",
        })
    return out


def run_one(d: Path, *, yes: bool) -> dict:
    kv = read_params(d)
    tex = next(iter(sorted(d.glob("*.tex"))), None)
    if tex is None:
        raise SystemExit(f"✗ {d.name}：没有 .tex")
    src = tex.read_text(encoding="utf-8")
    n_blocks = len(ig.split_source(src))
    rows = read_tags(d, n_blocks)
    items = items_of(rows)
    imgs = d / "图"
    src_dirs = [str(imgs)] if imgs.is_dir() else None
    kw = dict(src_dirs=src_dirs, book=kv.get("book") or "手工录入",
              label=kv["label"], region=kv.get("region") or "",
              year=int(kv["year"]), items=items)

    pv = ig.preview(src, **kw)
    why = []
    if pv["errors"]:
        why.append("解析问题 " + json.dumps(pv["errors"][:3], ensure_ascii=False))
    if pv["count"] != n_blocks:
        why.append(f"解析 {pv['count']} ≠ 块数 {n_blocks}")
    missing = [k for k, v in pv["images"].items() if v["status"] == "missing"]
    if missing:
        why.append("缺图 " + ", ".join(missing[:5]))
    if not pv.get("spec", {}).get("ok", True):
        why.append("复核后仍不规范 " + json.dumps(pv["spec"].get("after", [])[:2],
                                              ensure_ascii=False))
    bad = [it["key"] for it in pv["items"] if it.get("problems")]
    if bad:
        why.append(f"字段问题 {len(bad)} 道")
    if pv["impact"]["existing_questions"]:
        why.append(f"会动存量 {pv['impact']['existing_questions']} 道")
    # 考点 id 不合法时 `ingest` 是**静默丢掉**的（老库只认 152 个高中考点）。
    # 打错一个字母 → 这道题入库后没有标签，而且没有任何报错。所以按块逐条对。
    got = {int(it["block"]): list(it["points"] or []) for it in pv["items"]}
    lost = []
    for row in rows:
        b = int(row["block"]) - 1
        want = list(dict.fromkeys(row["points"]))
        if got.get(b) != want:
            lost.append(f"第 {b + 1} 块（要 {want}，得 {got.get(b)}）")
    if lost:
        why.append("考点没贴全（id 不合法会被静默丢弃）：" + "；".join(lost[:3]))

    d_ = pv["dup"]
    print(f"\n════ {d.name}　{n_blocks} 块　新增 {d_['new']}｜并入 {d_['merge']}"
          f"｜疑似 {d_['suspect']}｜升级 {d_['upgrade']}")
    print(f"     {kv['label']}　{kw['year']}　{kw['region']}　图 {len(pv['images'])} 张")
    if why:
        print("  ✗ " + " ✗ ".join(why))
        return {"ok": False, "why": why, "added": 0, "skipped": 0}
    if not yes:
        print("  ✓ 干跑全绿（未写入）")
        return {"ok": True, "added": 0, "skipped": 0, "dry": True}

    r = ig.commit(src, **kw)
    if not r.get("ok"):
        print("  ✗ commit 失败：" + str(r.get("error"))[:300])
        return {"ok": False, "why": [r.get("error")], "added": 0, "skipped": 0}
    print(f"  ✓ 新增 {r['added_count']}　跳过 {len(r['skipped'])}"
          f"　图 复制 {r['images']['copied']}/复用 {r['images']['reused']}"
          f"/缺 {len(r['images']['missing'])}")
    for s in r["skipped"][:5]:
        print(f"     - {s['key']}  {s['reason']}")
    return {"ok": True, "added": r["added_count"],
            "skipped": len(r["skipped"]), "why": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--yes", action="store_true", help="真的写库")
    a = ap.parse_args()
    dirs = [Path(x).expanduser() for x in a.dirs]
    dirs = sorted([p for p in dirs if p.is_dir()], key=lambda p: p.name)
    if not dirs:
        raise SystemExit("没有可处理的目录")
    bad = 0
    total = {"added": 0, "skipped": 0}
    for d in dirs:
        try:
            r = run_one(d, yes=a.yes)
        except SystemExit as e:
            print(str(e))
            r = {"ok": False}
        if not r.get("ok"):
            bad += 1
        total["added"] += r.get("added", 0)
        total["skipped"] += r.get("skipped", 0)
    print(f"\n总计：新增 {total['added']}　跳过 {total['skipped']}　失败批次 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
