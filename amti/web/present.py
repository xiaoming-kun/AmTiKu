"""题目 → 前端 JSON 的唯一序列化口径。

`_brief` 原来住在 `server.py`，审阅路由也要用；拆路由时如果直接
`from amti.web.server import _brief` 就会循环导入。这里只依赖 schema /
latex_blocks / review / query，不依赖 Web 层。
"""
from __future__ import annotations

from amti import knowledge_map
from amti import latex_blocks as lb
from amti import review as review_mod
from amti.schema import QTYPE_LABEL
from amti.web.query import flags_of


def stage_of(q, stage_map: dict | None = None) -> str:
    """一道题属于哪个学段。没有考点标签的存量题默认算高中。

    批量遍历时把 `stage_index()` 算一次传进来，别每道题 stat 一遍知识地图。
    """
    m = stage_map if stage_map is not None else knowledge_map.stage_index()
    for pid in q.points or ():
        s = m.get(pid)
        if s:
            return s
    return "senior"


def brief(q) -> dict:
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
        "flags": flags_of(q),
        "review": review_mod.info(q),
    }
