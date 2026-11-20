"""AmTiKu · 题库元数据读模型（SQLite，派生数据）

P1：列表的筛选/排序/计数不再靠 Python 全量扫 `Question` 对象。
真相仍是 `题目/*.tex`；这里只存一份可重建的元数据表：

    questions(key, stage, type, kind, difficulty, stars, year, source, ...)
    question_points(key, point)

由服务端按卷签名重建；没建好/过期时调用方自动回退到旧路径。
"""
from __future__ import annotations

import json
import sqlite3
import threading

# **必须走 `amti.paths.ROOT`**：按学段出包/免安装版靠 `AMTIKU_ROOT` 换数据根，
# 写死 `parents[1]` 会让包里起的服务把读模型写回源码仓库——实测把母库的
# readmodel 覆盖成了包里那 269 行，母库列表只剩初中题。
from .paths import ROOT

DB = ROOT / "数据" / "缓存" / "readmodel.sqlite"
_LOCK = threading.Lock()
_CACHE: dict = {"sig": None, "ok": False}
# 6：`dup` 口径从「duplicate_group 或 dup_of」收紧为「只认 duplicate_group」
#（相似不再算重复，2026-11-20）。改口径必须 bump，否则旧行的 dup=1 会留下。
_SCHEMA = 6


def _sig_of(sig: tuple) -> str:
    return json.dumps([list(x) for x in sig], ensure_ascii=False, sort_keys=True)


def current(sig: tuple) -> bool:
    try:
        if _CACHE.get("ok") and _CACHE.get("sig") == sig:
            return True
        with sqlite3.connect(DB) as c:
            row = c.execute("select v from meta where k='sig'").fetchone()
            ver = c.execute("select v from meta where k='schema'").fetchone()
        ok = bool(row and row[0] == _sig_of(sig)
                  and ver and ver[0] == str(_SCHEMA))
        _CACHE.update({"sig": sig, "ok": ok})
        return ok
    except Exception:
        _CACHE.update({"sig": sig, "ok": False})
        return False


def rebuild(rows: list[dict], sig: tuple) -> dict:
    """整体重建。先写临时文件再原子替换；失败旧模型不受影响。"""
    import os
    # 多进程（服务 + 测试/CLI）同时重建时，固定 `.tmp` 会互相踩出
    # `disk I/O error`；每个进程/线程用自己的临时文件，最后原子替换。
    tmp = DB.with_name("%s.tmp.%d.%d" % (DB.name, os.getpid(),
                                         threading.get_ident()))
    tmp.unlink(missing_ok=True)
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(tmp)
    try:
        c.executescript("""
        create table meta(k text primary key, v text);
        create table questions(
          key text primary key, stage text, type text, kind text,
          difficulty text, stars integer, year integer, source text, book text,
          region text, region_scope text, paper_complete integer,
          dup integer, lowres integer, point_source text, answer_source text,
          reviewed integer, has_answer integer, has_solution integer,
          has_figure integer, has_real_figure integer, has_points integer,
          seq integer, used integer,
          solved_at text, points text,
          review_status text, risk_score integer
        );
        create table question_points(key text, point text,
          primary key(key, point));
        create index idx_q_stage on questions(stage);
        create index idx_q_type on questions(type);
        create index idx_q_kind on questions(kind);
        create index idx_q_diff on questions(difficulty);
        create index idx_q_year on questions(year);
        create index idx_q_source on questions(source);
        create index idx_q_book on questions(book);
        create index idx_q_used on questions(used);
        create index idx_q_seq on questions(seq);
        create index idx_q_has_answer on questions(has_answer);
        create index idx_q_has_solution on questions(has_solution);
        create index idx_q_has_points on questions(has_points);
        create index idx_qp_point on question_points(point);
        """)
        qrows = []
        prows = []
        for r in rows:
            qrows.append((
                r["key"], r["stage"], r["type"], r["kind"], r["difficulty"],
                int(r["stars"] or 0), int(r["year"] or 0), r["source"],
                r.get("book") or "",
                r.get("region") or "", r.get("region_scope") or "",
                1 if r.get("paper_complete") is not False else 0,
                1 if r.get("dup") else 0, 1 if r.get("lowres") else 0,
                r.get("point_source") or "", r.get("answer_source") or "无",
                1 if r.get("reviewed") else 0,
                1 if r.get("has_answer") else 0, 1 if r.get("has_solution") else 0,
                1 if r.get("has_figure") else 0, 1 if r.get("has_real_figure") else 0,
                1 if r.get("has_points") else 0,
                int(r.get("seq") or 0), int(r.get("used") or 0),
                r.get("solved_at") or "", json.dumps(r.get("points") or [], ensure_ascii=False),
                r.get("review_status") or "pending", int(r.get("risk_score") or 0),
            ))
            for p in r.get("points") or []:
                prows.append((r["key"], p))
        c.executemany("insert into questions values (" + ",".join("?" * 28) + ")", qrows)
        c.executemany("insert or ignore into question_points values (?,?)", prows)
        c.execute("insert into meta(k,v) values('sig',?)", (_sig_of(sig),))
        c.execute("insert into meta(k,v) values('schema',?)", (str(_SCHEMA),))
        c.execute("insert into meta(k,v) values('n',?)", (str(len(rows)),))
        c.commit()
    finally:
        c.close()
    try:
        os.replace(tmp, DB)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    _CACHE.update({"sig": sig, "ok": True})
    return {"n": len(rows), "sig": sig}


