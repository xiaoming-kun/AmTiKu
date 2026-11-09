"""小初章节讲义回归：120 章是否都在、是否都按高中模板、是否只讲不练。

只读，不起服务。数据不在（例如公开仓库）时明确跳过，不算失败。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import topics  # noqa: E402
from amti import lecture_tex  # noqa: E402

BASE = ROOT / "数据" / "专题" / "小初"
MANIFEST = BASE / "manifest.json"


def _expected() -> dict[str, dict]:
    tree = json.loads((ROOT / "知识地图.json").read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for st in tree.get("stages", []):
        if st.get("key") not in ("primary", "junior"):
            continue
        for b in st.get("books", []):
            for c in b.get("chapters", []):
                pts = c.get("points") or []
                if not pts:
                    continue
                cid = str(pts[0].get("id") or "").rsplit(".", 1)[0]
                if cid:
                    out[cid] = {"stage": st["key"], "book": b.get("name"),
                                "chapter": c.get("title"), "points": [p["id"] for p in pts]}
    return out


def main() -> int:
    if not MANIFEST.is_file():
        print("跳过：没有 数据/专题/小初/manifest.json")
        return 0
    expected = _expected()
    ts = [t for t in topics.load() if t.get("stage") in ("primary", "junior")]
    bad: list[str] = []
    if len(ts) != len(expected):
        bad.append("讲义 %d 份，知识地图应有 %d 章" % (len(ts), len(expected)))
    seen = set()
    for t in ts:
        cid = str(t.get("id") or "")
        if cid in seen:
            bad.append("重复的章 id：%s" % cid)
        seen.add(cid)
        e = expected.get(cid)
        if not e:
            bad.append("%s 不在知识地图里" % cid)
            continue
        if t.get("stage") != e["stage"]:
            bad.append("%s 学段是 %s，地图是 %s" % (cid, t.get("stage"), e["stage"]))
        def _n(x):
            return str(x or "").replace("～", "~").replace("－", "-")
        if _n(t.get("book")) != _n(e["book"]) or _n(t.get("chapter")) != _n(e["chapter"]):
            bad.append("%s 册/章与地图不一致" % cid)
        if t.get("questions"):
            bad.append("%s 小初讲义不该挂精选题" % cid)
        if not t.get("summary") or not any(x.get("label") == "易错点" for x in t["summary"]):
            bad.append("%s 缺易错点总结" % cid)
        if set(t.get("points") or []) != set(e["points"]):
            bad.append("%s 挂的知识点与地图不一致" % cid)
        for k in ("pdf", "tex"):
            p = ROOT / "数据" / "专题" / str(t.get(k) or "")
            if not p.is_file():
                bad.append("%s 缺 %s" % (cid, k))
        tex = ROOT / "数据" / "专题" / str(t.get("tex") or "")
        if tex.is_file():
            s = tex.read_text(encoding="utf-8")
            for needle in ("\\documentclass[lang=cn,newtx,12pt,scheme=chinese]{elegantbook}",
                           "\\begin{introduction}", "\\begin{proposition}[本节小结]",
                           "title=教材溯源"):
                if needle not in s:
                    bad.append("%s 模板缺：%s" % (cid, needle[:40]))
            if "\\begin{document}" not in s or "\\end{document}" not in s:
                bad.append("%s 模板不完整" % cid)
        cp = BASE / "content" / f"{cid}.json"
        if cp.is_file():
            c = json.loads(cp.read_text(encoding="utf-8"))
            issues = lecture_tex.validate_content(c, cid)
            if issues:
                bad.append("%s 内容校验：%s" % (cid, "；".join(issues[:3])))
            if len(c.get("sections") or []) < 3:
                bad.append("%s 少于 3 节" % cid)
        hp = ROOT / "数据" / "专题" / "讲义" / cid / "index.html"
        if not hp.is_file():
            bad.append("%s 缺网页版 HTML" % cid)
        else:
            h = hp.read_text(encoding="utf-8")
            for needle in ('<div class="lecture">', 'class="lec-table"',
                           "易错点与总结"):
                if needle not in h:
                    bad.append("%s HTML 缺：%s" % (cid, needle))
            if h.count("<h2") < 3:
                bad.append("%s HTML 少于 3 个二级标题" % cid)
    missing = sorted(set(expected) - seen)
    if missing:
        bad.append("缺讲义：%s" % "、".join(missing[:20]))
    for x in bad[:40]:
        print("✗", x)
    print("小初讲义 %d 份（小学 %d / 初中 %d），问题 %d 个" % (
        len(ts),
        sum(1 for t in ts if t.get("stage") == "primary"),
        sum(1 for t in ts if t.get("stage") == "junior"),
        len(bad)))
    print("通过" if not bad else "失败")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
