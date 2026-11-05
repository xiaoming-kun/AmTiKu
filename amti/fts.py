r"""AmTiKu · FTS5 检索索引（候选召回 + BM25）

## 为什么还要这个

`amti/search.py` 的纯内存打分解决“相关度”，但 29k 道每次搜索都要把
23MB 正文扫一遍。数据再长（10 万道）就撑不住。这里用 SQLite FTS5 建一份
**可重建的派生索引**：`.tex` 仍是唯一真相，索引丢了随时重建。

## 中文 2 字查询的坑

FTS5 的 `trigram` 分词器至少吃 3 个字符，“函数”“导数”“椭圆”直接 0 结果；
`unicode61` 又把整段中文当一个 token。这里的办法是**建索引时把每个汉字
用空格隔开**，查询时把中文词变成字符短语（`"函 数"`）。2 字、3 字都能命中，
代价是索引比正文大一些——可重建，不值钱。

## 用法

    from amti import fts
    fts.search("函数 单调", limit=2000)   # 返回按 bm25 排好的 key 列表
    fts.status()                          # 索引在不在、多少条、签名

索引路径：`数据/索引.sqlite`（不进 git）。卷文件签名变了，下次搜索自动重建。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

from .paths import ROOT

DB = ROOT / "数据" / "索引.sqlite"
_LOCK = threading.Lock()
_CACHE = {"sig": (), "ok": False}

_CJK = r"\u3400-\u9fff"
_CJK_RE = re.compile(r"([%s])" % _CJK)
_TOKEN_RE = re.compile(r"[%s]+|[A-Za-z0-9_]+" % _CJK)


def _clean(s: str) -> str:
    r"""正文 → FTS 文本：LaTeX 去壳、汉字隔开、ASCII 小写。"""
    s = s or ""
    s = s.replace("\\dfrac", "\\frac").replace("\\left", " ").replace("\\right", " ")
    s = re.sub(r"\\[a-zA-Z]+", " ", s)      # 命令名不进索引（frac/sqrt 这类噪声）
    s = re.sub(r"[${}^_\\]", " ", s)
    s = _CJK_RE.sub(r" \1 ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def _phrase(t: str) -> str:
    """一个查询词 → FTS5 短语。中文按字隔开，英文按词。"""
    t = t.strip()
    if not t:
        return ""
    if all(re.match("[%s]" % _CJK, ch) for ch in t):
        return '"' + " ".join(t) + '"'
    t = re.sub(r'["\']', "", t)
    return '"' + t + '"' if t else ""


def _match(q: str) -> str:
    """查询 → `MATCH` 表达式：多词 AND，中文词按字符短语。"""
    parts = [_phrase(t) for t in _TOKEN_RE.findall(q or "")]
    return " AND ".join(p for p in parts if p)


def _sig() -> tuple:
    from . import store
    return store.volume_signature()


def _doc(q) -> str:
    return _clean(" ".join([
        q.stem or "", " ".join(o.text for o in q.options),
        q.answer or "", q.solution or "",
        " ".join(q.point_titles or []),
        str((q.meta or {}).get("book") or ""),
        str((q.meta or {}).get("source_label") or ""),
        str((q.meta or {}).get("region") or ""),
    ]))


def build(force: bool = False) -> dict:
    r"""重建索引。**先写临时文件再原子替换**，中途失败旧索引还能用。"""
    from . import store
    sig = _sig()
    if not force and DB.exists():
        try:
            with sqlite3.connect(DB) as c:
                row = c.execute("select v from meta where k='sig'").fetchone()
            if row and json.loads(row[0]) == [list(x) for x in sig]:
                _CACHE.update({"sig": sig, "ok": True})
                return {"built": False, "n": _count(), "sig": sig}
        except Exception:                                    # noqa: BLE001
            pass

    t0 = time.time()
    tmp = DB.with_name(DB.name + ".tmp")
    tmp.unlink(missing_ok=True)
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(tmp)
    try:
        c.execute("create table meta(k text primary key, v text)")
        c.execute("create virtual table docs using fts5(key unindexed, text, "
                  "tokenize='unicode61')")
        rows = [(q.key, _doc(q)) for q in store.load_cached()]
        c.executemany("insert into docs(key, text) values(?,?)", rows)
        n = len(rows)
        c.execute("insert into meta(k,v) values('sig',?)",
                  (json.dumps([list(x) for x in sig]),))
        c.execute("insert into meta(k,v) values('n',?)", (str(n),))
        c.commit()
    finally:
        c.close()
    os.replace(tmp, DB)
    _CACHE.update({"sig": sig, "ok": True})
    return {"built": True, "n": n, "sig": sig,
            "sec": round(time.time() - t0, 2)}


def _count() -> int:
    try:
        with sqlite3.connect(DB) as c:
            row = c.execute("select v from meta where k='n'").fetchone()
        return int(row[0]) if row else 0
    except Exception:                                        # noqa: BLE001
        return 0


def ensure() -> bool:
    """索引存在且与当前卷签名一致。第一次搜索会重建（约 2 秒）。"""
    sig = _sig()
    if _CACHE.get("ok") and _CACHE.get("sig") == sig:
        return True
    with _LOCK:
        if _CACHE.get("ok") and _CACHE.get("sig") == sig:
            return True
        try:
            build()
            return True
        except Exception:                                    # noqa: BLE001
            _CACHE["ok"] = False
            return False


def search(q: str, limit: int = 2000) -> list[str]:
    r"""按 bm25 排好的 key。索引不可用/查询为空时返回 `[]`（调用方回退）。"""
    expr = _match(q)
    if not expr or not ensure():
        return []
    try:
        with sqlite3.connect(DB) as c:
            rows = c.execute(
                "select key from docs where docs match ? order by bm25(docs) limit ?",
                (expr, max(1, min(int(limit), 10000)))).fetchall()
        return [r[0] for r in rows]
    except Exception:                                        # noqa: BLE001
        return []


def invalidate() -> None:
    """写了库之后调用（可选）：下次搜索重建。"""
    _CACHE.update({"sig": (), "ok": False})


def status() -> dict:
    try:
        with sqlite3.connect(DB) as c:
            sig = c.execute("select v from meta where k='sig'").fetchone()
            n = c.execute("select v from meta where k='n'").fetchone()
        return {"exists": True, "n": int(n[0]) if n else 0,
                "current": bool(sig and json.loads(sig[0])
                               == [list(x) for x in _sig()]),
                "bytes": DB.stat().st_size}
    except Exception:                                        # noqa: BLE001
        return {"exists": False, "n": 0, "current": False, "bytes": 0}


def _selftest() -> int:
    import tempfile
    global DB
    old, old_cache = DB, dict(_CACHE)
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + name + (("  " + extra) if extra else ""))
        if not cond:
            fails += 1

    tmp = Path(tempfile.mkdtemp(prefix="amti-fts-"))
    DB = tmp / "t.sqlite"
    try:
        # 直接造 docs，不依赖 store（自检要能在空库上跑）
        c = sqlite3.connect(DB)
        c.execute("create table meta(k text primary key, v text)")
        c.execute("create virtual table docs using fts5(key unindexed, text, "
                  "tokenize='unicode61')")
        docs = [("a", "已 知 函 数 的 单 调 性"),
                ("b", "椭 圆 的 离 心 率"),
                ("c", "导 数 与 极 值"),
                ("d", "函 数 的 单 调 性 与 导 数")]
        c.executemany("insert into docs(key,text) values(?,?)", docs)
        c.execute("insert into meta(k,v) values('n','4')")
        c.execute("insert into meta(k,v) values('sig','[]')")
        c.commit(); c.close()
        _CACHE.update({"ok": True, "sig": ()})

        # 绕过 ensure 的签名检查，直接查
        def q(x):
            expr = _match(x)
            with sqlite3.connect(DB) as c:
                return [r[0] for r in c.execute(
                    "select key from docs where docs match ? order by bm25(docs)",
                    (expr,)).fetchall()]
        check("2 字中文能命中", set(q("函数")) == {"a", "d"}, str(q("函数")))
        check("多词 AND", set(q("函数 单调")) == {"a", "d"}, str(q("函数 单调")))
        check("匹配不到返回空", q("不存在的词") == [], str(q("不存在的词")))
        check("短语构造", _phrase("函数") == '"函 数"', _phrase("函数"))
        check("清理去 LaTeX", "\\frac" not in _clean("$\\frac{1}{2}$"), _clean("$\\frac{1}{2}$"))
    finally:
        DB = old
        _CACHE.clear(); _CACHE.update(old_cache)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print("fts 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
