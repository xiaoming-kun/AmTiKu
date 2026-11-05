"""AmTiKu · Web 后端

只做三件事：把题目读出来、把统计算出来、把卷子导出来。
**不缓存、不写库**——分卷文件是唯一真相，每次请求现读。

接口按 UI 的需要设计，不是按数据库的表结构：

    GET  /api/questions      列表（带筛选）—— 工作台左中栏
    GET  /api/questions/{key} 单题详情
    POST /api/questions/{key}/source  改源码（默认只检查不写盘）
    GET  /api/stats          统计
    GET  /api/facets         筛选项（题型/来源/考点，带计数）
    POST /api/generate/replace 单题换题候选
    POST /api/export         导出套卷（LaTeX/elegantbook）
    GET  /api/figure         题图
"""
from __future__ import annotations

from amti.paths import ROOT, UI_DIST
import functools
import json
from collections import Counter, OrderedDict
import atexit
import os
import re
import sys
import threading
import time
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from typing import Annotated
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# 本文件在 amti/web/ 下，比 amti/store.py 深一级 → 项目根要退三层
PKG = ROOT
sys.path.insert(0, str(PKG))

from amti.logutil import get_logger                       # noqa: E402
from amti import knowledge                               # noqa: E402
from amti import latex_blocks as lb                       # noqa: E402
from amti import store                                    # noqa: E402
from amti.render_tex import question_to_tex               # noqa: E402
from amti.schema import KINDS, QTYPE_LABEL                # noqa: E402

DIFF_ORDER = {"简单题": 1, "中档题": 2, "难题": 3}

IMG_DIR = PKG / "图片"
# 白底转透明的缓存**不能放在 IMG_DIR 里**：那是内容寻址的源图目录，
# 混进 3,700 个可再生成的缓存文件之后，“孤儿图/未引用图”这类审计
# 就再也说不清了（`图片/` 一度有 230MB 是它）。缓存放数据目录，随便删。
TRANSPARENT_CACHE = PKG / "数据" / "缓存" / "transparent"

# ── 使用频次 ──────────────────────────────────────────────────
# 记录每道题被导出（试卷/讲义）的次数。存独立 JSON —— **不动题库源
# 文件**：17249 个 .tex 改起来又慢又险（verify 必须保持全绿）。
USAGE_PATH = PKG / "数据" / "使用频次.json"
_usage_lock = threading.Lock()
_usage_cache: dict | None = None


def _usage() -> dict:
    global _usage_cache
    if _usage_cache is None:
        try:
            _usage_cache = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        except Exception:
            log.warning("使用频次文件损坏，按空处理：%s", "", exc_info=True)
            _usage_cache = {}
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
# 前端是**随包只读资源**，不是用户数据：UI_DIST 一律来自 `amti.paths`
# （打包后是 `_internal/web/dist`）。
# 原来写的是 `PKG / "web" / "dist"`，而 PKG 是**数据目录**（exe 旁边）——
# 那里没有前端，于是 `if UI_DIST.exists()` 整段跳过：接口全通、首页 404。
from amti.paths import OUT_DIR, PREVIEW_DIR, kind_of   # 导出位置/分类/预览唯一来源

log = get_logger(__name__)

# ── 导出串行化 ────────────────────────────────────────────
# 后端审查报告 Important #6：导出是 30s~分钟级的长任务，且都调用同一套
# LaTeX 渲染、往同一个临时目录写。并发跑会互相踩（一个在清理
# 临时文件，另一个正在读）。用非阻塞锁：忙就回 429，而不是排队堆线程。
_EXPORT_LOCK = threading.Lock()


