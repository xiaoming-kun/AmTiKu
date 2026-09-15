"""AmTiKu · 知识点库

题目的**难度**和**考点名称**都从这里派生，不单独存：

    题目 → 主考点 id → 知识点库 → 星级 / 难度 / 名称

为什么不把难度存在题目上：旧库的 `difficulty` 字段 20,706 道里 **16,655 道是空的**，
填了的还格式不一（`中档题` / `中` / `C`）。而考点库 153 个考点的星级和难度
**是齐全的**——从主考点派生，覆盖率立刻从 20% 提到 100%（有标签的题）。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

KB_PATH = Path(__file__).resolve().parent.parent / "知识点.json"

# 星级 → 难度（考点库里两个字段都有，但偶尔缺一个，互相兜底）
STARS_DIFFICULTY = {1: "简单题", 2: "中档题", 3: "难题", 4: "难题"}


# 索引缓存。键取「知识点库文件的 mtime+size」——改了库自动失效。
_IDX: dict = {"key": None, "v": {}}


def _index() -> dict[str, dict]:
    r"""知识点库索引。

    ⚠️ **必须缓存**：`title_of()` / `difficulty_of()` 内部都调它，
    而一屏题目就要查上千次。老写法每次都重新读+解析一遍 JSON，
    `/api/facets` 因此要 0.6 秒。
    用「文件 mtime+size」做缓存键——改了知识点库会自动失效。
    """
    try:
        st = KB_PATH.stat()
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _IDX["key"] == sig:
        return _IDX["v"]

    if not KB_PATH.exists():
        return {}
    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for topic in kb.get("topics", []):
        for sec in topic.get("sections", []):
            # 小类名也要洗：原始 title 是
            # 「1 不等式的性质（考点1：运用性质比较大小）  ·/17 ★」这种，
            # 直接显示在侧栏里又长又吵。
            sec_name = _strip_tail(sec.get("title", ""))
            for p in sec.get("points", []):
                pid = p.get("id")
                if not pid:
                    continue
                stars = int(p.get("stars") or 0)
                out[pid] = {
                    "id": pid,
                    "title": p.get("title", ""),
                    "stars": stars,
                    "difficulty": p.get("difficulty") or STARS_DIFFICULTY.get(stars, ""),
                    "topic": topic.get("title", ""),
                    "section": sec_name,
                }
    _IDX["key"] = sig
    _IDX["v"] = out
    return out


def _strip_tail(t: str) -> str:
    r"""去掉 `（考点1：…）` 与 `·/17 ★★` 这类统计尾巴。"""
    t = re.sub(r"（考点[^）]*）", "", t or "")
    t = re.sub(r"\s*·/\S*", "", t)
    t = re.sub(r"\s*★+\s*$", "", t)
    return t.strip()


def get(point_id: str) -> dict:
    return _index().get((point_id or "").strip(), {})


def title_of(point_id: str) -> str:
    """考点名。考点库里的 title 带 `（考点1：…）` 这类尾巴，去掉更好读。"""
    return _strip_tail(get(point_id).get("title", ""))


def stars_of(point_id: str) -> int:
    return get(point_id).get("stars", 0)


def difficulty_of(point_id: str) -> str:
    return get(point_id).get("difficulty", "")


def all_points() -> list[dict]:
    return list(_index().values())


if __name__ == "__main__":
    from collections import Counter
    pts = all_points()
    print(f"考点 {len(pts)} 个")
    print("星级:", dict(Counter(p["stars"] for p in pts)))
    print("难度:", dict(Counter(p["difficulty"] for p in pts)))
    for p in pts[:3]:
        print(f"  {p['id']:8} ★{p['stars']} {p['difficulty']:4} {p['title'][:44]}")
