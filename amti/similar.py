"""AmTiKu · 相似题（P1）

给详情页找“同一考点 / 同一公式结构 / 同一题型”的题。**不做语义理解**，
只用三路可解释特征：

    formula  题干/选项/答案的数学文本 trigram，IDF 加权 Jaccard
    points   考点集合 Jaccard
    meta     题型 / 难度 / 类别 / 出处

真相仍是 `题目/*.tex`；索引按卷签名缓存，写库后自动失效，删了可重建。
内容库没建好时返回 `ready=False`，前端显示“索引构建中”，不编造结果。
"""
from __future__ import annotations

import math
import re
import sqlite3
import threading
from collections import OrderedDict, defaultdict

from . import content_store
from . import latex_ir
from . import readmodel
from . import store

_CAND = 600
_CACHE_MAX = 128
_GRAM_RE = re.compile(r"[^a-z0-9.]+")

_LOCK = threading.Lock()
_INDEX: dict = {
    "sig": None,
    "postings": {},
    "idf": {},
    "meta": {},
    "points": {},
    "by_point": {},
}
_CACHE: "OrderedDict[tuple, list]" = OrderedDict()


# ── 基础函数 ──────────────────────────────────────────────────────────

def _grams(text: str) -> set[str]:
    """数学文本 → 字符 trigram。去空格/运算符，比单词切分更能抓住公式结构。"""
    s = _GRAM_RE.sub("", (text or "").lower())[:160]
    if len(s) < 3:
        return set()
    return {s[i:i + 3] for i in range(len(s) - 2)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def _weighted(a: set, b: set, idf: dict) -> float:
    if not a or not b:
        return 0.0
    inter = sum(idf.get(g, 1.0) for g in a & b)
    union = sum(idf.get(g, 1.0) for g in a | b)
    return inter / union if union else 0.0


def _sig() -> tuple:
    return (tuple(store.volume_signature()), content_store.SCHEMA)


def _question_text(q) -> str:
    return " ".join([
        q.stem or "",
        " ".join(o.text for o in q.options),
        q.answer or "",
    ])


def _load_meta(vol_sig: tuple) -> tuple[dict, dict]:
    """(key → meta, key → points)。优先读 readmodel，坏掉再回退全库对象。"""
    meta: dict[str, tuple] = {}
    points: dict[str, set] = {}
    try:
        if readmodel.current(vol_sig):
            c = sqlite3.connect(readmodel.DB, timeout=5)
            try:
                for row in c.execute(
                        "select key,type,kind,difficulty,source,book,region,used "
                        "from questions"):
                    meta[row[0]] = tuple(row[1:])
                for key, p in c.execute("select key,point from question_points"):
                    points.setdefault(key, set()).add(p)
            finally:
                c.close()
            return meta, points
    except Exception:
        pass
    for q in store.load_cached():
        m = q.meta or {}
        points[q.key] = set(q.points or ())
        meta[q.key] = (q.type, q.kind, q.difficulty,
                       m.get("source_label") or m.get("book") or "",
                       m.get("book") or "", m.get("region") or "", 0)
    return meta, points


# ── 索引 ──────────────────────────────────────────────────────────────

def _build(sig: tuple) -> bool:
    rows = content_store.question_math_rows()
    if rows is None:
        return False
    postings: dict[str, set] = defaultdict(set)
    for key, text in rows:
        for g in _grams(text):
            postings[g].add(key)
    meta, points = _load_meta(sig[0])
    if not meta:
        return False
    n = max(1, len(meta))
    idf = {g: math.log(1.0 + n / max(1, len(ks))) + 1.0
           for g, ks in postings.items()}
    by_point: dict[str, set] = defaultdict(set)
    for key, ps in points.items():
        for p in ps:
            by_point[p].add(key)
    _INDEX.update({
        "sig": sig, "postings": dict(postings), "idf": idf,
        "meta": meta, "points": points, "by_point": dict(by_point),
    })
    _CACHE.clear()
    return True


def _ensure(sig: tuple) -> bool:
    if _INDEX["sig"] == sig:
        return True
    with _LOCK:
        if _INDEX["sig"] == sig:
            return True
        return _build(sig)


# ── 查询 ──────────────────────────────────────────────────────────────

def find(q, limit: int = 8) -> tuple[list[tuple[str, float]], bool]:
    """返回 `([(key, score)], ready)`；ready=False 表示索引还没建好。"""
    sig = _sig()
    if not content_store.current():
        content_store.ensure()
        return [], False
    if not _ensure(sig):
        return [], False

    ck = (sig, q.key, int(limit))
    with _LOCK:
        hit = _CACHE.get(ck)
        if hit is not None:
            _CACHE.move_to_end(ck)
            return hit, True

    target_text = content_store.math_for([q.key]).get(q.key)
    if not target_text:
        target_text = latex_ir.math_text(_question_text(q))[0]
    tg = _grams(target_text)
    tp = set(q.points or ())

    votes: dict[str, float] = defaultdict(float)
    idf = _INDEX["idf"]
    for g in tg:
        w = idf.get(g, 0.0)
        for key in _INDEX["postings"].get(g, ()):
            votes[key] += w
    for p in tp:
        for key in _INDEX["by_point"].get(p, ()):
            votes[key] += 2.0
    votes.pop(q.key, None)
    if not votes:
        return [], True

    cand = sorted(votes, key=votes.get, reverse=True)[:_CAND]
    math_by = content_store.math_for(cand)
    meta = _INDEX["meta"]
    points = _INDEX["points"]
    mine = meta.get(q.key, ("", "", "", "", "", "", 0))

    scored: list[tuple[float, int, str]] = []
    for key in cand:
        other_text = math_by.get(key, "")
        formula = _weighted(tg, _grams(other_text), idf) if other_text else 0.0
        pts = _jaccard(tp, points.get(key, set()))
        if formula <= 0 and pts <= 0:
            continue
        cm = meta.get(key)
        if not cm:
            continue
        meta_s = (0.5 * (cm[0] == mine[0])
                  + 0.3 * (cm[2] == mine[2])
                  + 0.2 * (cm[1] == mine[1]))
        if mine[3] and mine[3] == cm[3]:
            src_s = 1.0
        elif mine[4] and mine[4] == cm[4]:
            src_s = 0.5
        else:
            src_s = 0.0
        score = 0.52 * formula + 0.30 * pts + 0.10 * meta_s + 0.08 * src_s
        scored.append((score, int(cm[6] or 0), key))

    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    out = [(key, round(score, 4)) for score, _used, key in scored[:limit]]
    with _LOCK:
        _CACHE[ck] = out
        _CACHE.move_to_end(ck)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return out, True


def status() -> dict:
    return {
        "ready": _INDEX["sig"] is not None,
        "grams": len(_INDEX["postings"]),
        "keys": len(_INDEX["meta"]),
        "cache": len(_CACHE),
        "sig": bool(_INDEX["sig"]),
    }


def _selftest() -> int:
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + name + (("  " + extra) if extra else ""))
        if not cond:
            fails += 1

    a = _grams(latex_ir.math_text(r"\cos B=\frac{3}{4}")[0])
    b = _grams(latex_ir.math_text("cos b=(3)/(4)")[0])
    check("trigram 抹平写法", a == b, str((a, b)))
    check("Jaccard 空集", _jaccard(set(), {1}) == 0.0)
    check("Jaccard 半重合", abs(_jaccard({1, 2}, {2, 3}) - 1 / 3) < 1e-9)
    idf = {"a": 5.0, "b": 1.0}
    check("IDF 加权：稀有 gram 更重要",
          _weighted({"a"}, {"a", "b"}, idf) > _weighted({"b"}, {"a", "b"}, idf))
    print("similar 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