def _where(**kw) -> tuple[str, list]:
    where: list[str] = []
    ps: list = []

    def _in(col: str, vals) -> None:
        vals = list(vals or ())
        if not vals:
            return
        where.append(f"{col} in (select value from json_each(?))")
        ps.append(json.dumps(vals, ensure_ascii=False))

    for col, vals in (("stage", kw.get("stage")), ("type", kw.get("types")),
                      ("kind", kw.get("kinds")), ("difficulty", kw.get("diffs")),
                      ("source", kw.get("sources")),
                      ("region_scope", kw.get("scopes")),
                      ("answer_source", kw.get("answer_sources"))):
        _in(col, vals)
    if kw.get("years"):
        ys = []
        for y in kw["years"]:
            try: ys.append(int(y))
            except (TypeError, ValueError): pass
        _in("year", ys)
    if kw.get("points"):
        where.append("exists (select 1 from question_points qp where qp.key=q.key "
                     "and qp.point in (select value from json_each(?)))")
        ps.append(json.dumps(list(kw["points"]), ensure_ascii=False))
    if kw.get("paper_states"):
        vals = set(kw["paper_states"])
        bits = []
        if "complete" in vals: bits.append("paper_complete=1")
        if "partial" in vals: bits.append("paper_complete=0")
        if bits: where.append("(" + " or ".join(bits) + ")")
    if kw.get("star_states"):
        vals = set(kw["star_states"]); bits = []
        if "rated" in vals: bits.append("stars>0")
        if "unrated" in vals: bits.append("stars=0")
        if bits: where.append("(" + " or ".join(bits) + ")")
    if kw.get("qualities"):
        vals = set(kw["qualities"]); bits = []
        if "dup" in vals: bits.append("dup=1")
        if "lowres" in vals: bits.append("lowres=1")
        if bits: where.append("(" + " or ".join(bits) + ")")
    psrc = (kw.get("point_source") or "").strip()
    if psrc:
        if psrc == "无":
            where.append("point_source=''")
        else:
            where.append("point_source=?"); ps.append(psrc)
    rv = (kw.get("reviewed") or "").strip()
    if rv in ("yes", "no"):
        where.append("reviewed=?"); ps.append(1 if rv == "yes" else 0)
    if kw.get("review_status"):
        _in("review_status", kw.get("review_status"))
    if kw.get("incomplete"):
        # 「待补」= 缺答案或缺解析（任一）。两个 index 都在，走 OR 也快。
        where.append("(has_answer=0 or has_solution=0)")
    for name in kw.get("has") or ():
        col = {"答案": "has_answer", "解析": "has_solution",
               "图": "has_figure", "有图": "has_real_figure",
               "标签": "has_points"}.get(name)
        if col: where.append(f"{col}=1")
    for name in kw.get("missing") or ():
        col = {"答案": "has_answer", "解析": "has_solution",
               "图": "has_figure", "有图": "has_real_figure",
               "标签": "has_points"}.get(name)
        if col: where.append(f"{col}=0")
    if kw.get("fts_keys") is not None:
        keys = list(kw["fts_keys"])
        if not keys:
            where.append("0")
        else:
            where.append("key in (select value from json_each(?))")
            ps.append(json.dumps(keys, ensure_ascii=False))
    return (" where " + " and ".join(where)) if where else "", ps


