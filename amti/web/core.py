"""列表/读模型/使用频次等 Web 层共享读路径。

`_usage()`、`_seq_map()`、`_brief_cached*()`、`_readmodel_page()` 原来都在
`server.py`，questions 路由和 topics/overview 等都要用；拆 router 时如果
直接 import server 会循环。这里只依赖 store / 派生缓存 / present / query，
不依赖 FastAPI。
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict

from amti import content_store
from amti import knowledge_map
from amti import lite_cache
from amti import papers as papers_mod
from amti import readmodel
from amti import review as review_mod
from amti import store
from amti.logutil import get_logger
from amti.paths import ROOT as PKG
from amti.schema import QTYPE_LABEL
from amti.web.present import brief as _brief
from amti.web.present import stage_of as _stage_of
from amti.web.query import flags_of as _flags_of
from amti.web.query import source_of as _source_of

log = get_logger(__name__)

#: lite 缓存的 schema 版本。列表现在要带答案块，旧行必须失效重建。
_LITE_SCHEMA = "answer-v2"


def _lite_hash(q) -> str:
    return q.content_hash() + ":" + _LITE_SCHEMA


# ── 使用频次 ──────────────────────────────────────────────────
# 记录每道题被导出（试卷/讲义）的次数。存独立 JSON —— **不动题库源
# 文件**：17249 个 .tex 改起来又慢又险（verify 必须保持全绿）。
USAGE_PATH = PKG / "数据" / "使用频次.json"
_usage_lock = threading.Lock()
_usage_cache: dict | None = None
_usage_sig: tuple | None = None


def _usage_sig_now() -> tuple | None:
    try:
        st = USAGE_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _usage() -> dict:
    global _usage_cache, _usage_sig
    sig = _usage_sig_now()
    old = _usage_sig
    if _usage_cache is None or sig != _usage_sig:
        try:
            _usage_cache = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        except Exception:
            log.warning("使用频次文件损坏，按空处理：%s", "", exc_info=True)
            _usage_cache = {}
        _usage_sig = sig
        # 别的进程（CLI 导出）改了使用频次：读模型 used 列同步一下，
        # 否则按「使用频次」排序会一直用旧计数。
        if old is not None and sig != old:
            readmodel.set_used(_usage_cache)
    return _usage_cache


def _usage_bump(keys) -> None:
    """导出成功后给用到的题 +1（按次累计，不去重）。"""
    global _usage_cache
    with _usage_lock:
        d = _usage()
        n = 0
        for k in keys:
            if k:
                d[k] = d.get(k, 0) + 1
                n += 1
        if not n:
            return
        try:
            USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            USAGE_PATH.write_text(
                json.dumps(d, ensure_ascii=False, sort_keys=True),
                encoding="utf-8")
        except Exception:
            log.warning("使用频次写盘失败（本次计数丢失）", exc_info=True)
            pass
        global _usage_sig
        _usage_sig = _usage_sig_now()
        readmodel.set_used({k: d.get(k, 0) for k in keys if k})


# ── 题目 ──────────────────────────────────────────────────────────────

# 录入序号：key → 在全库里的追加位置（1 开始）。建一次，之后常驻。
_SEQ: dict[str, int] = {}
_SEQ_SIG: tuple | None = None


def _seq_map() -> dict[str, int]:
    global _SEQ_SIG
    sig = store.volume_signature()
    if _SEQ_SIG != sig:
        _SEQ.clear()
        for i, q in enumerate(store.load_cached(), start=1):
            _SEQ[q.key] = i
        _SEQ_SIG = sig
    return _SEQ


def _seq_of(key: str) -> int:
    return _seq_map().get(key, 0)


def _batches() -> list[dict]:
    r"""按录入顺序列出各来源（书/卷），带题数与序号范围。

    **录入顺序 = 文件追加顺序**，所以第一本书就是最早录进去的。
    """
    from collections import OrderedDict
    seen: "OrderedDict[str, dict]" = OrderedDict()
    for i, q in enumerate(store.load_cached(), start=1):
        b = q.meta.get("book") or "?"
        d = seen.setdefault(b, {"book": b, "n": 0, "first": i, "last": i,
                                "kind": q.kind})
        d["n"] += 1
        d["last"] = i
    return list(seen.values())


# ── 学段（小学 / 初中 / 高中）──────────────────────────────────
# 题目标签是考点 id，学段不在题上存一份，而是**从知识地图现推**——
# 存了就会漂移（改一次标签忘了改学段），而且小学/初中题一旦入库，
# 只要挂的是 x/c 前缀的考点，自动就归到对应学段，不用批量补字段。
_STAGE_KEYS = ("primary", "junior", "senior")
_STAGE_NAMES = {"primary": "小学", "junior": "初中", "senior": "高中"}


def _point_stage() -> dict[str, str]:
    """考点 id → 学段 key。**不读题库**——学段归属只看知识地图/知识点库。"""
    return knowledge_map.stage_index()


def _stage_set(raw: str) -> set[str]:
    return {x.strip() for x in (raw or "").split(",")
            if x.strip() in _STAGE_KEYS}


# `_brief` 要跑块级 IR 解析，一道题几毫秒；17,554 道全跑就是几秒。
# **按内容指纹缓存**：题没改就复用上一次的结果。
# 指纹只覆盖正文，所以改标签不会失效——那正好，标签每次都现算（很便宜）。
# 有上限的 LRU 缓存。
# 审查报告 Important #2：原本是只增不减的 dict，而值里含**解析后的块 IR**，
# 把 17k 道题翻一遍能涨到数百 MB。留最近 2000 道足够（列表翻页/详情往返都命中）。
_BRIEF: "OrderedDict[str, tuple[str, dict]]" = OrderedDict()
_BRIEF_MAX = 2000

# 列表只带 UI 真正读的 meta 键。详情页走 `_brief(q)` 拿全量：
# 时间戳、审阅备注、solved_by 这类“点开才看”的字段不该压在每张卡上。
_LIST_META_KEYS = (
    "book", "region", "region_scope", "source_region", "source_label", "source_no",
    "year", "answer_source", "solution_source", "point_source", "difficulty_source",
    "solve_warn", "solved_by", "solved_at", "duplicate_group", "dup_of",
    "similar_of", "figure_low_res", "paper_size", "paper_complete", "difficulty",
)


def _slim_list_item(d: dict) -> dict:
    """列表序列化：去掉卡片不读的字段。

    `solution` 文本、`review` 的审阅备注/指纹、`meta` 里的大半键都只在
    详情页用（详情走 `/api/questions/{key}` 的 `_brief`）。保留 `stem`
    是为了卡片的关键词命中判断（`QuestionCard` 用它和 `kw` 比对）。
    """
    out = {k: v for k, v in d.items() if k not in ("solution", "review", "meta")}
    m = d.get("meta") or {}
    out["meta"] = {k: m[k] for k in _LIST_META_KEYS if k in m}
    rv = d.get("review") or {}
    out["review"] = {k: rv[k] for k in ("status", "label", "short", "stale") if k in rv}
    return out


def _brief_cached_lite(q) -> dict:
    r"""列表用：**不带答案/解析的块 IR**。

    审查报告 💡#3：列表/卡片只需要题干（卡片画的就是题干），
    答案与解析的块 IR 只有详情页用。而 `parse_blocks` 是纯 CPU ——
    一页 20 题本要跑 60 次解析（题干+答案+解析），现在只跑 20 次。
    详情页走 `/api/questions/{key}` 拿全量（那里才需要）。

    解析结果落 SQLite（`amti/lite_cache.py`），按 content_hash 命中；
    进程重启后不用把同一页再解析一遍。
    """
    h = _lite_hash(q)
    hit = lite_cache.get(q.key, h)
    if hit is not None:
        # 磁盘缓存按**正文指纹**命中，但考点/难度/元数据不在指纹里：
        # 改完标签后正文没变，直接返回旧 hit 会让列表显示旧标签。
        # 和 `_brief_cached` 的内存命中一样，每次重新贴一遍便宜字段。
        d = dict(hit)
        d.update(_tag_fields(q))
        return _slim_list_item(d)
    d = _brief_cached(q)
    b = d.get("blocks")
    if isinstance(b, dict):
        d = dict(d)                      # 必须复制：cache 里那份不能改
        d["blocks"] = {"stem": b.get("stem"), "options": b.get("options"),
                       "answer": b.get("answer")}
        d["lite"] = True
    d = _slim_list_item(d)
    lite_cache.put(q.key, h, d)
    return d


def _brief_cached(q) -> dict:
    h = q.content_hash()
    hit = _BRIEF.get(q.key)
    if hit and hit[0] == h:
        _BRIEF.move_to_end(q.key)
        d = dict(hit[1])
        d.update(_tag_fields(q))            # 标签/难度/元数据每次现取
        return d
    d = _brief(q)
    _BRIEF[q.key] = (h, d)
    if len(_BRIEF) > _BRIEF_MAX:            # 超上限淘汰最久未用的
        _BRIEF.popitem(last=False)
    return d


def _tag_fields(q) -> dict:
    """只重算**不进入 content_hash 的字段**：考点/难度/题型/元数据。

    缓存命中时不能整份 `_cheap_fields` 现算——那里面的 problems()/missing()
    会遍历题干/解析，一页 100 条就是纯浪费；正文没变时这些不可能变。
    """
    return {
        "points": q.points,
        "stage": _stage_of(q),
        "type": q.type,
        "type_label": QTYPE_LABEL.get(q.type, q.type),
        "difficulty": q.difficulty,
        "stars": q.stars,
        "point_titles": q.point_titles,
        "meta": q.meta,
        "kind": q.kind,
        "flags": _flags_of(q),
        "review": review_mod.info(q),
    }


def _paper_usage() -> dict:
    """题目 key → 「被几份存档组过 / 最近一份」。派生自 `试卷/存档.json`。

    放这里而不是读模型：存档一变就得跟着变，而读模型按题库卷签名重建，
    为一份卷子重建 3 万行不值得（见 `amti/papers.usage_index`）。
    """
    return papers_mod.usage_index()


def _cheap_fields(q) -> dict:
    """不跑 IR 解析就能拿到的字段。筛选只看这些。"""
    d = {
        "points": q.points,
        "stage": _stage_of(q),
        "type": q.type,
        "type_label": QTYPE_LABEL.get(q.type, q.type),
        "difficulty": q.difficulty,
        "stars": q.stars,
        "point_titles": q.point_titles,
        "meta": q.meta,
        "kind": q.kind,
        "missing": q.missing(),
        "problems": q.problems(),
        "flags": _flags_of(q),
        "review": review_mod.info(q),
    }
    return d


_RM_BUILDING = False


def _readmodel_row(q, stage_map=None, usage=None, seq_map=None) -> dict:
    m = q.meta or {}
    flags = _flags_of(q)
    rv = review_mod.info(q)
    return {
        "key": q.key,
        "stage": _stage_of(q, stage_map) if stage_map is not None else _stage_of(q),
        "type": q.type, "kind": q.kind, "difficulty": q.difficulty,
        "stars": q.stars, "year": m.get("year") or 0,
        "source": _source_of(q), "book": m.get("book") or "模拟题",
        "region": m.get("region") or "",
        "region_scope": m.get("region_scope")
        or ("single" if m.get("region") else "unknown"),
        "paper_complete": m.get("paper_complete") is not False,
        "dup": bool(m.get("duplicate_group")),
        "lowres": bool(m.get("figure_low_res")),
        "point_source": m.get("point_source") or "",
        "answer_source": m.get("answer_source") or "无",
        "review_status": rv["status"],
        "reviewed": rv["status"] in review_mod.REVIEWED,
        "risk_score": rv["risk"],
        "has_answer": flags.get("答案"), "has_solution": flags.get("解析"),
        "has_figure": flags.get("图"), "has_real_figure": flags.get("有图"),
        "has_points": flags.get("标签"),
        "seq": (seq_map if seq_map is not None else _seq_map()).get(q.key, 0),
        "used": (usage if usage is not None else _usage()).get(q.key, 0),
        "solved_at": m.get("solved_at") or "", "points": list(q.points or ()),
    }


def _readmodel_rows() -> list[dict]:
    """把 store 的元数据摊成读模型行。只在后台重建时调用。"""
    stage_map = _point_stage()
    usage = _usage()
    seq_map = _seq_map()
    return [_readmodel_row(q, stage_map, usage, seq_map) for q in store.load_cached()]


def _rm_apply(keys: list[str], old_sig: tuple,
              items: dict | None = None) -> None:
    """写题后增量同步读模型与内容库；旧库不是 current 就留给后台整体重建。

    `items`（key → Question）由写接口直接给，避免为了同步一个 key 又
    `load_cached()` 解析全库——这一步以前比写盘本身还贵。
    """
    try:
        keys = list(dict.fromkeys(k for k in keys if k))
        if not keys:
            return
        # 内容库（详情页整题正文）与读模型是两套派生数据，各自判断 current。
        # 这里失败只影响详情速度：下次读会回退 store.find 并触发重建。
        try:
            content_store.apply(keys, old_sig, items)
        except Exception:
            log.warning("内容库增量同步失败，等待后台重建", exc_info=True)
        if not readmodel.current(old_sig):
            return
        if items is None:
            by = {q.key: q for q in store.load_cached()}
            seq_map = _seq_map()
        else:
            by = items
            # 改标签不会动 key/顺序：读模型里现成的 seq 就够，别重读全库。
            # 改名/新增的 key 在读模型里没有，退回全量 seq 表。
            seq_map = readmodel.seqs([k for k in keys if k in by])
            if any(k in by and k not in seq_map for k in keys):
                seq_map = _seq_map()
        rows = [_readmodel_row(by[k], seq_map=seq_map) for k in keys if k in by]
        readmodel.apply(rows, keys, old_sig, store.volume_signature())
    except Exception:
        log.warning("读模型增量同步失败，等待后台重建", exc_info=True)

def _rebuild_readmodel() -> None:
    global _RM_BUILDING
    if _RM_BUILDING:
        return
    _RM_BUILDING = True
    try:
        sig = store.volume_signature()
        rows = _readmodel_rows()
        sig2 = store.volume_signature()
        if sig2 != sig:
            # 构建期间库又变了：这棵树的旧/新行混在一起，别把新签名
            # 盖上去“假装 current”；留给下一轮。
            return
        readmodel.rebuild(rows, sig)
    except Exception:
        log.warning("读模型重建失败（回退旧路径）", exc_info=True)
    finally:
        _RM_BUILDING = False


def _ensure_readmodel() -> None:
    if readmodel.current(store.volume_signature()) or _RM_BUILDING:
        return
    threading.Thread(target=_rebuild_readmodel, daemon=True).start()


#: 元数据读模型能直接 SQL 判断的 flags。`小问`/`存疑` 没进表，
#: 带这两项时必须回退 Python 的 QuestionFilter，否则筛选会被**静默忽略**。
_READMODEL_FLAGS = frozenset(("答案", "解析", "图", "有图", "标签"))


def _readmodel_page(*, limit: int, offset: int, sort: str, lite: bool = True, **f) -> dict | None:
    """元数据表路径。返回 None = 未就绪/不支持，调用方回退。"""
    if not readmodel.current(store.volume_signature()):
        _ensure_readmodel()
        return None
    # 先读 usage：如果别的进程刚导出过，`_usage()` 会把 used 列同步进
    # 读模型；放在 query 后面就晚了，排序仍用旧计数。
    usage = _usage()
    res = readmodel.query(limit=limit, offset=offset, sort=sort, **f)
    if res is None:
        return None
    total, keys = res
    by = store.read_many(keys)
    page = [by[k] for k in keys if k in by]
    seq_map = readmodel.seqs([k for k in keys if k in by])
    if len(seq_map) < len(page):
        seq_map = _seq_map()
    papers = _paper_usage()
    out = []
    for item in page:
        b = _brief_cached_lite(item) if lite else _brief_cached(item)
        b["seq"] = seq_map.get(item.key, 0)
        b["used"] = usage.get(item.key, 0)
        hit = papers.get(item.key)
        if hit:
            b["papers"] = hit
        out.append(b)
    return {"total": total, "items": out}
