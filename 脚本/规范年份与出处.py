"""规范年份与出处（评估报告建议 #6 的可机械执行部分）。

做两件事：
1. `source_label` 有、`source_no` 空的题，按 key 末尾的 `#N` 补题号；
   补不到（key 不是 `…#N` 形状）的保持原样，单独计数。
2. `source_label`/key 里写「2027届」而 `meta.year` 不是 2027 的题，年份改 2027。
   无 `source_label` 的（`手工录入/录入#3`、`#4`，year 也缺）不动——需要人判断。

只改 meta（标签），不动正文：content_hash 不变，`amti.py diff` 的内容变化数不应变化。
每条改动写 `变更记录/<ts>_规范年份与出处.md`。

用法：
    python3 脚本/规范年份与出处.py            # 只统计
    python3 脚本/规范年份与出处.py --apply    # 真写库
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amti import store  # noqa: E402
from amti.audit import CHANGE_DIR  # noqa: E402

NO_RE = re.compile(r"#(\d+)$")


def _wanted(q) -> dict:
    """返回本题要改的 meta 字段（空 dict = 不改）。"""
    m = q.meta
    out: dict = {}
    lab = str(m.get("source_label") or "")
    sn = m.get("source_no")
    if lab and sn in (None, ""):
        hit = NO_RE.search(q.key)
        if hit:
            out["source_no"] = int(hit.group(1))
    if "2027届" in (lab + q.key) and m.get("year") != 2027:
        out["year"] = 2027
    return out


def main() -> int:
    apply_ = "--apply" in sys.argv[1:]
    t0 = time.time()
    qs = store.load_all()
    plan = []
    skipped_no_key = 0
    for q in qs:
        want = _wanted(q)
        if not want:
            continue
        if "source_no" in want:
            pass
        elif not q.meta.get("source_label"):
            skipped_no_key += 1
        plan.append((q, want))
    n_no = sum(1 for _q, w in plan if "source_no" in w)
    n_year = sum(1 for _q, w in plan if "year" in w)
    print("待补 source_no：%d 道；待改 year→2027：%d 道；合计 %d 道"
          % (n_no, n_year, len(plan)))
    print("无 source_label 的题（不动）：%d 道" % skipped_no_key)
    print("读库 %.1fs" % (time.time() - t0))
    if not apply_:
        print("写库：否（--apply 才写）")
        return 0

    def _fn(all_qs):
        by = {q.key: q for q in all_qs}
        changed = 0
        for q, want in plan:
            tgt = by.get(q.key)
            if tgt is None:
                continue
            for k, v in want.items():
                if tgt.meta.get(k) != v:
                    tgt.meta[k] = v
                    changed += 1
        return all_qs

    t1 = time.time()
    res = store.update(_fn)
    print("写库完成：%s（%.1fs）" % (res, time.time() - t1))

    CHANGE_DIR.mkdir(parents=True, exist_ok=True)
    led = CHANGE_DIR / ("%s_规范年份与出处.md" % time.strftime("%Y%m%d_%H%M%S"))
    lines = ["# 规范年份与出处", "",
             "- 时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "- 补 source_no：%d 道" % n_no,
             "- year→2027：%d 道" % n_year, "",
             "| 题目 | 改动 |", "|---|---|"]
    for q, want in plan:
        lines.append("| `%s` | %s |"
                     % (q.key, "、".join("%s=%s" % (k, v) for k, v in want.items())))
    led.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("台账：%s" % led)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