def _order(sort: str) -> str:
    if sort == "new": return " order by seq desc"
    if sort == "old": return " order by seq asc"
    if sort == "used": return " order by used desc, seq asc"
    if sort == "solved": return " order by solved_at desc, seq asc"
    if sort in ("diff", "diff2"):
        d = "ASC" if sort == "diff" else "DESC"
        return (" order by case difficulty when '简单题' then 1 when '中档题' then 2 "
                f"when '难题' then 3 else 9 end {d}, seq asc")
    if sort in ("year", "year2"):
        d = "DESC" if sort == "year" else "ASC"
        return f" order by case when year=0 then 1 else 0 end, year {d}, seq asc"
    if sort == "risk":
        return " order by risk_score desc, seq asc"
    return " order by seq asc"


def query(*, limit: int | None = 100, offset: int = 0, sort: str = "",
          **filters) -> tuple[int, list[str]] | None:
    """返回 (total, keys)。DB 不存在/坏了返回 None，调用方回退。"""
    where, ps = _where(**filters)
    try:
        with sqlite3.connect(DB) as c:
            if limit is None:
                keys = [r[0] for r in c.execute(
                    "select key from questions q" + where + _order(sort), ps)]
                return len(keys), keys
            total = c.execute("select count(*) from questions q" + where, ps).fetchone()[0]
            keys = [r[0] for r in c.execute(
                "select key from questions q" + where + _order(sort) +
                " limit ? offset ?", ps + [int(limit), int(offset)])]
            return total, keys
    except Exception:
        return None




def _row_tuple(r: dict) -> tuple:
    return (
        r["key"], r["stage"], r["type"], r["kind"], r["difficulty"],
        int(r["stars"] or 0), int(r["year"] or 0), r["source"],
        r.get("book") or "", r.get("region") or "",
        r.get("region_scope") or "",
        1 if r.get("paper_complete") is not False else 0,
        1 if r.get("dup") else 0, 1 if r.get("lowres") else 0,
        r.get("point_source") or "", r.get("answer_source") or "无",
        1 if r.get("reviewed") else 0,
        1 if r.get("has_answer") else 0, 1 if r.get("has_solution") else 0,
        1 if r.get("has_figure") else 0, 1 if r.get("has_real_figure") else 0,
        1 if r.get("has_points") else 0, int(r.get("seq") or 0), int(r.get("used") or 0),
        r.get("solved_at") or "", json.dumps(r.get("points") or [], ensure_ascii=False),
        r.get("review_status") or "pending", int(r.get("risk_score") or 0),
    )


def apply(rows: list[dict], keys: list[str], old_sig: tuple, new_sig: tuple) -> bool:
    """增量替换若干 key。

    只有 DB 在写入前是 `old_sig` 对应的 current 状态才允许；
    否则返回 False，让调用方等后台整体重建。
    """
    if not current(old_sig):
        return False
    keys = list(dict.fromkeys(keys))
    if not keys:
        return True
    try:
        with sqlite3.connect(DB) as c:
            for k in keys:
                c.execute("delete from question_points where key=?", (k,))
                c.execute("delete from questions where key=?", (k,))
            for r in rows:
                c.execute("insert into questions values (" + ",".join("?" * 28) + ")",
                          _row_tuple(r))
                c.executemany("insert or ignore into question_points values (?,?)",
                              [(r["key"], p) for p in (r.get("points") or [])])
            c.execute("insert into meta(k,v) values('sig',?) "
                      "on conflict(k) do update set v=excluded.v",
                      (_sig_of(new_sig),))
            c.commit()
        _CACHE.update({"sig": new_sig, "ok": True})
        return True
    except Exception:
        _CACHE.update({"sig": None, "ok": False})
        return False




def set_used(counts: dict[str, int]) -> None:
    """导出计数变化时同步 used 列，否则按 used 排序会过期。"""
    if not counts:
        return
    try:
        with sqlite3.connect(DB) as c:
            c.executemany("update questions set used=? where key=?",
                          [(int(v), k) for k, v in counts.items()])
            c.commit()
    except Exception:
        pass


def counts(column: str, stages=()) -> dict:
    allowed = {"type", "kind", "difficulty", "year", "source", "book",
               "region", "region_scope", "answer_source", "reviewed",
               "paper_complete", "stars", "dup", "lowres", "point_source",
               "review_status"}
    if column not in allowed:
        return {}
    stages = list(stages or ())
    where = ""
    ps: list = []
    if stages:
        where = " where stage in (select value from json_each(?))"
        ps.append(json.dumps(stages, ensure_ascii=False))
    try:
        with sqlite3.connect(DB) as c:
            return {r[0]: r[1] for r in c.execute(
                f"select {column},count(*) from questions{where} group by {column}", ps)}
    except Exception:
        return {}


