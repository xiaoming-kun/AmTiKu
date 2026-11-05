#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""答案栏 / 解析版面标记收口（2026-11-03）。

两件事，都只改写法、不改数学内容：

1. **解答题答案栏统一成「见解析」**
   规范要求解答题答案栏写「见解析」，但库里有 36 道写成了
   “（1）…；（2）…”的答案摘要。摘要本身有用，不能丢：
   把它挪到解析开头（`答案：…`），答案栏写「见解析」，同时留
   `meta.answer_summary` 供机器读。

2. **去掉解析开头从 PDF 带进来的版面标记**
   只去 `【解析】/【详解】/【解答】/【答案】` 这类**纯标记**，且只在
   解析最开头（或紧跟“答案：…”那行）。`【分析】/【点睛】/【法一】`
   是解题结构，保留。

用法：
    python3 脚本/答案栏与解析标记_20261103.py          # 干跑
    python3 脚本/答案栏与解析标记_20261103.py --apply  # 落盘
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import conform, store  # noqa: E402
from amti.latex_ir import fillin_answers, paren_answers  # noqa: E402

# 只在“开头”或“答案：… 之后”出现的纯标记
_LEAD = re.compile(r"^\s*(?:【(?:解析|详解|解答|答案)】\s*)+")
_AFTER_ANS = re.compile(r"^(答案[:：][^\n]*\n+)\s*(?:【(?:解析|详解|解答|答案)】\s*)+")


def fix(qs, stamp: str):
    notes = []
    touched = []
    for q in qs:
        if q.type == "detailed_answer":
            ans = (q.answer or "").strip()
            # 题干里本身有 `\fillin`/`\paren` 的（如统计表格填空），
            # 答案是从作答位读出来的，不能改成「见解析」——改了会在
            # 回读时被作答位重新覆盖，roundtrip 直接失败。
            has_blank = bool(fillin_answers(q.stem) or paren_answers(q.stem))
            if ans and ans not in ("见解析", "见解答") and not has_blank:
                sol = q.solution or ""
                if not re.match(r"^\s*答案[:：]", sol):
                    sol = "答案：%s\n\n%s" % (ans, sol.lstrip())
                q.solution = sol
                q.answer = "见解析"
                q.meta["answer_summary"] = ans
                q.meta["fixed_at"] = stamp
                notes.append("%s：答案摘要移入解析，答案栏改「见解析」" % q.key)
                touched.append(q)

        sol = q.solution or ""
        new = _LEAD.sub("", sol, count=1)
        new = _AFTER_ANS.sub(r"\1", new, count=1)
        if new != sol:
            q.solution = new
            q.meta["fixed_at"] = stamp
            notes.append("%s：去掉解析开头的版面标记" % q.key)
            if q not in touched:
                touched.append(q)
    return notes, touched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    qs, sig = store.load_for_update()
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    notes, touched = fix(qs, stamp)
    bad = [(q.key, p) for q in touched for p in q.problems()]
    if bad:
        for k, p in bad:
            print("✗", k, p)
        raise SystemExit("结构校验不过，未写回")
    viol = conform.run(touched)
    if viol:
        for v in viol:
            print("✗", v)
        raise SystemExit("规范审查不过，未写回")
    print("将改动 %d 道：" % len(touched))
    for n in notes:
        print("  · " + n)
    if not a.apply:
        print("\n干跑结束；加 --apply 落盘。")
        return 0
    rep = store.rewrite_all(qs, based_on=sig)
    print("已写回：%d 卷 / %d 道" % (rep["volumes"], rep["count"]))
    out = ROOT / "变更记录" / ("%s_答案栏与解析标记.md"
                              % _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.write_text("# 答案栏与解析标记收口\n\n- 时间：%s\n- 改动：%d 道\n\n%s\n"
                   % (stamp, len(touched), "\n".join("- " + n for n in notes)),
                   encoding="utf-8")
    print("变更记录：" + str(out.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
