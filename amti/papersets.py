r"""AmTiKu · 套卷（原卷）视图

一道题进库时带着 `meta.source_label`（「2026年新高考I卷」）和 `meta.source_no`
（第几题）。这些字段本来是为了印卷面出处，但它们合起来就是**一份完整的原卷**——
老师最常问的恰恰是「把 2026 新高考 I 卷整份拿出来看看」。

所以这里不新建数据，只做**派生索引**：

    source_label → 这一卷的 { 题号顺序, 题数, 缺答案/缺解析, 学段, 年份 }

真相仍是 `题目/*.tex` 的 meta；删一道题、改一次 label，下一次数就跟着变。
按卷签名缓存（题库没变就不重算）。

⚠️ 别把 `试卷/存档.json` 当成套卷：那是**我导出的卷子**。套卷是**外来的原卷**。
两者名字像，来源完全不同——混在一起，用户会以为自己的卷子被系统改过。
"""
from __future__ import annotations

import re
import threading

from amti import knowledge_map
from amti import store
from amti.schema import QTYPE_LABEL

_CACHE: dict = {"sig": None, "items": [], "index": {}}
_LOCK = threading.Lock()


def _num(v) -> int:
    """题号转整数：`"12"` / `"12."` / `"（12）"` 都认；认不出排到最后。"""
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else 10 ** 6


def _label_of(q) -> str:
    """这份题属于哪一卷。`source_label` 优先，其次 `book/region`。"""
    m = q.meta or {}
    lab = str(m.get("source_label") or "").strip()
    if lab:
        return lab
    book, region = str(m.get("book") or ""), str(m.get("region") or "")
    if region:
        return f"{book}/{region}" if book else region
    return ""


def _build() -> list[dict]:
    """扫一遍题库，摊成套卷列表。**不改缓存**——签名由 `_snapshot` 复核。"""
    stage_map = knowledge_map.stage_index()
    groups: dict[str, dict] = {}
    for seq, q in enumerate(store.load_cached(), start=1):
        lab = _label_of(q)
        if not lab:
            continue          # 没出处/没卷名的题不成套，不进这个视图
        m = q.meta or {}
        g = groups.get(lab)
        if g is None:
            stage = next((stage_map[p] for p in (q.points or ()) if p in stage_map),
                         "senior")
            g = groups[lab] = {
                "id": lab, "title": lab,
                "year": int(m.get("year") or 0),
                "region": str(m.get("region") or ""),
                "book": str(m.get("book") or ""),
                "stage": stage,
                "rows": [],
                "answers": 0, "solutions": 0, "figures": 0,
                "partial": False,
            }
        g["rows"].append((_num(m.get("source_no")), seq, q))
        g["answers"] += 1 if q.answer.strip() else 0
        g["solutions"] += 1 if q.has_solution else 0
        g["figures"] += 1 if q.figures else 0
        if m.get("paper_complete") is False:
            g["partial"] = True

    items = []
    for g in groups.values():
        rows = sorted(g.pop("rows"), key=lambda r: (r[0], r[1]))
        keys = [r[2].key for r in rows]
        types: dict[str, int] = {}
        for _, _, q in rows:
            label = QTYPE_LABEL.get(q.type, q.type)
            types[label] = types.get(label, 0) + 1
        items.append({**g, "n": len(keys), "keys": keys, "types": types})
    # 新的在前：年份大的优先，同年按题量多的优先（更像正式整卷）
    items.sort(key=lambda x: (-x["year"], -x["n"], x["title"]))
    return items


def _snapshot() -> tuple[list[dict], dict[str, dict]]:
    r"""当前的 `(items, index)`。缓存按**卷签名**失效。

    录入在另一个标签页/进程里写库时，签名可能在构建中途变化。把**新签名**
    配**旧数据**存进缓存，会让套卷一直少那几道新题——直到下一次写库。
    所以签名取两次：前后一致才缓存；不一致时**本次照用新数据，只是不落缓存**，
    下一次调用再重建。
    """
    sig = store.volume_signature()
    if _CACHE["sig"] == sig:
        return _CACHE["items"], _CACHE["index"]
    with _LOCK:
        sig = store.volume_signature()
        if _CACHE["sig"] == sig:
            return _CACHE["items"], _CACHE["index"]
        items = _build()
        index = {x["id"]: x for x in items}
        if store.volume_signature() == sig:
            _CACHE.update({"sig": sig, "items": items, "index": index})
        return items, index


def index(*, q: str = "", stage: str = "", year: str = "") -> list[dict]:
    """套卷列表（不含题号明细之外的正文）。"""
    items_all, _ = _snapshot()
    kw = (q or "").strip().lower()
    stages = {x.strip() for x in (stage or "").split(",") if x.strip()}
    years = {x.strip() for x in (year or "").split(",") if x.strip()}
    out = []
    for it in items_all:
        if stages and it["stage"] not in stages:
            continue
        if years and str(it["year"]) not in years:
            continue
        if kw and kw not in it["title"].lower():
            continue
        out.append({k: it[k] for k in
                    ("id", "title", "year", "region", "book", "stage",
                     "n", "answers", "solutions", "figures", "partial", "types")})
    return out


def get(sid: str) -> dict | None:
    """一份套卷的明细：题号顺序 + 每题该有的元信息。"""
    _, index = _snapshot()
    it = index.get(sid)
    if it is None:
        return None
    return dict(it)


def years() -> list[int]:
    items, _ = _snapshot()
    return sorted({x["year"] for x in items if x["year"]}, reverse=True)


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + name + (("  " + extra) if extra else ""))
        if not cond:
            fails += 1

    print("papersets 自检")
    check("题号认字符串与全角括号",
          _num("12") == 12 and _num("（12）") == 12 and _num("12.") == 12)
    check("认不出的大数排最后", _num("") == 10 ** 6)

    # 造两道同卷题，验证分组/排序/计数（不动真库：monkeypatch 缓存）
    from amti.schema import Option, Question
    qs = [
        Question(key="a#2", type="single_choice", stem="s2", answer="B",
                 solution="解析二", options=[Option("A", "1"), Option("B", "2")],
                 meta={"source_label": "测试卷", "source_no": "2", "year": 2026}),
        Question(key="a#1", type="fill_in_blank", stem="s1", answer="",
                 solution="", meta={"source_label": "测试卷", "source_no": "1",
                                    "year": 2026}),
    ]
    old_load, old_sig = store.load_cached, store.volume_signature
    store.load_cached = lambda: qs
    store.volume_signature = lambda: ("selftest",)
    try:
        _CACHE.update({"sig": None, "items": [], "index": {}})
        it = get("测试卷")
        check("按卷名分组", it is not None and it["n"] == 2, repr(it and it["n"]))
        check("题号升序", it["keys"] == ["a#1", "a#2"], str(it["keys"]))
        check("缺答案/缺解析计数", it["answers"] == 1 and it["solutions"] == 1)
        check("列表带学段", index()[0]["stage"] in ("primary", "junior", "senior"))
    finally:
        store.load_cached, store.volume_signature = old_load, old_sig
        _CACHE.update({"sig": None, "items": [], "index": {}})
    print("papersets 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
