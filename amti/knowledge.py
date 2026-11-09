"""AmTiKu · 知识点库

题目的**难度**和**考点名称**都从这里派生，不单独存：

    题目 → 主考点 id → 知识点库 → 星级 / 难度 / 名称

为什么不把难度存在题目上：旧库的 `difficulty` 字段 20,706 道里 **16,655 道是空的**，
填了的还格式不一（`中档题` / `中` / `C`）。而考点库 153 个考点的星级和难度
**是齐全的**——从主考点派生，覆盖率立刻从 20% 提到 100%（有标签的题）。

**两个来源，各管各的学段，名字都不复制第二份**：

    知识点.json   高中考点（数字 id）：名称、星级、难度、五要素
    知识地图.json 小学/初中知识点（`x`／`c` 前缀 id）：名称、册、章

小学/初中的题目一样要标签，所以 `get()` 两处都查；`all_points()` 默认仍只
返回高中考点——筛选面板、AI 打标提示词这些按学段走的调用方不受影响，
要小初的调用方显式传 `stage="junior"`／`"k12"`。
"""
from __future__ import annotations

from .paths import ROOT
import json
import re
from functools import lru_cache
from pathlib import Path

KB_PATH = ROOT / "知识点.json"
MAP_PATH = ROOT / "知识地图.json"

# 星级 → 难度（考点库里两个字段都有，但偶尔缺一个，互相兜底）
STARS_DIFFICULTY = {1: "简单题", 2: "中档题", 3: "难题", 4: "难题"}

# 索引缓存。键取「知识点库文件的 mtime+size」——改了库自动失效。
_IDX: dict = {"key": None, "v": {}}
# 小学/初中知识点索引（来自 知识地图.json），与高中分开缓存。
_SMALL: dict = {"key": None, "v": {}}


def signature() -> tuple:
    """知识点库的缓存签名（mtime+size）。

    给别的模块做**联合缓存**用：知识地图把考点名补进来，如果只按自己的文件
    mtime 缓存，改了 `知识点.json` 之后页面会一直显示旧标题。

    两个文件都进签名：小初的考点名只在 `知识地图.json`，只盯高中那份的话，
    改了地图里的知识点名，页面会一直显示旧的。
    """
    out: list[int] = []
    for p in (KB_PATH, MAP_PATH):
        try:
            st = p.stat()
            out += [st.st_mtime_ns, st.st_size]
        except OSError:
            out += [0, 0]
    return tuple(out)


def _index() -> dict[str, dict]:
    r"""高中考点索引（`知识点.json`）。

    ⚠️ **必须缓存**：`title_of()` / `difficulty_of()` 内部都调它，
    而一屏题目就要查上千次。老写法每次都重新读+解析一遍 JSON，
    `/api/facets` 因此要 0.6 秒。
    用「文件 mtime+size」做缓存键——改了知识点库会自动失效。
    """
    sig = signature()
    if not KB_PATH.exists():
        return {}
    if _IDX["key"] == sig:
        return _IDX["v"]

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
                    # 五要素（核心概念/核心公式/常用方法/常考题型/易错点）——
                    # 按考点印讲解时要用，索引里顺手带上，
                    # 免得别处再读一遍 知识点.json。
                    "fields": p.get("fields") or {},
                }
    _IDX["key"] = sig
    _IDX["v"] = out
    return out


def _small_index() -> dict[str, dict]:
    r"""小学/初中知识点索引（`知识地图.json` 的 `primary` / `junior` 两段）。

    这两段**只在地图里定义**（高中节点在地图里只存 id、名字现取），所以这里
    也不往 `知识点.json` 抄一份。字段与高中条目对齐，`topic` = 册名、
    `section` = 章名——前端按「册 → 章 → 知识点」展开，不用另写一套。
    """
    sig = signature()
    if _SMALL["key"] == sig:
        return _SMALL["v"]
    out: dict[str, dict] = {}
    try:
        raw = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    for st in raw.get("stages") or []:
        skey = str(st.get("key") or "")
        if skey not in ("primary", "junior"):
            continue
        for b in st.get("books") or []:
            book = str(b.get("name") or "")
            for c in b.get("chapters") or []:
                chapter = str(c.get("title") or "")
                for p in c.get("points") or []:
                    pid = str(p.get("id") or "").strip()
                    if not pid:
                        continue
                    # 小初的知识点没有星级/难度（教材只给位置和一句话说明）；
                    # 题目的难度由录入时逐题给定，存在题目自己的 meta 上。
                    out[pid] = {
                        "id": pid,
                        "title": p.get("title", ""),
                        "stars": int(p.get("stars") or 0),
                        "difficulty": p.get("difficulty") or "",
                        "topic": book,
                        "section": chapter,
                        "fields": {},
                        "stage": skey,
                    }
    _SMALL["key"] = sig
    _SMALL["v"] = out
    return out


def _strip_tail(t: str) -> str:
    r"""去掉 `（考点1：…）` 与 `·/17 ★★` 这类统计尾巴。"""
    t = re.sub(r"（考点[^）]*）", "", t or "")
    t = re.sub(r"\s*·/\S*", "", t)
    t = re.sub(r"\s*★+\s*$", "", t)
    return t.strip()


def get(point_id: str) -> dict:
    """按 id 取考点：先高中，再小学/初中。都不是就返回空 dict。"""
    pid = (point_id or "").strip()
    return _index().get(pid) or _small_index().get(pid) or {}


def title_of(point_id: str) -> str:
    """考点名。考点库里的 title 带 `（考点1：…）` 这类尾巴，去掉更好读。"""
    return _strip_tail(get(point_id).get("title", ""))


def stars_of(point_id: str) -> int:
    return get(point_id).get("stars", 0)


def fields_of(point_id: str) -> dict:
    """考点的五要素 `{核心概念: [...], 常考题型: [...], …}`，没有就返回空。"""
    return get(point_id).get("fields", {})


def difficulty_of(point_id: str) -> str:
    return get(point_id).get("difficulty", "")


def all_points(stage: str = "senior") -> list[dict]:
    """考点表。`stage`：

    * `senior`（默认）——只看 `知识点.json`，与历史调用口径一致
    * `junior` / `primary`——只看地图里对应学段
    * `k12`——三段全给
    """
    s = (stage or "senior").strip()
    if s == "senior":
        return list(_index().values())
    small = list(_small_index().values())
    if s == "k12":
        return list(_index().values()) + small
    return [v for v in small if v.get("stage") == s]


if __name__ == "__main__":
    from collections import Counter
    for stage in ("senior", "junior"):
        pts = all_points(stage)
        print(f"{stage} 考点 {len(pts)} 个")
        if not pts:
            continue
        print("星级:", dict(Counter(p["stars"] for p in pts)))
        print("难度:", dict(Counter(p["difficulty"] for p in pts)))
        for p in pts[:3]:
            print(f"  {p['id']:8} ★{p['stars']} {p['difficulty']:4} {p['title'][:44]}")