def _serialized_export(fn):
    """导出端点装饰器：**串行化**执行，且无论如何都释放锁。

    直接在每个端点里手写 acquire/finally 容易漏（早期版本就是这么漏掉
    timeout 的），装饰器只加一行、不会漏。
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        lock = _export_guard()
        try:
            return fn(*a, **kw)
        finally:
            lock.release()
    return wrapper


def _export_guard() -> threading.Lock:
    if not _EXPORT_LOCK.acquire(blocking=False):
        raise HTTPException(429, "已有一个导出在进行，请稍候再试")
    return _EXPORT_LOCK


app = FastAPI(title="AmTiKu")


@app.middleware("http")
async def _count_inflight(request, call_next):
    """进出各加减一次，给看门狗判断"现在有没有活没干完"。

    数**所有**请求而不是只数导出：除了导出，录入、统计、讲义生成
    也都是几秒到几十秒的长活，中途被 `os._exit` 砍掉一样会留半成品。
    """
    _INFLIGHT[0] += 1
    try:
        return await call_next(request)
    finally:
        _INFLIGHT[0] -= 1


@app.middleware("http")
async def _same_origin_only(request, call_next):
    r"""只接受本机来源的请求。

    后端审查报告 Important #4：只 bind 127.0.0.1 是**对的一半** ——
    浏览器允许**任意网页**向 http://127.0.0.1:8899 发 POST（同源策略
    只挡"读取响应"，不挡"发送"）。而删题/改源码现在**不需要口令**，
    任意网页都能触发 `/api/trash/delete`——Origin 白名单因此更重要。
    校验 Origin 同时挡住 CSRF 与 DNS-rebinding。

    curl / 同源页面不带或带本机 Origin，都放行。
    """
    origin = request.headers.get("origin")
    if origin and not origin.startswith(
            ("http://127.0.0.1", "http://localhost", "http://[::1]")):
        log.warning("拒绝跨站请求：Origin=%s path=%s", origin, request.url.path)
        return JSONResponse({"detail": "拒绝跨站请求（只允许本机页面调用）"},
                            status_code=403)
    return await call_next(request)


# ── 题目 ──────────────────────────────────────────────────────────────

# 录入序号：key → 在全库里的追加位置（1 开始）。建一次，之后常驻。
_SEQ: dict[str, int] = {}


def _seq_of(key: str) -> int:
    if not _SEQ:
        for i, q in enumerate(store.load_cached(), start=1):
            _SEQ[q.key] = i
    return _SEQ.get(key, 0)


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


def _source_of(q) -> str:
    """卷别（如「新课标I卷」）。试卷上标注来源用的就是它。"""
    return q.meta.get("region") or (q.meta.get("source_label") or "").split("年")[-1]


# `_brief` 要跑块级 IR 解析，一道题几毫秒；17,554 道全跑就是几秒。
# **按内容指纹缓存**：题没改就复用上一次的结果。
# 指纹只覆盖正文，所以改标签不会失效——那正好，标签每次都现算（很便宜）。
# 有上限的 LRU 缓存。
# 审查报告 Important #2：原本是只增不减的 dict，而值里含**解析后的块 IR**，
# 把 17k 道题翻一遍能涨到数百 MB。留最近 2000 道足够（列表翻页/详情往返都命中）。
_BRIEF: "OrderedDict[str, tuple[str, dict]]" = OrderedDict()
_BRIEF_MAX = 2000


def _brief_cached_lite(q) -> dict:
    r"""列表用：**不带答案/解析的块 IR**。

    审查报告 💡#3：列表/卡片只需要题干（卡片画的就是题干），
    答案与解析的块 IR 只有详情页用。而 `parse_blocks` 是纯 CPU ——
    一页 20 题本要跑 60 次解析（题干+答案+解析），现在只跑 20 次。
    详情页走 `/api/questions/{key}` 拿全量（那里才需要）。
    """
    d = _brief_cached(q)
    b = d.get("blocks")
    if isinstance(b, dict):
        d = dict(d)                      # 必须复制：cache 里那份不能改
        d["blocks"] = {"stem": b.get("stem"), "options": b.get("options")}
        d["lite"] = True
    return d


def _brief_cached(q) -> dict:
    h = q.content_hash()
    hit = _BRIEF.get(q.key)
    if hit and hit[0] == h:
        _BRIEF.move_to_end(q.key)
        d = dict(hit[1])
        d.update(_cheap_fields(q))          # 标签/难度/元数据每次现取
        return d
    d = _brief(q)
    _BRIEF[q.key] = (h, d)
    if len(_BRIEF) > _BRIEF_MAX:            # 超上限淘汰最久未用的
        _BRIEF.popitem(last=False)
    return d


# 题干里**明说"如图"却找不到图**——这才是真的缺图。
#
# 早先的判据是"有没有 `\includegraphics`"，于是**每道没图的题都被标成"缺图"**：
def _has_figure(q) -> bool:
    """`图` 这一格：图**不缺**——有图，或者这题本来就不需要图。

    口径已经收到 `Question.figure_ok`（录入干跑/列表共用一套），
    这里只做兼容包装，别再写第二份正则。
    """
    return q.figure_ok


def _has_figure_real(q) -> bool:
    r"""`有图`：**真的有插图**（位图或 TikZ），不管这题需不需要。

    为什么要和 `图` 分开：`图` 是完整度（不需要图也算"不缺"），全库 98% 都是真。
    用户点「只看有·图」要的是真的有图的题（三千道上下），拿 `图` 去筛，
    出来两万八——**条件看着对、结果全不对**，实测被这么报过一次。
    """
    if q.figures:
        return True
    for text in [q.stem, q.solution] + [o.text for o in q.options]:
        if text and ("\\includegraphics" in text or "tikzpicture" in text):
            return True
    return False


def _flags_of(q) -> dict:
    """一道题的 `flags`。**只此一份**——`_brief`/`_cheap_fields`/`_flag_fields`
    三处都要它，各写一遍必然分叉（实测就是这么把 `有图` 漏了的）。"""
    return {
        "答案": bool(q.answer.strip()),
        "解析": q.has_solution,
        "图": _has_figure(q),          # 图不缺（完整度）
        "有图": _has_figure_real(q),    # 真的有图（「只看有」用这个）
        "标签": bool(q.points),
        "小问": "\\begin{enumerate}" in q.stem,
        "存疑": bool(q.meta.get("solve_warn")),
    }


def _flag_fields(q) -> dict:
    r"""筛选**只需要**的字段：`flags`。

    为什么要和 `_cheap_fields` 分开：`_cheap_fields` 里还算了 `problems()`
    和 `point_titles`，两者都要遍历整份题干/解析，全库各约 **929 ms / 327 ms**。
    而 `has=`/`missing=` 这两个筛选项只读 `flags` —— 也就是说
    `/api/questions?has=答案&missing=解析` 一次请求里，**九成以上的时间花在
    没人看的字段上**（实测 1226 ms → 33 ms）。

    只留 `flags` 里的六项判定，它们都是字符串包含/切片，逐题约 1 µs。
    """
    return {
        "flags": _flags_of(q),
    }


def _cheap_fields(q) -> dict:
    """不跑 IR 解析就能拿到的字段。筛选只看这些。"""
    d = {
        "points": q.points,
        "difficulty": q.difficulty,
        "stars": q.stars,
        "point_titles": q.point_titles,
        "meta": q.meta,
        "kind": q.kind,
        "missing": q.missing(),
        "problems": q.problems(),
        "flags": _flags_of(q),
    }
    return d


def _brief(q) -> dict:
    """列表用的精简结构。**完整性信息必须带上**——旧 UI 的病根就是
    "看不出哪些题是半成品"，用户导出后才发现没有解析。

    `blocks` 是**解析好的块级 IR**，前端只负责画，不再碰 LaTeX 语法。
    理由见 `amti/latex_blocks.py` 开头：前端自己解析时，嵌套列表、
    表格列格式、环境配对全错过。
    """
    return {
        "key": q.key,
        "type": q.type,
        "type_label": QTYPE_LABEL.get(q.type, q.type),
        "stem": q.stem,
        "options": [{"label": o.label, "text": o.text} for o in q.options],
        "answer": q.answer,
        "solution": q.solution,
        "blocks": {
            "stem": lb.parse_blocks(q.stem, parts=True),
            "answer": lb.parse_blocks(q.answer),
            "solution": lb.parse_blocks(q.solution),
            "options": [lb.parse_blocks(o.text) for o in q.options],
        },
        "points": q.points,
        # 难度与考点名：界面上要显示、要能筛。难度是**主考点派生**的，
        # 卷面上的难度另按位置算（见 amti/paper.py 的 POSITION_RULE）。
        "difficulty": q.difficulty,
        "stars": q.stars,
        "point_titles": q.point_titles,
        "meta": q.meta,
        "kind": q.kind,
        "hash": q.content_hash(),
        "missing": q.missing(),
        "problems": q.problems(),
        "figures": [f.id for f in q.figures],
        "flags": _flags_of(q),
    }


#: 搜索框的提示语写着「搜索题目、答案、考点、出处」——这四个字段都得真能搜。
_TAG_HAYSTACK_FIELDS = ("id", "title", "topic", "section")


def _tag_ids_matching(kw: str) -> set[str]:
    r"""考点表里**编号／名称／章节／主题**含 `kw` 的考点 id。

    考点表只有 152 条，一次算完；逐题只做一次集合判断。
    别在两万八千道题上逐条拼标签串——`list_questions` 的筛选阶段
    刻意只碰字符串和布尔值（见下面「先筛、先排、先切片，最后才渲染」那段）。
    """
    k = kw.lower()
    out: set[str] = set()
    for node in knowledge.all_points():
        hay = " ".join(str(node.get(f) or "") for f in _TAG_HAYSTACK_FIELDS).lower()
        if k in hay:
            out.add(str(node.get("id")))
    return out


def _source_hit(item, kw: str) -> bool:
    """出处（书名／卷名／卷别／key）含不含这个关键词。大小写不敏感。

    `key` 也要看：`模拟题/2026精选模拟题/004#1` 这类历史 key 里的目录，
    和 `meta.book`/`source_label` 不一定同构；只比 meta 会漏。
    搜索框写的是「出处」，用户会把整条卷名、甚至 `#22` 抄进来。
    """
    k = kw.lower()
    m = item.meta or {}
    if any(k in str(m.get(f) or "").lower()
           for f in ("source_label", "book", "region")):
        return True
    return k in str(getattr(item, "key", "") or "").lower()


def _kw_hit(item, kw: str, tag_ids: set[str], *, deep: bool = False) -> bool:
    r"""关键词命中 **题干／答案／考点标签／出处** 任意一处就算命中。

    搜索框的提示语是「搜索题目、答案、考点、出处」，可后端原来只比了
    `stem` 与 `answer` 两个字段——输「余弦定理」「6.4.2」「解析几何」
    「南通一模」一个都出不来，看上去像标签坏了，其实是检索没查这两类字段。

    **列表与组卷共用这一条**：两边的筛选链本来就是一份逻辑，
    各写一遍必然分叉（改了一处，另一处还是搜不到）。

    `deep=True` 时**连解析一起搜**——只在列表搜索里开；组卷选池不开，
    否则“题干里没提导数、解析里提了一句”的题会被搜进导数卷。
    多词查询按 **AND**：每个词都要在某一处命中（整串比会永远搜不到
    “函数 单调”这种带空格的输入）。
    """
    if not kw:
        return True
    parts = [t for t in re.split(r"[\s,，、;；]+", kw.strip()) if t]
    if len(parts) > 1:
        return all(_kw_hit(item, t, tag_ids, deep=deep) for t in parts)
    if kw in item.stem or kw in item.answer:
        return True
    if deep and kw in (item.solution or ""):
        return True
    if tag_ids & set(item.points or ()):
        return True
    return _source_hit(item, kw)


@app.get("/api/questions")
def list_questions(
    q: str = "", type: str = "", kind: str = "",
    point: str = "",          # 考点 id，逗号分隔，命中任一即可
    difficulty: str = "",     # 难度，逗号分隔
    year: str = "",           # 年份，逗号分隔
    source: str = "",         # 卷别，逗号分隔
    region_scope: str = "",   # single/multi/unknown/book
    paper_state: str = "",    # complete/partial
    star_state: str = "",     # rated/unrated
    quality: str = "",        # dup/lowres
    # 考点标注来源：`无` = 没记来源（早期批量录入），其余按 meta.point_source
    # 精确匹配（llm/human/manual/agent…）。题库体检的「无标签来源」点进来用它。
    point_source: str = "",
    # 答案来源：human / workbuddy / legacy（2026-11-03 回填后每道都有）
    answer_source: str = "",
    # 复核：yes（有 reviewed_at）/ no（人改过答案/解析会自动打复核戳）
    reviewed: str = "",
    has: str = "",            # 逗号分隔：答案,解析,图,标签 → 只列**有**的
    missing: str = "",        # 逗号分隔：只列**缺**的
    sort: str = "",           # "" 原序 / new 新录入 / old 旧录入 / solved 刚解出的
                              # / year 年份新→旧 / year2 年份旧→新
    keys: str = "",           # 逗号分隔的题号 → 只要这些，且**按给定顺序**返回
    # 后端审查报告 Important #1：原本没有上界，而前端就在传 limit=5000。
    # limit=999999 会让服务端构造 17k 条 _brief（每条都要把 LaTeX 解析成
    # 块 IR，纯 CPU），足以让服务卡住几十秒。
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    # 默认**瘦身**：列表只带题干块 IR（答案/解析留给详情页）。
    # 全量校验脚本（`web/check.mjs`）需要答案/解析的块 IR —— 它显式传 lite=0，
    # 并且**分页**取，所以既拿到全量又不会一次压垮服务。
    lite: bool = True,
) -> dict:
    has_set = {x.strip() for x in has.split(",") if x.strip()}
    miss_set = {x.strip() for x in missing.split(",") if x.strip()}
    pt_set = {x.strip() for x in point.split(",") if x.strip()}
    diff_set = {x.strip() for x in difficulty.split(",") if x.strip()}
    year_set = {x.strip() for x in year.split(",") if x.strip()}
    src_set = {x.strip() for x in source.split(",") if x.strip()}
    scope_set = {x.strip() for x in region_scope.split(",") if x.strip()}
    paper_set = {x.strip() for x in paper_state.split(",") if x.strip()}
    star_set = {x.strip() for x in star_state.split(",") if x.strip()}
    quality_set = {x.strip() for x in quality.split(",") if x.strip()}
    ps_filter = point_source.strip()
    as_set = {x.strip() for x in answer_source.split(",") if x.strip()}
    rv_filter = reviewed.strip()
    kw = q.strip()
    # 「搜考点」必须在**进循环之前**算一次：逐题去查 152 条考点表是白干
    tag_ids = _tag_ids_matching(kw) if kw else set()

    # **录入顺序 = 文件里的追加顺序。**
    # `store.append` 只追加，所以遍历顺序天然就是「先录的在前」。
    # 不需要额外的入库时间戳，也不需要改数据。
    rows = list(store.load_cached())

    # **按题号取题**：`keys` 一旦给了就只看这些题，并且**保持给定顺序**。
    # 存档的卷子/合集只存题号（`amti/papers.py`），前端要把它重新摊成
    # 可编辑的题目列表，就得有这么一条"按题号还原"的路。
    # 顺序用给定顺序是**有意的**——卷子里的题目次序是内容的一部分。
    key_list = [x.strip() for x in keys.split(",") if x.strip()]
    if key_list:
        _by_key = {it.key: it for it in rows}
        rows = [_by_key[k] for k in key_list if k in _by_key]

    # ⚠️ **先筛、先排、先切片，最后才渲染。**
    #
    # 老写法对**全部 17,554 道题**都跑一遍 `_brief`（块级 IR 解析，
    # 一道几毫秒），再切片返回 200 条——只要 1 道题也要 3 秒。
    # 现在筛选阶段只碰字符串和布尔值，`_brief` 只对**真正要返回的那一页**跑。
    keep: list = []
    for item in rows:
        if type and item.type != type:
            continue
        # 只分高考/模拟两类，不再按册子筛
        if kind and item.kind != kind:
            continue
        if pt_set and not (pt_set & set(item.points)):
            continue
        if diff_set and item.difficulty not in diff_set:
            continue
        if year_set and str(item.meta.get("year") or "") not in year_set:
            continue
        if src_set and (_source_of(item)) not in src_set:
            continue
        if scope_set:
            sc = item.meta.get("region_scope") or ("single" if item.meta.get("region") else "unknown")
            if sc not in scope_set:
                continue
        if paper_set:
            partial = item.meta.get("paper_complete") is False
            if ("partial" if partial else "complete") not in paper_set:
                continue
        if star_set:
            rated = item.stars > 0
            if ("rated" if rated else "unrated") not in star_set:
                continue
        if quality_set:
            ok = (("dup" in quality_set and item.meta.get("duplicate_group"))
                  or ("lowres" in quality_set and item.meta.get("figure_low_res")))
            if not ok:
                continue
        if ps_filter:
            got = str(item.meta.get("point_source") or "")
            # 「无」是 /api/stats/detail 里 `or "无"` 那个合成组的名字
            if (ps_filter == "无" and got) or (ps_filter != "无" and got != ps_filter):
                continue
        if as_set and str(item.meta.get("answer_source") or "无") not in as_set:
            continue
        if rv_filter:
            rv = bool(item.meta.get("reviewed_at"))
            if (rv_filter == "yes") != rv:
                continue
        if not _kw_hit(item, kw, tag_ids, deep=True):
            continue
        if has_set or miss_set:
            c = _flag_fields(item)
            if has_set and not all(c["flags"].get(k) for k in has_set):
                continue
            if miss_set and not all(not c["flags"].get(k) for k in miss_set):
                continue
        keep.append(item)

    # 有关键词时默认按**相关度**排（仍保留使用频次做同分次序）；
    # 用户明确选了别的排序（年份/难度/录入顺序）就尊重他。
    #
    # 排序分两层：
    #   ① SQLite FTS5 给候选召回的 bm25 名次（中文 2 字也能命中，见 amti/fts.py）；
    #   ② 同一个名次里再用 `search.score` 按“题干 > 考点 > 答案 > 解析”细排。
    # 索引没建好/查询里有 FTS 不认的符号时，`fts_rank` 为空，自动退回纯打分。
    if kw and sort in ("", "used"):
        from amti import search as _se
        fts_rank: dict[str, int] = {}
        try:
            from amti import fts as _fts
            fts_rank = {k: i for i, k in enumerate(_fts.search(kw, limit=3000))}
        except Exception:                                   # noqa: BLE001
            fts_rank = {}
        u = _usage()
        keep.sort(key=lambda q: (fts_rank.get(q.key, 10 ** 9),
                                 -_se.score(q, kw, _source_of(q)),
                                 -u.get(q.key, 0), q.key))
    elif sort == "new":
        keep.reverse()
    elif sort in ("diff", "diff2"):
        # 按难度排。`diff` 是**从易到难**（最常见的诉求：
        # 「我要某个知识点的题，从简单到难排一遍」），`diff2` 反过来。
        from amti.generate import DIFF_ORDER as _D
        keep.sort(key=lambda q: _D.get(q.difficulty, 9),
                  reverse=(sort == "diff2"))
    elif sort == "used":
        # **按使用频次倒序**——老师导出过多次的题（高频题/经典题）
        # 排前面，打开题库默认就能看到。没用过的按原序跟在后面。
        u = _usage()
        keep.sort(key=lambda q: u.get(q.key, 0), reverse=True)
    elif sort == "solved":
        # **按求解时间倒序**——求解任务的产出顺序和录入顺序不一样，
        # 想看"刚解出来的几道"就得按 `solved_at` 排。
        # 没解过的排在最后（空字符串倒序时天然靠后）。
        keep.sort(key=lambda q: (q.meta or {}).get("solved_at") or "", reverse=True)
    elif sort in ("year", "year2"):
        # **按年份排**。`year` = 新→旧，`year2` = 旧→新。
        # 没写年份的题**两档都排在最后**（不能因为 0 最小就在"旧→新"里
        # 跑到最前面，那会让一批无年份的题把开头占满）。
        def _y(q) -> int:
            v = (q.meta or {}).get("year")
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0
        keep.sort(key=lambda q: (_y(q) == 0, -_y(q) if sort == "year" else _y(q)))

    total = len(keep)
    page = keep[offset:offset + limit]
    out = []
    usage = _usage()
    for item in page:
        b = _brief_cached_lite(item) if lite else _brief_cached(item)
        b["seq"] = _seq_of(item.key)
        b["used"] = usage.get(item.key, 0)
        out.append(b)
    return {"total": total, "items": out}


@app.get("/api/questions/{key:path}")
def get_question(key: str) -> dict:
    q = store.find(urllib.parse.unquote(key))
    if not q:
        raise HTTPException(404, f"没有这道题：{key}")
    d = _brief(q)
    d["tex"] = question_to_tex(q)
    d["used"] = _usage().get(q.key, 0)
    return d


# ── 改答案时的格式处理 ────────────────────────────────────────────────
#
# 用户要的是「看到解析但没答案，随手补进去」。随手写的输入五花八门：
# 全角字母、小写、带括号、多打了顿号……所以**统一在这一层规整**，
# 规整不了就明确报错，绝不把半成品写进库。

# 题干里的**作答位置**。有两种写法，比对时都要抹平：
#   · 规范化之后的 `\paren[B]` / `\fillin[$x$]`
#   · 规范化之前的裸括号 `（ ）` / `（\quad）` / `(\qquad)`
#
# 只认前者的话，一道题干写 `（ ）` 的题在补答案时会被护栏判成
# "题干被改了"而拒绝——可那本来就是同一个位置，只是换了写法。
_SLOT = re.compile(
    # `\fillin` 有三种形态，**都要吃掉**：
    #   `\fillin{}`        空的（规范化前）
    #   `\fillin[$18$]`    填好的（规范化后）
    #   `\fillin`          光杆的
    # 早先只认中间那种，于是 `\fillin{}` 被替成占位符后**还剩一个 `{}`**，
    # 而填好的那个替完就没了 `{}`——两边一比就"不一样"，
    # 改答案时被误判成"动了题干"而拒绝。实测踩过。
    r"\\(paren|fillin)\s*(\[[^\]]*\])?\s*(\{[^{}]*\})?"
    r"|[（(]\s*(?:\\quad|\\qquad)?\s*[）)]")


def _content_outside_answer(q) -> tuple:
    r"""**除答案与作答括号之外**的内容快照。

    改答案会正当地改到两处：`answer` 字段，和题干里的 `\paren[…]`／`fillin[…]`。
    除此之外——题干正文、选项、解析、配图——**一个字节都不许变**。
    改完拿这个快照比对，对不上就说明改答案的路上动了别的东西。
    """
    # 两种写法都替换成同一个占位符，并**去掉所有空白**——
    # 我们关心的是"正文有没有被动过"，不是排版空白或作答位置用哪种写法。
    stem = re.sub(r"\s+", "", _SLOT.sub("§", q.stem or ""))
    return (stem, q.solution or "",
            tuple((o.label, o.text) for o in q.options),
            tuple(f.id for f in (q.figures or [])))


def _clean_answer_input(q, raw) -> str:
    r"""把界面上随手写的答案**规整成规范形态**；规整不了就报 400。

    按题型分别处理（这是"注意格式问题"的核心）：

    | 题型 | 收什么 | 规整成 |
    |---|---|---|
    | 单选 | `b` / `Ｂ` / `B、` / `选B` | `B`，**只能一个** |
    | 多选 | `abd` / `A,B,D` / `ABD` | `ABD`，排序去重，2–4 个 |
    | 填空 | 任意结果，如 `$\frac{1}{2}$`、`②③` | 去空白，检查 `$` 配平 |
    | 解答 | 结论文字（一般留空，结论写解析里） | 原样，同样检查 `$` 配平 |

    **不猜**：字母超范围（比如 `E`）、单选题给了两个字母、`$` 不配平——
    一律报错说清楚，而不是硬塞一个进去。
    """
    txt = str(raw or "").strip()
    if not txt:
        return ""                      # 允许清空（等于"这题确实没答案"）

    if q.type in ("single_choice", "multi_choice"):
        # 全角字母先转半角，再去掉所有非 A–D 的字符
        t = "".join(chr(ord(c) - 0xFEE0) if "Ａ" <= c <= "Ｚ" else c for c in txt)
        letters = sorted(set(re.findall(r"[A-Da-d]", t.upper())))
        if not letters:
            raise HTTPException(400, "选择题的答案要写选项字母，比如 B 或 ABD；收到 %r" % txt)
        # 有 E 之后的字母说明写错了（本库选项只有 A–D）
        stray = sorted(set(re.findall(r"[E-Za-z]", t.upper())))
        if stray:
            raise HTTPException(400, "选项只有 A–D，收到 %s" % "、".join(stray))
        if q.type == "single_choice" and len(letters) != 1:
            raise HTTPException(
                400, "这是**单选题**，只能填一个字母；收到 %s。"
                     "如果这题本来就该多选，请先把题型改成多选。" % "".join(letters))
        if q.type == "multi_choice" and len(letters) < 2:
            raise HTTPException(400, "这是**多选题**，至少要两个字母；收到 %s" % "".join(letters))
        return "".join(letters)

    # 填空/解答：结果本身可以是任意 LaTeX，但有两个硬要求
    if txt.count("$") % 2:
        raise HTTPException(400, "答案里的 `$` 个数是奇数（%d 个），数学模式没闭合" % txt.count("$"))
    if _SLOT.search(txt):
        raise HTTPException(400, "答案里不能写 `\\paren`／`\\fillin`——那是题干里的作答位置")
    return txt


# ── 改题型 ────────────────────────────────────────────────────────────
#
# 用户会遇到：**题目其实是多选，却被标成了单选**（选项 B、C、D 都对）。
# 题面里那句「则下列说法正确的是」根本看不出单选还是多选，判错很正常。
#
# 但改题型会**牵动答案的合法性**：
#   单选 → 恰好 1 个字母      多选 → 至少 2 个字母
# 所以这里不许"只改题型"了事——要么现有的答案对新题型也合法，
# 要么在**同一次请求**里把答案一起改好。**绝不悄悄把答案清掉。**
#
# 目前只放开**单选 ↔ 多选**：两者用同一个作答位置 `\paren[…]`，
# 换过去不影响题干。换成填空/解答要动选项和作答位置，那是另一回事，
# 会把题目改残，所以明确拒绝并说明原因。

_CHOICE_TYPES = ("single_choice", "multi_choice")


def _convert_type(q, new_type: str) -> str:
    r"""改题型。返回一句说明；不合法就抛 400。"""
    from amti.schema import QTYPE_LABEL
    if new_type not in QTYPE_LABEL:
        raise HTTPException(400, "没有这个题型：%s（可选：%s）"
                            % (new_type, "、".join(QTYPE_LABEL)))
    old = q.type
    if new_type == old:
        return ""
    if old not in _CHOICE_TYPES or new_type not in _CHOICE_TYPES:
        raise HTTPException(400, (
            "目前只支持**单选 ↔ 多选**互改。%s → %s 要动选项和作答位置，"
            "改下去容易把题目改残——请改题目源文件后重新录入。"
            % (QTYPE_LABEL.get(old, old), QTYPE_LABEL[new_type])))
    # 选择题得有选项，否则改完就是一道空壳
    if len(q.options) < 2:
        raise HTTPException(400, "这道题只有 %d 个选项，不能算选择题" % len(q.options))
    q.type = new_type
    return "%s → %s" % (QTYPE_LABEL[old], QTYPE_LABEL[new_type])


def retry_on_concurrent(fn):
    r"""乐观并发被拒就**自动重跑一遍**这个接口。

    `store.rewrite_all(..., based_on=…)` 在读全库之后、写回之前发现库被别人
    写过（求解器在后台写解析、另一个 `amti.py` 在跑），会抛 `ConcurrentWrite`
    拒绝覆盖。对用户来说那是"保存失败，请重试"—— 但没必要让人手动重试：
    这里重跑整个接口，等于重新读、重新改、重新写。

    重跑是安全的：这两个接口在写回之前**没有任何外部副作用**
    （改的都是内存里那个 Question 对象，写被拒就等于没改过）。

    重跑若干次仍被拒，才回 409 让人稍后再来。
    """
    @functools.wraps(fn)
    def _wrapped(*a, **kw):
        for i in range(4):
            try:
                return fn(*a, **kw)
            except store.ConcurrentWrite:
                if i == 3:
                    break
                time.sleep(0.05 * (i + 1))
        raise HTTPException(
            409, "题库正被别的进程连续写入（多半是后台求解器），"
                 "为避免覆盖别人的改动，这次**没有保存**。请在几秒后再试一次。")
    return _wrapped


def _audit_tag_change(q, *, before: str, fields) -> None:
    r"""把「界面改标签」记一份档。

    只记标签变化，不记正文 —— 正文根本走不到这里（指纹校验会拦住）。
    记档失败**不阻断**修改，但必须留下日志：审查报告 Important #3 指出，
    原本全项目 0 处 logging，"改了但没记录"这种事没人知道。
    """
    from amti.audit import CHANGE_DIR
    try:
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_界面改标签.md" % time.strftime("%Y%m%d_%H%M%S"))
        f.write_text(
            "# 界面改标签\n\n"
            "- 时间：%s\n- 题目：`%s`\n- 改动：%s\n"
            "- 内容指纹：%s → %s（**没变**，改的只是标签）\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), q.key,
               "、".join(sorted(fields)), before, q.content_hash()),
            encoding="utf-8")
    except Exception:
        log.warning("标签变更记档失败（修改已生效）：%s", q.key, exc_info=True)


#: 存档里存的是**题目 key 字符串**（`试卷/存档.json` 的 `keys`、讲义存档的 blocks）。
#: 改 key 不跟着改，那几份卷子/讲义里这一题就**静默消失**——打开只看出来"少一道"，
#: 不报错，也没人知道为什么。
#:
#: `数据/订正台账.json` 也存 key（`patches[].key`、`retired[]`）。不迁的话，
#: 台账里多出一批死账，而 `fixups.run` 是「一条对不上就整批不执行」——
#: 1252 条待办全被卡住（`脚本/批量改出处.py` 把这一条列为必迁落点）。
_KEY_REF_FILES = ("试卷/存档.json", "讲义/讲义存档.json", "数据/订正台账.json")

#: 改名台账：`store.diff()` 读它，把「改了个名字」和「删一道 + 加一道」分开。
#: 不记的话，每改一次出处，顶栏的「删除」就红一次——那样的红灯很快就没人看了。
#: 路径**只有一处**（`store.RENAME_LEDGER`），这里只引用，别写第二份。


def _migrate_key_refs(old: str, new: str) -> list[str]:
    r"""把存档里引用的 `old` 换成 `new`。返回改到的文件（相对路径）。

    只做**整串替换**（连引号一起比），不解析结构：
    存档是给人看的 JSON，重排一遍会把 diff 弄得面目全非。
    改完**必须仍能 `json.loads`**，否则宁可不动——那说明替换改坏了文件。
    """
    a = json.dumps(old, ensure_ascii=False)
    b = json.dumps(new, ensure_ascii=False)
    hit: list[str] = []
    for rel in _KEY_REF_FILES:
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if a not in t:
            continue
        t2 = t.replace(a, b)
        try:
            json.loads(t2)
        except ValueError:
            log.warning("改出处：%s 里替换后不是合法 JSON，跳过（引用会留在旧 key 上）", rel)
            continue
        try:
            p.write_text(t2, encoding="utf-8")
            hit.append(rel)
        except OSError:
            log.warning("改出处：写 %s 失败", rel, exc_info=True)
    return hit


def _migrate_usage(old: str, new: str) -> None:
    r"""改出处 = 改 key：把「被组过几次」也跟着迁到新 key。

    `数据/使用频次.json` 按 key 记次数。不迁的话，改一次出处这道题的
    「用过 N 次」就归零——默认排序按使用频次，用户会发现「我常用的题不见了」。

    **内存缓存必须一起改**：`_usage()` 只读一次盘，缓存里还是旧 key 的话，
    下次 `_usage_bump` 会把旧 key 写回文件，等于把迁移覆盖掉。
    """
    with _usage_lock:
        d = _usage()
        if old not in d:
            return
        n = d.pop(old)
        d[new] = d.get(new, 0) + n
        try:
            USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            USAGE_PATH.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True),
                                  encoding="utf-8")
        except OSError:
            log.warning("改出处：使用频次迁移写盘失败（改名已生效）", exc_info=True)


def _migrate_meta_refs(qs, old: str, new: str) -> int:
    r"""把**别的题 meta 里指向旧 key 的引用**换成新 key。

    `dup_of`（和谁雷同）、`also_in`（还出现在哪）、`merged_keys`（合并过谁）
    存的是题目 key。改出处换了 key 而这里不换，查重提示/孪生题对账就会
    指向一道不存在的题（`semantic.py` 会报 `dup_of_dangling`）。
    返回改了几处。
    """
    n = 0
    for x in qs:
        m = x.meta if isinstance(getattr(x, "meta", None), dict) else {}
        if m.get("dup_of") == old:
            m["dup_of"] = new
            n += 1
        for f in ("also_in", "merged_keys"):
            v = m.get(f)
            if isinstance(v, list) and old in v:
                m[f] = [new if z == old else z for z in v]
                n += 1
    return n


def _audit_key_rename(old: str, new: str) -> None:
    r"""记两笔：给程序读的台账 + 给人读的报告。**失败不阻断**。"""
    try:
        led = ROOT / store.RENAME_LEDGER
        led.parent.mkdir(parents=True, exist_ok=True)
        with led.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "from": old, "to": new}, ensure_ascii=False) + "\n")
    except OSError:
        log.warning("改出处台账写入失败（改名已生效）：%s", old, exc_info=True)
    try:
        from amti.audit import CHANGE_DIR
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f2 = CHANGE_DIR / ("%s_界面改出处.md" % time.strftime("%Y%m%d_%H%M%S"))
        f2.write_text(
            "# 界面改出处\n\n- 时间：%s\n- 原 key：`%s`\n- 新 key：`%s`\n"
            "- 内容指纹：**没变**（改的只是出处）\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), old, new), encoding="utf-8")
    except Exception:
        log.warning("改出处记档失败（改名已生效）：%s", old, exc_info=True)


@app.patch("/api/questions/{key:path}")
@retry_on_concurrent
def patch_question(key: str, body: dict) -> dict:
    r"""改标签：**考点**和**难度**。

    权威入口是 `store.rewrite_volume`（MIGRATE 级的那个），
    因为改标签必须落到主文件里才算数。安全性由指纹保证：

        内容指纹只覆盖 题干/选项/答案/解析/配图，
        **标签与元数据不在其中**（`schema.HASH_FIELDS`）。

    所以这个接口**改不动一道题的正文**——就算传了别的字段也白传。
    改完把新指纹回给前端，对不上就说明碰了不该碰的。

    请求体（字段都可选）：
        {"points": ["3.2.2","3.2.1"],   # 考点 id，第一条是主考点
         "difficulty": "难题",           # 空字符串 = 恢复成按主考点派生
         "stars": 3,
         "answer": "B",                  # **补答案**
         "type": "multi_choice",         # **改题型**（目前只放开 单选↔多选）
         "source": {"book": "…", "label": "…", "year": 2027,
                    "region": "…", "no": 22}}
                                         # **改出处**：改完 key 跟着改；
                                         # `no` 是题号（key 里 `#` 后面那截）
    """
    # ⚠️ **白名单：只有这几个字段能改，其余一律拒绝。**
    #
    # 界面上「考点」「难度」「出处」是标签，改它们是日常操作；
    # **题目正文（题干/选项/答案/解析/配图）一个字都不许从界面改**——
    # 那是数据，改它要走「改题目 → 重新录入」的正规路径，
    # 而且要过规范验证、查重、影响面这几关。
    #
    # 老写法是「只读认识的字段、其余静默忽略」——安全，但**不响**：
    # 有人想改题干，接口回 200，他会以为改成功了。
    # 现在直接 400 说清楚。
    ALLOWED = {"points", "difficulty", "stars", "answer", "type", "source",
               "reviewed"}
    unknown = set(body) - ALLOWED
    if unknown:
        raise HTTPException(400, (
            "只允许改 %s；收到 %s。"
            "题目正文（题干/选项/解析/配图）**不能从界面改**——"
            "要改请改题目源文件后重新录入。"
            "（**答案**可以改，见 `answer`。）"
            % ("、".join(sorted(ALLOWED)), "、".join(sorted(unknown)))))

    k = urllib.parse.unquote(key)
    qs, _sig = store.load_for_update()
    q = next((x for x in qs if x.key == k), None)
    if q is None:
        raise HTTPException(404, f"没有这道题：{k}")

    before = q.content_hash()
    # 改答案会**有意**改到正文（答案在指纹里，题干里的作答括号也要跟着变），
    # 所以单独记一份"**除答案和作答括号之外**"的内容快照。
    # 改完拿它比对：只要题干正文、选项、解析、配图有一个字节变了，就拒绝。
    content_before = _content_outside_answer(q)
    if "points" in body:
        pts = [str(p).strip() for p in (body.get("points") or []) if str(p).strip()]
        bad = [p for p in pts if p not in knowledge._index()]
        if bad:
            raise HTTPException(400, "考点不存在：%s" % "、".join(bad))
        q.points = pts
        # 人工改过的标签，来源标成 human —— 以后一眼能看出哪些不是模型打的
        q.meta["point_source"] = "human"
    if "difficulty" in body:
        d = (body.get("difficulty") or "").strip()
        if d:
            q.meta["difficulty"] = d
        else:
            q.meta.pop("difficulty", None)      # 恢复成按主考点派生
    if "stars" in body:
        try:
            n = int(body["stars"])
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            q.meta["stars"] = n
        else:
            q.meta.pop("stars", None)

    # ── 出处（书 / 卷名 / 年份 / 地区）──────────────────────────────
    #
    # 用户的要求：「录入时填错了出处，录完就改不回来了」。
    # 难点不在改 meta —— 在 **key**：`书/卷名#序号` 是自然键，改出处就得改名。
    # 改名要连带三件事，缺一件就是静默损坏：
    #   ① 查重（新 key 不能已存在）
    #   ② 迁引用（`试卷/存档.json`、`讲义/讲义存档.json` 里存的是 key 字符串）
    #   ③ 记账（`数据/改出处.jsonl`）——`store.diff()` 靠它把"改名"和
    #      "一道题被删、另一道题被加"区分开；不记的话顶栏每改一次出处就红一次
    renamed_from = ""
    if "source" in body:
        src = body.get("source")
        if not isinstance(src, dict):
            raise HTTPException(400, "source 要给对象：{book, label, year, region, no}")
        unknown = set(src) - {"book", "label", "year", "region", "no"}
        if unknown:
            raise HTTPException(400, "source 里不认识的字段：%s"
                                % "、".join(sorted(unknown)))
        book = str(src.get("book", (q.meta or {}).get("book", "")) or "").strip()
        label = str(src.get("label", (q.meta or {}).get("source_label", "")) or "").strip()
        if not book or not label:
            raise HTTPException(400, "来源（书）和出处（卷名）都不能空")
        # key 是 `书/卷名#序号`，这三样里出现分隔符会把 key 结构弄坏
        for bad in ("/", "#"):
            if bad in book or bad in label:
                raise HTTPException(400, "来源/出处里不能有 `%s`（key 的分隔符）" % bad)
        # **题号**（key 里 `#` 后面那截）也能和出处一起改：出处录错时，
        # 「第几题」往往跟着错。统一成不带前导零的正整数——库里的 key
        # 尾串统一成不带前导零的正整数，排序与比较才可靠。
        tail = key.rsplit("#", 1)[-1] if "#" in key else "1"
        head = key.rsplit("#", 1)[0] if "#" in key else key
        new_tail = tail
        if "no" in src:
            raw_no = src.get("no")
            new_tail = str(raw_no).strip()
            if not new_tail.isdigit() or int(new_tail) < 1:
                raise HTTPException(400, "题号要是正整数，收到 %r" % (raw_no,))
            new_tail = str(int(new_tail))
        # ⚠️ **改名判据要拿改名前的书/卷名**：下面 q.meta 会被覆盖，
        # 覆盖之后再取等于拿新值跟旧 key 比——那永远不会同构，改名就静默失效。
        old_book = str((q.meta or {}).get("book", "") or "")
        old_label = str((q.meta or {}).get("source_label", "") or "")
        q.meta["book"] = book
        q.meta["source_label"] = label
        year = src.get("year", (q.meta or {}).get("year", ""))
        if str(year).strip():
            try:
                q.meta["year"] = int(str(year).strip())
            except ValueError:
                raise HTTPException(400, "年份要是整数，收到 %r" % (year,))
        else:
            q.meta.pop("year", None)
        region = str(src.get("region", (q.meta or {}).get("region", "")) or "").strip()
        if region:
            q.meta["region"] = region
        else:
            q.meta.pop("region", None)

        # **只有 key 本来就是 `书/卷名#号` 拼出来的，才跟着改名。**
        # 反例（真踩过）：`高考真题汇编/2024/新高考I卷#1` 的出处是
        # `2024年新高考I卷`——key 里多一层年份目录，和出处**不同构**。
        # 按 meta 重拼 key 会把它改成 `书/2024年新高考I卷#1`，等于
        # 悄悄给这道题换了身份：基线上的旧 key 变成"被删了"，
        # 组进卷子里的引用也跟着断。宁可只改标签，把 key 留着。
        #
        # 但**题号是用户明确改的**：不同构的 key 也要换掉 `#` 后面那截，
        # 否则界面上改了题号、卷子里还印旧号。目录（head）一个字不动。
        if head == "%s/%s" % (old_book, old_label):
            new_key = "%s/%s#%s" % (book, label, new_tail)
        else:
            new_key = key if new_tail == tail else "%s#%s" % (head, new_tail)
        if new_tail != tail:
            # 卷面/讲义印的「第 N 题」优先读 `meta.source_no`
            # （见 `render_tex.source_tag`）——只改 key 不改它，印出来还是旧题号。
            q.meta["source_no"] = new_tail
        if new_key != q.key:
            if any(x is not q and x.key == new_key for x in qs):
                raise HTTPException(409, "已经有这道题了：%s（出处不能重名，"
                                         "同一卷的多道题请用不同题号）" % new_key)
            renamed_from = q.key
            q.key = new_key
            # 改名是**有意动数据**：和别的"界面补录"一样盖时间戳，
            # 免得 `store.diff()` 把它报成"内容变化"
            q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    if "reviewed" in body:
        # 复核只动 meta：标记“人看过答案/解析了”，不改正文、不改指纹
        if body["reviewed"]:
            q.meta["reviewed_at"] = time.strftime("%Y-%m-%d %H:%M")
        else:
            q.meta.pop("reviewed_at", None)

    type_note = ""
    if "type" in body:
        type_note = _convert_type(q, str(body.get("type") or "").strip())
        if type_note:
            q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    if "answer" in body:
        new_ans = _clean_answer_input(q, body.get("answer"))
        q.answer = new_ans
        q.meta["answer_source"] = "human"       # 人补的，和求解器写的分开记
        q.meta["reviewed_at"] = time.strftime("%Y-%m-%d %H:%M")
        # **盖时间戳**：`store.diff()` 靠它把"界面补录"和"规则偷偷动数据"分开。
        # 不盖的话，你在界面上改一道答案，顶栏就报一次"⚠ 内容变化"——
        # 自己改的东西被当成异常，那这个报警很快就没人看了。
        q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
        # **格式问题就出在这一步**：答案要写进题干的 `\paren[…]`／`\fillin[…]`，
        # 否则卷面上不出现作答括号、答案也没地方显示。
        from amti import normalize as _norm
        _norm.normalize(q, _norm.ENTRY)

    # 改了题型但**没同时给答案**时，现有的答案必须对新题型也合法。
    # 否则会出现"单选题只剩一个字母却标成多选"这种自相矛盾的状态。
    if type_note and "answer" not in body and q.answer.strip():
        try:
            _clean_answer_input(q, q.answer)
        except HTTPException:
            q.type = "multi_choice" if q.type == "single_choice" else "single_choice"
            raise HTTPException(400, (
                "现在这个答案是 %r，改成%s后不合法。"
                "改题型时要**同时**把答案改好（比如把 B 改成 BD）。"
                % (q.answer, "多选题" if q.type == "single_choice" else "单选题")))

    # 没改答案/题型时，指纹必须**一个字节都没变**（改标签不该动正文）
    if "answer" not in body and "type" not in body and q.content_hash() != before:
        raise HTTPException(500, "内容指纹变了——说明动到了正文，已拒绝")
    # 改答案时：除答案与作答括号之外，正文必须一个字节都没变
    if ("answer" in body or "type" in body) and _content_outside_answer(q) != content_before:
        raise HTTPException(500, "改答案时动到了题干正文/选项/解析，已拒绝")

    # **规范审查**：改完必须仍然合规，否则不存。
    # 答案写错格式（`$` 不配平、把 `\paren` 塞进答案里…）在这里被挡住。
    from amti import conform as _cf
    viol = _cf.run([q])
    if viol:
        raise HTTPException(400, "改完不规范，没有保存：%s（%s/%s）"
                            % (viol[0]["why"], viol[0]["check"], viol[0]["field"]))

    # 改名的**跨题引用**也一起迁（`dup_of`/`also_in`/`merged_keys` 存的是
    # 别的题的 key）；必须在整库重写之前改，才会跟着落盘。
    if renamed_from:
        _migrate_meta_refs(qs, renamed_from, q.key)

    # ⚠️ 用 rewrite_all（**按 PER_VOLUME 重新分卷**），不要用 rewrite_volume(1,…)：
    # 后者会把所有卷的题都写进第 1 卷，而其它卷还在 → 整库重复。
    #
    # `based_on` 是乐观并发校验：读全库之后、写回之前若求解器/别的进程写了库，
    # 这次保存会被**拒绝**而不是把人家的写入覆盖掉。
    # ⚠️ **不要在这里 catch**：`@retry_on_concurrent` 靠捕获 `ConcurrentWrite`
    # 自动重跑一遍。在这里转成 HTTPException 的话装饰器永远接不到，
    # 「自动重试」形同虚设（复核时发现的）。
    _changed = [key, q.key] + ([renamed_from] if renamed_from else [])
    store.rewrite_all(qs, based_on=_sig,
                      changed_keys=list(dict.fromkeys(_changed)))

    # **记档**：标签是人工改的，要留痕（只记标签，不记正文）
    _audit_tag_change(q, before=before, fields=body)

    # 改名才有的三件事：存档里的引用跟着改、使用频次跟着迁、台账记一笔
    if renamed_from:
        moved = _migrate_key_refs(renamed_from, q.key)
        _migrate_usage(renamed_from, q.key)
        _audit_key_rename(renamed_from, q.key)
        log.info("改出处：%s → %s（引用已迁：%s）", renamed_from, q.key,
                 "、".join(moved) or "无")

    d = _brief(q)
    d["tex"] = question_to_tex(q)
    if renamed_from:
        # 前端拿它把选中项/列表里那条旧 key 换掉（否则右栏会停在旧 key 上）
        d["renamed_from"] = renamed_from
    return d


class BatchTagBody(BaseModel):
    r"""批量改标签：列表里勾 N 道，一次改完、**一次写盘**。

    以前只能一道一道开详情改，16 道就是 16 次“读全库 + 写 6 卷”。
    这里只放开标签字段（考点/难度/星级/年份/地区/书/卷名），
    正文（题干/选项/解析/答案）仍然只能走单题详情或重新录入——
    批量接口不该成为绕过规范审查的后门。
    """
    model_config = {"extra": "forbid"}     # 传 stem/solution 进来直接 422，不静默忽略
    keys: list[str]
    points: list[str] | None = None        # 整组替换；[] = 清空
    difficulty: str | None = None          # '' = 恢复按主考点派生
    stars: int | None = None               # 0 = 恢复按主考点派生
    year: int | str | None = None          # '' / 0 = 清空
    region: str | None = None              # '' = 清空
    book: str | None = None                # 改书名（和 label 一起给）
    label: str | None = None               # 改卷名
    reviewed: bool | None = None           # 标记/取消“已复核”


@retry_on_concurrent
@app.post("/api/questions/batch")
def batch_patch(body: BatchTagBody) -> dict:
    r"""批量改标签（**一次写回**）。语义与 `patch_question` 的单题标签一致。

    · 只改标签，不碰正文；改完仍要过 `conform`，不过就整批不写。
    · 改书名/卷名时按单题同一条规则重拼 key：只有 key 本来就是
      `书/卷名#号` 拼出来的才改，`高考真题汇编/2024/新高考I卷#1` 这种
      “多一层目录”的保持原 key，只改 meta（和单题一致）。
    · 改名撞车 → 整批 409，不写一半。
    """
    from amti import conform as _cf
    if not body.keys:
        raise HTTPException(400, "keys 不能为空")
    keys = list(dict.fromkeys(body.keys))
    if len(keys) > 500:
        raise HTTPException(400, "一次最多改 500 道（再多就分批）")
    fields = {k for k in ("points", "difficulty", "stars", "year", "region",
                          "book", "label", "reviewed")
              if getattr(body, k) is not None}
    if not fields:
        raise HTTPException(400, "没有给任何要改的字段")

    if body.points is not None:
        idx = knowledge._index()
        unknown = [p for p in body.points if p not in idx]
        if unknown:
            raise HTTPException(400, "不认识的考点：%s" % "、".join(unknown[:5]))
    if body.difficulty not in (None, "", "简单题", "中档题", "难题"):
        raise HTTPException(400, "难度只能是 简单题/中档题/难题/空")
    if body.stars is not None and not (0 <= body.stars <= 4):
        raise HTTPException(400, "星级只能是 0–4（0 = 按考点派生）")

    qs, sig = store.load_for_update()
    by = {q.key: q for q in qs}
    missing = [k for k in keys if k not in by]
    if missing:
        raise HTTPException(404, "有 %d 道题找不到：%s"
                            % (len(missing), "、".join(missing[:3])))

    stamp = time.strftime("%Y-%m-%d %H:%M")
    touched = []
    renamed: list[tuple[str, str]] = []
    taken = set(by)                     # 本批改名后的 key 也要占位，避免批内撞车
    for k in keys:
        q = by[k]
        if body.points is not None:
            q.points = list(body.points)
        if body.difficulty is not None:
            if body.difficulty:
                q.meta["difficulty"] = body.difficulty
            else:
                q.meta.pop("difficulty", None)
        if body.stars is not None:
            if body.stars:
                q.meta["stars"] = body.stars
            else:
                q.meta.pop("stars", None)
        if body.year is not None:
            ys = str(body.year).strip()
            if ys in ("", "0"):
                q.meta.pop("year", None)
            else:
                try:
                    q.meta["year"] = int(ys)
                except ValueError:
                    raise HTTPException(400, "年份要是整数：%r" % (body.year,))
        if body.region is not None:
            if body.region.strip():
                q.meta["region"] = body.region.strip()
            else:
                q.meta.pop("region", None)
        if body.reviewed is not None:
            if body.reviewed:
                q.meta["reviewed_at"] = stamp
            else:
                q.meta.pop("reviewed_at", None)

        if body.book is not None or body.label is not None:
            old_book = str(q.meta.get("book") or "")
            old_label = str(q.meta.get("source_label") or "")
            new_book = (body.book if body.book is not None else old_book).strip()
            new_label = (body.label if body.label is not None else old_label).strip()
            if not new_book or not new_label:
                raise HTTPException(400, "书 / 卷名不能为空：%s" % k)
            q.meta["book"] = new_book
            q.meta["source_label"] = new_label
            head, _, tail = k.rpartition("#")
            # 和 patch_question 同一条判据：拿**改名前的**书/卷名比
            if head and head == "%s/%s" % (old_book, old_label):
                new_key = "%s/%s#%s" % (new_book, new_label, tail)
            else:
                new_key = k
            if new_key != q.key:
                if new_key in taken and new_key != k:
                    raise HTTPException(409, "改名撞车：%s" % new_key)
                _migrate_meta_refs(qs, k, new_key)
                taken.discard(k)
                taken.add(new_key)
                q.key = new_key
                renamed.append((k, new_key))

        q.meta["edited_at"] = stamp
        touched.append(q)

    viol = _cf.run(touched)
    if viol:
        v = viol[0]
        raise HTTPException(400, "改完不规范，没有保存：%s（%s/%s）"
                            % (v["why"], v["check"], v["field"]))

    all_changed = list(dict.fromkeys(
        [k for k in keys] + [q.key for q in touched]))
    rep = store.rewrite_all(qs, based_on=sig, changed_keys=all_changed)

    # 改名后的跨文件引用迁移（存档/讲义/台账）+ 使用频次；写成功之后才做
    for old, new in renamed:
        _migrate_key_refs(old, new)
        _migrate_usage(old, new)
        _audit_key_rename(old, new)

    from amti.audit import CHANGE_DIR
    try:
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_批量改标签.md" % time.strftime("%Y%m%d_%H%M%S"))
        rmap = dict(renamed)
        lines = ["- `%s`%s" % (k, (" → `%s`" % rmap[k]) if k in rmap else "")
                 for k in keys]
        f.write_text(
            "# 批量改标签\n\n- 时间：%s\n- 题目：%d 道\n- 字段：%s\n"
            "- 改名：%d 道\n\n%s\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), len(touched),
               "、".join(sorted(fields)), len(renamed), "\n".join(lines)),
            encoding="utf-8")
    except Exception:
        log.warning("批量改标签记档失败（修改已生效）", exc_info=True)

    return {"ok": True, "changed": len(touched), "renamed": len(renamed),
            "volumes": rep.get("volumes"), "partial": rep.get("partial", False)}


# ── 补解析／补答案 ────────────────────────────────────────────────────
#
# 用户的原话：「没有解析也没有答案，我可以在题目界面直接录入 latex 代码，
# 经规范审查后，可以把解析写入，答案我也可以录进去了」。
#
# 这是**从界面改正文**，比改答案重，所以按录入那条路的规矩来，一步不少：
#
#     ① 规范化   过一遍 `normalize`（答案进作答括号、行间公式去壳…）
#     ② 规范审查 `conform` 必须 0 违规
#     ③ 落盘     写库 + 记 `变更记录/`
#
# **仍然改不了题干和选项**——那两个字段不在这个接口的射程里。
# 题干是题目的本体，改它等于换了一道题，必须走重新录入。

# ── 从整份文档里取出解析 ──────────────────────────────────────────────
#
# 用户是**直接粘整份 `.tex`** 的：`\documentclass`、`\usepackage`、
# `\begin{document}`、题目环境、解析环境全在里面。原样塞进 `solution`
# 会被规范检查拦住（`\documentclass` 会当正文渲染成一堆反斜杠）——
# 拦得对，但对用户没用：他要的是"贴进去就能用"。
#
# 所以这里把**解析那一段**取出来，其余部分丢掉。

_SOL_ENV = re.compile(r"\\begin\{solution\}(.*?)\\end\{solution\}", re.S)
_DOC_ENV = re.compile(r"\\begin\{document\}(.*?)\\end\{document\}", re.S)
_PREAMBLE = re.compile(
    r"\\(documentclass|usepackage|RequirePackage|geometry|examsetup)"
    r"\s*(\[[^\]]*\])?\s*\{[^}]*\}")
_Q_ENV = re.compile(r"\\begin\{question\}(.*?)\\end\{question\}", re.S)
# 解里若混进选题的 `choices`，说明取错了范围
_CHOICES = re.compile(r"\\begin\{choices\}")


def _extract_solution(raw: str) -> tuple[str, list[str]]:
    r"""把用户贴进来的东西**规整成纯解析正文**。返回 (正文, 做了什么)。

    处理顺序（每一步都记进 `notes`，干跑时给人看）：

      ① 有 `\begin{solution}…\end{solution}` → 只取里面
      ② 有 `\begin{document}…\end{document}`   → 只取里面
      ③ 去掉导言区命令（`\documentclass`／`\usepackage`…）
      ④ 若还剩 `\begin{question}…\end{question}` → 整段丢掉
         （那是题面，不是解析；**解析里不该有题面**）

    只认这几种，别的**不猜**：剩下的内容照原样交给规范器去审。
    """
    notes: list[str] = []
    t = raw or ""

    m = _SOL_ENV.search(t)
    if m:
        t = m.group(1)
        notes.append("从 `\\begin{solution}…\\end{solution}` 里取出解析")
    else:
        m2 = _DOC_ENV.search(t)
        if m2:
            t = m2.group(1)
            notes.append("从 `\\begin{document}…\\end{document}` 里取出正文")

    t2, n = _PREAMBLE.subn("", t)
    if n:
        t = t2
        notes.append("去掉了 %d 条导言区命令" % n)

    t2, n = _Q_ENV.subn("", t)
    if n:
        t = t2
        notes.append("去掉了 %d 个题目环境（那是题面，不该进解析）" % n)

    if _CHOICES.search(t):
        notes.append("⚠ 解析里还留着 `choices` 环境——请确认取的范围对不对")

    return t.strip(), notes


# 从解析里**读**答案（不是解题）。只认明说的写法，读不到就留空。
_ANS_BOXED = re.compile(r"\\boxed\{\\text\{([^}]*)\}\}|\\boxed\{([^}]*)\}")
_ANS_SAID = re.compile(r"(?:故选|答案为|答案[：:])\s*([A-D](?:\s*[、,，]?\s*[A-D])*)")


def _answer_from_solution(sol: str, q) -> str:
    r"""解析里明写了答案就顺手读出来。**读不到就返回空**，不猜。

    用户的原文以 `\boxed{\text{A、B、C}}` 收尾——这种一眼能看出来的，
    没必要让人再手填一遍。
    """
    if not sol:
        return ""
    m = _ANS_BOXED.search(sol)
    if m:
        txt = m.group(1) or m.group(2) or ""
        letters = "".join(sorted(set(re.findall(r"[A-D]", txt.upper()))))
        if letters:
            return letters
    m = _ANS_SAID.search(sol)
    if m:
        letters = "".join(sorted(set(re.findall(r"[A-D]", m.group(1).upper()))))
        if letters:
            return letters
    return ""


class SolutionBody(BaseModel):
    solution: str = ""
    answer: str = ""
    dry_run: bool = True                # 默认只审不写


@app.post("/api/questions/{key:path}/solution")
@retry_on_concurrent
def question_solution(key: str, body: SolutionBody) -> dict:
    r"""补/改**解析与答案**。默认干跑，`dry_run=false` 才落盘。"""
    from amti import conform as _cf
    from amti import normalize as _norm

    k = urllib.parse.unquote(key)
    qs, _sig = store.load_for_update()
    q = next((x for x in qs if x.key == k), None)
    if q is None:
        raise HTTPException(404, "没有这道题：%s" % k)

    # 在一份**副本**上试，干跑和落盘走的是同一条路——
    # 不然"预览看到的"和"真写进去的"就不是一个东西了。
    from copy import deepcopy
    t = deepcopy(q)

    before_viol = [{"check": v["check"], "why": v["why"], "field": v["field"]}
                   for v in _cf.run([t])]

    notes: list[str] = []
    if body.solution.strip():
        # **贴整份文档也认**：把解析那一段取出来，导言区和题面丢掉
        sol, notes = _extract_solution(body.solution)
        if not sol.strip():
            return {"ok": False, "saved": False, "error":
                    "没找到解析内容。可以贴整份文档（含 \begin{solution}…），"
                    "也可以只贴解析正文。", "notes": notes}
        t.solution = sol
    # 答案：手填的优先；没填就从解析里读（只认明写的写法）
    if body.answer.strip():
        t.answer = _clean_answer_input(t, body.answer)
    elif t.solution:
        got = _answer_from_solution(t.solution, t)
        if got:
            t.answer = _clean_answer_input(t, got)
            notes.append("从解析里读出了答案：%s" % got)

    fixed = _norm.normalize(t, _norm.ENTRY)         # ① 规范化
    after_viol = [{"check": v["check"], "why": v["why"], "field": v["field"]}
                  for v in _cf.run([t])]            # ② 规范审查
    if after_viol:
        return {"ok": False, "saved": False,
                "before": before_viol, "fixed": fixed, "after": after_viol,
                "error": "规范审查没通过：%s（%s）"
                         % (after_viol[0]["why"], after_viol[0]["check"])}

    if body.dry_run:
        return {"ok": True, "saved": False, "before": before_viol,
                "fixed": fixed, "after": [], "solution": t.solution,
                "answer": t.answer, "stem": t.stem, "notes": notes}

    # ③ 落盘。**改的只能是解析和答案**，别的字段一个字都不许动。
    #
    # ⚠️ 题干要**先抹掉作答括号再比**：规范化本来就会把答案写进
    # `\paren[…]`／`\fillin[…]`（这正是「答案进作答括号」那条规则干的事），
    # 拿原样题干去比必然误报。除掉这个位置之后，正文才是一个字节都不许变。
    def _guard_of(x):
        return (_content_outside_answer(x)[0],
                [(o.label, o.text) for o in x.options],
                [f.id for f in (x.figures or [])],
                list(x.points))

    guard = _guard_of(q)
    old_sol, old_ans, old_stem = q.solution, q.answer, q.stem
    q.solution, q.answer = t.solution, t.answer
    # ⚠️ **题干也要跟着规范化后的走**。
    # 「答案进作答括号」改的正是题干（往里插 `\paren[B]`）——只拷答案不拷题干的话，
    # 这条规则白做，卷面上不出现作答括号、答案也没地方显示。
    # 安全性由上面那道 `_guard_of` 保证：除作答位置外，题干正文一个字节都没变。
    q.stem = t.stem
    if _guard_of(q) != guard:
        q.solution, q.answer, q.stem = old_sol, old_ans, old_stem   # 回滚
        raise HTTPException(500, "改解析时动到了题干正文/选项/配图/考点，已拒绝")
    q.meta["solution_source"] = "human"
    q.meta["reviewed_at"] = time.strftime("%Y-%m-%d %H:%M")
    if body.answer.strip():
        q.meta["answer_source"] = "human"
    q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    # 同 patch_question：**交给 @retry_on_concurrent 处理**，别在这里转 409，
    # 否则装饰器永远接不到 ConcurrentWrite、自动重试失效。
    store.rewrite_all(qs, based_on=_sig, changed_keys=[q.key])

    try:
        from amti.audit import CHANGE_DIR
        import time as _t
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_界面补解析.md" % _t.strftime("%Y%m%d_%H%M%S"))
        f.write_text(
            "# 界面补解析\n\n- 时间：%s\n- 题目：`%s`\n"
            "- 解析：%d → %d 字\n- 答案：%r → %r\n"
            "- 规范化改动：%s\n- 规范审查：通过（0 违规）\n"
            % (_t.strftime("%Y-%m-%d %H:%M:%S"), q.key,
               len(old_sol or ""), len(q.solution or ""), old_ans, q.answer,
               "、".join(fixed) if fixed else "无"),
            encoding="utf-8")
    except Exception:
        log.warning("解析变更记档失败（修改已生效）：%s", "", exc_info=True)
        pass

    d = _brief(q)
    d["tex"] = question_to_tex(q)
    d.update({"ok": True, "saved": True, "before": before_viol,
              "fixed": fixed, "after": [], "notes": notes})
    return d


# ── 改源码 ────────────────────────────────────────────────────────────
#
# 详情页的「改源码」：把整道题的 LaTeX 正文（`\begin{question}…\end{question}`）
# 拿来直接改。**不设口令**（用户明确说没必要）：打开就是编辑器；
# 安全性由下面几道校验兜住，而不是靠多输一次密码——
#   · 只改正文，`%% @q` 元数据行不进来（key/出处/考点不会被手改坏）；
#   · 解析 → 规范化 → 规范审查，结构/格式不过一律不写；
#   · `expect_hash` 防并发覆盖；`store.update` 的写锁 + 临时文件 + rename
#     保证不会写半截。
#
# 保存走 `store.update`：读全库、改这一道、整库写回都在同一把锁里，
# 不会覆盖别人同时写进来的题。`expect_hash` 再挡一层「这道题本身被改过」。

class SourceBody(BaseModel):
    tex: str | None = None             # 不给 = 把当前源码发回来
    dry_run: bool = True               # 默认只检查不写盘
    expect_hash: str = ""              # 打开编辑器时那道题的内容指纹


def _source_candidate(old, tex: str):
    r"""界面上的源码 → 一道题。**只碰正文，元数据一律沿用库里的。**

    返回 `(候选题, 改之前的问题, 规范化改动, 复核后的问题, 结构问题)`。
    解析不出来直接 400 —— 这种情况没有"部分成功"可言。
    """
    from amti import conform as _cf
    from amti import normalize as _norm
    from amti.latex_ir import parse_question

    text = (tex or "").strip()
    # 用户可能把 `%% @q` 那行一起贴回来；元数据不在编辑范围内，直接丢掉。
    text = re.sub(r"(?m)^[ \t]*%%[ \t]*@q[^\n]*\n?", "", text).strip()
    if not text:
        raise HTTPException(400, "源码是空的")

    # **只允许一道题。** 多贴一道时 `parse_question` 会静默只取第一道，
    # 后面的内容看起来"保存成功"其实丢了——宁可当场拒绝。
    if len(re.findall(r"\\begin\{(?:question|problem)\}", text)) != 1:
        raise HTTPException(
            400, r"这里只改一道题：源码里要恰好有一个 \begin{question} 或 \begin{problem}")
    if not re.search(r"\\end\{(?:question|problem)\}\s*$", text):
        raise HTTPException(
            400, r"源码要在 \end{question}（或 \end{problem}）结束，后面不要带别的题")

    cand = parse_question(text)
    if cand is None:
        raise HTTPException(
            400, r"没认出题目环境：源码里要有 \begin{question} … \end{question}")

    # key / 考点不能从源码里改（源码里也没有它们）。
    cand.key = old.key
    cand.points = list(old.points)
    # 分值由正文的 `[points=…]` 表达；其余元数据（出处/年份/难度/来源）
    # 沿用库里的。旧分值先删掉，否则把 `[points=…]` 删了也改不回去。
    meta = dict(old.meta or {})
    meta.pop("points", None)
    meta.update(cand.meta or {})
    cand.meta = meta

    # **改之前**：用户这份源码本身合不合规。必须跑在规范化**之前**——
    # 跑在后面的话"改之前"和"复核后"是同一份，报告就成了摆设。
    before = [{"check": v["check"], "why": v["why"], "field": v["field"]}
              for v in _cf.run([cand])]

    fixed = _norm.normalize(cand, _norm.ENTRY)
    after = [{"check": v["check"], "why": v["why"], "field": v["field"]}
             for v in _cf.run([cand])]
    problems = cand.problems()

    # **防手滑删光。** 源码编辑是整段替换：少写一行 `\paren[A]`、把
    # `\begin{solution}` 连同内容一起删掉，格式上都是合法的，`conform`
    # 也看不出来——但题目会悄悄变成"没答案/没解析"。
    # 库的规矩是「没答案或没解析一律不许入库」，所以这里必须拦；
    # 真想清空就走「改答案」那条路（那里本来就有明确的提示）。
    if (old.answer or "").strip() and not (cand.answer or "").strip():
        problems.insert(0, "答案被清空了——如果是有意换答案，请在同一份源码里把新答案写进去")
    if old.has_solution and not cand.has_solution:
        problems.insert(0, "解析被删空了——可以改写，但不能把整段解析删掉")
    return cand, before, fixed, after, problems


def _source_images(q) -> dict:
    r"""这道题引用了哪些图、在不在库里。

    `改源码` 不能上传图片（那是录入那条路的事），所以这里只**如实报**：
    缺的图保存后会露在卷面上，必须在按保存之前看见。
    """
    from amti import images as _im
    out: dict[str, dict] = {}
    for text in [q.stem, q.solution] + [o.text for o in q.options]:
        for name in _im.collect(text or ""):
            if name in out:
                continue
            out[name] = ({"status": "ok", "note": "已在库"}
                         if (IMG_DIR / name).is_file()
                         else {"status": "missing", "note": "库里没有这张图"})
    return out


def _source_report(cand, before, fixed, after, problems) -> dict:
    r"""检查结果 + 渲染预览。**检查与保存走同一个构造函数**，
    所以"预览看到的"就是"真写进去的"（和补解析接口同一个原则）。

    报告的**分块与录入页那套一致**（`spec` / `images` / `impact`）：
    改源码和录新题是同一件事的两半，界面不该有两套说法。
    """
    try:
        d = _brief(cand)
    except Exception:
        # 源码坏到连预览都解析不了时，仍然把审查报告交回去；
        # 不能因为预览失败就让整个接口 500（那样用户什么也看不到）。
        log.warning("源码预览解析失败：%s", cand.key, exc_info=True)
        d = {
            "key": cand.key, "type": cand.type,
            "type_label": QTYPE_LABEL.get(cand.type, cand.type),
            "stem": cand.stem,
            "options": [{"label": o.label, "text": o.text} for o in cand.options],
            "answer": cand.answer, "solution": cand.solution,
            "blocks": {"stem": [], "answer": [], "solution": [], "options": []},
            "points": cand.points, "difficulty": cand.difficulty, "stars": cand.stars,
            "point_titles": cand.point_titles, "meta": cand.meta, "kind": cand.kind,
            "hash": cand.content_hash(), "missing": cand.missing(),
            "problems": problems, "figures": [f.id for f in cand.figures],
            "flags": {},
        }
    d.update({
        "ok": not after and not problems,
        "saved": False,
        "tex": question_to_tex(cand),
        "fixed": fixed,
        "after": after,
        "problems": problems,
        # ── 与录入页同一套报告字段 ──
        "spec": {"before": before, "fixed": fixed, "after": after,
                 "ok": not after and not problems},
        "images": _source_images(cand),
        "impact": {
            "existing_questions": 0,
            "note": "只改这一道；其余题目内容一个字节不动"
                    "（保存时整卷重写，但别的题逐字不变）。",
        },
    })
    return d


def _source_audit(q, before: str, after: str, fixed) -> None:
    r"""改源码的记档。失败**不阻断**保存，但必须留日志——
    「改了但没记录」正是审查报告 Important #3 要防的事。"""
    try:
        from amti.audit import CHANGE_DIR
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_界面改源码.md" % time.strftime("%Y%m%d_%H%M%S"))
        f.write_text(
            "# 界面改源码\n\n- 时间：%s\n- 题目：`%s`\n"
            "- 内容指纹：%s → %s\n- 规范化改动：%s\n"
            "- 规范审查：通过（0 违规）\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), q.key, before, after,
               "、".join(fixed) if fixed else "无"),
            encoding="utf-8")
    except Exception:
        log.warning("改源码记档失败（修改已生效）：%s", q.key, exc_info=True)


