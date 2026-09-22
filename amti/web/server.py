"""AmTiKu · Web 后端

只做三件事：把题目读出来、把统计算出来、把卷子导出来。
**不缓存、不写库**——分卷文件是唯一真相，每次请求现读。

接口按 UI 的需要设计，不是按数据库的表结构：

    GET  /api/questions      列表（带筛选）—— 工作台左中栏
    GET  /api/questions/{key} 单题详情
    GET  /api/stats          统计
    GET  /api/facets         筛选项（题型/来源/考点，带计数）
    POST /api/export         导出套卷（LaTeX/elegantbook）
    POST /api/export/slidev  导出 Slidev 讲义（幻灯片式）
    POST /api/export/slidev-blocks  从内容块导出讲义（块模式）
    POST /api/export/slidev-canvas  从画布导出讲义（绝对定位 + 模板类）
    GET/POST/DELETE /api/handouts   讲义存档
    GET  /api/figure         题图
"""
from __future__ import annotations

from amti.paths import ROOT, UI_DIST
import json
from collections import Counter, OrderedDict
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
from pydantic import BaseModel

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
OUT_DIR = PKG / "试卷"

log = get_logger(__name__)

# ── 导出串行化 ────────────────────────────────────────────
# 后端审查报告 Important #6：导出是 30s~分钟级的长任务，且都往同一个
# Slidev 临时目录写、共用一份 node_modules。并发跑会互相踩（一个在清理
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
async def _same_origin_only(request, call_next):
    r"""只接受本机来源的请求。

    后端审查报告 Important #4：只 bind 127.0.0.1 是**对的一半** ——
    浏览器允许**任意网页**向 http://127.0.0.1:8899 发 POST（同源策略
    只挡"读取响应"，不挡"发送"）。而删除口令默认写死在源码里，
    于是任意网页都能触发 `/api/trash/delete`。
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
# 列表里一屏七道题六道飘着红标签，而绝大多数数学题本来就不需要图。
# 警报发得太滥就等于没有警报——真正缺图的那几道反而被淹了。
_NEEDS_FIGURE = re.compile(r"如图|如下图|上图|下图|右图|左图|图中|如图\s*\d|如图所示的")


def _has_figure(q) -> bool:
    """有图，**或者根本不需要图**。只有"说了如图却没有图"才返回 False。"""
    stem = q.stem or ""
    if "\\includegraphics" in stem or "tikzpicture" in stem or q.figures:
        return True
    return not _NEEDS_FIGURE.search(stem)


def _cheap_fields(q) -> dict:
    """不跑 IR 解析就能拿到的字段。筛选只看这些。"""
    return {
        "points": q.points,
        "difficulty": q.difficulty,
        "stars": q.stars,
        "point_titles": q.point_titles,
        "meta": q.meta,
        "kind": q.kind,
        "missing": q.missing(),
        "problems": q.problems(),
        "flags": {
            "答案": bool(q.answer.strip()),
            "解析": bool(q.solution.strip()),
            "图": _has_figure(q),
            "标签": bool(q.points),
            "小问": "\\begin{enumerate}" in q.stem,
            "存疑": bool(q.meta.get("solve_warn")),
        },
    }


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
            "stem": lb.parse_blocks(q.stem),
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
        "flags": {
            "答案": bool(q.answer.strip()),
            "解析": bool(q.solution.strip()),
            "图": _has_figure(q),
            "标签": bool(q.points),
            "小问": "\\begin{enumerate}" in q.stem,
            # 求解自相矛盾（解析说选 D、答案栏写 C）——界面标黄提示人工复核
            "存疑": bool(q.meta.get("solve_warn")),
        },
    }


@app.get("/api/questions")
def list_questions(
    q: str = "", type: str = "", kind: str = "",
    point: str = "",          # 考点 id，逗号分隔，命中任一即可
    difficulty: str = "",     # 难度，逗号分隔
    year: str = "",           # 年份，逗号分隔
    source: str = "",         # 卷别，逗号分隔
    has: str = "",            # 逗号分隔：答案,解析,图,标签 → 只列**有**的
    missing: str = "",        # 逗号分隔：只列**缺**的
    sort: str = "",           # "" 原序 / new 新录入 / old 旧录入 / solved 刚解出的
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
    kw = q.strip()

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
        if kw and kw not in item.stem and kw not in item.answer:
            continue
        if has_set or miss_set:
            c = _cheap_fields(item)
            if has_set and not all(c["flags"].get(k) for k in has_set):
                continue
            if miss_set and not all(not c["flags"].get(k) for k in miss_set):
                continue
        keep.append(item)

    if sort == "new":
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


@app.patch("/api/questions/{key:path}")
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
         "type": "multi_choice"}         # **改题型**（目前只放开 单选↔多选）
    """
    # ⚠️ **白名单：只有这三个字段能改，其余一律拒绝。**
    #
    # 界面上「考点」「难度」是标签，改它们是日常操作；
    # **题目正文（题干/选项/答案/解析/配图）一个字都不许从界面改**——
    # 那是数据，改它要走「改题目 → 重新录入」的正规路径，
    # 而且要过规范验证、查重、影响面这几关。
    #
    # 老写法是「只读认识的字段、其余静默忽略」——安全，但**不响**：
    # 有人想改题干，接口回 200，他会以为改成功了。
    # 现在直接 400 说清楚。
    ALLOWED = {"points", "difficulty", "stars", "answer", "type"}
    unknown = set(body) - ALLOWED
    if unknown:
        raise HTTPException(400, (
            "只允许改 %s；收到 %s。"
            "题目正文（题干/选项/解析/配图）**不能从界面改**——"
            "要改请改题目源文件后重新录入。"
            "（**答案**可以改，见 `answer`。）"
            % ("、".join(sorted(ALLOWED)), "、".join(sorted(unknown)))))

    k = urllib.parse.unquote(key)
    qs = store.load_all()
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

    type_note = ""
    if "type" in body:
        type_note = _convert_type(q, str(body.get("type") or "").strip())
        if type_note:
            q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    if "answer" in body:
        new_ans = _clean_answer_input(q, body.get("answer"))
        q.answer = new_ans
        q.meta["answer_source"] = "human"       # 人补的，和求解器写的分开记
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

    # ⚠️ 用 rewrite_all（**按 PER_VOLUME 重新分卷**），不要用 rewrite_volume(1,…)：
    # 后者会把所有卷的题都写进第 1 卷，而其它卷还在 → 整库重复。
    store.rewrite_all(qs)

    # **记档**：标签是人工改的，要留痕（只记标签，不记正文）
    _audit_tag_change(q, before=before, fields=body)

    d = _brief(q)
    d["tex"] = question_to_tex(q)
    return d


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
def question_solution(key: str, body: SolutionBody) -> dict:
    r"""补/改**解析与答案**。默认干跑，`dry_run=false` 才落盘。"""
    from amti import conform as _cf
    from amti import normalize as _norm

    k = urllib.parse.unquote(key)
    qs = store.load_all()
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
    if body.answer.strip():
        q.meta["answer_source"] = "human"
    q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    store.rewrite_all(qs)

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
    (types, kinds, points, diffs, years,
     sources) = (Counter(), Counter(), Counter(), Counter(), Counter(), Counter())
    for q in store.load_cached():
        types[q.type] += 1
        kinds[q.kind] += 1          # 只有两类：高考 / 模拟
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
        # 录入批次：按「书」给出先后（文件里的追加顺序）。
        # 用户想看「我新录的 vs 早先录的」，这个顺序就是答案。
        "batches": _batches(),
    }


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
    kw = body.q.strip()

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
        if kw and kw not in item.stem and kw not in item.answer:
            continue
        if has_set or miss_set:
            f = _cheap_fields(item)["flags"]
            if has_set and not all(f.get(k) for k in has_set):
                continue
            if miss_set and not all(not f.get(k) for k in miss_set):
                continue
        pool.append(item)

    if body.mode == "coverage":
        # **按考点覆盖率组卷**：以「尽量多覆盖考点」为目标挑题，
        # 挑完**按易→难排好**。跟 `gaokao` 那种"填卷面位置"是两回事。
        r = _gen.generate_by_coverage(pool, want=body.want,
                                      coverage=body.coverage, seed=body.seed)
        r["slots"] = []
    else:
        r = _gen.generate(pool, mode=body.mode, seed=body.seed)

    # 顺带把每道题的显示信息带上，前端要列卷子
    by_key = {q.key: _brief(q) for q in pool}
    r["items"] = [by_key.get(k) for k in r["keys"] if k in by_key]
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
    update_existing: bool = True        # 库里已有这道题：手里这份更全就**升级**
    update_force: bool = False          # 连已有的解析也覆盖（默认只补不覆盖）
    merge_into: dict = {}               # {新题key: 库内key} —— 界面上点「并入这道」
    dup_threshold: float = 0.80


