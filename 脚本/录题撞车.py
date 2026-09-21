#!/usr/bin/env python3
r"""录题撞车预检：拿卷面标题（试卷第 1 页那行）去比库里已有的模拟卷。

用法：python3 脚本/录题撞车.py "某市2026届六校联合体高三8月学情调研"
判据：去掉数字/年月/标点后用**字符二元组重合度**打分，≥0.55 视为疑似同卷，交人工/我确认。
比按文件名匹配可靠——卷名里「2025年8月」的位置各家不一样，纯字符串包含会漏。
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BK = json.loads((ROOT / "数据/录题/库内模拟卷清单.json").read_text(encoding="utf-8"))


def norm(s):
    s = re.sub(r"[0-9]+", "", s or "")
    s = re.sub(r"[年月日]", "", s)
    return re.sub(r"[^\w一-鿿]", "", s)


def bg(s):
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def main(title):
    tb = bg(title)
    if not tb:
        return print("标题太短，无法比对")
    scored = []
    for lab, info in BK.items():
        cands = [lab] + info.get("卷面标题", [])
        best = max((len(tb & bg(c)) / max(1, min(len(tb), len(bg(c)))) for c in cands if bg(c)), default=0)
        if best:
            scored.append((best, lab, info["题数"]))
    scored.sort(reverse=True)
    print("比对标题:", title)
    for s, lab, n in scored[:6]:
        flag = "⚠️ 疑似同卷" if s >= 0.55 else "  "
        print("  %s %.2f  %s（%d 题）" % (flag, s, lab, n))
    if not scored or scored[0][0] < 0.55:
        print("  → 没有 ≥0.55 的命中，按新卷处理")


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]))
