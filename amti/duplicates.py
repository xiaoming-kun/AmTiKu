"""AmTiKu · 重复题标注（只提示，不合并）

用户口径：**界面标“重复题”即可，绝不自动合并**。
真相仍是 `题目/*.tex`；这里只读，分组结果按卷签名缓存。

分组来源（两路并集，都表示“逐字重复”）：
  1. `meta.duplicate_group`：查重 / 人工确认留下的组；
  2. `ingest.dup_fingerprint()`：题干 + 选项归一化后完全相同（答案/解析不计）。

`meta.dup_of` / `meta.similar_of` 是**相似**关系（0.80–0.99，录入判重时记下的
“和谁像”），不参与分组：它进 `similar()`，只用于详情页“相似题”提示和组卷去重。
把相似当重复，会把 4,858 道“同型题”误标成重复题（2026-11-20 实测：
5,043 条 dup_of 里指纹真正相同的只有 167 条）。

第 2 路复用 `dedup.norm_stem`，和录入时的判重是同一把尺子；它只判
“整题完全相同”，不判 0.96 的近似——近似会误伤“单调递增/递减”这种
故意设置的对照题。
"""
from __future__ import annotations

import hashlib
import threading
from collections import defaultdict

from . import ingest, store

_LOCK = threading.Lock()
_CACHE: dict = {"sig": None, "info": {}, "similar": {}, "by_key": {}}


class _UF:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        p = self.p.setdefault(x, x)
        while p != x:
            x, p = p, self.p.setdefault(p, p)
        self.p[x] = p
        return p

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _build(questions) -> dict[str, dict]:
    """逐字重复分组：duplicate_group + 题干/选项指纹。"""
    labels: dict[str, list[str]] = defaultdict(list)
    for q in questions:
        g = q.meta.get("duplicate_group")
        if g:
            labels["meta:%s" % g].append(q.key)
        try:
            fp = ingest.dup_fingerprint(q)
        except Exception:
            fp = ""
        if fp:
            labels["fp:%s" % hashlib.sha1(fp.encode("utf-8")).hexdigest()[:16]].append(q.key)

    uf = _UF()
    for keys in labels.values():
        if len(keys) < 2:
            continue
        first = keys[0]
        for k in keys[1:]:
            uf.union(first, k)

    members: dict[str, list[str]] = defaultdict(list)
    for key in list(uf.p):
        members[uf.find(key)].append(key)

    info: dict[str, dict] = {}
    for keys in members.values():
        keys = sorted(set(keys))
        if len(keys) < 2:
            continue
        gid = "dup-" + hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()[:10]
        rec = {"group": gid, "n": len(keys), "keys": keys}
        for k in keys:
            info[k] = rec
    return info


def _similar(questions) -> dict[str, list[str]]:
    """key → 相似 key 列表（不含自己）。来源 dup_of / similar_of，双向。"""
    pair: dict[str, set[str]] = defaultdict(set)
    keys = {q.key for q in questions}
    for q in questions:
        ref = q.meta.get("similar_of") or q.meta.get("dup_of")
        if not ref or ref == q.key or ref not in keys:
            continue
        pair[q.key].add(str(ref))
        pair[str(ref)].add(q.key)
    return {k: sorted(v) for k, v in pair.items() if v}


def groups() -> dict[str, dict]:
    """key → `{group, n, keys}`（逐字重复）；按卷签名缓存。只读。"""
    sig = store.volume_signature()
    if _CACHE["sig"] == sig:
        return _CACHE["info"]
    with _LOCK:
        if _CACHE["sig"] != sig:
            qs = store.load_cached()
            _CACHE.update({"sig": sig, "info": _build(qs),
                           "similar": _similar(qs),
                           "by_key": {q.key: q for q in qs}})
    return _CACHE["info"]


def info(key: str) -> dict | None:
    return groups().get(key)


def members(key: str) -> list:
    """同组题目对象（含自己）；没有组返回 []。直接复用 groups() 已加载的对象。"""
    rec = info(key)
    if not rec:
        return []
    by = _CACHE.get("by_key") or {}
    return [by[k] for k in rec["keys"] if k in by]


def similar(key: str) -> list:
    """相似（非逐字重复）的题目对象；没有返回 []。"""
    groups()
    ks = (_CACHE.get("similar") or {}).get(key) or []
    by = _CACHE.get("by_key") or {}
    return [by[k] for k in ks if k in by]


def clear() -> None:
    _CACHE.update({"sig": None, "info": {}, "similar": {}, "by_key": {}})


def status() -> dict:
    g = groups()
    sim = _CACHE.get("similar") or {}
    return {"keys_in_groups": len(g),
            "groups": len({v["group"] for v in g.values()}),
            "keys_with_similar": len(sim)}


def _selftest() -> int:
    from .schema import Option, Question

    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + name + (("  " + extra) if extra else ""))
        if not cond:
            fails += 1

    def mk(key, stem, opts=("1", "2"), **meta):
        q = Question(key=key, type="single_choice", stem=stem,
                     options=[Option("A", opts[0]), Option("B", opts[1])],
                     answer="A", solution="解", meta=meta)
        return q

    a = mk("a", "已知 $a>0$，求最小值。")
    b = mk("b", "已知 $a>0$，求最小值。")
    c = mk("c", "已知 $a<0$，求最大值。")
    d = mk("d", "另一道题。", duplicate_group="g1")
    e = mk("e", "再一道题。", duplicate_group="g1")
    f = mk("f", "目标题。")
    g = mk("g", "指向目标。", dup_of="f")
    h = mk("h", "另一处相似。", similar_of="g", similar_score=0.91)
    qs = [a, b, c, d, e, f, g, h]
    info = _build(qs)
    sim = _similar(qs)
    check("同指纹成组", a.key in info and info[a.key]["n"] == 2,
          str(info.get(a.key)))
    check("不同题不成组", c.key not in info)
    check("meta group 成组", d.key in info and e.key in info)
    check("dup_of 不进重复组", f.key not in info and g.key not in info)
    check("similar 双向可查", sim.get("f") == ["g"] and sim.get("g") == ["f", "h"],
          str(sim.get("g")))
    check("similar_of 也认", sim.get("h") == ["g"], str(sim.get("h")))
    check("组 id 稳定", info[a.key]["group"] == info[b.key]["group"])
    check("只有两组（相似不算组）",
          len({v["group"] for v in info.values()}) == 2,
          str(sorted({v["group"] for v in info.values()})))
    print("duplicates 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