@app.post("/api/ingest/preview")
def ingest_preview(body: IngestBody) -> dict:
    """**干跑**：解析 + 图片预检 + 查重 + 校验 + 影响面。什么都不写。"""
    from amti import ingest as _ig
    src = [body.src_dir] if body.src_dir.strip() else None
    pts = [x.strip() for x in body.points.split(",") if x.strip()]
    pv = _ig.preview(body.text, src_dirs=src, book=body.book, label=body.label,
                     region=body.region, year=body.year,
                     source_no=body.source_no, points=pts or None,
                     difficulty=body.difficulty.strip(),
                     update_force=body.update_force,
                     merge_into=body.merge_into or None,
                     dup_threshold=body.dup_threshold)
    # 顺带把渲染用的块级 IR 也带上，前端要实时预览
    for it, q in zip(pv["items"], _ig.parse_source(
            body.text, book=body.book, label=body.label,
            region=body.region, year=body.year,
            source_no=body.source_no, points=pts or None,
            difficulty=body.difficulty.strip())["questions"]):
        it["blocks"] = {
            "stem": lb.parse_blocks(q.stem),
            "answer": lb.parse_blocks(q.answer),
            "solution": lb.parse_blocks(q.solution),
            "options": [lb.parse_blocks(o.text) for o in q.options],
        }
    return pv