@app.post("/api/questions/{key:path}/source")
def question_source(key: str, body: SourceBody) -> dict:
    r"""改一道题的 LaTeX 源码。

    三种用法（同一个接口，只差参数）：

        {}                                              → 返回当前源码
        {"tex": "…"}                                    → 只检查（dry_run 默认 true）
        {"tex": "…", "dry_run": false}                  → 检查 → 写盘

    不设口令（用户明确说没必要）；安全性靠解析/规范化/规范审查、
    `expect_hash` 并发校验和原子写盘。
    """
    k = urllib.parse.unquote(key)

    # ── 取源码 ──
    if body.tex is None:
        q = store.find(k)
        if q is None:
            raise HTTPException(404, f"没有这道题：{k}")
        return {"ok": True, "key": q.key, "tex": question_to_tex(q),
                "hash": q.content_hash()}

    # ── 干跑：只看不写 ──
    if body.dry_run:
        q = store.find(k)
        if q is None:
            raise HTTPException(404, f"没有这道题：{k}")
        if body.expect_hash and q.content_hash() != body.expect_hash:
            raise HTTPException(
                409, "这道题刚被别的进程改过（内容指纹变了），"
                     "为免覆盖别人的改动，请关掉重开再改。")
        cand, before, fixed, after, problems = _source_candidate(q, body.tex)
        return _source_report(cand, before, fixed, after, problems)

    # ── 快速档：没改动 / 改坏了 → 根本不进写锁 ──
    #
    # 真写要「读全库 → 改一道 → 整库重写」，实测约 8 秒。可用户点保存时
    # 经常一个字都没改（先点检查再保存），或者源码明显不合规——这两种情况
    # 都**不需要写盘**。下面先拿当前快照算一遍：
    #   · 内容指纹一样 → 直接回「没有改动」；
    #   · 结构/规范不过 → 直接把报告交回去（写进去也会被同一套检查拒绝）。
    # 真正要写时，`store.update` 里还会**再算一遍**，所以这里只省时间，
    # 不放松「保存前必须过检查」这条。
    q0 = store.find(k)
    if q0 is None:
        raise HTTPException(404, f"没有这道题：{k}")
    if body.expect_hash and q0.content_hash() != body.expect_hash:
        raise HTTPException(
            409, "这道题刚被别的进程改过（内容指纹变了），"
                 "为免覆盖别人的改动，请关掉重开再改。")
    cand0, before0, fixed0, after0, problems0 = _source_candidate(q0, body.tex)
    if after0 or problems0:
        return _source_report(cand0, before0, fixed0, after0, problems0)
    if cand0.content_hash() == q0.content_hash():
        rep = _source_report(cand0, before0, fixed0, after0, problems0)
        rep.update({"ok": True, "saved": False, "unchanged": True})
        return rep

    # ── 真写：读-改-写在同一把锁里 ──
    out: dict = {}

    def _do(qs):
        for i, q in enumerate(qs):
            if q.key != k:
                continue
            before = q.content_hash()
            if body.expect_hash and before != body.expect_hash:
                out["conflict"] = True
                return store.NO_WRITE

            cand, before, fixed, after, problems = _source_candidate(q, body.tex)
            out["report"] = _source_report(cand, before, fixed, after, problems)
            if problems or after:
                out["invalid"] = True
                return store.NO_WRITE

            after_hash = cand.content_hash()
            if after_hash == before:
                # 一个字没改：**不写盘**。否则整库重写会把所有卷的 mtime
                # 都改掉，别的进程的 `based_on` 校验会白失败一次。
                out["unchanged"] = True
                return store.NO_WRITE

            cand.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
            # 源码里改了 `\source{}` 也可能换 key。和「改出处」一样，
            # 跨题 meta 引用要在整库写回之前跟着换；存档/台账在写回后迁。
            if cand.key != q.key:
                out["renamed_from"] = q.key
                _migrate_meta_refs(qs, q.key, cand.key)
            qs[i] = cand
            out.update({"before": before, "after_hash": after_hash,
                        "fixed": fixed, "cand": cand})
            return qs
        out["missing"] = True
        return store.NO_WRITE

    store.update(_do)

    if out.get("missing"):
        raise HTTPException(404, f"没有这道题：{k}")
    if out.get("conflict"):
        raise HTTPException(
            409, "这道题在你改的时候被别的进程改过了，"
                 "为免覆盖别人的改动，**没有保存**。请关掉重开再改。")
    rep = out["report"]
    if out.get("invalid"):
        return rep
    if out.get("unchanged"):
        rep.update({"ok": True, "saved": False, "unchanged": True})
        return rep

    # 源码改出处 → 换 key：存档/使用频次/改名台账在写回之后迁
    # （和 `patch_question` 同一套；不然改一次 `\source{}` 引用就全断了）
    renamed_from = out.get("renamed_from") or ""
    if renamed_from:
        moved = _migrate_key_refs(renamed_from, out["cand"].key)
        _migrate_usage(renamed_from, out["cand"].key)
        _audit_key_rename(renamed_from, out["cand"].key)
        rep["renamed_from"] = renamed_from
        log.info("源码改出处：%s → %s（引用已迁：%s）", renamed_from,
                 out["cand"].key, "、".join(moved) or "无")

    _source_audit(out["cand"], out["before"], out["after_hash"], out["fixed"])
    rep.update({"ok": True, "saved": True, "unchanged": False,
                "hash": out["after_hash"]})
    return rep


