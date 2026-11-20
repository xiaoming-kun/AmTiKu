"""规模基线：让"这些操作还能秒回"变成可验收的事实。

## 为什么加这条（问题⑥）

性能假设原来只写在注释里——「scan_meta 约 0.7 秒」「首次建相似索引 0.4 秒」
「列表主键读 2ms」。这类注释在库长到 10 万道之前都没错，然后某天某个索引
没建好，列表从 40ms 变成 4s，**除了用户觉得卡，没有任何信号**。

这里钉住四条关键路径的**上限**：

    scan_meta         全库元数据扫描（按出处/年份筛的候选池）
    readmodel.query   列表分页（派生 SQLite；没建好会回退全量 Python）
    iter_questions    全库解析（迁移、校验、快照的地基）
    recall            检索召回（中文 FTS；公式召回另算）

阈值取实测量级的 4–8 倍，**只抓数量级退化**，不抓 20% 抖动：
CI/笔记本快慢差一倍是常态，但"索引没了"是 100 倍。
数据量也一起打印——量变导致的时间变长能一眼看出来。

跑法：

    python3 测试/性能基线.py          # 超阈值 → 退出码 1
    python3 测试/性能基线.py -v       # 顺带打印每个阶段的分项
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import readmodel, recall, store              # noqa: E402

#: 秒。32k 题实测：scan_meta ≈ 0.7、readmodel ≈ 0.02、iter_questions ≈ 2、recall ≈ 0.1。
LIMITS = {
    "scan_meta": 5.0,
    "readmodel.query": 2.0,
    "iter_questions": 20.0,
    "recall": 5.0,
}


def _time(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def main() -> int:
    verbose = "-v" in sys.argv
    meta = store.scan_meta()
    n = len(meta)
    print("题库 %d 道   卷 %d 个" % (n, len(store.existing_volumes())))
    if n == 0:
        print("跳过：还没有题目")
        return 0

    rows: list[tuple[str, float, float, str]] = []

    def case(name: str, fn, note: str = "") -> None:
        dt = _time(fn)
        rows.append((name, dt, LIMITS[name], note))

    case("scan_meta", lambda: store.scan_meta(), "元数据扫描")
    # 列表分页：取第一页 20 条；返回 None 说明 SQLite 没建好、走了 Python 回退
    got = readmodel.query(limit=20, offset=0, sort="")
    case("readmodel.query", lambda: readmodel.query(limit=20, offset=0, sort=""),
         "已建" if got is not None else "**未建/异常 → 回退 Python**")
    case("iter_questions", lambda: sum(1 for _ in store.iter_questions()), "全库解析")
    hit = recall.recall("三角形")
    n_hit = len(hit.get("keys") or [])
    case("recall", lambda: recall.recall("三角形"),
         "中文 FTS，命中 %d 条" % n_hit)

    bad = 0
    for name, dt, limit, note in rows:
        flag = "✗" if dt > limit else "✓"
        if dt > limit:
            bad += 1
        print("  %s %-16s %7.2fs / %5.1fs  %s"
              % (flag, name, dt, limit, note))
        if verbose:
            print("      （本题库 %d 道，单题约 %.2fms）" % (n, dt * 1000 / max(n, 1)))

    if bad:
        print("\n✗ 性能基线未通过：%d 条路径超阈值" % bad)
        print("  先看是不是索引没建：python3 -m amti.readmodel build / "
              "python3 -m amti.content_store build")
        return 1
    print("\n性能基线通过（%d 条路径都在数量级内）" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