@app.post("/api/ingest/commit")
def ingest_commit(body: IngestBody) -> dict:
    """正式导入：图片入库 → 追加主文件。返回变更报告。"""
    from amti import ingest as _ig
    src = [body.src_dir] if body.src_dir.strip() else None
    pts = [x.strip() for x in body.points.split(",") if x.strip()]
    return _ig.commit(body.text, src_dirs=src, book=body.book, label=body.label,
                      region=body.region, year=body.year,
                      source_no=body.source_no, points=pts or None,
                      difficulty=body.difficulty.strip(),
                      update_existing=body.update_existing,
                      update_force=body.update_force,
                      merge_into=body.merge_into or None)


@app.get("/api/stats/detail")
def stats_detail() -> dict:
    """统计页：考点覆盖、难度分布、完整性缺口、标签来源。"""
    from collections import Counter
    from amti import knowledge as kb
    qs = store.load_cached()
    pts: Counter = Counter()
    for q in qs:
        for p in q.points:
            pts[p] += 1
    src = Counter(q.meta.get("point_source") or "无" for q in qs)
    miss: Counter = Counter()
    for q in qs:
        for m in q.missing():
            miss[m] += 1
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
        "points_covered": len(pts),
        "points_total": len(kb.all_points()),
        # 全部考点，含 0 题目的——**空考点本身就是要看的信息**
        "all_points": [{"value": p["id"], "title": kb.title_of(p["id"]),
                        "n": pts.get(p["id"], 0), "topic": p["topic"],
                        "section": p["section"],
                        "stars": p["stars"], "difficulty": p["difficulty"]}
                       for p in sorted(kb.all_points(),
                                       key=lambda x: [int(y) if y.isdigit() else 0
                                                      for y in x["id"].split(".")])],
        "by_topic": [{"value": t, "n": sum(pts.get(p["id"], 0)
                                           for p in kb.all_points() if p["topic"] == t),
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
    """在访达中显示。**只允许项目内的路径**，防止把任意路径交给 Finder。"""
    import subprocess
    p = Path(path).resolve()
    root = PKG.resolve()
    if root not in p.parents and p != root:
        raise HTTPException(403, "只能打开项目内的文件")
    if not p.exists():
        raise HTTPException(404, f"不存在：{p}")
    subprocess.Popen(["open", "-R", str(p)])
    return {"ok": True, "revealed": str(p)}


@app.get("/api/figure")
def figure(path: str, raw: int = 0):
    r"""题库图片。

    默认做**白底转透明** —— 题库的图多是白底，贴在米色讲义上会显出一个
    白方块，很突兀。讲义导出时（slidev_handout._copy_trimmed）也做同样处理，
    这样**编辑器预览与导出 PDF 一致**。
    传 ?raw=1 拿原图。
    """
    p = (IMG_DIR / path).resolve()
    if not str(p).startswith(str(IMG_DIR.resolve())) or not p.exists():
        raise HTTPException(404, f"没有这张图：{path}")
    if raw:
        return FileResponse(p)

    # 处理结果缓存到 图片/_transparent/
    cache_dir = IMG_DIR / "_transparent"
    try:
        cache_dir.mkdir(exist_ok=True)
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
    answers_at_end: bool = False        # 答案与解析统一放卷末（真高考卷的做法）
    handout_font: str = ""              # 讲义字号，见 paper.HANDOUT_SIZES
    bottom_sep: str = ""                # 题目间距，如 "0.6em"
    problem_blank_cm: float | None = None
    mode: str = "gaokao"                # gaokao 高考卷 / test 纯测试题 / handout 讲义
    compile: bool = True


class BlocksBody(BaseModel):
    """讲义内容块列表（讲义编辑器用）。

    块类型：chapter/section/point/text/formula/question
    其中 question 只存 key，引用题库；其余是老师自己写的内容。
    """
    title: str = ""
    out: str = ""
    blocks: list[dict] = []
    ratio: str = "16:9"
    density: str = "normal"
    with_answers: bool = False
    compile: bool = True


class CanvasBody(BaseModel):
    """画布讲义（绝对定位）。

    pages: [{"blocks":[{"type","x","y","w","h",...}]}]
    坐标用百分比（0-100），换比例时按比例重算。
    """
    title: str = ""
    out: str = ""
    pages: list[dict] = []
    ratio: str = "16:9"
    with_answers: bool = False
    compile: bool = True
    title_font: str = ""       # 标题字体（CSS font-family）
    body_font: str = ""        # 正文字体
    show_source: bool = True   # 高考题是否标出处（2024新高考I卷 第1题）


class CanvasSaveBody(BaseModel):
    name: str
    title: str = ""
    pages: list[dict] = []
    ratio: str = "16:9"
    with_answers: bool = False
    title_font: str = ""
    body_font: str = ""
    show_source: bool = True


class HandoutSaveBody(BaseModel):
    name: str
    title: str = ""
    blocks: list[dict] = []
    ratio: str = "16:9"
    density: str = "normal"
    with_answers: bool = False


class SlidevHandoutBody(BaseModel):
    """Slidev 讲义（幻灯片式，低密度、可批注）。

    与 ExportBody 的 `handout` 模式区别：
      handout 模式 → LaTeX/elegantbook，A4 印刷讲义
      本模型       → Slidev，16:9 / A4 / 4:3 幻灯片讲义
    """
    title: str = ""
    out: str = ""
    keys: list[str] = []
    ratio: str = "16:9"                 # 16:9 / a4 / 4:3
    density: str = "normal"             # tight / normal / loose
    with_answers: bool = False          # 教师版显示答案
    page_numbers: bool = True
    compile: bool = True


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
                   show_answers=body.show_answers, answers_at_end=body.answers_at_end,
        handout_font=body.handout_font or _paper.HANDOUT_FONT_DEFAULT,
                   bottom_sep=body.bottom_sep or "0.6em",
                   problem_blank_cm=(body.problem_blank_cm
                                     if body.problem_blank_cm is not None else 4.0),
                   do_compile=body.compile, mode=body.mode)
    if not r.get("ok") and r.get("error"):
        raise HTTPException(400, r["error"])
    _usage_bump(body.keys)                      # ← 试卷导出计入频次
    return r


@app.post("/api/export/slidev-blocks")
@_serialized_export
def export_slidev_blocks(body: BlocksBody) -> dict:
    r"""从内容块导出讲义（支持自己写的讲解 + 题库选题）。"""
    from amti import slidev_handout as sh
    r = sh.export_blocks(body.blocks, title=body.title, out=body.out,
                         ratio=body.ratio, density=body.density,
                         with_answers=body.with_answers,
                         do_compile=body.compile)
    if not r.get("ok") and r.get("error"):
        raise HTTPException(400, r["error"])
    _usage_bump(b.get("key") for b in body.blocks
                if b.get("type") == "question")   # ← 计入频次
    return r


@app.post("/api/export/slidev-canvas")
@_serialized_export
def export_slidev_canvas(body: CanvasBody) -> dict:
    r"""从画布导出讲义（绝对定位 + 模板类）。"""
    from amti import slidev_handout as sh
    r = sh.export_canvas(body.pages, title=body.title, out=body.out,
                         ratio=body.ratio, with_answers=body.with_answers,
                         do_compile=body.compile,
                         title_font=body.title_font, body_font=body.body_font,
                         show_source=body.show_source)
    if not r.get("ok") and r.get("error"):
        raise HTTPException(400, r["error"])
    _usage_bump(b.get("key") for pg in body.pages
                for b in (pg.get("blocks") or [])
                if b.get("type") == "question")   # ← 计入频次
    return r


@app.post("/api/canvas")
def save_canvas(body: CanvasSaveBody) -> dict:
    """保存画布讲义（复用讲义存档，按 name 覆盖）。"""
    from amti import slidev_handout as sh
    # 存进 blocks 字段（存档结构兼容），内容换成 pages
    return sh.save_handout(body.name, title=body.title,
                           blocks=body.pages, ratio=body.ratio,
                           with_answers=body.with_answers,
                           extra={"title_font": body.title_font,
                                  "body_font": body.body_font,
                                  "show_source": body.show_source})


@app.post("/api/canvas/save", deprecated=True)
def save_canvas_legacy(body: CanvasSaveBody) -> dict:
    """旧路径（`/api/canvas/save`）→ 语义与 `POST /api/canvas` 相同。

    审查报告 🟡「REST 命名」：路径里不该带动词。这里保留旧路径做兼容，
    新代码请用 `POST /api/canvas`。
    """
    return save_canvas(body)


@app.get("/api/canvas/{name:path}")
def get_canvas(name: str) -> dict:
    from amti import slidev_handout as sh
    h = sh.get_handout(name)
    if not h:
        raise HTTPException(404, f"没有这份讲义：{name}")
    return h


@app.get("/api/handouts")
def list_handouts() -> dict:
    """讲义列表（不含 blocks）。"""
    from amti import slidev_handout as sh
    return {"items": sh.list_handouts()}


@app.get("/api/handouts/{name:path}")
def get_handout(name: str) -> dict:
    """读一份讲义（含 blocks）。"""
    from amti import slidev_handout as sh
    h = sh.get_handout(name)
    if not h:
        raise HTTPException(404, f"没有这份讲义：{name}")
    return h


@app.post("/api/handouts")
def save_handout(body: HandoutSaveBody) -> dict:
    """新建或覆盖一份讲义（同名覆盖）。"""
    from amti import slidev_handout as sh
    return sh.save_handout(body.name, title=body.title, blocks=body.blocks,
                           ratio=body.ratio, density=body.density,
                           with_answers=body.with_answers)


@app.delete("/api/handouts/{name:path}")
def delete_handout(name: str) -> dict:
    from amti import slidev_handout as sh
    return {"ok": sh.remove_handout(name)}


@app.get("/api/pdf")
def pdf(path: str):
    """预览用：把导出的 PDF 发出去。"""
    p = (OUT_DIR / path).resolve()
    if not str(p).startswith(str(OUT_DIR.resolve())) or not p.exists():
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
EXIT_IDLE_SEC = 25.0


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
    r"""页面关掉了（`navigator.sendBeacon`）。

    把最后 ping 时间往前推，看门狗下一轮就退出。
    用 beacon 是因为它**在页面卸载时也能发出去**，`fetch` 不保证。
    """
    _LAST_PING[0] = time.monotonic() - EXIT_IDLE_SEC - 1
    print("页面已关闭，准备退出", flush=True)
    return {"ok": True}


def _watchdog() -> None:
    """没 ping 了就退出。只在 `--exit-with-browser` 下起。"""
    while True:
        time.sleep(2.0)
        if not _PING_SEEN[0]:
            continue                       # 页面还没打开过，不算
        if time.monotonic() - _LAST_PING[0] > EXIT_IDLE_SEC:
            print("页面已关闭，题库服务退出")
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
    password: str = ""                  # 删题/清空要口令；恢复不要


@app.post("/api/questions/{key:path}/trash")
def question_trash(key: str, body: TrashBody) -> dict:
    """把一道题移进回收站。"""
    from amti import paper as _paper
    from amti import trash as T
    r = T.delete([urllib.parse.unquote(key)], reason=body.reason.strip(),
                 password=body.password)
    if not r["ok"]:
        raise HTTPException(400, r["error"])
    return r


class BatchDeleteBody(BaseModel):
    keys: list[str] = []
    reason: str = ""
    password: str = ""


@app.post("/api/trash")
def trash_delete_batch(body: BatchDeleteBody) -> dict:
    r"""**批量删题**。一次移进回收站，原因和口令与单题删除同一套规矩。

    「很多题目现在不考了」——一道道点太慢，所以要能批量。
    但批量删更危险，所以规矩一条不减：**口令 + 原因必选 + 整批原子**
    （有一条题号对不上就整批不执行，绝不删一半）。
    """
    from amti import trash as T
    r = T.delete(body.keys, reason=body.reason.strip(), password=body.password)
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
    items = []
    for x in T.all_items():
        q = x.get("question") or {}
        items.append({
            "key": x["key"], "deleted_at": x.get("deleted_at", ""),
            "reason": x.get("reason", ""), "type": q.get("type", ""),
            "stem": (q.get("stem") or "")[:200],
            "has_solution": bool((q.get("solution") or "").strip()),
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
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
