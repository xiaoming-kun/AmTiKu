"""筛选面板 / 学段驾驶舱 / 小初诊断题路由。

只读聚合：facets/overview/diagnostics。数据源是 store/readmodel/
knowledge_map/papers/topics，不写题库。
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from amti import knowledge
from amti import knowledge_map
from amti import open_lectures
from amti import readmodel
from amti import review as review_mod
from amti import store
from amti import topics
from amti.logutil import get_logger
from amti.schema import KINDS, QTYPE_LABEL
from amti.web.core import (
    _STAGE_KEYS, _STAGE_NAMES, _batches, _ensure_readmodel, _point_stage,
    _stage_set, _stage_of,
)
from amti.web.query import flags_of as _flags_of

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["insights"])
DIFF_ORDER = {"简单题": 1, "中档题": 2, "难题": 3}


_FACETS_CACHE: dict = {}


def _facets_fast(stage_set: set[str], stage: str) -> dict | None:
    """读模型版筛选项。没就绪/出异常返回 None，调用方回退旧路径。"""
    from amti import knowledge as kb
    stages = list(stage_set)
    cnt = lambda col: readmodel.counts(col, stages)
    types_c, kinds_c, diff_c = cnt("type"), cnt("kind"), cnt("difficulty")
    year_c, source_c, book_c = cnt("year"), cnt("source"), cnt("book")
    region_c, scope_c, asrc_c = cnt("region"), cnt("region_scope"), cnt("answer_source")
    rv_c, paper_c, stars_c = cnt("reviewed"), cnt("paper_complete"), cnt("stars")
    rvs_c = cnt("review_status")
    dup_c, low_c = cnt("dup"), cnt("lowres")
    pc = readmodel.point_counts(stages)

    if stage_set and "senior" not in stage_set:
        point_list = []
        for st in knowledge_map.tree().get("stages", []):
            if st.get("key") not in stage_set:
                continue
            for b in st.get("books", []):
                for c in b.get("chapters", []):
                    for p in c.get("points", []):
                        point_list.append({
                            "value": p["id"], "n": pc.get(p["id"], 0),
                            "title": p.get("title") or p["id"],
                            "topic": b.get("name") or "",
                            "section": c.get("title") or "",
                            "stars": 0, "difficulty": "",
                        })
    else:
        point_list = [{"value": p["id"], "n": pc.get(p["id"], 0),
                       "title": kb.title_of(p["id"]),
                       "topic": p["topic"], "section": p["section"],
                       "stars": p["stars"], "difficulty": p["difficulty"]}
                      for p in kb.all_points()]
        point_list.sort(key=lambda x: [int(y) if y.isdigit() else 0
                                       for y in x["value"].split(".")])

    years = [{"value": str(y), "n": n} for y, n in
             sorted(((int(y), n) for y, n in year_c.items() if y and int(y) > 0),
                    reverse=True)]
    reviewed = [{"value": "yes", "n": rv_c.get(1, 0)},
                {"value": "no", "n": rv_c.get(0, 0)}]
    reviewed = [x for x in reviewed if x["n"]]
    papers = [{"value": "complete", "n": paper_c.get(1, 0)},
              {"value": "partial", "n": paper_c.get(0, 0)}]
    papers = [x for x in papers if x["n"]]
    rated = sum(n for s, n in stars_c.items() if int(s or 0) > 0)
    unrated = sum(n for s, n in stars_c.items() if int(s or 0) <= 0)
    stars = [x for x in ({"value": "rated", "n": rated},
                         {"value": "unrated", "n": unrated}) if x["n"]]
    quals = [x for x in ({"value": "dup", "n": dup_c.get(1, 0)},
                         {"value": "lowres", "n": low_c.get(1, 0)}) if x["n"]]
    return {
        "types": [{"value": k, "label": QTYPE_LABEL.get(k, k), "n": v}
                  for k, v in sorted(types_c.items(), key=lambda x: -x[1])],
        "kinds": [{"value": k, "n": kinds_c.get(k, 0)} for k in KINDS],
        "points": point_list,
        "points_covered": sum(1 for x in point_list if x["n"]),
        "difficulties": [{"value": k, "n": v} for k, v in
                         sorted(diff_c.items(), key=lambda x: DIFF_ORDER.get(x[0], 9))],
        "years": years,
        "sources": [{"value": k, "n": v} for k, v in
                    sorted(source_c.items(), key=lambda x: -x[1]) if k],
        "books": [{"value": k, "n": v} for k, v in
                  sorted(book_c.items(), key=lambda x: -x[1]) if k],
        "regions": [{"value": k, "n": v} for k, v in
                    sorted(region_c.items(), key=lambda x: -x[1]) if k],
        "answer_sources": [{"value": k, "n": v} for k, v in
                           sorted(asrc_c.items(), key=lambda x: -x[1])],
        "reviewed_states": reviewed,
        "review_states": [{"value": k, "n": v} for k, v in
                          sorted(rvs_c.items(), key=lambda x: -x[1])],
        "region_scopes": [{"value": k, "n": v} for k, v in
                          sorted(scope_c.items(), key=lambda x: -x[1]) if k],
        "paper_states": papers,
        "star_states": stars,
        "qualities": quals,
        "batches": readmodel.batches(),
    }


@router.get("/facets")
def facets(stage: str = "", rm: bool = True) -> dict:
    """筛选面板要的选项 + 计数。

    `stage` 给了就只数这个学段的题。学段不在题上存，按考点现推；
    小学/初中题目还没有时，计数就是 0（界面显示"题库建设中"）。
    """
    from collections import Counter
    from amti import knowledge as kb
    stage_set = _stage_set(stage)
    ck = (stage, store.volume_signature(), knowledge_map._sig(), kb.signature())
    hit = _FACETS_CACHE.get(ck)
    if hit is not None:
        return hit
    if rm and readmodel.current(store.volume_signature()):
        try:
            fast = _facets_fast(stage_set, stage)
            if fast is not None:
                # 和下面回退路径一样限 12 条；否则每改一次题就多一个
                # 按卷签名做 key 的完整 facets 字典，进程会慢慢涨。
                if len(_FACETS_CACHE) > 12:
                    _FACETS_CACHE.clear()
                _FACETS_CACHE[ck] = fast
                return fast
        except Exception:
            log.warning("读模型 facets 失败，回退全量", exc_info=True)
    else:
        _ensure_readmodel()
    stage_map = _point_stage()
    (types, kinds, points, diffs, years, sources,
     scopes, papers, stars, quals, books, regions, asrc, rvc, rvs) = (
        Counter(), Counter(), Counter(), Counter(), Counter(), Counter(),
        Counter(), Counter(), Counter(), Counter(), Counter(), Counter(), Counter(),
        Counter(), Counter())
    for q in store.load_cached():
        if stage_set and _stage_of(q, stage_map) not in stage_set:
            continue
        types[q.type] += 1
        kinds[q.kind] += 1          # 只有两类：高考 / 模拟
        books[q.meta.get("book") or "模拟题"] += 1
        if q.meta.get("region"):
            regions[str(q.meta.get("region"))] += 1
        asrc[str(q.meta.get("answer_source") or "无")] += 1
        est = review_mod.effective_status(q)
        rvs[est] += 1
        rvc["yes" if est in review_mod.REVIEWED else "no"] += 1
        for p in q.points:
            points[p] += 1
        if q.difficulty:
            diffs[q.difficulty] += 1
        y = q.meta.get("year")
        if y:
            years[int(y)] += 1
        # 「来源」= 卷别（如「新课标I卷」）。试卷上要标的就是它，
        # 和年份拼成「2026年新课标I卷-6」。
        lab = q.meta.get("region") or ""
        if not lab:
            lab = (q.meta.get("source_label") or "").split("年")[-1]
        if lab:
            sources[lab] += 1
        scope = q.meta.get("region_scope") or ("single" if q.meta.get("region") else "unknown")
        scopes[scope] += 1
        papers["partial" if q.meta.get("paper_complete") is False else "complete"] += 1
        stars["rated" if q.stars > 0 else "unrated"] += 1
        if q.meta.get("duplicate_group"):
            quals["dup"] += 1
        if q.meta.get("figure_low_res"):
            quals["lowres"] += 1
    # 考点：**列出这个学段的全部知识点**，没有题目的计数为 0。
    # 高中取 `知识点.json` 的 152 个考点；小学/初中取 `知识地图.json` 的
    # 教材点（x/c 前缀），topic=册、section=章——这样小初题库的筛选树
    # 和正式题库是同一套，题目录进来立刻能按册章筛。
    if stage_set and "senior" not in stage_set:
        point_list = []
        for st in knowledge_map.tree().get("stages", []):
            if st.get("key") not in stage_set:
                continue
            for b in st.get("books", []):
                for c in b.get("chapters", []):
                    for p in c.get("points", []):
                        point_list.append({
                            "value": p["id"], "n": points.get(p["id"], 0),
                            "title": p.get("title") or p["id"],
                            "topic": b.get("name") or "",
                            "section": c.get("title") or "",
                            "stars": 0, "difficulty": "",
                        })
    else:
        allpts = kb.all_points()
        point_list = [{"value": p["id"], "n": points.get(p["id"], 0),
                       "title": kb.title_of(p["id"]),
                       "topic": p["topic"], "section": p["section"],
                       "stars": p["stars"], "difficulty": p["difficulty"]}
                      for p in allpts]
        point_list.sort(key=lambda x: [int(y) if y.isdigit() else 0
                                       for y in x["value"].split(".")])
    out = {
        "types": [{"value": k, "label": QTYPE_LABEL.get(k, k), "n": v}
                  for k, v in types.most_common()],
        "kinds": [{"value": k, "n": kinds.get(k, 0)} for k in KINDS],
        "points": point_list,
        "points_covered": sum(1 for x in point_list if x["n"]),
        "difficulties": [{"value": k, "n": v}
                         for k, v in sorted(diffs.items(),
                                            key=lambda x: DIFF_ORDER.get(x[0], 9))],
        # 年份：**倒序**（新的在前），高考题尤其要看这个
        "years": [{"value": str(y), "n": n}
                  for y, n in sorted(years.items(), reverse=True)],
        "sources": [{"value": k, "n": v} for k, v in sources.most_common()],
        "books": [{"value": k, "n": v} for k, v in books.most_common()],
        "regions": [{"value": k, "n": v} for k, v in regions.most_common()],
        "answer_sources": [{"value": k, "n": v} for k, v in asrc.most_common()],
        "reviewed_states": [{"value": k, "n": v} for k, v in rvc.most_common()],
        "review_states": [{"value": k, "n": v} for k, v in rvs.most_common()],
        "region_scopes": [{"value": k, "n": v} for k, v in scopes.most_common()],
        "paper_states": [{"value": k, "n": v} for k, v in papers.most_common()],
        "star_states": [{"value": k, "n": v} for k, v in stars.most_common()],
        "qualities": [{"value": k, "n": v} for k, v in quals.most_common()],
        # 录入批次：按「书」给出先后（文件里的追加顺序）。
        # 用户想看「我新录的 vs 早先录的」，这个顺序就是答案。
        "batches": _batches(),
    }
    if len(_FACETS_CACHE) > 12:
        _FACETS_CACHE.clear()
    _FACETS_CACHE[ck] = out
    return out


# ── 开源小初讲义 ──────────────────────────────────────────────
# 数据在 `数据/开源讲义/`，内容版权归原作者，按 MIT / LPPL 使用。
# 本接口只读：清单、Markdown→HTML、图片、PDF。

_OVERVIEW_CACHE: dict = {"key": None, "v": None}


def _archive_sig() -> tuple:
    from amti import papers as P
    try:
        st = P.ARCHIVE.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


@router.get("/overview")
def stage_overview(stage: str = "senior", rm: bool = True) -> dict:
    """学段驾驶舱：知识图谱 / 讲义 / 题库 / 组卷四段流水线的一次性汇总。

    只读、不加缓存。全库 3 万道题的 `_stage_of + _flags_of` 在 100ms 量级，
    比让前端发四五个请求再自己拼要快，也少一次数据打架。
    """
    from collections import Counter
    from amti import papers as P

    st = stage if stage in _STAGE_KEYS else "senior"
    tree = knowledge_map.tree()
    ck = (st, store.volume_signature(), knowledge_map._sig(), knowledge.signature(),
          topics._sig(), _archive_sig(), open_lectures._sig())
    if _OVERVIEW_CACHE["key"] == ck and _OVERVIEW_CACHE["v"] is not None:
        return _OVERVIEW_CACHE["v"]
    node = next((x for x in tree.get("stages", []) if x["key"] == st), None) or {}
    books = node.get("books", [])
    point_nodes = [p for b in books for c in b.get("chapters", []) for p in c.get("points", [])]
    point_ids = {p["id"] for p in point_nodes}

    # 一次遍历，三个学段的题库计数一起算（避免前端切学段再扫库）。
    # P2：读模型就绪时直接 SQL 聚合；没就绪回退旧的全库遍历。
    bank = None
    if rm and readmodel.current(store.volume_signature()):
        try:
            bank = readmodel.bank_stats()
            for b in bank.values():
                b["types"] = Counter({QTYPE_LABEL.get(k, k): v
                                      for k, v in b["types"].items()})
        except Exception:
            log.warning("读模型总览失败，回退全量", exc_info=True)
            bank = None
    else:
        _ensure_readmodel()
    if bank is None:
        bank = {k: {"total": 0, "types": Counter(), "diff": Counter(),
                    "missing": Counter(), "untagged_source": 0,
                    "unreviewed": 0, "points": set()} for k in _STAGE_KEYS}
        stage_map = _point_stage()
        for q in store.load_cached():
            s = _stage_of(q, stage_map)
            b = bank.setdefault(s, {"total": 0, "types": Counter(), "diff": Counter(),
                                    "missing": Counter(), "untagged_source": 0,
                                    "unreviewed": 0, "points": set()})
            b["total"] += 1
            b["types"][QTYPE_LABEL.get(q.type, q.type)] += 1
            if q.difficulty:
                b["diff"][q.difficulty] += 1
            flags = _flags_of(q)
            for k in ("答案", "解析", "图", "标签"):
                if not flags.get(k):
                    b["missing"][k] += 1
            if not q.meta.get("point_source"):
                b["untagged_source"] += 1
            if review_mod.effective_status(q) not in review_mod.REVIEWED:
                b["unreviewed"] += 1
            b["points"].update(q.points or ())
    for k in _STAGE_KEYS:
        bank.setdefault(k, {"total": 0, "types": Counter(), "diff": Counter(),
                            "missing": Counter(), "untagged_source": 0,
                            "unreviewed": 0, "points": set()})

    # 诊断题 / 讲义覆盖：按学段各算一遍（585 个点，很快）。
    diag = {k: {"total": 0, "points": set(), "by_level": Counter()}
            for k in _STAGE_KEYS}
    for s in tree.get("stages", []):
        sk = s.get("key", "")
        for b in s.get("books", []):
            for c in b.get("chapters", []):
                for p in c.get("points", []):
                    qs = knowledge_map.questions_of(p["id"])
                    if not qs:
                        continue
                    d = diag.setdefault(sk, {"total": 0, "points": set(),
                                             "by_level": Counter()})
                    d["total"] += len(qs)
                    d["points"].add(p["id"])
                    for x in qs:
                        d["by_level"][x.get("level") or "standard"] += 1

    lecture = {k: {"total": 0, "points": set()} for k in _STAGE_KEYS}
    for t in topics.load():
        tid = str(t.get("id") or "")
        s = str(t.get("stage") or _point_stage().get(tid, "") or "")
        if not s:
            continue
        lecture.setdefault(s, {"total": 0, "points": set()})
        lecture[s]["total"] += 1
        # 高中一份讲义=一个考点；小初一份讲义=一章，覆盖章下全部知识点。
        for pid in (t.get("points") or [tid]):
            if pid:
                lecture[s]["points"].add(str(pid))

    try:
        saved = P.all_items()
    except Exception:                       # 存档坏了不该让驾驶舱空白
        saved = []
    recent = [{"name": x.get("name"), "title": x.get("title") or x.get("name"),
               "kind": x.get("kind") or "试卷", "n": x.get("n", 0),
               "at": x.get("updated") or x.get("at")}
              for x in saved[:5]]

    b = bank.get(st, {"total": 0, "types": Counter(), "diff": Counter(),
                      "missing": Counter(), "untagged_source": 0,
                      "unreviewed": 0, "points": set()})
    d = diag.get(st, {"total": 0, "points": set(), "by_level": Counter()})
    lec = lecture.get(st, {"total": 0, "points": set()})
    bank_covered = len(b["points"] & point_ids)
    diag_covered = len(d["points"] & point_ids)
    lecture_covered = len(lec["points"] & point_ids)

    tasks = []
    if b["missing"]["解析"]:
        tasks.append({"id": "bank.no_solution", "label": "缺解析",
                      "n": b["missing"]["解析"], "tone": "warn", "page": "bank",
                      "filters": {"missing": "解析"},
                      "hint": "这些题不能直接上卷面，补完解析再导出"})
    if b["missing"]["标签"]:
        tasks.append({"id": "bank.no_point", "label": "没有考点",
                      "n": b["missing"]["标签"], "tone": "warn", "page": "bank",
                      "filters": {"missing": "标签"},
                      "hint": "没有考点就进不了知识图谱和专题"})
    if b["untagged_source"]:
        tasks.append({"id": "bank.no_source", "label": "考点来源未登记",
                      "n": b["untagged_source"], "tone": "info", "page": "bank",
                      "filters": {"psrc": "无"},
                      "hint": "早期批量录入留下的；不影响使用，抽样复核即可"})
    if b["unreviewed"]:
        tasks.append({"id": "bank.unreviewed", "label": "待审题",
                      "n": b["unreviewed"], "tone": "info", "page": "review",
                      "hint": "按风险排序抽样复核；改过正文的旧复核会标成“失效”"})
    if st in ("primary", "junior"):
        no_diag = len(point_ids) - diag_covered
        if no_diag:
            tasks.append({"id": "diag.gap", "label": "知识点还没有诊断题",
                          "n": no_diag, "tone": "warn", "page": "map",
                          "hint": "诊断题是给知识点做入口的，先补这一层"})
        if not b["total"]:
            tasks.append({"id": "bank.empty", "label": "题库还没有这个学段的题",
                          "n": 0, "tone": "warn", "page": "ingest",
                          "hint": "从诊断题升级，或直接录新题；录进来就自动归到这个学段"})
    no_lec = len(point_ids) - lecture_covered
    if no_lec:
        tasks.append({"id": "lecture.gap", "label": "正式讲义还没铺满",
                      "n": no_lec, "tone": "info", "page": "lectures",
                      "hint": "开源讲义已接入；正式专题仍按知识点一份建设"})
    if st == "senior":
        no_bank = len(point_ids) - bank_covered
        if no_bank:
            tasks.append({"id": "bank.point_gap", "label": "知识点还没有题",
                          "n": no_bank, "tone": "warn", "page": "bank",
                          "hint": "考点覆盖是组卷的底，先把每个点铺上题"})

    open_by_stage = {k: open_lectures.list_for_stage(k)["total"]
                     for k in ("primary", "junior", "senior")}
    open_total = open_by_stage.get(st, 0)

    out = {
        "stage": {"key": st, "name": _STAGE_NAMES[st],
                  "points": len(point_ids), "books": len(books),
                  "chapters": sum(len(b.get("chapters", [])) for b in books),
                  "edges": len([e for e in tree.get("edges", [])
                                if e.get("from") in point_ids and e.get("to") in point_ids])},
        "edition": tree.get("edition", ""),
        "updated": tree.get("updated", ""),
        "coverage": {"points": len(point_ids), "bank": bank_covered,
                     "diagnostics": diag_covered, "lectures": lecture_covered},
        "bank": {"total": b["total"],
                 "types": [{"label": k, "n": v} for k, v in b["types"].most_common()],
                 "difficulty": [{"value": k, "n": v} for k, v in
                                sorted(b["diff"].items(),
                                       key=lambda x: DIFF_ORDER.get(x[0], 9))],
                 "missing": dict(b["missing"]),
                 "untagged_source": b["untagged_source"],
                 "unreviewed": b["unreviewed"]},
        "diagnostics": {"total": d["total"], "points": diag_covered,
                        "levels": [{"value": k, "n": v}
                                   for k, v in d["by_level"].most_common()]},
        "lectures": {"total": lec["total"], "points": lecture_covered},
        "open_lectures": {"total": open_total, "by_stage": open_by_stage},
        "papers": {"total": len(saved), "recent": recent},
        "stages": [{"key": s.get("key"), "name": s.get("name"),
                    "points": sum(b.get("n", 0) for b in s.get("books", [])),
                    "bank": bank.get(s.get("key"), {}).get("total", 0),
                    "diagnostics": diag.get(s.get("key"), {}).get("total", 0),
                    "lectures": lecture.get(s.get("key"), {}).get("total", 0),
                    "open_lectures": open_by_stage.get(s.get("key"), 0)}
                   for s in tree.get("stages", [])],
        "tasks": tasks,
    }
    _OVERVIEW_CACHE["key"], _OVERVIEW_CACHE["v"] = ck, out
    return out


def _diagnostic_items(stage: str = "", q: str = "", book: str = "",
                      chapter: str = "", point: str = "", level: str = "") -> list[dict]:
    """小初诊断题的扁平列表（两个端点共用：列表 + 导出）。

    数据源是 `小初诊断题.json`（知识点 id → 题），学段/册/章从
    `知识地图.json` 现取——不在题上再存一份，改了地图自动跟着走。
    """
    stage_set = _stage_set(stage)
    pt_filter = {x.strip() for x in point.split(",") if x.strip()}
    kw = q.strip()
    tokens = [t for t in re.split(r"[\s,，、;；]+", kw) if t] if kw else []

    def hit(it: dict) -> bool:
        if stage_set and it["stage"] not in stage_set:
            return False
        if pt_filter and it["point"] not in pt_filter:
            return False
        if book and it["book"] != book:
            return False
        if chapter and it["chapter"] != chapter:
            return False
        if level and it["level"] != level:
            return False
        if tokens:
            hay = " ".join([it["prompt"], it["answer"], it.get("explanation") or "",
                            it["point_title"], it["book"], it["chapter"]]).lower()
            if not all(t.lower() in hay for t in tokens):
                return False
        return True

    items: list[dict] = []
    for s_ in knowledge_map.tree().get("stages", []):
        sk = s_.get("key", "")
        for b in s_.get("books", []):
            for c in b.get("chapters", []):
                for p in c.get("points", []):
                    qs = knowledge_map.questions_of(p["id"])
                    for i, x in enumerate(qs):
                        it = {
                            "key": f"{p['id']}#{i + 1}",
                            "stage": sk,
                            "stage_name": s_.get("name") or _STAGE_NAMES.get(sk, sk),
                            "book": b.get("name", ""), "chapter": c.get("title", ""),
                            "grade": b.get("grade", 0),
                            "point": p["id"], "point_title": p.get("title", ""),
                            "type": x.get("type") or "choice",
                            "level": x.get("level") or "standard",
                            "prompt": x.get("prompt") or "",
                            "answer": x.get("answer") or "",
                            "choices": x.get("choices") or [],
                            "explanation": x.get("explanation") or "",
                        }
                        if hit(it):
                            items.append(it)
    return items


@router.get("/diagnostics")
def diagnostics_list(
    stage: str = "", q: str = "", book: str = "", chapter: str = "",
    point: str = "", level: str = "",
    limit: Annotated[int, Query(ge=1, le=500)] = 60,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """小学/初中的诊断题库。高中走 `/api/questions`，这里只汇总教材地图里的诊断题。"""
    items = _diagnostic_items(stage, q, book, chapter, point, level)
    facet_books = Counter(x["book"] for x in items)
    facet_chapters = Counter(x["chapter"] for x in items)
    facet_levels = Counter(x["level"] for x in items)
    facet_points = Counter((x["point"], x["point_title"]) for x in items)
    return {
        "total": len(items), "items": items[offset:offset + limit],
        "facets": {
            "books": [{"value": k, "n": v} for k, v in facet_books.most_common()],
            "chapters": [{"value": k, "n": v} for k, v in facet_chapters.most_common()],
            "levels": [{"value": k, "n": v} for k, v in facet_levels.most_common()],
            "points": [{"value": k[0], "title": k[1], "n": v}
                       for k, v in facet_points.most_common()],
        },
    }


class DiagExportBody(BaseModel):
    stage: str = "primary"
    q: str = ""
    book: str = ""
    chapter: str = ""
    point: str = ""
    level: str = ""
    limit: int = 20
    title: str = ""
    answers: bool = False
    out: str = ""


@router.post("/diagnostics/export")
def diagnostics_export(body: DiagExportBody) -> dict:
    """把小初诊断题排成一份 PDF（学生卷 / 教师版）。

    不写试卷存档：这些题还不在正式题库里，存下来也只能还原成 key。
    产物落在「测试卷」分类下，和正式测试卷放在一起。
    """
    from amti import diagnostic as _diag
    items = _diagnostic_items(body.stage, body.q, body.book, body.chapter,
                              body.point, body.level)
    if not items:
        raise HTTPException(400, "这个条件下没有诊断题")
    n = max(1, min(200, int(body.limit or 20)))
    try:
        return _diag.export(items[:n], title=body.title,
                            answers=bool(body.answers), out=body.out)
    except Exception as e:                       # noqa: BLE001
        log.exception("诊断卷导出失败")
        raise HTTPException(500, f"导出失败：{e}") from e
