"""AmTiKu · 列表 lite 缓存（SQLite，派生数据）

`_brief_cached_lite` 的块 IR 要跑 LaTeX 解析，一页 100 条约 0.2–2 秒。
这里把**已经解析过的 lite JSON** 按 `content_hash` 落盘：
- 热请求直接读 SQLite，不再解析；
- 源码改了 hash 变，旧行自然命中不了，重新解析后覆盖；
- 整个库是派生数据，删掉 `数据/缓存/lite.sqlite` 随时可重建。

它不是题库真相：真相仍是 `题目/*.tex`。
"""
from __future__ import annotations

import json
import sqlite3
import zlib
import threading
from .paths import ROOT

DB = ROOT / "数据" / "缓存" / "lite.sqlite"
_LOCK = threading.Lock()
_LOCAL = threading.local()


def _conn() -> sqlite3.Connection:
    c = getattr(_LOCAL, "c", None)
    if c is not None:
        return c
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.execute("pragma journal_mode=wal")
    c.execute("pragma synchronous=normal")
    c.execute(
        "create table if not exists lite ("
        " key text primary key, hash text not null, data blob not null, at real)"
    )
    _LOCAL.c = c
    return c


def get(key: str, h: str) -> dict | None:
    try:
        c = _conn()
        row = c.execute("select data from lite where key=? and hash=?", (key, h)).fetchone()
        if not row:
            return None
        raw = row[0]
        if isinstance(raw, str):
            return json.loads(raw)
        return json.loads(zlib.decompress(raw).decode("utf-8"))
    except Exception:
        return None


def put(key: str, h: str, data: dict) -> None:
    try:
        c = _conn()
        with _LOCK:
            c.execute(
                "insert into lite(key,hash,data,at) values(?,?,?,strftime('%s','now')) "
                "on conflict(key) do update set hash=excluded.hash,data=excluded.data,at=excluded.at",
                (key, h, zlib.compress(
                    json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)),
            )
            c.commit()
    except Exception:
        # 缓存写失败不影响请求；下次再解析。
        pass


def put_many(items: list[tuple[str, str, dict]]) -> None:
    """后台同步用：一批一个事务，避免 10 万次 commit。"""
    if not items:
        return
    try:
        c = _conn()
        rows = [(k, h, zlib.compress(
            json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6))
            for k, h, d in items]
        with _LOCK:
            c.executemany(
                "insert into lite(key,hash,data,at) values(?,?,?,strftime('%s','now')) "
                "on conflict(key) do update set hash=excluded.hash,data=excluded.data,at=excluded.at",
                rows,
            )
            c.commit()
    except Exception:
        pass




def prune(valid: dict[str, str]) -> int:
    """删除已不在题库里、或 hash 已过期的行。后台同步末尾调用。"""
    if not valid:
        return 0
    try:
        c = _conn()
        with _LOCK:
            c.execute("create temp table if not exists _keep(key text primary key, hash text)")
            c.execute("delete from _keep")
            c.executemany("insert into _keep(key,hash) values(?,?)",
                          list(valid.items()))
            before = c.execute("select count(*) from lite").fetchone()[0]
            c.execute("delete from lite where not exists ("
                      "select 1 from _keep k where k.key=lite.key and k.hash=lite.hash)")
            c.commit()
            after = c.execute("select count(*) from lite").fetchone()[0]
            return before - after
    except Exception:
        return 0


def hashes() -> dict[str, str]:
    """key → content_hash；后台同步用，一次取全表。"""
    try:
        c = _conn()
        return dict(c.execute("select key,hash from lite").fetchall())
    except Exception:
        return {}


def clear() -> None:
    try:
        c = _conn()
        with _LOCK:
            c.execute("delete from lite")
            c.commit()
    except Exception:
        pass


def status() -> dict:
    try:
        c = _conn()
        n = c.execute("select count(*) from lite").fetchone()[0]
        return {"exists": DB.exists(), "n": n, "path": str(DB)}
    except Exception as e:
        return {"exists": DB.exists(), "error": str(e)}
