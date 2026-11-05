r"""外部大模型求解结果的机检（对应 `docs/求解要求_外部模型.md` 第 8 节）。

用法：

    python3 脚本/求解结果机检.py                # 检全部（求解批次 ↔ 求解结果 逐批对账）
    python3 脚本/求解结果机检.py --only 3       # 只检第 3 批（子代理自查用）
    python3 脚本/求解结果机检.py --only 3,4,5
    python3 脚本/求解结果机检.py --summary      # 只看总量对账：哪些题还没有结果

判据分两档：

* **错误**（挡住，必须改）：缺块/多块/key 不符/状态取值非法/`ok` 但解析空或含占位、
  LaTeX 括号不配对、`mismatch` 没给答案或依据、`核对` 与题干答案自相矛盾等。
* **提示**（不挡住，人工看一眼）：解析长短越界、多选只选一个、`ok` 却填了答案等。

只读不改：本脚本不碰题库、也不改结果文件。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "数据" / "题库审阅" / "求解批次"
OUT_DIR = ROOT / "数据" / "题库审阅" / "求解结果"
INPUT_JSONL = sorted((ROOT / "数据" / "题库审阅").glob("求解输入_*.jsonl"))

STATUS = {"ok", "unsure", "needs_figure", "error"}
CHECK = {"match", "mismatch", "missing"}
#: `ok` 的解析里不许出现的占位（整段就是这个字样才算，避免「战略」「省略」误报）
PLACEHOLDER = re.compile(r"^(?:解析|答案)?(?:无|略|同上|同参考答案|同答案|从略|待补)[。.]*$")
FORBID = ("$$", "//", "\\mbox", "\\begin{enumerate}", "\\begin{itemize}",
          "\\begin{itemize*}", "<解析>", "</解析>", "解析：", "解析:", "答案：", "答案:")
MARKDOWN = re.compile(r"\*\*|^#{1,6}\s|^\s*\|.*\|\s*$|^```", re.M)
#: 只认真正的标签（`<b>`、`</p>`、`<br/>`），避免把 `$x<y$` 这种数学比较误判成 HTML
HTML = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]{0,15}(\s+[a-zA-Z-]+=\"[^\"]*\")*\s*/?>")
PICKED = re.compile(r"故选\s*([A-D](?:\s*[、,，]?\s*[A-D])*)")


def _tag(body: str, tag: str) -> str:
    r"""取 `<tag>…</tag>` 内容；闭合标签缺了就取到块尾（跟 `amti.solve._block` 一致）。"""
    m = re.search(r"<%s>\s*" % tag, body)
    if not m:
        return ""
    rest = body[m.end():]
    end = rest.find("</%s>" % tag)
    return (rest[:end] if end >= 0 else rest).strip()


def split_blocks(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    r"""返回 ([(key, 块正文)], [块外杂讯行])。"""
    blocks, noise = [], []
    cur, buf = None, []
    for line in text.splitlines():
        if line.startswith("@@Q "):
            if cur is not None:
                blocks.append((cur, "\n".join(buf)))
                noise.append("⚠ 块尾缺 @@END：%s" % cur)
            cur, buf = line[4:].strip(), []
            continue
        if line.strip() == "@@END":
            if cur is None:
                noise.append("⚠ 孤立的 @@END")
            else:
                blocks.append((cur, "\n".join(buf)))
            cur, buf = None, []
            continue
        if cur is None:
            if line.strip():
                noise.append("⚠ 块外内容：%s" % line.strip()[:60])
        else:
            buf.append(line)
    if cur is not None:
        blocks.append((cur, "\n".join(buf)))
        noise.append("⚠ 文件在块内结束（输出被截断）：%s" % cur)
    return blocks, noise


def _unescaped(s: str, i: int) -> bool:
    r"""s[i] 前面有没有偶数个反斜杠（奇数个=被转义）。"""
    n = 0
    j = i - 1
    while j >= 0 and s[j] == "\\":
        n += 1
        j -= 1
    return n % 2 == 0


def tex_problems(s: str) -> list[str]:
    r"""花括号 / `$` / `\[ \]` / `\left \right` 是否成对。"""
    bad = []
    lb = sum(1 for i, c in enumerate(s) if c == "{" and _unescaped(s, i))
    rb = sum(1 for i, c in enumerate(s) if c == "}" and _unescaped(s, i))
    if lb != rb:
        bad.append("花括号不配对（{ %d 个，} %d 个）" % (lb, rb))
    dollar = sum(1 for i, c in enumerate(s) if c == "$" and _unescaped(s, i))
    if dollar % 2:
        bad.append("行内公式 `$` 是奇数个（%d）" % dollar)
    disp = len(re.findall(r"(?<!\\)\\\[", s))
    dispe = len(re.findall(r"(?<!\\)\\\]", s))
    if disp != dispe:
        bad.append("\\[ \\] 不配对（开 %d 闭 %d）" % (disp, dispe))
    nleft, nright = len(re.findall(r"\\left\b", s)), len(re.findall(r"\\right\b", s))
    if nleft != nright:
        bad.append("\\left \\right 不配对（%d / %d）" % (nleft, nright))
    for tok in FORBID:
        if tok in s:
            bad.append("出现禁用写法 %s" % tok)
    if MARKDOWN.search(s):
        bad.append("解析里混进 Markdown（** / 标题 / 表格 / 代码围栏）")
    if HTML.search(s):
        bad.append("解析里混进 HTML 标签")
    return bad


def letters(s: str) -> str:
    return "".join(sorted(set(re.findall(r"[A-D]", (s or "").upper()))))


def check_block(rec: dict, key: str, body: str) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    st, ck = _tag(body, "状态"), _tag(body, "核对")
    ans, sol, note = _tag(body, "答案"), _tag(body, "解析"), _tag(body, "备注")
    if not st:
        errs.append("缺 <状态>")
    if st not in STATUS:
        errs.append("状态非法：%r" % st)
    if not ck:
        errs.append("缺 <核对>")
    if ck not in CHECK:
        errs.append("核对非法：%r" % ck)

    if st == "ok":
        if not sol:
            errs.append("状态 ok 但解析为空")
        if PLACEHOLDER.match(sol or ""):
            errs.append("解析是占位：%r" % sol)
        if ck == "mismatch" and (ans in ("", "-")):
            errs.append("mismatch 但 <答案> 没填")
        if ck == "mismatch" and (note in ("", "-")):
            errs.append("mismatch 但 <备注> 没写依据")
        if ck not in ("mismatch", "missing") and ans not in ("", "-"):
            warns.append("核对是 %s，<答案> 却填了内容（应写 -）" % ck)
        for p in tex_problems(sol):
            errs.append(p)
        # 选择题：解析末尾的「故选 X」要和答案栏/题库答案自洽
        if rec["type"] in ("single_choice", "multi_choice"):
            picks = PICKED.findall(sol)
            got = letters(picks[-1]) if picks else ""
            if not got:
                errs.append("选择题解析里没有「故选 X」")
            elif ck == "match" and got != letters(rec.get("answer", "")):
                errs.append("解析说「故选 %s」，题库答案是 %s，却标 match"
                            % (got, rec.get("answer")))
            elif ck == "mismatch" and ans not in ("", "-") and got != letters(ans):
                errs.append("解析说「故选 %s」，<答案> 是 %s，自相矛盾" % (got, ans))
            if rec["type"] == "multi_choice" and len(got) < 2:
                warns.append("多选只选到 %r（%s），先怀疑漏选或题型标错" % (got, key))
    elif st in ("unsure", "needs_figure", "error"):
        if sol not in ("-", "", "－"):
            errs.append("状态 %s 的解析应写 -（实际有内容）" % st)
        if note in ("", "-"):
            errs.append("状态 %s 但 <备注> 没说明原因" % st)

    # 解析长度：按去掉空格后的字符数估（LaTeX 命令会虚增，故上限比要求的「字数」宽一些）
    if st == "ok":
        n = len(re.sub(r"\s", "", sol))
        lim = 1600 if rec["type"] == "detailed_answer" else 900
        if n < 60:
            warns.append("解析只有 %d 字，偏短" % n)
        elif n > lim:
            warns.append("解析 %d 字，超过建议上限 %d" % (n, lim))
    return errs, warns


def check_batch(n: int) -> tuple[int, int, list[str], dict]:
    r"""检一批，返回 (错误数, 提示数, 打印行, 统计)。"""
    bf = BATCH_DIR / ("批次_%03d.jsonl" % n)
    rf = OUT_DIR / ("结果_%03d.txt" % n)
    lines, stat = [], {"ok": 0, "unsure": 0, "needs_figure": 0, "error": 0,
                      "match": 0, "mismatch": 0, "missing": 0, "题数": 0}
    if not bf.exists():
        return 1, 0, ["批次_%03d.jsonl 不存在" % n], stat
    recs = [json.loads(l) for l in bf.read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in recs:
        stat["题数"] += 1
    if not rf.exists():
        lines.append("批次_%03d：%d 题 ✗ 结果文件不存在（%s）" % (n, len(recs), rf.name))
        return 1, 0, lines, stat

    blocks, noise = split_blocks(rf.read_text(encoding="utf-8"))
    errs = list(noise)
    warns: list[str] = []
    by_key = {}
    for key, body in blocks:
        if key in by_key:
            errs.append("key 重复：%s" % key)
        by_key[key] = body
    want = [r["key"] for r in recs]
    missing = [k for k in want if k not in by_key]
    extra = [k for k in by_key if k not in want]
    if missing:
        errs.append("漏题 %d 道：%s" % (len(missing), "；".join(missing[:5])
                                        + ("…" if len(missing) > 5 else "")))
    for k in extra:
        errs.append("多出来的 key（题库里没有）：%s" % k)
    for r in recs:
        body = by_key.get(r["key"])
        if body is None:
            continue
        e, w = check_block(r, r["key"], body)
        st = _tag(body, "状态")
        ck = _tag(body, "核对")
        if st in stat:
            stat[st] += 1
        if ck in stat:
            stat[ck] += 1
        for x in e:
            errs.append("%s：%s" % (r["key"], x))
        for x in w:
            warns.append("%s：%s" % (r["key"], x))

    n_ok = stat["ok"]
    lines.append("批次_%03d：%d 题，块 %d 个，ok %d / unsure %d / needs_figure %d / error %d"
                 "　｜核对 match %d mismatch %d missing %d　→ %s"
                 % (n, len(recs), len(blocks), n_ok, stat["unsure"], stat["needs_figure"],
                    stat["error"], stat["match"], stat["mismatch"], stat["missing"],
                    "✓ 全绿" if not errs else "✗ %d 处错误" % len(errs)))
    lines += ["    ✗ " + x for x in errs]
    lines += ["    · " + x for x in warns]
    return len(errs), len(warns), lines, stat


def summary() -> int:
    r"""总量对账：求解输入里的每一题，是否都有 `ok` 结果。"""
    if not INPUT_JSONL:
        print("找不到 数据/题库审阅/求解输入_*.jsonl")
        return 1
    src = INPUT_JSONL[-1]
    keys = [json.loads(l)["key"] for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    done: dict[str, str] = {}
    for rf in sorted(OUT_DIR.glob("结果_*.txt")) if OUT_DIR.exists() else []:
        blocks, _ = split_blocks(rf.read_text(encoding="utf-8"))
        for key, body in blocks:
            done[key] = _tag(body, "状态") or "?"
    ok = [k for k in keys if done.get(k) == "ok"]
    other = [k for k in keys if k in done and done[k] != "ok"]
    todo = [k for k in keys if k not in done]
    print("输入 %s：%d 题" % (src.name, len(keys)))
    print("  ok（可用）        %d" % len(ok))
    print("  非 ok（待人工）    %d" % len(other))
    print("  还没有结果         %d" % len(todo))
    for k in keys:
        if k not in done:
            print("    未做：%s" % k)
    return 0


def todo(n: int) -> int:
    r"""列出某批还没有结果的题号（一行一个 key），供续跑时只补漏。"""
    bf = BATCH_DIR / ("批次_%03d.jsonl" % n)
    if not bf.exists():
        print("批次_%03d.jsonl 不存在" % n)
        return 1
    keys = [json.loads(l)["key"]
            for l in bf.read_text(encoding="utf-8").splitlines() if l.strip()]
    rf = OUT_DIR / ("结果_%03d.txt" % n)
    done = set()
    if rf.exists():
        blocks, _ = split_blocks(rf.read_text(encoding="utf-8"))
        done = {k for k, _ in blocks}
    miss = [k for k in keys if k not in done]
    for k in miss:
        print(k)
    print("批次_%03d：共 %d 题，已有结果 %d，待补 %d" % (n, len(keys), len(keys) - len(miss), len(miss)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="外部模型求解结果机检")
    ap.add_argument("--only", default="", help="只检这些批次号，逗号分隔，如 3 或 3,4,5")
    ap.add_argument("--summary", action="store_true", help="只做总量对账")
    ap.add_argument("--todo", type=int, default=0, help="列出某批还没有结果的题号（续跑用）")
    a = ap.parse_args()
    if a.todo:
        return todo(a.todo)
    if a.summary:
        return summary()

    batches = sorted(int(p.stem.split("_")[1]) for p in BATCH_DIR.glob("批次_*.jsonl"))
    if a.only:
        pick = {int(x) for x in re.split(r"[,\s]+", a.only) if x.strip()}
        batches = [b for b in batches if b in pick]
        if not batches:
            print("批次号没匹配上：%s" % a.only)
            return 1
    e_tot = w_tot = 0
    agg = {"ok": 0, "unsure": 0, "needs_figure": 0, "error": 0,
           "match": 0, "mismatch": 0, "missing": 0, "题数": 0}
    for n in batches:
        e, w, lines, stat = check_batch(n)
        e_tot += e
        w_tot += w
        for k in agg:
            agg[k] += stat.get(k, 0)
        for ln in lines:
            print(ln)
    print("— 合计：应有 %d 题；ok %d，unsure %d，needs_figure %d，error %d；"
          "核对 match %d / mismatch %d / missing %d"
          % (agg["题数"], agg["ok"], agg["unsure"], agg["needs_figure"], agg["error"],
             agg["match"], agg["mismatch"], agg["missing"]))
    print("  错误 %d 处，提示 %d 处 → %s"
          % (e_tot, w_tot, "全绿" if not e_tot else "要改"))
    return 1 if e_tot else 0


if __name__ == "__main__":
    raise SystemExit(main())