def point_counts(stages=()) -> dict:
    stages = list(stages or ())
    where = ""
    ps: list = []
    if stages:
        where = " where q.stage in (select value from json_each(?))"
        ps.append(json.dumps(stages, ensure_ascii=False))
    try:
        with sqlite3.connect(DB) as c:
            return {r[0]: r[1] for r in c.execute(
                "select qp.point,count(*) from question_points qp "
                "join questions q on q.key=qp.key" + where + " group by qp.point", ps)}
    except Exception:
        return {}


def batches() -> list:
    try:
        with sqlite3.connect(DB) as c:
            rows = c.execute(
                "select book,count(*),min(seq),max(seq) from questions "
                "group by book order by min(seq)").fetchall()
            out = []
            for book, n, first, last in rows:
                kind = c.execute(
                    "select kind from questions where book=? order by seq limit 1",
                    (book,)).fetchone()
                out.append({"book": book, "n": n, "first": first,
                            "last": last, "kind": (kind or [""])[0]})
            return out
    except Exception:
        return []


def bank_stats() -> dict:
    """总览用：所有学段的题库计数 + 覆盖点。"""
    from collections import Counter
    out = {}
    try:
        with sqlite3.connect(DB) as c:
            for stage, typ, n in c.execute(
                    "select stage,type,count(*) from questions group by stage,type"):
                b = out.setdefault(stage, {"total": 0, "types": Counter(),
                                           "diff": Counter(), "missing": Counter(),
                                           "untagged_source": 0, "unreviewed": 0,
                                           "points": set()})
                b["total"] += n; b["types"][typ] += n
            for stage, diff, n in c.execute(
                    "select stage,difficulty,count(*) from questions group by stage,difficulty"):
                if diff:
                    out.setdefault(stage, {"total": 0, "types": Counter(),
                                           "diff": Counter(), "missing": Counter(),
                                           "untagged_source": 0, "unreviewed": 0,
                                           "points": set()})["diff"][diff] += n
            for row in c.execute(
                    "select stage,sum(has_answer=0),sum(has_solution=0),"
                    "sum(has_figure=0),sum(has_points=0),sum(point_source=''),"
                    "sum(reviewed=0) from questions group by stage"):
                stage, a, s, f, p, ps, rv = row
                b = out.setdefault(stage, {"total": 0, "types": Counter(),
                                           "diff": Counter(), "missing": Counter(),
                                           "untagged_source": 0, "unreviewed": 0,
                                           "points": set()})
                if a: b["missing"]["答案"] += a
                if s: b["missing"]["解析"] += s
                if f: b["missing"]["图"] += f
                if p: b["missing"]["标签"] += p
                b["untagged_source"] += ps or 0
                b["unreviewed"] += rv or 0
            for stage, point in c.execute(
                    "select q.stage,qp.point from question_points qp "
                    "join questions q on q.key=qp.key"):
                out.setdefault(stage, {"total": 0, "types": Counter(),
                                       "diff": Counter(), "missing": Counter(),
                                       "untagged_source": 0, "unreviewed": 0,
                                       "points": set()})["points"].add(point)
        return out
    except Exception:
        return {}



def seqs(keys: list[str]) -> dict[str, int]:
    """按 key 取读模型里的 `seq`（录入顺序）。

    单题热路径改完标签后，key 集合/顺序没变，没必要为了拿这几道题的
    `seq` 再把全库 `load_cached()` 一遍；直接问读模型。
    读模型不可用时返回空 dict，调用方回退 `_seq_map()`。
    """
    keys = list(dict.fromkeys(k for k in keys if k))
    if not keys or not DB.exists():
        return {}
    try:
        with sqlite3.connect(DB) as c:
            qs = ",".join("?" * len(keys))
            rows = c.execute(
                f"select key, seq from questions where key in ({qs})", keys
            ).fetchall()
        return {k: int(s or 0) for k, s in rows}
    except Exception:
        return {}


def status() -> dict:
    try:
        with sqlite3.connect(DB) as c:
            n = c.execute("select count(*) from questions").fetchone()[0]
            sig = c.execute("select v from meta where k='sig'").fetchone()
        return {"exists": DB.exists(), "n": n, "sig": bool(sig), "path": str(DB)}
    except Exception as e:
        return {"exists": DB.exists(), "error": str(e)}