@app.get("/api/stats")
def stats() -> dict:
    from collections import Counter
    by_type, by_book, miss = Counter(), Counter(), Counter()
    total = 0
    for q in store.load_cached():
        total += 1
        by_type[q.type] += 1
        by_book[q.kind] += 1
        for m in q.missing():
            miss[m] += 1
    return {
        "total": total,
        "by_type": [{"key": k, "label": QTYPE_LABEL.get(k, k), "n": v}
                    for k, v in by_type.most_common()],
        "by_book": by_book.most_common(10),
        "missing": dict(miss),
        "volumes": [{"name": p.name, "n": store.vol_count(p)}
                    for p in store.existing_volumes()],
        "baseline": len(store.load_snapshot()),
    }


@app.get("/api/facets")
def facets() -> dict:
    """筛选面板要的选项 + 计数。"""
    from collections import Counter
    from amti import knowledge as kb
    (types, kinds, points, diffs, years, sources,
     scopes, papers, stars, quals, books, regions, asrc, rvc) = (
        Counter(), Counter(), Counter(), Counter(), Counter(), Counter(),
        Counter(), Counter(), Counter(), Counter(), Counter(), Counter(), Counter(),
        Counter())
    for q in store.load_cached():
        types[q.type] += 1
        kinds[q.kind] += 1          # 只有两类：高考 / 模拟
        books[q.meta.get("book") or "模拟题"] += 1
        if q.meta.get("region"):
            regions[str(q.meta.get("region"))] += 1
        asrc[str(q.meta.get("answer_source") or "无")] += 1
        rvc["yes" if q.meta.get("reviewed_at") else "no"] += 1
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
    # 考点：**列出知识点库里全部 153 个**，没有题目的计数为 0。
    # 早先只列「有题目的」，于是看不出哪些考点还是空的——而那正是要补的。
    # 顺序按知识点库本身的层级（大类 → 节 → 考点），不是按题量。
    allpts = kb.all_points()
    point_list = [{"value": p["id"], "n": points.get(p["id"], 0),
                   "title": kb.title_of(p["id"]),
                   "topic": p["topic"], "section": p["section"],
                   "stars": p["stars"], "difficulty": p["difficulty"]}
                  for p in allpts]
    point_list.sort(key=lambda x: [int(y) if y.isdigit() else 0
                                   for y in x["value"].split(".")])
    return {
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
        "region_scopes": [{"value": k, "n": v} for k, v in scopes.most_common()],
        "paper_states": [{"value": k, "n": v} for k, v in papers.most_common()],
        "star_states": [{"value": k, "n": v} for k, v in stars.most_common()],
        "qualities": [{"value": k, "n": v} for k, v in quals.most_common()],
        # 录入批次：按「书」给出先后（文件里的追加顺序）。
        # 用户想看「我新录的 vs 早先录的」，这个顺序就是答案。
        "batches": _batches(),
    }


