"""统一重复题口径（评估报告建议 #1）。

口径（2026-11-20 定）：**逐字重复才叫「重复题」**。

* `meta.duplicate_group`：逐字重复（题干 + 选项指纹完全相同）的组号，
  界面徽章 / 查重面板的 `items` 只认它；
* `meta.dup_of` / `meta.similar_of`：**相似**（0.80–0.99），只做“同型/疑似”提示，
  不参与分组、不标重复徽章。

本脚本做两件事（幂等）：
1. 给现有指纹重复组补 `duplicate_group = "fp-" + sha1(指纹)[:10]`（318 道）；
2. 清掉指向不存在 key 的 `dup_of` / `similar_of` 悬空引用（18 条）。

用法：
    python3 脚本/统一重复题口径.py            # 只统计，不写库
    python3 脚本/统一重复题口径.py --apply    # 写库（整库重写，约 1 分钟）
"""
from __future__ import annotations

import datetime
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amti import ingest, store  # noqa: E402
from amti.audit import CHANGE_DIR  # noqa: E402

KEEP = ("dup_of", "similar_of")


def _fp_buckets(qs):
    buckets: dict[str, list[str]] = defaultdict(list)
    for q in qs:
        try:
            fp = ingest.dup_fingerprint(q)
        except Exception:
            fp = ""
        if fp:
            buckets[hashlib.sha1(fp.encode("utf-8")).hexdigest()[:16]].append(q.key)
    return {h: sorted(v) for h, v in buckets.items() if len(v) > 1}


def main() -> int:
    apply_ = "--apply" in sys.argv[1:]

    def _do(qs):
        assigned: list[str] = []
        cleared: list[tuple[str, str]] = []
        done: list[str] = list(assigned)
        by = {q.key: q for q in qs}

        for h, keys in _fp_buckets(qs).items():
            gid = "fp-" + h[:10]
            for k in keys:
                q = by.get(k)
                if q is None:
                    continue
                if not isinstance(q.meta, dict):
                    q.meta = {}
                if q.meta.get("duplicate_group") != gid:
                    q.meta["duplicate_group"] = gid
                    assigned.append(k)

        for q in qs:
            if not isinstance(q.meta, dict):
                continue
            for f in KEEP:
                t = q.meta.get(f)
                if t and t not in by:
                    q.meta.pop(f, None)
                    cleared.append((q.key, f))
                    if q.key not in done:
                        done.append(q.key)
        for k in assigned:
            if k not in done:
                done.append(k)
        report = {"assigned": list(assigned), "cleared": cleared}
        _do.report = report  # type: ignore[attr-defined]
        return qs

    r = store.update(_do, dry_run=not apply_)
    rep = getattr(_do, "report", {"assigned": [], "cleared": []})
    print("指纹重复组补 duplicate_group：%d 道" % len(rep["assigned"]))
    print("悬空引用清理：%d 条" % len(rep["cleared"]))
    for k, f in rep["cleared"][:10]:
        print("  - %s  %s" % (k, f))
    print("写库：%s  %s" % ("是" if apply_ else "否（--apply 才写）", r))

    if apply_ and (rep["assigned"] or rep["cleared"]):
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        f = CHANGE_DIR / ("%s_统一重复题口径.md" % ts)
        lines = ["# 统一重复题口径", "",
                 "- 时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "- 规则：逐字重复（题干+选项指纹相同）→ `duplicate_group`；"
                 "相似（0.80–0.99）→ `dup_of`/`similar_of`，不标重复徽章。",
                 "- 补 `duplicate_group`：%d 道" % len(rep["assigned"]),
                 "- 清悬空引用：%d 条" % len(rep["cleared"]), ""]
        lines += ["- `%s`" % k for k in rep["assigned"][:400]]
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("台账：%s" % f.relative_to(store.ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
