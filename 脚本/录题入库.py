#!/usr/bin/env python3
r"""录题入库：成品 JSON → Question → preview → commit（走 ingest 唯一入口）。

用法：python3 脚本/录题入库.py <成品.json> [--commit]
不带 --commit 只干跑。preview 有 errors / problems / missing_images 时**拒绝入库**。
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from amti import record2 as R2, store, ingest


def main(path, do_commit):
    recs = json.loads(Path(path).read_text(encoding="utf-8"))
    label = re_label(path)
    year = int(label[:4]) if label[:4].isdigit() else None
    fixed = tidy(recs)
    if fixed:
        Path(path).write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
        print("修掉相邻数学段拼成 `$$` 的写法 %d 处（会让 conform 的数学段配对错位）" % fixed)
    qs = [R2.rec_to_question(r, label) for r in recs]
    tex = "\n\n".join(store.render_question(q) for q in qs)
    pv = ingest.preview(tex, book="模拟题", label=label)
    print("count=%s dup=%s" % (pv["count"], pv["dup"]))
    bad = pv["errors"] or pv["problems"] or pv["missing_images"]
    for k in ("errors", "problems", "missing_images"):
        if pv[k]:
            print("%s: %s" % (k, json.dumps(pv[k], ensure_ascii=False)[:1200]))
    if bad:
        sys.exit("⛔ preview 不干净，不许入库")
    if not do_commit:
        print("干跑通过（未加 --commit，没有写库）")
        return
    rep = ingest.commit(tex, book="模拟题", label=label, year=year)
    print("ok=%s added=%s" % (rep.get("ok"), rep.get("added_count")))
    if not rep.get("ok"):
        print(json.dumps(rep, ensure_ascii=False, indent=1)[:1500])
        sys.exit("commit 失败")
    if rep.get("skipped"):
        print("skipped:", json.dumps(rep["skipped"], ensure_ascii=False)[:600])


def tidy(recs):
    r"""相邻两个数学段之间没有分隔会拼成 `$$`，让 conform 的 `$…$` 配对错位、
    把中文吞进数学模式（实测第 3 场 #7/#19 被闸门拒收）。补一个空格即可。
    本项目行间公式一律 `\\[ \\]`，所以 `$$` 不可能是合法写法。
    """
    n = 0
    for r in recs:
        for f in ("题干", "解析"):
            t = r.get(f) or ""
            if "$$" in t:
                r[f] = t.replace("$$", "$ $")
                n += t.count("$$")
        for k, v in list((r.get("选项") or {}).items()):
            if "$$" in v:
                r["选项"][k] = v.replace("$$", "$ $")
                n += v.count("$$")
    return n


def re_label(path):
    import re
    return re.sub(r"^\d+_", "", Path(path).stem).replace(".成品", "")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--commit"]
    main(a[0], "--commit" in sys.argv)