class ReplaceBody(BaseModel):
    """单题换题：给当前题找同题型/同板块/同难度的替补。"""
    key: str
    type: str = ""
    section: str = ""          # 解答题的板块（三角/数列、概率统计…）
    want_diff: str = ""        # 目标难度；空 = 用当前题的难度
    exclude: list[str] = Field(default_factory=list)
    limit: int = 8


class GenerateBody(BaseModel):
    """组卷。`pool` 是筛选条件，和 `/api/questions` 一致。

    `mode`：
      * `gaokao`    按高考卷面结构（8+3+3+5，填补位置）
      * `test`      不约束，按传入顺序
      * `coverage`  **按考点覆盖率组卷**（易→难排序）
    """
    mode: str = "gaokao"
    coverage: float = 0.9               # coverage 模式的目标覆盖率
    want: int = 19                      # coverage 模式要几道题
    # coverage 模式：**要不要保住高考卷面的题型比例**（8 单选 3 多选 3 填空 5 解答，
    # 按 want 等比缩放）。默认保——不保的话贪心只认考点个数，
    # 46 道题能挑出 23 道解答题（解答题考点密度最高），那卷子没法用。
    # 代价是覆盖率约掉 2.6 个百分点（85.5% → 82.9%），说明里会报出来。
    keep_structure: bool = True
    seed: int | None = None             # 同 seed 出同一套
    q: str = ""
    type: str = ""
    kind: str = ""
    point: str = ""
    difficulty: str = ""
    year: str = ""
    source: str = ""
    has: str = ""
    missing: str = ""
    # **和 `/api/questions` 同一套筛选**。以前这里只有 7 个，
    # 列表那边新增的「地区/完整度/星级/质检」四个维度压根传不进来——
    # 用户在列表里筛到 300 道，组卷却按"没筛"的池子挑，出题完全不是他要的。
    region_scope: str = ""
    paper_state: str = ""
    star_state: str = ""
    quality: str = ""
    point_source: str = ""       # 与 /api/questions 同义（「无」= 没记来源）
    # 组卷硬约束：缺图/短解析不上卷；year_from>0 只要近年；同一考点上限
    exclude_missing_figure: bool = True
    min_solution_len: int = 20
    year_from: int = 0
    point_quota: int = 2
    # 目标时长（分钟）：0 = 不检查；组完只提示“超了/少了”，不自动改题
    target_minutes: int = 120
    # 按地区/卷别选题（精确匹配 meta.region；逗号分隔取并集）
    region: str = ""
    # 非 `gaokao` 模式是"照单全收"语义（`generate()` 直接把整个池子摊成卷子）。
    # 不加这道闸门，筛完 2.8 万道再点「取筛选结果」，前端会拿到 2.8 万道题的
    # 完整 brief——浏览器直接卡死。超出就截断，并在报告里**明说**截了。
    max_items: int = 500


