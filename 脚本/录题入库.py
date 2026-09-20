#!/usr/bin/env python3
r"""录题入库：成品 JSON → Question → preview → commit（走 ingest 唯一入口）。

用法：python3 脚本/录题入库.py <成品.json> [--commit] [--force]
不带 --commit 只干跑。preview 有 errors / problems / missing_images 时**拒绝入库**。
`--force` = 库里已有同 key 且解析非空时，以手里这份为准（补录解析用）。
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from amti import record2 as R2, store, ingest


def main(path, do_commit, force=False):
    recs = json.loads(Path(path).read_text(encoding="utf-8"))
    label = re_label(path)
    year = int(label[:4]) if label[:4].isdigit() else None
    fixed = tidy(recs)
    if fixed:
        Path(path).write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
        print("修掉相邻数学段拼成 `$$` 的写法 %d 处（会让 conform 的数学段配对错位）" % fixed)
    qs = [R2.rec_to_question(r, label) for r in recs]
    tex = "\n\n".join(store.render_question(q) for q in qs)
    pv = ingest.preview(tex, book="模拟题", label=label, update_force=force)
    print("count=%s dup=%s" % (pv["count"], pv["dup"]))
    # `merge` > 0 = 有题**指纹完全相同**已在库。整场录题里出现它，多半说明
    # **这一整场就是重复卷**，只是队列的卷名和库里的 source_label 写法不同，
    # 卷面标题预检没拦住（实测第 43 场：队列叫「2025年10月杭二高三月考」，
    # 库里叫「杭州第二中学2025年10月高三年级适应性检测」，#17/#18 指纹 1.0）。
    # 这时先停下来核对，别把同一场录两遍。
    if pv["dup"]["merge"]:
        print("⚠️ 有 %d 题指纹已在库，先核对是不是整场撞车：" % pv["dup"]["merge"])
        for it in pv["items"]:
            if it["same_key"]:
                hits = it["dups"][:1]
                print("   %s ←→ %s" % (it["key"], hits[0]["key"] if hits else "同 key"))
    # ⚠️ `spec.after` 也要拦：commit 里还有一道「规范复核不过就不录」的闸门，
    # 只查 errors/problems 会白跑一次 commit 才被拒（实测第 29 场 #19）。
    spec_after = pv["spec"]["after"]
    bad = pv["errors"] or pv["problems"] or pv["missing_images"] or spec_after
    for k in ("errors", "problems", "missing_images"):
        if pv[k]:
            print("%s: %s" % (k, json.dumps(pv[k], ensure_ascii=False)[:1200]))
    if spec_after:
        print("spec.after: %s" % json.dumps(spec_after, ensure_ascii=False)[:1200])
    if bad:
        sys.exit("⛔ preview 不干净，不许入库")
    if not do_commit:
        print("干跑通过（未加 --commit，没有写库）")
        return
    rep = ingest.commit(tex, book="模拟题", label=label, year=year, update_force=force)
    print("ok=%s added=%s upgraded=%s"
          % (rep.get("ok"), rep.get("added_count"), len(rep.get("upgraded") or [])))
    if not rep.get("ok"):
        print(json.dumps(rep, ensure_ascii=False, indent=1)[:1500])
        sys.exit("commit 失败")
    if rep.get("upgraded"):
        print("upgraded:", json.dumps(rep["upgraded"], ensure_ascii=False)[:600])
    if rep.get("skipped"):
        print("skipped:", json.dumps(rep["skipped"], ensure_ascii=False)[:600])


def tidy(recs):
    r"""两处固化下来的清洗（都是实测踩过、闸门会拒的写法）：

    1. 相邻两个数学段之间没有分隔会拼成 `$$`，让 conform 的 `$…$` 配对错位、
       把中文吞进数学模式（实测第 3 场 #7/#19 被闸门拒收）。补一个空格即可。
       本项目行间公式一律 `\\[ \\]`，所以 `$$` 不可能是合法写法。
    2. 生成脚本里用 Python **原始字符串** 写正文时，`\\n` 不会变成换行，
       落库就成了正文里的两个字符（实测第 28 场 8 道题被闸门拒收）。
       只认后面不接字母的那种，`\\neq`、`\\nu` 这类命令不受影响。
    """
    import re
    fake_nl = re.compile(r"\\n(?![a-zA-Z])")
    n = 0
    for r in recs:
        for f in ("题干", "答案", "解析"):
            t = r.get(f) or ""
            if "$$" in t:
                n += t.count("$$")
                t = t.replace("$$", "$ $")
            t2, k = fake_nl.subn("\n", t)
            r[f] = t2
            n += k
        opts = {}
        for k, v in list((r.get("选项") or {}).items()):
            if "$$" in v:
                n += v.count("$$")
                v = v.replace("$$", "$ $")
            v, k2 = fake_nl.subn("\n", v)
            opts[k] = v
            n += k2
        if r.get("选项"):
            r["选项"] = opts
    return n


def re_label(path):
    import re
    return re.sub(r"^\d+_", "", Path(path).stem).replace(".成品", "")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x not in ("--commit", "--force")]
    main(a[0], "--commit" in sys.argv, "--force" in sys.argv)
