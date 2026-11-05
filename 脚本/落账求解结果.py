r"""把外部求解结果落账：`状态=ok` 且 `核对=match/missing` 的解析写进题库（**答案不动**）。

来源：`数据/题库审阅/求解结果/结果_*.txt`（1208 道缺解析题的外部求解）。
口径（2026-10-18 用户定）：

* `ok` + `match`（答案与题库一致）+ `ok` + `missing`（题库答案是「见解析」/没有可核对答案）
  → 写解析，**答案一个字不改**；
* `mismatch`（191 道，答案与题库打架）→ 不动，等人工复核；
* `unsure`（5 道）→ 不动；
* `error` / `needs_figure`（97 道）→ 已另行删除（见 `删求解判坏的九十七道.py`）。

写库前逐条过 `amti/conform.py` 的同一套文本检查；过不了的**跳过并报出来**。
写库后逐题比对指纹：除这 915 道外一个字段都不许变。

用法：

    python3 脚本/落账求解结果.py --dry-run   # 只检查、列问题，不写库
    python3 脚本/落账求解结果.py             # 写库
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import conform, store  # noqa: E402

OUT_DIR = ROOT / "数据" / "题库审阅" / "求解结果"
RECORD = ROOT / "数据" / "题库审阅" / "求解落账_20261018.json"

_TAG = re.compile(r"<(状态|核对|答案|解析|备注)>\s*(.*?)(?:</\1>|\Z)", re.S)


def blocks(text: str):
    cur = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("@@Q "):
            if cur is not None:
                yield cur, "\n".join(buf)
            cur, buf = line[4:].strip(), []
        elif line.strip() == "@@END":
            if cur is not None:
                yield cur, "\n".join(buf)
            cur, buf = None, []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        yield cur, "\n".join(buf)


def collect() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(OUT_DIR.glob("结果_*.txt")):
        for key, body in blocks(f.read_text(encoding="utf-8")):
            t = {m.group(1): m.group(2).strip() for m in _TAG.finditer(body)}
            out.setdefault(key, t)
    return out


# 解析正文里三处排版坏掉（conform / KaTeX 会拦），落账时做最小订正。
# 每条是 (原文片段, 订正后片段)，必须命中一次。
FIXUPS: dict[str, list[tuple[str, str]]] = {
    # 公式里混了裸中文（conform「数学里的中文」）
    "模拟题/河南青桐鸣2026届高三上学期第二次联考#17": [
        (r"\quad对一切\ x\in(0,+\infty)\ 成立。",
         r"\quad\text{对一切 }x\in(0,+\infty)\text{ 成立}"),
    ],
    "模拟题/湖北省部分名校2026届高三上学期9月月考#11": [
        (r"$(甲,乙)$", r"$(\text{甲},\text{乙})$"),
    ],
    # `\frac` 少花括号：TeX 勉强能吞，KaTeX 直接 parse error
    "模拟题/江苏省扬州市2025-2026学年高三上学期11月期中考试（含） - 副本#18": [
        (r"\frac2\mathrm{e}", r"\frac{2}{\mathrm{e}}"),
        (r"\frac1\mathrm{e}", r"\frac{1}{\mathrm{e}}"),
    ],
}

CHECKS = [
    ("环境配对", conform.chk_env),
    ("美元符落单", conform.chk_double_dollar),
    ("定界符配对", conform.chk_delim),
    ("行内公式定界符", conform.chk_inline_delim),
    ("句末标点", conform.chk_sentence_period),
    ("数学里的中文", conform.chk_cjk_in_math),
    ("私有宏", conform.chk_private),
    ("注释残留", conform.chk_comment),
    ("列表选项", conform.chk_enum_opt),
    ("平行号 //", conform.chk_slash_parallel),
    ("竖线开闭", conform.chk_bar_pair),
    ("$$ 成对", conform.style_double_dollar),
]


def check_solution(s: str) -> list[str]:
    probs = []
    for name, fn in CHECKS:
        try:
            r = fn(s)
        except Exception as e:                       # 检查器自己崩了也要报
            r = "检查异常 %r" % e
        if r:
            probs.append("%s：%s" % (name, r))
    if s.count(r"\left") != s.count(r"\right"):
        probs.append(r"\left/\right 不配对")
    return probs


def fingerprint(qs) -> dict:
    return {q.key: hashlib.md5(json.dumps(
        [q.type, q.stem, q.answer, q.solution,
         [[o.label, o.text] for o in q.options],
         [f.id for f in (q.figures or [])]], ensure_ascii=False).encode()
    ).hexdigest() for q in qs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rows = collect()
    sel = {k: t for k, t in rows.items()
           if t.get("状态") == "ok" and t.get("核对") in ("match", "missing")}
    print(f"结果块 {len(rows)} 道；选中 ok+match/missing {len(sel)} 道"
          f"（match {sum(1 for t in sel.values() if t['核对'] == 'match')}，"
          f"missing {sum(1 for t in sel.values() if t['核对'] == 'missing')}）")
    if len(sel) != 915:
        print("✗ 数量与既定口径（915）不符，不动库")
        return 1

    bank = {q.key: q for q in store.load_all()}
    missing = [k for k in sel if k not in bank]
    if missing:
        print("✗ 这些题号不在库里，整批不写：", missing[:10])
        return 1

    todo: dict[str, str] = {}
    skipped: dict[str, list[str]] = {}
    for k, t in sel.items():
        raw = (t.get("解析") or "").strip()
        s = raw
        ok = True
        for old, new in FIXUPS.get(k, []):
            if old not in s:
                skipped[k] = ["订正锚点没找到：%r" % old]
                ok = False
                break
            s = s.replace(old, new)
        if not ok:
            continue
        if not s:
            skipped[k] = ["解析为空"]
            continue
        cur = (bank[k].solution or "").strip()
        # 幂等：库里已经是「原文」或「订正后的原文」= 上一次就是本脚本写的，
        # 允许再写一遍（这次只为补 meta）；别的非空解析一律不动。
        ours = cur in (raw, s)
        if bank[k].has_solution and not ours:
            skipped[k] = ["库里已有真解析（不覆盖）"]
            continue
        probs = check_solution(s)
        if probs:
            skipped[k] = probs
            continue
        todo[k] = s

    print(f"可落账 {len(todo)} 道；跳过 {len(skipped)} 道")
    for k, why in list(skipped.items())[:20]:
        print("  ✗", k, "｜", "；".join(why))

    before = fingerprint(bank.values())
    before_n = len(bank)
    if a.dry_run:
        print("\n[dry-run] 未写库。")
        return 0

    stamp = time.strftime("%Y-%m-%d %H:%M")

    def _do(qs):
        n = 0
        for q in qs:
            s = todo.get(q.key)
            if s is None:
                continue
            q.solution = s
            # 让 `store.diff()` 把这次改动记成**有意编辑**（界面补录），
            # 而不是"规则偷偷动了存量"；与 `exchange.collect` 同一套标记。
            q.meta["solution_source"] = "workbuddy"
            q.meta["edited_at"] = stamp
            n += 1
        print(f"  update() 内写入 {n} 道（解析 + meta）")
        return qs

    rep = store.update(_do)
    print(f"写回报告：changed={len(rep.get('changed', []))}  volumes={rep.get('volumes')}")

    after = {q.key: q for q in store.load_all()}
    if len(after) != before_n:
        print("✗ 题数变了：%d → %d" % (before_n, len(after)))
        return 1
    after_fp = fingerprint(after.values())
    changed = [k for k in before if before[k] != after_fp[k]]
    if set(changed) - set(todo):
        print("✗ 有落账名单之外的题被改了：", sorted(set(changed) - set(todo))[:5])
        return 1
    bad = [k for k in todo if after[k].solution != todo[k]]
    if bad:
        print("✗ 解析没写进去：", bad[:5])
        return 1
    untagged = [k for k in todo if after[k].meta.get("edited_at") != stamp]
    if untagged:
        print("✗ 这些题没打上编辑标记：", untagged[:5])
        return 1
    print(f"题数不变：{before_n}；内容改动 {len(changed)} 道；"
          f"{len(todo)} 道解析与编辑标记就位；其余题目一个字段都没动")

    RECORD.write_text(json.dumps({
        "date": "2026-10-18",
        "source": "数据/题库审阅/求解结果（外部模型求解）",
        "rule": "状态 ok 且 核对 match/missing → 只写解析，答案不动",
        "count": len(todo),
        "match": sorted(k for k in todo if sel[k]["核对"] == "match"),
        "missing": sorted(k for k in todo if sel[k]["核对"] == "missing"),
        "skipped": skipped,
        "fixups": {k: list(v) for k, v in FIXUPS.items()},
        "not_included": {
            "mismatch(ok)": sum(1 for t in rows.values()
                                if t.get("状态") == "ok" and t.get("核对") == "mismatch"),
            "unsure": sum(1 for t in rows.values() if t.get("状态") == "unsure"),
            "error/needs_figure": "已删（见 求解判坏删除_20261018.json）",
        },
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("记录写到：", RECORD.relative_to(ROOT))
    print("题型：", dict(Counter(after[k].type for k in todo)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
