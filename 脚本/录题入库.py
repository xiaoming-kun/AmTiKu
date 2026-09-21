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
    # 库里已有同一场卷（卷名逐字相同），#17/#18 指纹 1.0）。
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
    # ⚠️ 「缺答案/缺解析」这一类 errors 是**入库**的闸门（ingest._incomplete_errors，
    # 2026-09-21 新规矩），不是解析阶段的闸门。无答案卷的成品本来就该空着，
    # 把它算进失败会逼着执行的人去凑答案 —— 那是伪造原卷内容。
    # 所以这里按「是不是完整性闸拦的」分流：只有**其它**错误才算失败。
    # 精确匹配 ingest._incomplete_errors 的固定句式，不用宽松关键词
    # ——「缺」+「答案」这种组合会误吞真正的错误。
    _INC_REASON = "本库规矩：没有答案或没有解析的题目不许入库"

    def _incomplete(e):
        return _INC_REASON in json.dumps(e, ensure_ascii=False)

    inc = [e for e in pv["errors"] if _incomplete(e)]
    hard = [e for e in pv["errors"] if not _incomplete(e)]
    bad = hard or pv["problems"] or pv["missing_images"] or spec_after
    for k, arr in (("errors", hard), ("problems", pv["problems"]),
                   ("missing_images", pv["missing_images"])):
        if arr:
            print("%s: %s" % (k, json.dumps(arr, ensure_ascii=False)[:1200]))
    if spec_after:
        print("spec.after: %s" % json.dumps(spec_after, ensure_ascii=False)[:1200])
    if inc:
        print("ℹ️ 另有 %d 条「缺答案/缺解析」被入库完整性闸拦下 —— 无答案卷属正常，"
              "**不许为了清空它去编答案**，照常收尾即可" % len(inc))
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
    3. 反过来，用**普通字符串**写 LaTeX 时 `\\v`、`\\f`、`\\b`、`\\a`、`\\e`
       会被 Python 吃掉成控制符，**而且命令的首字母一起没了**
       （实测：第 79、132 场的 `$\\varphi$` 落成 `$<0x0b>arphi$`）。
       所以必须还原成「反斜杠 + 那个字母」，只补反斜杠会得到 `\\arphi` 这种假命令。
       **不动 `\\t`(0x09) 和 `\\n`(0x0a)**——这两个在本项目正文里是合法的段落分隔。
       映射表以外的控制符（0x01-0x06 等）不动，留着让闸门报错，别猜。
    """
    import re
    fake_nl = re.compile(r"\\n(?![a-zA-Z])")
    CTRL2CMD = {"\x07": "\\a", "\x08": "\\b", "\x0b": "\\v",
                "\x0c": "\\f", "\x0d": "\\r", "\x1b": "\\e", "\x00": "\\0"}
    ctrl = re.compile("[" + "".join(CTRL2CMD) + "]")
    n = 0

    def fix(t):
        nonlocal n
        if "$$" in t:
            n += t.count("$$")
            t = t.replace("$$", "$ $")
        t, k = fake_nl.subn("\n", t)
        n += k
        t, k = ctrl.subn(lambda mo: CTRL2CMD[mo.group()], t)
        n += k
        return t

    for r in recs:
        for f in ("题干", "答案", "解析"):
            r[f] = fix(r.get(f) or "")
        opts = {}
        for k, v in list((r.get("选项") or {}).items()):
            opts[k] = fix(v)
        if r.get("选项"):
            r["选项"] = opts
    return n


def re_label(path):
    import re
    return re.sub(r"^\d+_", "", Path(path).stem).replace(".成品", "")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x not in ("--commit", "--force")]
    main(a[0], "--commit" in sys.argv, "--force" in sys.argv)
