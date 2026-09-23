#!/usr/bin/env python3
"""合并两路分类结果 → .tobias/分类/最终标签.json（一次性）。

规则：
  · 默认信「模型逐题分类」（batches/r*.json）；
  · 题目带 `dup_of`（查重命中孪生题）且孪生题也有考点时：
      两边题干相似度 ≥ 0.95（近乎同一道题）→ 信继承（库里已有的标签）；
      否则 → 仍信模型（查重命中不等于同一道题，实测不少只有 0.4–0.7 相似）。
"""
import difflib, glob, json, re, sys
from pathlib import Path

WORK = Path(__file__).resolve().parent


def norm(s):
    return re.sub(r"\s+", " ", s)


# 1) 题目与孪生题的题干
sys.path.insert(0, str(WORK.parents[1]))
import glob as g
stems = {}
for f in sorted(g.glob(str(WORK.parents[1] / "题目" / "*.tex"))):
    for line in open(f, encoding="utf-8"):
        if line.startswith("%% @q "):
            d = json.loads(line[6:])
            stems[d["key"]] = d

# 2) 分类输入（i → key）
items = {}
for name in ("待分类.json", "待分类2.json"):
    p = WORK / name
    if p.exists():
        for it in json.loads(p.read_text(encoding="utf-8")):
            items[it["i"]] = it

# 3) 模型结果
model = {}
for f in sorted(glob.glob(str(WORK / "batches" / "r*.json"))):
    for row in json.loads(Path(f).read_text(encoding="utf-8")):
        model[row["i"]] = row["points"]

# 4) 继承候选
inh = {r["key"]: r for r in json.loads((WORK / "继承.json").read_text(encoding="utf-8"))}

out = []
missing = []
for i in sorted(items):
    it = items[i]
    key = it["key"]
    pts = model.get(i)
    if pts is None:
        missing.append(i)
        continue
    src, note = "llm", ""
    row = inh.get(key)
    if row:
        other = stems.get(row["from"])
        if other is not None:
            s = difflib.SequenceMatcher(None, norm(stems[key]["stem"]),
                                        norm(other["stem"])).ratio()
            if s >= 0.95 and row["points"]:
                pts, src = row["points"], "dup"
                note = "继承 %s（题干相似 %.2f）" % (row["from"], s)
            else:
                note = "查重命中 %s 但题干相似仅 %.2f，按分类" % (row["from"], s)
    out.append({"key": key, "points": pts, "source": src, "note": note})

if missing:
    raise SystemExit("还有未分类的序号：%s" % missing[:20])
(WORK / "最终标签.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("最终标签：%d 道（继承 %d，分类 %d）"
      % (len(out), sum(1 for r in out if r["source"] == "dup"),
         sum(1 for r in out if r["source"] == "llm")))