@app.post("/api/generate")
def api_generate(body: GenerateBody) -> dict:
    r"""按高考的结构与排布惯例随机组一套卷。

    规则见 `amti/generate.py`：分值结构、解答题板块顺序、小题章节上限。
    """
    from amti import generate as _gen
    has_set = {x.strip() for x in body.has.split(",") if x.strip()}
    miss_set = {x.strip() for x in body.missing.split(",") if x.strip()}
    pt_set = {x.strip() for x in body.point.split(",") if x.strip()}
    diff_set = {x.strip() for x in body.difficulty.split(",") if x.strip()}
    year_set = {x.strip() for x in getattr(body, "year", "").split(",") if x.strip()}
    src_set = {x.strip() for x in getattr(body, "source", "").split(",") if x.strip()}
    scope_set = {x.strip() for x in body.region_scope.split(",") if x.strip()}
    paper_set = {x.strip() for x in body.paper_state.split(",") if x.strip()}
    star_set = {x.strip() for x in body.star_state.split(",") if x.strip()}
    quality_set = {x.strip() for x in body.quality.split(",") if x.strip()}
    ps_filter = body.point_source.strip()
    region_set = {x.strip() for x in body.region.split(",") if x.strip()}
    kw = body.q.strip()
    tag_ids = _tag_ids_matching(kw) if kw else set()   # 与列表同一套关键词判据

    pool = []
    for item in store.load_cached():
        if body.type and item.type != body.type:
            continue
        if body.kind and item.kind != body.kind:
            continue
        if pt_set and not (pt_set & set(item.points)):
            continue
        if diff_set and item.difficulty not in diff_set:
            continue
        if year_set and str(item.meta.get("year") or "") not in year_set:
            continue
        if src_set and (_source_of(item)) not in src_set:
            continue
        # 四个新维度：**与列表逐条对齐**，否则"列表里筛到的"和"组出来的"不是同一批题
        if scope_set:
            sc = item.meta.get("region_scope") or ("single" if item.meta.get("region") else "unknown")
            if sc not in scope_set:
                continue
        if paper_set:
            partial = item.meta.get("paper_complete") is False
            if ("partial" if partial else "complete") not in paper_set:
                continue
        if star_set:
            rated = item.stars > 0
            if ("rated" if rated else "unrated") not in star_set:
                continue
        if quality_set:
            ok = (("dup" in quality_set and item.meta.get("duplicate_group"))
                  or ("lowres" in quality_set and item.meta.get("figure_low_res")))
            if not ok:
                continue
        if ps_filter:
            got = str(item.meta.get("point_source") or "")
            if (ps_filter == "无" and got) or (ps_filter != "无" and got != ps_filter):
                continue
        if not _kw_hit(item, kw, tag_ids):
            continue
        if has_set or miss_set:
            f = _flag_fields(item)["flags"]
            if has_set and not all(f.get(k) for k in has_set):
                continue
            if miss_set and not all(not f.get(k) for k in miss_set):
                continue
        pool.append(item)

    # 硬约束先过一遍：**列表里还在、但印出来做不了的题**不该进卷。
    # `test` 模式是“老师明确选的”，不过滤。
    if body.mode != "test":
        pool = _gen.filter_pool(
            pool,
            exclude_missing_figure=body.exclude_missing_figure,
            min_solution_len=body.min_solution_len,
            year_from=body.year_from)

    if body.mode == "coverage":
        # **按考点覆盖率组卷**：以「尽量多覆盖考点」为目标挑题，
        # 挑完**按易→难排好**。跟 `gaokao` 那种"填卷面位置"是两回事。
        mix = _gen.gaokao_mix(body.want) if body.keep_structure else None
        r = _gen.generate_by_coverage(pool, want=body.want, coverage=body.coverage,
                                      seed=body.seed, type_mix=mix,
                                      report_cost=bool(mix))
        r["slots"] = []
    else:
        # 非 `gaokao` 模式是"照单全收"：`generate()` 会把整个池子摊成卷子。
        # 筛完 2.8 万道再点「取筛选结果」，前端会拿到 2.8 万条 brief——卡死。
        cap = max(1, int(body.max_items or 500))
        r = _gen.generate(pool[:cap], mode=body.mode, seed=body.seed,
                          exclude_missing_figure=body.exclude_missing_figure,
                          min_solution_len=body.min_solution_len,
                          year_from=body.year_from,
                          point_quota=body.point_quota)
        if len(pool) > cap:
            r["report"]["note"] = (
                f"筛选到 {len(pool):,} 道，按当前顺序取前 {cap:,} 道入卷")

    # 顺带把每道题的显示信息带上，前端要列卷子。
    # **只给真正入卷的那几道渲染 brief**：`pool` 可能是筛选后的 2.8 万道，
    # 全量渲染块级 IR 会把这个服务卡住几十秒（列表接口早就为此改成
    # "先筛、先切，最后才渲染"），这里以前是漏的。
    # 时长预算：只提示，不偷偷换题——换题会破坏细目表和已排好的顺序
    _target = max(0, int(body.target_minutes or 0))
    _mins = r.get("minutes") or (r.get("report") or {}).get("minutes")
    if _target and _mins:
        _gap = int(_mins) - _target
        if _gap > 10:
            r["report"].setdefault("notes", []).append(
                "预计 %d 分钟，比目标 %d 分钟多 %d 分钟；可减少题量或换简单题"
                % (_mins, _target, _gap))
        elif _gap < -15:
            r["report"].setdefault("notes", []).append(
                "预计 %d 分钟，比目标 %d 分钟少 %d 分钟；题量还可以再加"
                % (_mins, _target, -_gap))

    picked = set(r["keys"])
    chosen = {q.key: q for q in pool if q.key in picked}
    r["items"] = [_brief(chosen[k]) for k in r["keys"] if k in chosen]
    return r


class IngestBody(BaseModel):
    text: str = ""                      # 源材料（LaTeX）
    book: str = "手工录入"
    label: str = ""                     # 出处，如 "第14套武汉三调"
    region: str = ""
    year: int | None = None
    source_no: str = ""
    src_dir: str = ""                   # 图片来源目录，留空用默认
    points: str = ""                    # 考点 id，逗号分隔（界面上选的）
    difficulty: str = ""                # 简单题/中档题/难题（界面上选的）
    qtype: str = ""                     # 题型（界面上选的）；留空=按正文推断
    # 手工录入规则：库里已有同题 → 整题跳过，不新增、不更新。
    # 这两个字段保留只为兼容旧客户端；`/api/ingest/commit` 会固定按 False 执行。
    update_existing: bool = False
    update_force: bool = False
    merge_into: dict = {}               # {新题key: 库内key} —— 旧界面/脚本用
    merge_blocks: dict = {}             # {题块下标: 库内key} —— 多题界面用（key 会随出处变）
    items: list[dict] = Field(default_factory=list)  # 逐题覆盖（勾选/考点/难度/题号）
    dup_threshold: float = 0.80
    near_threshold: float = 0.95      # 整题相似 > 这个值 → 不录入；默认 95%
    # 补旧题模式：只给库里已有题补空考点/空难度，不新增、不改正文。
    # 和默认录入规则分开，避免把「已有不更新」的承诺悄悄放开。
    backfill: bool = False


class VlmBody(BaseModel):
    data: str = ""                      # 文件内容的 base64（不带 data: 前缀）
    name: str = "upload.png"            # 只为报错和显示用
    dpi: int = 200                      # PDF 栅格化 dpi



@app.post("/api/generate/replace")
def api_generate_replace(body: ReplaceBody) -> dict:
    r"""单题换题：返回可替换当前题的候选。

    排序不是随机的，按教师的实际偏好加权：
      ① 同主考点（+6）/ 同解答题板块（+5）
      ② 同目标难度（+4）
      ③ 与当前题有共同考点标签（+2）
      ④ 有解析（+1）、同类别（+0.5）
      ⑤ 用得少的题略微优先（-0.02/次，最多 -0.4）

    只返回 `limit` 条列表用 brief；答案/解析块 IR 不带（详情再取）。
    """
    from amti import generate as gen

    qs = list(store.load_cached())
    by_key = {q.key: q for q in qs}
    cur = by_key.get(body.key)
    if cur is None:
        raise HTTPException(404, "题不在库里")

    typ = body.type or cur.type
    want_diff = body.want_diff or cur.difficulty or ""
    section = body.section or ""
    topic = gen.topic_of(cur)
    section_topics = gen.SECTION_TOPICS.get(section, set())
    exclude = set(body.exclude) | {cur.key}
    usage = _usage()

    scored: list[tuple[float, object]] = []
    for q in qs:
        if q.key in exclude or q.type != typ:
            continue
        qt = gen.topic_of(q)
        s = 0.0
        if topic and qt == topic:
            s += 6
        if section_topics and qt in section_topics:
            s += 5
        if want_diff and q.difficulty == want_diff:
            s += 4
        if set(q.points) & set(cur.points):
            s += 2
        if q.has_solution:
            s += 1
        if q.kind == cur.kind:
            s += 0.5
        s -= min(usage.get(q.key, 0), 20) * 0.02
        scored.append((s, q))

    scored.sort(key=lambda x: (-x[0], getattr(x[1], "seq", 0) or 0))
    limit = max(1, min(int(body.limit or 8), 12))
    out = []
    for s, q in scored[:limit]:
        d = _brief_cached_lite(q)
        d["match"] = {
            "topic": bool(topic and gen.topic_of(q) == topic),
            "section": bool(section_topics and gen.topic_of(q) in section_topics),
            "difficulty": bool(want_diff and q.difficulty == want_diff),
        }
        d["score"] = round(s, 2)
        out.append(d)
    return {"items": out, "want_diff": want_diff, "topic": topic}


@app.get("/api/vlm/status")
def vlm_status() -> dict:
    """**读图**服务的现状。**只查，不启动**——启动由 `/api/vlm/extract` 负责。

    ⚠️ 现在的识别链是 **PaddleOCR-VL 认字 → 27B 改格式**（2026-10-27 起
    MinerU 已移除）。这里原来只报 llama.cpp（:1235）那套的"就绪"，
    但这条后备只在没装 Paddle 时才走；装了 Paddle 的机器上界面永远是灰点，
    看起来像"读图不可用"，其实点下去照样能识别。
    """
    from amti import lms as _lms
    from amti import paddle as _paddle
    from amti import vlm as _vlm
    ok_p, why_p = _paddle.available()
    return {
        # 真正决定"按下有没有用"的是：Paddle 装好（走主链），
        # 或者 llama.cpp 读图服务在跑，或者 LM Studio 在跑（27B 顶班）
        "ready": bool(ok_p or _lms.up_vision() or _lms.up()),
        "engine": "paddle+27b" if ok_p else "llama.cpp",
        "paddle": {"installed": ok_p, "why": why_p, "service": _paddle.up()},
        "solve": {"up": _lms.up(), "model": _vlm.SOLVE_MODEL},
        "api": _lms.VISION_API,
        "model": _vlm.MODEL,
        "runtime": "llama.cpp",
        "engine_installed": _lms.LLAMA_SERVER.is_file(),
        "model_files": {
            "model": (_lms.VISION_MODEL.is_file(), str(_lms.VISION_MODEL)),
            "mmproj": (_lms.VISION_MMPROJ.is_file(), str(_lms.VISION_MMPROJ)),
        },
    }


@app.post("/api/vlm/extract")
def vlm_extract(body: VlmBody) -> dict:
    """图片 / PDF → LaTeX 文本。**只识别，不写库。**

    产物由前端填进录入框，再走 `/api/ingest/preview` → 人工审阅 →
    `/api/ingest/commit`。这样"审阅后才入库"和"存量一个字不变"
    都由 `ingest` 那一条现成管线保证，这里不重复实现。
    """
    import base64 as _b64
    from amti import vlm as _vlm
    if not body.data.strip():
        raise HTTPException(400, "没有收到文件内容")
    try:
        raw = _b64.b64decode(body.data, validate=True)
    except Exception:
        raise HTTPException(400, "文件内容不是合法的 base64")
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(413, "文件太大（>80MB）")
    try:
        return _vlm.extract(raw, body.name, dpi=max(72, min(body.dpi, 400)))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        # 模型没配好 / 读不了图 —— 这是**用户要动手修**的事，
        # 所以原文带出去，别吞成"服务器错误"。
        raise HTTPException(503, str(e))


@app.post("/api/ingest/preview")
def ingest_preview(body: IngestBody) -> dict:
    """**干跑**：解析 + 图片预检 + 查重 + 校验 + 影响面。什么都不写。"""
    from amti import dedup as _dd
    from amti import ingest as _ig
    src = [body.src_dir] if body.src_dir.strip() else None
    pts = [x.strip() for x in body.points.split(",") if x.strip()]
    pv = _ig.preview(body.text, src_dirs=src, book=body.book, label=body.label,
                     region=body.region, year=body.year,
                     source_no=body.source_no, points=pts or None,
                     difficulty=body.difficulty.strip(),
                     qtype=body.qtype.strip(),
                     update_force=body.update_force,
                     merge_into=body.merge_into or None,
                     merge_blocks=body.merge_blocks or None,
                     items=body.items or None,
                     allow_upgrade=(body.backfill
                                    or _ig.MANUAL_INGEST_POLICY["allow_upgrade"]),
                     skip_near=((not body.backfill)
                                and _ig.MANUAL_INGEST_POLICY["skip_near"]),
                     near_threshold=max(0.80, min(1.0, body.near_threshold)),
                     dup_threshold=body.dup_threshold,
                     backfill=body.backfill)
    # 顺带把渲染用的块级 IR 也带上，前端要实时预览
    for it, q in zip(pv["items"], _ig.parse_source(
            body.text, book=body.book, label=body.label,
            region=body.region, year=body.year,
            source_no=body.source_no, points=pts or None,
            difficulty=body.difficulty.strip(),
            qtype=body.qtype.strip(), items=body.items or None)["questions"]):
        it["blocks"] = {
            "stem": lb.parse_blocks(q.stem, parts=True),
            "answer": lb.parse_blocks(q.answer),
            "solution": lb.parse_blocks(q.solution),
            "options": [lb.parse_blocks(o.text) for o in q.options],
        }
    return pv


@app.post("/api/ingest/commit")
def ingest_commit(body: IngestBody) -> dict:
    """正式导入：图片入库 → 追加主文件。返回变更报告。"""
    from amti import dedup as _dd
    from amti import ingest as _ig
    src = [body.src_dir] if body.src_dir.strip() else None
    pts = [x.strip() for x in body.points.split(",") if x.strip()]
    return _ig.commit(body.text, src_dirs=src, book=body.book, label=body.label,
                      region=body.region, year=body.year,
                      source_no=body.source_no, points=pts or None,
                      difficulty=body.difficulty.strip(),
                      qtype=body.qtype.strip(),
                      # 默认手工录入的硬规则：库里已有同题 → 跳过，不新增也不更新。
                      # 只有显式 `backfill=True` 才放开「只补空考点/难度」。
                      # LLM 录题走 `ig.commit` 的默认值，不受这个端点影响。
                      update_existing=(body.backfill
                                       or _ig.MANUAL_INGEST_POLICY["update_existing"]),
                      update_force=False,
                      skip_near=((not body.backfill)
                                 and _ig.MANUAL_INGEST_POLICY["skip_near"]),
                      near_threshold=max(0.80, min(1.0, body.near_threshold)),
                      backfill=body.backfill,
                      merge_into=body.merge_into or None,
                      merge_blocks=body.merge_blocks or None,
                      items=body.items or None)


class IngestSourceBody(BaseModel):
    text: str = ""


@app.post("/api/ingest/source")
def ingest_source(body: IngestSourceBody) -> dict:
    r"""只从源材料**前几行**认标题/年份（`\title{…}` 或第一行纯文本）。

    单独一个轻量接口：不用为了填「出处」先跑一遍整库查重。
    多题录入界面在干跑前先调它，把出处填好，干跑就只跑一次。
    """
    from amti.ingest import extract_source_hint
    return extract_source_hint(body.text)


class IngestTagItem(BaseModel):
    stem: str = ""
    options: list[dict] = Field(default_factory=list)
    type: str = ""


class IngestTagBody(BaseModel):
    items: list[IngestTagItem] = Field(default_factory=list)
    model: str = ""                 # 留空用 qwen3.5-9b-mlx；失败自动回落 27B
    workers: int = 4


class LlmUnloadBody(BaseModel):
    model: str = ""


