"""AmTiKu · 题目内容库（SQLite，派生数据）

详情页要的是**一道题**的完整正文。真相仍是 `题目/*.tex`；这里把每道题的
原始题块（`%% @q` 元数据行 + LaTeX）按 key 存进 SQLite：

    读一道题 = 主键查一行 + 解压 + 解析这一块    约 1–3ms
    以前     = 把 7 卷 195MB 全部解析成 Question  约 1.4s

**它不是题库真相**：删掉 `数据/缓存/content.sqlite` 随时可以从 `.tex` 重建。
因此这里只做两件事：让详情读得快、让内容能被 SQL 查询；写仍然走 `store.py`。

一致性
──────
- `meta.sig` 记录建库时的**卷签名**（7 个卷文件的 mtime_ns + size）+ schema 版本。
- 读之前先比对当前卷签名；对不上就返回 None，调用方回退 `store.find()`
  （约 90ms），同时后台重建。**绝不拿旧行冒充新题。**
- 界面改题后，`amti.web.core._rm_apply()` 会带着新 Question 调 `apply()`，
  只改受影响的行并把签名推到新值；这里失败也只是退化成“下次重建”。
- 重建写临时文件再原子替换；构建期间库又变了就整份丢弃，不盖假签名。

用法
────
    from amti import content_store
    q = content_store.get(key)          # 没建好/过期 → None
    content_store.ensure()              # 非阻塞，触发后台重建
    content_store.apply(keys, old_sig, {key: q, ...})   # 写后增量同步

命令行：
    python3 -m amti.content_store status
    python3 -m amti.content_store build
    python3 -m amti.content_store clear
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import zlib
from pathlib import Path

import re

from . import latex_ir
from . import store
from .logutil import get_logger
from .paths import ROOT

log = get_logger(__name__)

DB = ROOT / "数据" / "缓存" / "content.sqlite"
SCHEMA = 4
_ZLIB_LEVEL = 6
#: 题面（题干/选项/答案）与解析分开：相似题只看题面，避免解析文风干扰。
_SOLUTION_RE = re.compile(r"\\begin\{solution\}.*?\\end\{solution\}", re.S)

#: 建库/增量写互斥；读不加锁（SQLite 自己处理）。
_LOCK = threading.Lock()
_BUILDING = False
#: 最近一次校验结果，避免每个请求都开库读 meta。
_STATE: dict = {"sig": None, "ok": False}


# ── 签名 ──────────────────────────────────────────────────────────────

def signature(vol_sig: tuple | None = None) -> tuple:
    """内容库的有效性签名：schema 版本 + 卷签名。

    `vol_sig` 传进来时用它（写路径拿到的是**写之前**的签名），不传就取当前。
    """
    return (SCHEMA, vol_sig if vol_sig is not None else store.volume_signature())


def _sig_of(sig: tuple) -> str:
    return json.dumps(sig, ensure_ascii=False)


def current(sig: tuple | None = None) -> bool:
    """库里的内容是否对应 `sig`（默认当前卷签名）。"""
    sig = signature() if sig is None else sig
    if _STATE["sig"] == sig:
        return bool(_STATE["ok"])
    ok = False
    try:
        if DB.exists():
            c = sqlite3.connect(DB, timeout=5)
            try:
                row = c.execute("select v from meta where k='sig'").fetchone()
                ver = c.execute("select v from meta where k='schema'").fetchone()
            finally:
                c.close()
            ok = bool(row and row[0] == _sig_of(sig)
                      and ver and ver[0] == str(SCHEMA))
    except Exception:
        ok = False
    _STATE.update({"sig": sig, "ok": ok})
    return ok


# ── 读 ────────────────────────────────────────────────────────────────

def get(key: str):
    """按 key 取一道题；没建好/过期/没命中返回 None。

    返回的是**新解析出来的 Question**，调用方可以放心改；不会污染任何缓存。
    """
    if not key:
        return None
    sig = signature()
    if not current(sig):
        ensure()
        return None
    try:
        c = sqlite3.connect(DB, timeout=5)
        try:
            row = c.execute(
                "select body from question_content where key=?", (key,)
            ).fetchone()
        finally:
            c.close()
    except Exception:
        return None
    if not row:
        return None
    try:
        block = zlib.decompress(row[0]).decode("utf-8")
        return store.question_from_block(block)
    except Exception:
        # 坏一行不该让详情挂掉：回退 store.find，并让下次重建修它。
        log.warning("内容库这一行解不开，回退 store.find：%s", key, exc_info=True)
        return None


def _math_keys(c, forms, limit: int) -> set[str]:
    like = "math_strict like ? escape '!' or math_loose like ? escape '!'"
    sql = ("select key from question_content where "
           + " or ".join([like] * len(forms)) + " limit ?")
    params: list = []
    for f in forms:
        p = "%" + f.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        params += [p, p]
    params.append(int(limit))
    return {row[0] for row in c.execute(sql, params)}


def search_math(forms, *, base=None, limit: int = 50000) -> dict[str, int] | None:
    r"""公式召回：返回 `{key: 0/1}`；库没建好返回 None。

    0 = 原始写法（严格/宽松）命中；1 = 等价写法命中（如 `1/2` 搜到 `0.5`）。
    列表排序会先出 0，再出 1，避免等价写法把精确结果压到后面。

    `forms` 由 `search.math_forms()` 生成。用 `LIKE '%…%'` 扫 31k 行，
    约 50–150ms；10 万题再换 FTS trigram。
    """
    forms = [f for f in forms if f and len(f) >= 2]
    if not forms:
        return {}
    sig = signature()
    if not current(sig):
        ensure()
        return None
    base = [f for f in (base or forms[:2]) if f and len(f) >= 2] or forms[:2]
    ranks: dict[str, int] = {}
    try:
        c = sqlite3.connect(DB, timeout=5)
        try:
            groups = [(base, 0)]
            if set(forms) - set(base):
                groups.append((forms, 1))
            for group, rank in groups:
                for key in _math_keys(c, group, limit):
                    ranks.setdefault(key, rank)
        finally:
            c.close()
    except Exception:
        log.warning("内容库公式召回失败，回退普通检索", exc_info=True)
        return None
    return ranks


def question_math_rows() -> list[tuple[str, str]] | None:
    """`(key, math_q)` 全量；相似题建倒排用。库没建好返回 None。"""
    if not current():
        ensure()
        return None
    try:
        c = sqlite3.connect(DB, timeout=5)
        try:
            return c.execute(
                "select key, math_q from question_content "
                "where math_q <> ''").fetchall()
        finally:
            c.close()
    except Exception:
        return None


def math_for(keys) -> dict[str, str]:
    """按 key 批量取 math_q（相似题候选打分用）。"""
    keys = [k for k in dict.fromkeys(keys) if k]
    if not keys or not current():
        return {}
    out: dict[str, str] = {}
    try:
        c = sqlite3.connect(DB, timeout=5)
        try:
            for i in range(0, len(keys), 400):
                chunk = keys[i:i + 400]
                sql = ("select key, math_q from question_content where key in ("
                       + ",".join("?" * len(chunk)) + ")")
                out.update(c.execute(sql, chunk).fetchall())
        finally:
            c.close()
    except Exception:
        return {}
    return out


# ── 建库 ──────────────────────────────────────────────────────────────

def _question_only(block: str) -> str:
    """去掉解析，只留题干/选项/答案；相似题用，避免解析文风干扰。"""
    text = block.split("\n", 1)[1] if block.lstrip().startswith("%% @q") else block
    return _SOLUTION_RE.sub(" ", text)


def _iter_blocks():
    """按卷顺序产出 `(key, volume, block)`。只读文件，不构造全库 Question。"""
    for p in store.existing_volumes():
        try:
            no = int(p.stem)
        except ValueError:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for block in store.split_questions(text):
            if store.GRAVE_MARK in block:
                continue
            m = store.META_RE.search(block)
            if not m:
                continue
            try:
                key = json.loads(m.group(1)).get("key", "")
            except ValueError:
                key = ""
            if key:
                yield key, no, block


def _block_hash(block: str) -> str:
    """题块内容哈希。**只对题块本身**——用来在重建时复用旧行的归一化结果。"""
    return hashlib.blake2b(block.encode("utf-8"), digest_size=16).hexdigest()


def _old_rows() -> dict[str, tuple]:
    """读旧库做增量复用：key → (block_hash, body, math_strict, math_loose, math_q)。

    只在**schema 相同**时复用：`math_text()` 规则变了要 bump `SCHEMA`，
    否则旧行的 math 列会按旧规则留下来。读不了/旧库坏 → 返回空，整库重算。
    """
    if not DB.exists():
        return {}
    c = None
    try:
        c = sqlite3.connect(DB, timeout=5)
        ver = c.execute("select v from meta where k='schema'").fetchone()
        if not ver or ver[0] != str(SCHEMA):
            return {}
        rows = c.execute(
            "select key, block_hash, body, math_strict, math_loose, math_q "
            "from question_content where block_hash <> ''")
        return {r[0]: tuple(r[1:]) for r in rows}
    except Exception:
        return {}
    finally:
        if c is not None:
            c.close()


def _build(sig: tuple) -> None:
    """整库重建：写临时文件 → 原子替换。失败不影响旧库。

    增量：题块哈希与旧库一致的行，**直接复用**压缩 body 和 math 三列；
    只有改过的题才跑 `math_text` + zlib。改一道题的重建从 11s 降到 1–2s。
    """
    global _BUILDING
    DB.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB.with_name("%s.tmp.%d.%d" % (DB.name, os.getpid(),
                                         threading.get_ident()))
    tmp.unlink(missing_ok=True)
    c = None
    try:
        t0 = time.perf_counter()
        c = sqlite3.connect(tmp)
        c.execute("pragma journal_mode=off")
        c.execute("pragma synchronous=off")
        c.executescript("""
        create table meta(k text primary key, v text);
        create table question_content(
          key text primary key,
          volume integer not null,
          body blob not null,
          math_strict text not null default '',
          math_loose text not null default '',
          math_q text not null default '',
          block_hash text not null default '',
          at real not null
        );
        """)
        old = _old_rows()
        n = reused = 0
        for key, no, block in _iter_blocks():
            bh = _block_hash(block)
            hit = old.get(key)
            if hit is not None and hit[0] == bh:
                body, m_strict, m_loose, m_q = hit[1], hit[2], hit[3], hit[4]
                reused += 1
            else:
                body = zlib.compress(block.encode("utf-8"), _ZLIB_LEVEL)
                text = block.split("\n", 1)[1] if block.startswith("%% @q") else block
                m_strict, m_loose = latex_ir.math_text(text)
                m_q = latex_ir.math_text(_question_only(block))[0]
            cur = c.execute(
                "insert or ignore into question_content"
                "(key,volume,body,math_strict,math_loose,math_q,block_hash,at) "
                "values(?,?,?,?,?,?,?,?)",
                (key, no, body, m_strict, m_loose, m_q, bh, time.time()))
            n += cur.rowcount                       # 重复 key 只留第一份
        c.executemany("insert into meta(k,v) values(?,?)", [
            ("sig", _sig_of(sig)),
            ("schema", str(SCHEMA)),
            ("n", str(n)),
            ("at", str(time.time())),
        ])
        c.commit()
        if store.volume_signature() != sig[1]:
            # 构建期间库被写了：这份树里的新旧内容混在一起，不能当 current。
            return
        c.close()
        c = None
        os.replace(tmp, DB)
        _STATE.update({"sig": sig, "ok": True})
        log.info("内容库重建完成：%d 道（复用 %d），%.1f MB，%.1fs",
                 n, reused, DB.stat().st_size / 1e6, time.perf_counter() - t0)
    except Exception:
        log.warning("内容库重建失败，继续回退 store.find", exc_info=True)
    finally:
        if c is not None:
            c.close()
        tmp.unlink(missing_ok=True)
        _BUILDING = False


def _rebuild() -> None:
    global _BUILDING
    try:
        _build(signature())
    finally:
        _BUILDING = False


def ensure() -> None:
    """非阻塞：库过期就起一个后台线程重建，当前请求继续走回退路径。"""
    global _BUILDING
    if _BUILDING or current():
        return
    with _LOCK:
        if _BUILDING or current():
            return
        _BUILDING = True
    threading.Thread(target=_rebuild, name="content-build", daemon=True).start()


def rebuild() -> dict:
    """同步重建（CLI / 验收用）。返回 status()。"""
    global _BUILDING
    with _LOCK:
        if _BUILDING:
            return {"ok": False, "busy": True, **status()}
        _BUILDING = True
    _build(signature())
    return status()


# ── 写后增量同步 ──────────────────────────────────────────────────────

def apply(keys: list[str], old_sig: tuple,
          items: dict | None = None) -> bool:
    r"""写题后只更新受影响的 key；成功时把 meta.sig 推到**当前**卷签名。

    `old_sig` 是**写之前**的 `store.volume_signature()`；`items` 是 key →
    新 Question。items 里没有的 key 视为删除。`items is None` 时不猜新状态，
    直接返回 False，让下一次读触发整体重建。

    只有“写之前内容库是 current”才允许增量；否则返回 False。
    """
    if not keys or _BUILDING:
        return False
    old = signature(old_sig)
    if not current(old):
        return False
    if items is None:
        return False
    new = signature()
    rows: list[tuple] = []
    deletes: list[str] = []
    for k in dict.fromkeys(k for k in keys if k):
        q = items.get(k)
        if q is None:
            deletes.append(k)
            continue
        try:
            text = store.render_question(q)
        except Exception:
            log.warning("内容库增量同步渲染失败：%s", k, exc_info=True)
            return False
        m_strict, m_loose = latex_ir.math_text(text)
        m_q = latex_ir.math_text(_question_only(text))[0]
        rows.append((k, 0, zlib.compress(text.encode("utf-8"), _ZLIB_LEVEL),
                     m_strict, m_loose, m_q, _block_hash(text.strip()),
                     time.time()))
    try:
        c = sqlite3.connect(DB, timeout=10)
        try:
            with c:
                c.executemany(
                    "insert into question_content"
                    "(key,volume,body,math_strict,math_loose,math_q,block_hash,at) "
                    "values(?,?,?,?,?,?,?,?) on conflict(key) do update set "
                    "body=excluded.body, math_strict=excluded.math_strict, "
                    "math_loose=excluded.math_loose, math_q=excluded.math_q, "
                    "block_hash=excluded.block_hash, at=excluded.at", rows)
                c.executemany("delete from question_content where key=?",
                              [(k,) for k in deletes])
                c.execute("update meta set v=? where k='sig'", (_sig_of(new),))
                c.execute("update meta set v=? where k='at'", (str(time.time()),))
        finally:
            c.close()
        _STATE.update({"sig": new, "ok": True})
        return True
    except Exception:
        _STATE.update({"sig": None, "ok": False})
        log.warning("内容库增量同步失败，等待后台重建", exc_info=True)
        return False


# ── 维护 ──────────────────────────────────────────────────────────────

def clear() -> None:
    """删掉派生库；下次读会自动重建。"""
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(str(DB) + suffix).unlink(missing_ok=True)
    _STATE.update({"sig": None, "ok": False})


def status() -> dict:
    n = n_math = n_q = n_hash = None
    if DB.exists():
        try:
            c = sqlite3.connect(DB, timeout=5)
            try:
                n = c.execute("select count(*) from question_content").fetchone()[0]
                n_math = c.execute(
                    "select count(*) from question_content "
                    "where math_loose <> ''").fetchone()[0]
                n_q = c.execute(
                    "select count(*) from question_content "
                    "where math_q <> ''").fetchone()[0]
                n_hash = c.execute(
                    "select count(*) from question_content "
                    "where block_hash <> ''").fetchone()[0]
            finally:
                c.close()
        except Exception:
            pass
    return {
        "db": str(DB),
        "exists": DB.exists(),
        "bytes": DB.stat().st_size if DB.exists() else 0,
        "rows": n,
        "math_rows": n_math,
        "math_q_rows": n_q,
        "hash_rows": n_hash,
        "current": current(),
        "building": _BUILDING,
    }


if __name__ == "__main__":
    import sys
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").strip()
    if cmd == "build":
        print(json.dumps(rebuild(), ensure_ascii=False, indent=2))
    elif cmd == "clear":
        clear()
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    elif cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        raise SystemExit("用法：python3 -m amti.content_store [status|build|clear]")
