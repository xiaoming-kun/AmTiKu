"""AmTiKu · 重复题标注（只提示，不合并）

用户口径：**界面标“疑似重复”即可，绝不自动合并**。
真相仍是 `题目/*.tex`；这里只读，分组结果按卷签名缓存。

分组来源（三路并集）：
  1. `meta.duplicate_group`：之前查重/人工确认留下的组；
  2. `meta.dup_of`：指向同组代表题；
  3. `ingest.dup_fingerprint()`：题干 + 选项归一化后完全相同（答案/解析不计）。

第 3 路复用 `dedup.norm_stem`，和录入时的判重是同一把尺子；它只判
“整题完全相同”，不判 0.96 的近似——近似会误伤“单调递增/递减”这种
故意设置的对照题。疑似但非完全相同的题，仍由 `dedup.DedupIndex` 在
录入/查重工具里处理，不进这个全局标注。
"""
from __future__ import annotations

import hashlib
import threading
from collections import defaultdict

from . import ingest, store

_LOCK = threading.Lock()
_CACHE: dict = {"sig": None, "info": {}, "by_key": {}}


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
    labels: dict[str, list[str]] = defaultdict(list)
    for q in questions:
        g = q.meta.get("duplicate_group")
        if g:
            labels["meta:%s" % g].append(q.key)
        of = q.meta.get("dup_of")
        if of:
            labels["of:%s" % of].append(q.key)
            labels["of:%s" % of].append(str(of))
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


def groups() -> dict[str, dict]:
    """key → `{group, n, keys}`；按卷签名缓存。只读。"""
    sig = store.volume_signature()
    if _CACHE["sig"] == sig:
        return _CACHE["info"]
    with _LOCK:
        if _CACHE["sig"] != sig:
            qs = store.load_cached()
            _CACHE.update({"sig": sig, "info": _build(qs),
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


def clear() -> None:
    _CACHE.update({"sig": None, "info": {}, "by_key": {}})


def status() -> dict:
    g = groups()
    return {"keys_in_groups": len(g),
            "groups": len({v["group"] for v in g.values()})}


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
    info = _build([a, b, c, d, e, f, g])
    check("同指纹成组", a.key in info and info[a.key]["n"] == 2,
          str(info.get(a.key)))
    check("不同题不成组", c.key not in info)
    check("meta group 成组", d.key in info and e.key in info)
    check("dup_of 把目标也带进来",
          f.key in info and g.key in info and info[f.key]["n"] == 2)
    check("组 id 稳定", info[a.key]["group"] == info[b.key]["group"])
    print("duplicates 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