@app.get("/api/llm/status")
def llm_status() -> dict:
    r"""标注模型/27B 现在有没有在内存里；只读，不加载。

    用户对 9B 常驻有明确顾虑（默认自动标已关、TTL 30 分钟）；
    界面要能看见“现在到底加载了什么”，并给一个卸载按钮。
    """
    from amti import lms as _lms
    from amti import record2
    rows = _lms.ps_json()
    loaded = [{
        "identifier": r.get("identifier") or r.get("modelKey") or "",
        "model_key": r.get("modelKey") or "",
        "display_name": r.get("displayName") or "",
        "context_length": r.get("contextLength"),
        "ttl_ms": r.get("ttlMs"),
        "status": r.get("status") or "",
        "size_bytes": r.get("sizeBytes"),
    } for r in rows if r.get("type") == "llm"]
    return {
        "ok": True,
        "tag_model": record2.TAG_MODEL,
        "tag_ttl": record2.TAG_TTL,
        "loaded": loaded,
    }


@app.post("/api/llm/unload")
def llm_unload(body: LlmUnloadBody) -> dict:
    """卸载一个已加载模型（9B/27B）。只释放内存，不碰题库。"""
    from amti import lms as _lms
    ok, why = _lms.unload(body.model.strip())
    if not ok:
        raise HTTPException(400, why)
    return {"ok": True, "model": body.model.strip(), "message": why}


@app.post("/api/ingest/tag")
def ingest_tag(body: IngestTagBody) -> dict:
    r"""给多题录入的卡片**预标考点/难度**（只读，不写库）。

    模型默认 `qwen3.5-9b-mlx`（用户点名要 qwen3.5；9B 够快）。它只负责
    "粗标"——编号必须来自考点清单，非法编号会被丢掉。人可以在卡片上改，
    确认后才走 `/api/ingest/commit`。

    **不碰题库**：这里只返回标签，写库仍然只走 ingest 那一条线。
    """
    from amti import knowledge as kb
    from amti import record2

    if not body.items:
        return {"ok": False, "error": "没有题目", "items": [], "model": "", "failed": 0}
    if len(body.items) > 60:
        raise HTTPException(413, "一次最多标注 60 道（整卷请分批）")

    # 空题干的题跳过；下标要记住，返回的数组必须和请求**一一对应**，
    # 否则前端会把 A 题的标签贴到 B 题上。
    idx: list[int] = []
    recs: list[dict] = []
    for i, it in enumerate(body.items):
        if not (it.stem or "").strip():
            continue
        opts: dict[str, str] = {}
        for o in it.options or []:
            if not isinstance(o, dict):
                continue
            label = str(o.get("label") or "").strip()
            text = str(o.get("text") or "")
            if label:
                opts[label] = text
        idx.append(i)
        recs.append({"题干": it.stem, "选项": opts, "题型": it.type or ""})

    out: list[dict] = [{"points": [], "point_titles": [], "difficulty": "",
                        "stars": 0, "point_source": ""}
                       for _ in body.items]
    if not recs:
        return {"ok": False, "error": "没有可标注的题干", "items": out,
                "model": "", "failed": 0}

    model = (body.model or "").strip() or record2.TAG_MODEL
    workers = max(1, min(int(body.workers or 4), 8))
    res = record2.tag_points_detailed(recs, model=model, workers=workers,
                                      with_difficulty=True, retry_empty=True)
    used = res.get("model") or model
    # qwen3.5 没装/没起来 → 回落 27B（它可能已经在内存里）。只在**一条都没标上**
    # 时回落；部分失败是模型抽风，重跑比换模型更稳。
    if not res.get("n") and not res.get("n_diff") and res.get("error"):
        alt = record2.tag_points_detailed(recs, model="", workers=workers,
                                          with_difficulty=True, retry_empty=True)
        if alt.get("n") or alt.get("n_diff"):
            res, used = alt, alt.get("model") or "qwen/qwen3.8-27b"

    for j, r in zip(idx, recs):
        pts = [p for p in (r.get("points") or []) if kb.get(p)][:2]
        diff = str(r.get("difficulty") or "").strip()
        if diff not in ("简单题", "中档题", "难题"):
            diff = kb.difficulty_of(pts[0]) if pts else ""
        out[j] = {
            "points": pts,
            "point_titles": [kb.title_of(p) for p in pts],
            "difficulty": diff,
            "stars": kb.stars_of(pts[0]) if pts else 0,
            "point_source": "llm" if (pts or diff) else "",
        }
    ok = bool(res.get("n") or res.get("n_diff"))
    return {"ok": ok, "error": res.get("error") or "",
            "model": used, "items": out,
            "failed": int(res.get("failed") or 0),
            "retried": int(res.get("retried") or 0),
            "filled": int(res.get("filled") or 0)}


@app.get("/api/stats/detail")
def stats_detail() -> dict:
    """统计页：考点覆盖、难度分布、完整性缺口、标签来源。"""
    from collections import Counter
    from amti import knowledge as kb
    qs = store.load_cached()
    pts: Counter = Counter()
    # 每个考点内部的难度分布：体检页要回答“哪个考点没有简单题/难题”，
    # 只给总数看不出来。一次遍历顺手算掉，不额外读库。
    pd: dict[str, Counter] = {}
    for q in qs:
        for p in q.points:
            pts[p] += 1
            pd.setdefault(p, Counter())[q.difficulty] += 1
    src = Counter(q.meta.get("point_source") or "无" for q in qs)
    src_all = Counter(_source_of(q) for q in qs)
    # 章节题量按**题**去重：一道题挂 3 个本章考点只算 1 道。
    # 直接 sum(pts) 会把同一道题重复计数，页面上的数和工作台筛出来的数对不上。
    topic_n: Counter = Counter()
    for q in qs:
        for t in {kb.get(p).get("topic", "") for p in q.points}:
            if t:
                topic_n[t] += 1
    miss: Counter = Counter()
    for q in qs:
        for m in q.missing():
            miss[m] += 1
    reviewed = sum(1 for q in qs if q.meta.get("reviewed_at"))
    return {
        "total": len(qs),
        "by_type": [{"value": k, "label": QTYPE_LABEL.get(k, k), "n": v}
                    for k, v in Counter(q.type for q in qs).most_common()],
        "by_kind": [{"value": k, "n": v}
                    for k, v in Counter(q.kind for q in qs).most_common()],
        "by_difficulty": [{"value": k, "n": v} for k, v in sorted(
            Counter(q.difficulty for q in qs if q.difficulty).items(),
            key=lambda x: DIFF_ORDER.get(x[0], 9))],
        "by_year": [{"value": k, "n": v} for k, v in sorted(
            Counter(str(q.meta.get("year")) for q in qs if q.meta.get("year")).items())],
        "by_point_source": [{"value": k, "n": v} for k, v in src.most_common()],
        "reviewed": reviewed,
        "unreviewed": len(qs) - reviewed,
        "points_covered": len(pts),
        "points_total": len(kb.all_points()),
        "untagged": sum(1 for q in qs if not q.points),
        "by_source": [{"value": k or "未标来源", "n": n}
                      for k, n in src_all.most_common(12)],
        # 全部考点，含 0 题目的——**空考点本身就是要看的信息**
        "all_points": [{"value": p["id"], "title": kb.title_of(p["id"]),
                        "n": pts.get(p["id"], 0), "topic": p["topic"],
                        "section": p["section"],
                        "stars": p["stars"], "difficulty": p["difficulty"],
                        "by_diff": {d: pd.get(p["id"], Counter()).get(d, 0)
                                    for d in ("简单题", "中档题", "难题")}}
                       for p in sorted(kb.all_points(),
                                       key=lambda x: [int(y) if y.isdigit() else 0
                                                      for y in x["id"].split(".")])],
        "by_topic": [{"value": t, "n": topic_n.get(t, 0),
                      "total": sum(1 for p in kb.all_points() if p["topic"] == t),
                      "covered": sum(1 for p in kb.all_points()
                                     if p["topic"] == t and pts.get(p["id"], 0))}
                     for t in dict.fromkeys(p["topic"] for p in kb.all_points())],
        "top_points": [{"value": k, "title": kb.title_of(k), "n": v}
                       for k, v in pts.most_common(15)],
        "missing": [{"value": k, "n": v} for k, v in miss.most_common()],
        "figures": im_mod_stats(),
    }


def im_mod_stats() -> dict:
    from amti import images as _im
    st = _im.stats()
    return {"files": st["files"], "bytes": st["bytes"]}


@app.get("/api/reveal")
def reveal(path: str):
    """在访达中显示。**只允许项目内或导出文件夹里的路径**，防止把任意路径交给 Finder。

    导出位置可以在 `数据/导出位置.txt` 里改到项目外（用户的资料夹），
    所以不能只认 PKG —— 否则导完点「在访达中显示」永远 403。
    """
    import subprocess
    p = Path(path).resolve()
    roots = (PKG.resolve(), OUT_DIR.resolve())
    if not any(r == p or r in p.parents for r in roots):
        raise HTTPException(403, "只能打开项目内或导出文件夹里的文件")
    if not p.exists():
        raise HTTPException(404, f"不存在：{p}")
    subprocess.Popen(["open", "-R", str(p)])
    return {"ok": True, "revealed": str(p)}


class TikzBody(BaseModel):
    tex: str = ""


@app.post("/api/tikz/render")
def tikz_render(body: TikzBody) -> dict:
    r"""把一段 TikZ 源码渲成 PNG，供录入卡片预览。

    只给**手工作台审题**用：源码来自用户粘贴的材料，先查缓存再编译；
    产物是内容寻址的 `图片/tikz-*.png`。**不写题目**。
    """
    from amti import tikzfig
    tex = (body.tex or "").strip()
    if not tex:
        raise HTTPException(400, "TikZ 源码为空")
    p = tikzfig.png_cached(tex)
    if p is None:
        _pdf, why = tikzfig.render(tex)
        p = tikzfig.png_cached(tex)
        if p is None:
            raise HTTPException(422, "TikZ 渲染失败：%s" % (why or "没有产出 PNG"))
    return {"ok": True, "path": p.name}


@app.get("/api/ingest/preview-image")
def ingest_preview_image(path: str, src_dir: str = ""):
    r"""干跑时的题图原图。**只读**，且只能读来源目录/默认待录入图片里的文件。

    卡片上的 `\includegraphics` 引用的是**将要复制过去**的内容寻址名，
    这时 `图片/` 里还没有它；没有这个入口，带图题在审阅时是破图。
    """
    from amti import images as im
    roots: list[Path] = []
    if src_dir.strip():
        roots.append(Path(src_dir).expanduser())
    roots.append(im.OLD_IMG)
    raw = Path(path).expanduser()
    candidates = [raw] if raw.is_absolute() else [r / raw for r in roots]
    for c in candidates:
        try:
            c = c.resolve()
            if c.is_file() and any(c.is_relative_to(r.expanduser().resolve()) for r in roots):
                return FileResponse(c)
        except (OSError, ValueError):
            continue
    raise HTTPException(404, "图片不在来源目录里")


@app.get("/api/figure")
def figure(path: str, raw: int = 0):
    r"""题库图片。

    默认做**白底转透明** —— 题库的图多是白底，贴在米色讲义上会显出一个
    白方块，很突兀。出卷/讲义时也做同样处理，保证预览与导出 PDF 一致。
    传 ?raw=1 拿原图。
    """
    p = (IMG_DIR / path).resolve()
    if not str(p).startswith(str(IMG_DIR.resolve())) or not p.exists():
        raise HTTPException(404, f"没有这张图：{path}")
    if raw:
        return FileResponse(p)

    # 处理结果缓存到 `数据/缓存/transparent`（见 TRANSPARENT_CACHE）
    cache_dir = TRANSPARENT_CACHE
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        dst = cache_dir / p.name
        if not dst.exists() or dst.stat().st_mtime < p.stat().st_mtime:
            from PIL import Image
            import numpy as np
            im = Image.open(p).convert("RGBA")
            a = np.array(im)
            r, g, b, alpha = a[:, :, 0], a[:, :, 1], a[:, :, 2], a[:, :, 3]
            near_white = (r > 242) & (g > 242) & (b > 242)
            a[:, :, 3] = np.where(near_white, 0, alpha)
            Image.fromarray(a).save(dst)
        return FileResponse(dst, media_type="image/png")
    except Exception:
        log.debug("图片透明处理失败，返回原图：%s", "", exc_info=True)
        return FileResponse(p)          # 处理失败就给原图，不阻断


# ── 导出 ──────────────────────────────────────────────────────────────

class ExportBody(BaseModel):
    title: str = ""
    out: str = ""                       # 文件名，留空用「标题_时间戳」
    keys: list[str] = []                # 选的题
    show_answers: bool = False
    show_source: bool = True            # 题干第一行印出处（年份/卷别，不含原卷题号）
    answers_at_end: bool = False        # 答案与解析统一放卷末（真高考卷的做法）
    handout_font: str = ""              # 讲义字号，见 paper.HANDOUT_SIZES
    bottom_sep: str = ""                # 题目间距，如 "0.6em"
    problem_blank_cm: float | None = None
    mode: str = "gaokao"                # gaokao 高考卷 / test 纯测试题 / handout 讲义
    # 分类子目录（试卷 / 测试卷 / 讲义，见 paths.OUT_KINDS）。留空按卷型推；
    # 界面把「考点覆盖卷」归到 试卷（它渲染用 test 卷型），所以显式传。
    kind: str = ""
    compile: bool = True
    # 「编译预览」：只编译给人看。产物进 数据/预览/，**不存档、不计使用频次**。
    # 以前预览和导出是同一个请求，点一次预览就在资料夹里留一份 PDF、
    # 还把题目的「用过 N 次」+1（默认排序都跟着变）。
    preview: bool = False
    # 卷末附一页答题卡（姓名/考号 + 选择填涂 + 填空横线；解答题在卷面留白）
    answer_sheet: bool = False
    # 解答题“一页一题”：每道解答题新起一页，题目下面填满空白；老师版不分页。
    # 界面已删除这个选项；API 仍保留，调用方显式传 true 才启用。
    detail_one_page: bool = False
    # 卷头总分框 + 第一页密封线
    score_box: bool = True
    seal_line: bool = True
    # 目标时长（分钟）：0 = 不检查；组完只提示“超了/少了”，不自动改题
    target_minutes: int = 120


@app.post("/api/export")
@_serialized_export
def export(body: ExportBody) -> dict:
    r"""导出套卷。

    **必须回传落盘位置**（`tex_abs`/`pdf_abs`/`dir_abs`）——旧项目导出完
    只说一句"已生成"，用户还得自己去翻文件夹找。
    """
    from amti import export as _ex
    from amti import paper as _paper          # 这个函数里必须自己导入：
    # 原来只在 1580 行的另一个函数里 `from amti import paper as _paper`，
    # 这里用 _paper.HANDOUT_FONT_DEFAULT 却是未定义名。平时不炸是因为下一行
    # 用 `or` 短路（前端总会传 handout_font）；只有不传该字段的 API 调用才会
    # NameError（导出直接 500）。
    r = _ex.export(body.keys, title=body.title, out=body.out,
                   show_answers=body.show_answers, show_source=body.show_source,
                   answers_at_end=body.answers_at_end,
        handout_font=body.handout_font or _paper.HANDOUT_FONT_DEFAULT,
                   bottom_sep=body.bottom_sep or "0.6em",
                   problem_blank_cm=(body.problem_blank_cm
                                     if body.problem_blank_cm is not None else 4.0),
                   do_compile=body.compile, mode=body.mode, kind=body.kind,
                   preview=body.preview, answer_sheet=body.answer_sheet,
                   detail_one_page=body.detail_one_page,
                   score_box=body.score_box, seal_line=body.seal_line)
    if not r.get("ok") and r.get("error"):
        raise HTTPException(400, r["error"])
    # 预览**不计**使用频次：那是"看一眼排版"，不代表这套题被用出去了。
    if not body.preview:
        _usage_bump(body.keys)                  # ← 试卷导出计入频次
    # 前端预览 `<iframe>` 直接用这个地址（普通导出走导出位置，预览走预览目录）。
    if r.get("pdf_rel"):
        from urllib.parse import quote as _q
        r["pdf_url"] = ("/api/pdf?path=" + _q(r["pdf_rel"])
                        + ("&root=preview" if r.get("preview") else ""))
    return r


@app.get("/api/settings")
def settings() -> dict:
    """界面要知道的**只读设置**。

    导出位置 + **分类子目录**：界面上的「存为 xxx/试卷/yyy.pdf」得说真话。
    以前前端写死「试卷/」，而导出位置其实可以在 `数据/导出位置.txt` 里改，
    写死的那个就会骗人；分类名也同理——映射从 `paths.kind_of` 拿，
    前端不再自己写一份（`coverage` 是界面上的「考点覆盖卷」，归 试卷）。
    """
    from amti.version import __version__

    return {"out_dir": str(OUT_DIR),
            "version": __version__,
            "out_name": OUT_DIR.name or str(OUT_DIR),
            "kinds": {m: kind_of(m)
                      for m in ("gaokao", "test", "coverage", "handout")}}


@app.get("/api/pdf")
def pdf(path: str, root: str = "out"):
    r"""预览用：把 PDF 发出去。

    `path` 相对 `root`：默认导出位置（可带分类子目录）；`root=preview`
    是「编译预览」的产物目录（`数据/预览/`，不落用户资料夹）。
    """
    base = (PREVIEW_DIR if root == "preview" else OUT_DIR).resolve()
    p = (base / path).resolve()
    if (base not in p.parents and p != base) or not p.exists():
        raise HTTPException(404, f"没有这个文件：{path}")
    return FileResponse(p, media_type="application/pdf")


