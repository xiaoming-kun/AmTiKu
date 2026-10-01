#!/usr/bin/env python3
r"""**入库前体检**：逐场走一遍真实入库路径到 `preview` 为止，出一份能不能入的账。

只读——**不调 `commit`、不写成品、不碰 `题目/*.tex`**。
与 `录题入库.py` 走同一条路（tidy → merge_sidecar → attach_answers → rec_to_question
→ attach_points → render → preview），差别只在这里不回写成品文件。

    python3 脚本/入库前体检.py            # 全池
    python3 脚本/入库前体检.py 447 514     # 只点这几场

产出：`数据/录题/入库前体检.json`（逐场明细）＋ `数据/录题/入库前体检.md`（结论）。
"""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ONLY = set(sys.argv[1:])           # 先收参数：下面加载 录题入库.py 时它会读 sys.argv
sys.argv = [sys.argv[0]]
import importlib.util                                  # noqa: E402

spec = importlib.util.spec_from_file_location("ri", ROOT / "脚本/录题入库.py")
RI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RI)
from amti import ingest, record2 as R2, store          # noqa: E402

V2 = ROOT / "数据/录题/输出_v2"
SKIP_NEEDED = {"76": ["4"]}          # 原卷印坏、只能摘题入库的场（见 录题入库.py 的 --skip）


def scan(path: Path) -> dict:
    recs = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
    RI.tidy(recs)                                     # 不回写，只在内存里规整
    RI.merge_sidecar(path, recs)
    skip = SKIP_NEEDED.get(path.name.split("_")[0], [])
    recs, gone = RI.drop_skipped(path, recs, tuple(skip))
    label = RI.re_label(path)
    qs = [R2.rec_to_question(r, label) for r in recs]
    n_pt = RI.attach_points(path, recs, qs)
    tex = "\n\n".join(store.render_question(q) for q in qs)
    pv = ingest.preview(tex, book="模拟题", label=label)
    inc = [e for e in pv["errors"] if RI.incomplete(e)]
    hard = [e for e in pv["errors"] if not RI.incomplete(e)]
    return {
        "场": path.name[: -len(".成品.json")],
        "题数": len(recs),
        "考点覆盖": n_pt,
        "摘除": gone,
        "new": pv["dup"]["new"], "merge": pv["dup"]["merge"],
        "suspect": pv["dup"]["suspect"], "upgrade": pv["dup"]["upgrade"],
        "硬错误": hard[:6], "problems": pv["problems"][:6],
        "缺图": pv["missing_images"][:6], "spec.after": pv["spec"]["after"][:6],
        "完整性拦下": len(inc),
    }


def main() -> None:
    only = ONLY
    files = sorted(V2.glob("*.成品.json"))
    if only:
        files = [f for f in files if f.name.split("_")[0] in only]
    out, t0 = [], 0.0
    for i, f in enumerate(files, 1):
        r = scan(f)
        r["能入"] = not (r["硬错误"] or r["problems"] or r["缺图"] or r["spec.after"]
                        or r["完整性拦下"])
        out.append(r)
        if i % 40 == 0:
            print("%d/%d 已扫，目前能入 %d" % (i, len(files), sum(1 for x in out if x["能入"])),
                  flush=True)
    (ROOT / "数据/录题/入库前体检.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ok = [r for r in out if r["能入"]]
    bad = [r for r in out if not r["能入"]]
    why = Counter()
    for r in bad:
        if r["完整性拦下"]:
            why["完整性闸（缺答案/缺解析）"] += 1
        if r["硬错误"]:
            why["preview 硬错误"] += 1
        if r["problems"]:
            why["problems（结构/写法）"] += 1
        if r["spec.after"]:
            why["spec.after（规范化后仍不合规范）"] += 1
        if r["缺图"]:
            why["缺图"] += 1
        if r["merge"]:
            why["有题指纹已在库（疑似撞车）"] += 1
    L = ["# 入库前体检", "",
         "扫法：逐场走 `录题入库.py` 到 `preview` 为止，**不 commit、不写成品**。", "",
         "- 场数 %d，总题数 %d" % (len(out), sum(r["题数"] for r in out)),
         "- **四道闸全过、可直接入库：%d 场 %d 题**" % (len(ok), sum(r["题数"] for r in ok)),
         "- 有拦项：%d 场" % len(bad), ""]
    for k, v in why.most_common():
        L.append("  · %s：%d 场" % (k, v))
    L += ["", "## 拦项最多的场（前 20）", "", "| 场 | 题数 | 完整性拦下 | 硬错误 | problems | spec.after | 缺图 | merge |",
          "|---|---|---|---|---|---|---|---|"]
    for r in sorted(bad, key=lambda x: -(x["完整性拦下"] + len(x["硬错误"]) + len(x["problems"])
                                         + len(x["spec.after"]) + len(x["缺图"])))[:20]:
        L.append("| %s | %d | %d | %d | %d | %d | %d | %d |" % (
            r["场"].split("_")[0], r["题数"], r["完整性拦下"], len(r["硬错误"]),
            len(r["problems"]), len(r["spec.after"]), len(r["缺图"]), r["merge"]))
    dup = [r for r in out if r["merge"]]
    L += ["", "## 有题指纹已在库（`dup.merge > 0`，入库前必须逐场核对是不是撞车）",
          "", "%d 场" % len(dup), ""]
    for r in sorted(dup, key=lambda x: -x["merge"])[:25]:
        L.append("- %s：merge %d / %d 题" % (r["场"][:52], r["merge"], r["题数"]))
    (ROOT / "数据/录题/入库前体检.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("写了 入库前体检.md：%d 场能直接入库 / 共 %d 场" % (len(ok), len(out)))


if __name__ == "__main__":
    main()
