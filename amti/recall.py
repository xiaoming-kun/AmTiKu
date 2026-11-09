"""AmTiKu · 检索召回的唯一入口。

`amti/web/query.py` 负责“命中/过滤/排序”，这里只负责**把候选集缩到几百到
几千条**，两者合起来才是完整检索：

    recall(kw) ──┬─ 纯中文 2 字以上 → FTS5（bm25 名次）
                 ├─ 公式特征       → 内容库 math_strict/math_loose
                 └─ 其他           → None（走原来的 kw_hit 全库扫）

为什么要单独一层：列表和组卷必须**从同一批候选**里挑题。以前 FTS 逻辑
内联在 `/api/questions`，组卷根本不知道“列表搜到了哪 300 道”；现在两边
都调 `recall()`，再交给同一个 `QuestionFilter`。

边界：
- 公式召回返回 `None` = 内容库没建好/过期，调用方回退（不要当成 0 结果）。
- 公式召回返回空集 = 真没命中，调用方可以按空集处理，也可以回退原文扫；
  这里选择回退（`keys=None`），保证 `\\cos` 这类原文写法仍能中。
- 中文+公式混合查询暂不拆词，走原路径；逐词 AND 是下一阶段。
"""
from __future__ import annotations

import re

from . import content_store
from . import fts
from . import search

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_PURE_CJK_RE = re.compile(r"^[\u3400-\u9fff]{2,}$")
_TERM_SPLIT = re.compile(r"[\s,，、;；]+")


def _term_keys(t: str) -> set[str] | None:
    """单个词 → 候选集；召回不了返回 None。"""
    if _CJK_RE.search(t):
        keys = fts.search(t, limit=3000)
        return set(keys) if keys else None
    if search.looks_math(t):
        forms = search.math_forms(t)
        ranks = content_store.search_math(forms, base=search.math_base(t))
        return set(ranks) if ranks else None
    return None


def recall(kw: str) -> dict:
    """返回 `{mode, keys, ranks, normalized}`。

    mode：
      * `fts`  纯中文；keys 是候选，ranks 是 bm25 名次
      * `math` 公式；keys 是命中集，调用方应跳过 `kw_hit`
      * `none` 没有召回，按原路径全库扫
    """
    kw = (kw or "").strip()
    out = {"mode": "none", "keys": None, "ranks": {}, "normalized": ""}
    if not kw:
        return out

    if _PURE_CJK_RE.match(kw):
        keys = fts.search(kw, limit=3000)
        if keys:
            out.update(mode="fts", keys=frozenset(keys),
                       ranks={k: i for i, k in enumerate(keys)},
                       normalized=kw)
        return out

    # 多词且含公式：逐词召回取交集（`三角形 cosB`、`cosB sinA`）。
    # 每个词都必须能召回；有一个召回不了就退回原路径，不猜。
    terms = [t for t in _TERM_SPLIT.split(kw) if t]
    has_math = any(search.looks_math(t) and not _CJK_RE.search(t) for t in terms)
    if has_math and len(terms) > 1:
        sets = []
        for t in terms:
            got = _term_keys(t)
            if not got:
                return out
            sets.append(got)
        inter = set.intersection(*sets)
        if inter:
            out.update(mode="mixed", keys=frozenset(inter), normalized=kw)
        return out

    # 纯中文多词（`函数 单调`）仍走原路径：`kw_hit` 的逐词 AND 更精确
    if _CJK_RE.search(kw):
        return out

    if search.looks_math(kw):
        forms = search.math_forms(kw)
        ranks = content_store.search_math(forms, base=search.math_base(kw))
        if ranks:
            out.update(mode="math", keys=frozenset(ranks), ranks=ranks,
                       normalized=forms[0] if forms else kw)
        # keys 为空/None 都回退原路径：`\cos` 这类原文写法还能中
    return out


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(recall(" ".join(sys.argv[1:]) or "cosB"),
                     ensure_ascii=False, default=list))