# ── 心跳：页面活着服务器就活着，页面一关就退出 ────────────────────
#
# 用一个**单调递增的时间戳**记录最后一次 ping。看门狗线程发现
# 「已经收到过 ping」且「超过 IDLE 秒没有新 ping」就退出进程。
#
# 为什么用心跳而不是 WebSocket：浏览器崩溃、断电、强制退出时，
# WebSocket 的关闭帧根本发不出来，服务器会一直挂着。心跳不依赖
# 优雅关闭——**只要不再 ping，就当作人走了**。
#
# ⚠️ 只在 `--exit-with-browser` 时启用。命令行/脚本调用时页面从没打开过，
#    永远收不到 ping，看门狗会立刻把服务杀掉。
_LAST_PING = [0.0]
_PING_SEEN = [False]
# 多久没 ping 才认为"人走了"。
#
# **必须明显大于 60 秒**：Chrome 对**后台标签页**的定时器有节流
# （隐藏 5 分钟后降为每分钟一次），而心跳是 8 秒一次。
# 原来设 25 秒 → 把标签页切到后台几分钟，服务就自己退了，
# 用户切回来看到的是「连不上题库服务」。
EXIT_IDLE_SEC = 95.0
# 「页面说它要走了」之后还给多久。**不能是 0**：
# `pagehide` 不只页面关闭时触发，**刷新（F5 / ⌘R）也会触发**——
# 用户早先那个"刷新一下就再也连不上"就是这么来的：
# beacon 一到，看门狗 2 秒内自杀，新页面还没加载完服务就没了。
# 给 **30 秒**宽限：心跳间隔是 8 秒，而新页面要加载完（冷启动时 JS 包不小）
# 才会发出第一声心跳。宽限必须**大于"最慢的一次刷新"**，
# 否则刷新时服务还是会在新页面发出心跳之前退掉。30 秒也给人留出
# 「关错了/想马上再开」的余地——这段时间内重新打开页面，服务还活着。
GONE_GRACE_SEC = 30.0

# **正在处理的请求数**。看门狗靠它避免"活干到一半被退出"。
#
# 起因：用户点「导出并保存」（两遍 xelatex，几十秒），期间页面关闭
# （或者别的什么发了 `/api/gone`），看门狗 2 秒内就 `os._exit(0)`——
# 编译被拦腰砍断，用户看到的是 fetch 失败 →「连不上题库服务」，
# 而真正的原因是**服务把自己退了**。半成品 .tex/.pdf 也留在磁盘上。
_INFLIGHT = [0]


@app.post("/api/alive")
def alive() -> dict:
    """页面每几秒 ping 一次。`unload=1` 是关页面时的最后一声。"""
    if not _PING_SEEN[0]:
        print("浏览器已连接 —— 关掉页面服务会自动退出", flush=True)
    _LAST_PING[0] = time.monotonic()
    _PING_SEEN[0] = True
    return {"ok": True}


@app.post("/api/gone")
def gone() -> dict:
    r"""页面说它要走了（`navigator.sendBeacon`）。

    **不能立刻退**：`pagehide` 在刷新时也会触发（见 GONE_GRACE_SEC 的说明），
    所以这里只把倒计时缩短到 `GONE_GRACE_SEC` 秒——刷新来得及接上，
    真关掉也只是多等几秒。
    """
    _LAST_PING[0] = time.monotonic() - (EXIT_IDLE_SEC - GONE_GRACE_SEC)
    print("页面说要走 —— %d 秒内没有新的心跳就退出" % GONE_GRACE_SEC, flush=True)
    return {"ok": True}


def _cleanup_vision() -> None:
    r"""收掉**本进程起的**读图服务。可以重复调用（`lms` 那边会清标志）。

    只收自己起的：你手动 `./启动.sh vision` 起的那个也许正被别的脚本用着。
    """
    from amti import lms as _lms
    try:
        msg = _lms.stop_vision_if_ours()
        if msg:
            print("  " + msg)
    except Exception:
        pass


def _watchdog() -> None:
    """没 ping 了就退出。只在 `--exit-with-browser` 下起。

    **有请求在跑就不退**：导出要几十秒，退在这儿等于把活砍一半。
    等它跑完，下一轮（2 秒后）再看，那时没 ping 就正常退出。
    """
    while True:
        time.sleep(2.0)
        if not _PING_SEEN[0]:
            continue                       # 页面还没打开过，不算
        if _INFLIGHT[0] > 0:
            continue                       # 有请求在跑，等它干完
        if time.monotonic() - _LAST_PING[0] > EXIT_IDLE_SEC:
            print("页面已关闭，题库服务退出")
            # ⚠️ **必须在这里收，不能指望 `finally`/`atexit`** ——
            # `os._exit()` 会跳过它们（实测：读图服务因此变成孤儿跑了 10 小时）。
            _cleanup_vision()
            os._exit(0)


# ── 试卷存档 / 合集 ──────────────────────────────────────────────────

@app.get("/api/papers")
def papers_list() -> dict:
    r"""出过的卷子 + 合集，按时间倒序。

    每条带 `keys`，所以能**原样重现**那套卷。
    """
    from amti import papers as P
    return {"items": P.all_items()}


class PaperBody(BaseModel):
    name: str
    keys: list[str] = []
    title: str = ""
    mode: str = "gaokao"
    kind: str = "试卷"          # 试卷 / 合集
    note: str = ""
    params: dict = {}


@app.post("/api/papers")
def papers_save(b: PaperBody) -> dict:
    """存一份卷子，或把挑好的题存成**合集**。"""
    from amti import papers as P
    if not b.name.strip():
        raise HTTPException(400, "得给个名字")
    return P.add(b.name.strip(), b.keys, title=b.title or b.name, mode=b.mode,
                 kind=b.kind, note=b.note, params=b.params)


@app.get("/api/papers/{name:path}")
def papers_get(name: str) -> dict:
    from amti import papers as P
    d = P.get(urllib.parse.unquote(name))
    if not d:
        raise HTTPException(404, "没有这份存档")
    return d


@app.delete("/api/papers/{name:path}")
def papers_delete(name: str) -> dict:
    from amti import papers as P
    return {"ok": P.remove(urllib.parse.unquote(name))}


# ── 回收站 ────────────────────────────────────────────────────────────
#
# 「删除」不是真删：移进 `回收站/回收站.json`（存整道题），随时能恢复。
# 只有 `purge` 那一步不可逆，所以界面上要二次确认。

class TrashBody(BaseModel):
    keys: list[str] = []
    reason: str = ""
    password: str = ""                  # 清空要口令；删除/恢复不要


@app.post("/api/questions/{key:path}/trash")
def question_trash(key: str, body: TrashBody) -> dict:
    """把一道题移进回收站。**不需要口令**（删除可恢复）。"""
    from amti import paper as _paper
    from amti import trash as T
    r = T.delete([urllib.parse.unquote(key)], reason=body.reason.strip())
    if not r["ok"]:
        raise HTTPException(400, r["error"])
    return r


class BatchDeleteBody(BaseModel):
    keys: list[str] = []
    reason: str = ""
    password: str = ""                  # 清空要口令；删除不要


@app.post("/api/trash")
def trash_delete_batch(body: BatchDeleteBody) -> dict:
    r"""**批量删题**。一次移进回收站，和单题删除同一套规矩。

    「很多题目现在不考了」——一道道点太慢，所以要能批量。
    但批量删更危险，所以规矩一条不减：**原因必选 + 整批原子**
    （有一条题号对不上就整批不执行，绝不删一半）。
    **不再要口令**（删除可恢复）；清空回收站才要口令。
    """
    from amti import trash as T
    r = T.delete(body.keys, reason=body.reason.strip())
    if not r["ok"]:
        raise HTTPException(400, r["error"])
    return r


@app.post("/api/snapshot")
def update_snapshot() -> dict:
    r"""**把当前状态存成新基线**。

    基线的用途是"我上次确认过的题，之后有没有被悄悄改动"。
    所以**每次有意改完数据（删题、批量订正、补录解析）都该更新一次**——
    更新之后这些改动就成了"已确认"，顶栏回到「存量未改动」，
    下次报警才是真的有事。

    这个动作**不改任何题目**，只是把当前指纹记下来，所以不需要口令。
    """
    from amti import store as _st
    d = _st.snapshot()
    # 快照变了，「基线与现状的差」也就变了；`_BASE` 只按卷文件签名失效，
    # 而存基线**不动任何卷**——不清缓存的话前端刷新后仍显示旧的删除/变化数，
    # 用户会以为「存基线没生效」。
    _BASE["key"] = None
    _BASE["v"] = None
    return {"ok": True, "questions": d["questions"],
            "at": time.strftime("%Y-%m-%d %H:%M:%S")}


@app.get("/api/trash/reasons")
def trash_reasons() -> dict:
    """删题的**原因选项**。界面照着渲染，不在前端再抄一份。"""
    from amti import trash as T
    return {"items": T.DELETE_REASONS}


@app.get("/api/trash")
def trash_list() -> dict:
    """回收站内容。带原题题干，好认。"""
    from amti import trash as T
    from amti.schema import NO_SOLUTION_MARKS
    items = []
    for x in T.all_items():
        q = x.get("question") or {}
        _sol = (q.get("solution") or "").strip()
        items.append({
            "key": x["key"], "deleted_at": x.get("deleted_at", ""),
            "reason": x.get("reason", ""), "type": q.get("type", ""),
            "stem": (q.get("stem") or "")[:200],
            # 与 `Question.has_solution` 同一口径：占位符不算解析
            "has_solution": bool(_sol) and _sol not in NO_SOLUTION_MARKS,
            "has_answer": bool((q.get("answer") or "").strip()),
            "points": q.get("points") or [],
        })
    return {"items": items, "count": len(items)}


@app.post("/api/trash/restore")
def trash_restore(body: TrashBody) -> dict:
    """恢复。**整批原子**：有一条对不上就整批不动。"""
    from amti import trash as T
    r = T.restore(body.keys)
    if not r["ok"]:
        raise HTTPException(400, r["error"] + "：" + "、".join(
            r.get("not_found", []) + r.get("clash", [])))
    return r


@app.post("/api/trash/delete", deprecated=True)
def trash_delete_batch_legacy(body: BatchDeleteBody) -> dict:
    """旧路径 → 同 `POST /api/trash`（REST：往回收站这个集合里放东西）。"""
    return trash_delete_batch(body)


@app.delete("/api/trash")
def trash_purge_rest(body: BatchDeleteBody) -> dict:
    """REST 版清空：`DELETE /api/trash`（旧路径 `/api/trash/purge` 保留）。"""
    return trash_purge(body)


@app.post("/api/trash/purge", deprecated=True)
def trash_purge(body: TrashBody) -> dict:
    """**真删**，之后恢复不了。`keys` 为空 = 清空整个回收站。"""
    from amti import trash as T
    r = T.purge(body.keys or None, password=body.password, confirm_all=True)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error") or "清空失败")
    return r


@app.get("/api/changes")
def changes() -> dict:
    r"""**变更记录**列表。

    这些是 MIGRATE 级迁移留下的报告（`变更记录/*.md`）——每次「规则改了
    存量数据」都要留一份，写清**改了几道、改了哪些、依据是什么**。
    顶层设计 §4.3 要求 MIGRATE 可追溯，这就是那本账。
    """
    from amti.audit import CHANGE_DIR as d      # 项目根下的 变更记录/
    if not d.is_dir():
        return {"items": []}
    items = []
    for f in sorted(d.glob("*.md"), reverse=True):
        st = f.stat()
        # 文件名形如 `20260913_023556_答案写进填空位.md`
        parts = f.stem.split("_", 2)
        stamp = parts[0]
        if len(parts) >= 2:
            stamp = "%s-%s-%s %s:%s" % (parts[0][:4], parts[0][4:6], parts[0][6:8],
                                        parts[1][:2], parts[1][2:4])
        items.append({
            "name": f.name,
            "rule": parts[2] if len(parts) > 2 else f.stem,
            "at": stamp,
            "bytes": st.st_size,
            "mtime": st.st_mtime,
        })
    return {"items": items}


@app.get("/api/changes/{name:path}")
def change_detail(name: str) -> dict:
    """读一份变更记录。**只允许读 变更记录/ 里的 .md**，防目录穿越。"""
    from amti.audit import CHANGE_DIR as d
    f = (d / urllib.parse.unquote(name)).resolve()
    if d.resolve() not in f.parents or f.suffix != ".md" or not f.is_file():
        raise HTTPException(404, "没有这份记录")
    return {"name": f.name, "text": f.read_text(encoding="utf-8")}


_BASE: dict = {"key": None, "v": None}


@app.get("/api/baseline")
def baseline() -> dict:
    """冻结基线的状态——UI 顶部常驻显示「存量题有没有被改」。

    缓存按卷文件签名失效：`store.diff()` 要把全库解析一遍（0.9 秒），
    而顶部这块**每次打开页面都要读**。
    """
    sig = store._vol_signature()
    if _BASE["key"] == sig and _BASE["v"] is not None:
        return _BASE["v"]
    d = store.diff()
    v = {"基线": d["基线题数"], "当前": d["当前题数"],
         "新增": len(d["新增"]),
         "内容变化": len(d["内容变化"]),
         "删除": len(d["删除"]),
         # 有意为之的三类，分开报——顶栏不该把自己改的东西也标成警告
         "求解写入": len(d.get("求解写入", [])),
         "录入升级": len(d.get("录入升级", [])),
         "界面补录": len(d.get("界面补录", [])),
         "规则迁移": len(d.get("规则迁移", [])),
         "变动清单": d["内容变化"][:20]}
    _BASE["key"] = sig
    _BASE["v"] = v
    return v


@app.get("/api/search/status")
def search_status() -> dict:
    """检索索引状态：在不在、多少条、是不是当前卷签名、占多少字节。"""
    from amti import fts as _fts
    return _fts.status()


# ── 静态前端 ──────────────────────────────────────────────────────────

if UI_DIST.exists():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        # no-cache：前端重建后刷新即生效（旧项目的坑：
        # index.html 没缓存头 → 改了前端要 Cmd+Shift+R 才看得到）
        return FileResponse(UI_DIST / "index.html",
                            headers={"Cache-Control": "no-cache, must-revalidate"})
else:
    # 别静默跳过：以前这里什么都不说，免安装版就成了"接口都能用、首页 404"，
    # 排查时只能靠猜。源码运行时没构建前端也会走到这里。
    log.warning("找不到前端 %s —— 只提供 API，界面打不开"
                "（源码运行请先 cd web && npm run build）", UI_DIST)


def main() -> int:
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser(description="AmTiKu Web 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--open", action="store_true",
                    help="启动后自动打开浏览器")
    ap.add_argument("--exit-with-browser", action="store_true",
                    help="浏览器页面一关就退出（配合 --open 用）")
    a = ap.parse_args()

    url = f"http://{a.host}:{a.port}"
    print(f"AmTiKu → {url}")

    # **预热**：把全库读进缓存、把知识点索引建好。
    # 不做的话，第一次打开页面要等 2 秒多（全库 17,554 道现读现解析）。
    # 这里花 1 秒，换用户第一次点开就是快的。
    def _warm():
        t0 = time.time()
        try:
            n = len(store.load_cached())
            from amti import knowledge as _kb
            _kb._index()
            _seq_of("")                     # 建 key→录入序号 表
            print("  已预热 %d 道（%.1fs）" % (n, time.time() - t0))
        except Exception as e:
            print("  预热失败（不影响使用）：%s" % e)
    threading.Thread(target=_warm, daemon=True).start()

    if a.exit_with_browser:
        # 看门狗只在这里起。命令行调用时页面从没打开过，
        # 起看门狗会**立刻**把服务杀掉。
        threading.Thread(target=_watchdog, daemon=True).start()
        print("  页面关闭后会自动退出")

    if a.open:
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    # 预热「录入序号」表：原本首个列表请求要全库走一遍才建好
    try:
        _seq_of("")
        log.info("录入序号表已预热：%s 道", len(_SEQ))
    except Exception:
        log.warning("预热录入序号表失败（不影响启动）", exc_info=True)

    log.info("AmTiKu 服务启动：http://%s:%s", a.host, a.port)
    # 服务退了就把**我们自己起的**读图服务一并收掉，否则它会变成孤儿进程
    # 一直占内存（实测残留过 10 小时）。`atexit` 覆盖正常退出；
    # `os._exit` 那条路（关浏览器的看门狗）由 `_cleanup_vision()` 单独负责。
    atexit.register(_cleanup_vision)
    # `atexit` 在**被信号打死**时不执行（实测 `kill -TERM` 进程直接没了，
    # 读图服务就成了孤儿）。所以 SIGTERM/SIGINT 也要自己接一下：
    # 先收尾，再交回默认行为退出。
    import signal

    def _on_signal(signum, _frame):
        _cleanup_vision()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for _sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(_sig, _on_signal)
        except (ValueError, OSError):
            pass                                  # 非主线程 / 平台不支持
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
