r"""AmTiKu · 知识链路

题目的**难度**从考点库派生（`knowledge.py`），考点的**前后关系**从这里派生。
本模块是 `知识链路.json` 的**唯一入口**：加载 / 校验 / 邻接 / 拓扑分层 / 体检，
别处不许再解析这个文件（`AGENTS.md` 第三节）。

数据分两层，各存一份，绝不互相复制：

    知识点.json    节点（id / 名称 / 星级 / 大类 / 节）—— knowledge.py 负责，本模块**只读**
    知识链路.json  边（pre → post，hard/soft + 理由）—— 本模块负责

为什么不把节点也存进来：存了就是第二份真相，而两份真相迟早分叉，
分叉了没有任何机制能发现。所以这里只存边，节点一律现取。

边的语义只有一种（见 `设计/知识链路.md`）：

    pre → post 表示「先学 pre，再学 post」
    strength="hard"  不掌握 pre，post 学不会   —— **硬性前置必须无环**，否则死锁
    strength="soft"  先学过 post 明显更顺，但非必需

数据里只放**直接**前置。传递闭包（祖先/后代）一律由代码算，
写进数据等于同一件事记两遍，改一处必漏另一处。
"""
from __future__ import annotations

from .paths import ROOT
import json
import re
from pathlib import Path

EDGES_PATH = ROOT / "知识链路.json"

STRENGTHS = ("hard", "soft")
# 排序权重：hard 在前。前端的「只看 hard」和清单都按这个顺序读。
_ORDER = {"hard": 0, "soft": 1}

# 理由的废话模板：复核时这种理由等于没写（起草规则里明令禁止）
_BOILER = re.compile(r"^(前置|基础|先学|是后续|后续内容|前面学过|相关内容|重要|掌握)")

# 索引缓存。键取「文件 mtime+size」——改了链路自动失效。
# knowledge.py 踩过这个坑：不缓存的话一屏 152 个节点要重读解析 JSON 上千次。
_IDX: dict = {"key": None, "v": None}


# ── 加载与清洗 ────────────────────────────────────────────────

def _sig() -> tuple | None:
    try:
        st = EDGES_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def raw() -> dict:
    """文件原样内容。文件不存在时返回空壳（模块要能在没有链路数据时也不炸）。"""
    sig = _sig()
    if sig is None:
        return {"version": 1, "edges": []}
    try:
        return json.loads(EDGES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "edges": []}


def index() -> dict:
    r"""清洗后的图：`{edges, fwd, rev, dropped}`。

    `dropped` 是**被剔掉的边**（悬空引用 / 自环 / 重复 / 字段非法），
    体检面板要把它们报出来——静默丢弃等于数据坏了没人知道。
    """
    sig = _sig()
    if _IDX["key"] == sig and _IDX["v"] is not None:
        return _IDX["v"]
    from . import knowledge as kb          # 局部导入：本模块不依赖 store，自检才快
    v = _build(raw().get("edges") or [], set(kb._index()))
    _IDX["key"] = sig
    _IDX["v"] = v
    return v


def _build(raw_edges: list, known: set[str]) -> dict:
    """纯函数：把原始边清洗成邻接表。不碰文件，自检直接喂合成数据。

    清洗规则（每条被剔的边都留痕）：
      ① id 不在知识点库 → 剔（用户可能整个换掉 知识点.json）
      ② 自环 → 剔
      ③ 同一 (pre, post) 重复 → 去重；hard 与 soft 同时出现 → **取 hard**
      ④ strength / reason / 名缺失或非法 → 剔
    """
    edges: dict[tuple, dict] = {}
    dropped: list[dict] = []

    for e in raw_edges:
        if not isinstance(e, dict):
            dropped.append({"edge": e, "why": "不是对象"})
            continue
        pre, post = str(e.get("pre") or "").strip(), str(e.get("post") or "").strip()
        st = str(e.get("strength") or "").strip()
        why = str(e.get("reason") or "").strip()
        if pre not in known or post not in known:
            dropped.append({"edge": {"pre": pre, "post": post}, "why": "引用了知识点库里没有的 id"})
            continue
        if pre == post:
            dropped.append({"edge": {"pre": pre, "post": post}, "why": "自环"})
            continue
        if st not in STRENGTHS:
            dropped.append({"edge": {"pre": pre, "post": post}, "why": "strength 非法：%r" % st})
            continue
        if not why:
            dropped.append({"edge": {"pre": pre, "post": post}, "why": "没有理由"})
            continue
        key = (pre, post)
        old = edges.get(key)
        if old is None:
            edges[key] = {"pre": pre, "post": post, "strength": st, "reason": why,
                          "kind": str(e.get("kind") or "prereq")}
        elif _ORDER[st] < _ORDER[old["strength"]]:
            # 同一条边既标 hard 又标 soft：以 hard 为准（hard 是更强的断言，
            # 若它成立，soft 只是同一句话说得更弱）
            edges[key] = {"pre": pre, "post": post, "strength": st, "reason": why,
                          "kind": str(e.get("kind") or "prereq")}

    out = sorted(edges.values(), key=lambda x: (_ORDER[x["strength"]], x["post"], x["pre"]))
    fwd: dict[str, list[dict]] = {}
    rev: dict[str, list[dict]] = {}
    for e in out:
        fwd.setdefault(e["pre"], []).append(e)      # pre 的后续
        rev.setdefault(e["post"], []).append(e)     # post 的前置
    return {"edges": out, "fwd": fwd, "rev": rev, "dropped": dropped}


# ── 查询 ──────────────────────────────────────────────────────

def prereqs_of(pid: str) -> list[dict]:
    """直接前置（先修），hard 在前，同强度按 id 排。"""
    r = index()["rev"].get(pid, [])
    return sorted(r, key=lambda e: (_ORDER[e["strength"]], e["pre"]))


def next_of(pid: str) -> list[dict]:
    """直接后续（学完它之后能学什么）。"""
    r = index()["fwd"].get(pid, [])
    return sorted(r, key=lambda e: (_ORDER[e["strength"]], e["post"]))


def closure(pid: str, direction: str = "pre", hard_only: bool = False) -> list[str]:
    r"""全部祖先（`pre`）或全部后代（`post`），**去重**，按拓扑深度由近到远。

    数据里只存直接边，所以这种"一路往上/往下"的查询必须由代码算。
    成环时靠 `seen` 兜底，不会转不出来。
    """
    adj = index()["rev" if direction == "pre" else "fwd"]
    step = "pre" if direction == "pre" else "post"
    seen: set[str] = set()
    layer = [pid]
    out: list[str] = []
    while layer:
        nxt: list[str] = []
        for cur in layer:
            for e in adj.get(cur, []):
                if hard_only and e["strength"] != "hard":
                    continue
                q = e[step]
                if q in seen or q == pid:
                    continue
                seen.add(q)
                out.append(q)
                nxt.append(q)
        layer = nxt
    return out


def roots() -> list[str]:
    """没有前置的考点（起点）。"""
    from . import knowledge as kb
    return [p["id"] for p in kb.all_points() if not prereqs_of(p["id"])]


def depth() -> dict[str, int]:
    r"""按 **hard** 边算拓扑深度：0 = 起点，n = 最长 hard 前置链长度。

    为什么只用 hard：soft 边是"有帮助"，拿它分层会把"可跳过的建议"
    画成必须的纵深，图会失真。soft 环也不会污染分层（规则③）。
    成环（不该发生，但数据是人写的）时把剩下的节点按已知深度兜底，绝不抛异常。
    """
    from . import knowledge as kb
    ids = [p["id"] for p in kb.all_points()]
    known = set(ids)
    indeg = {i: 0 for i in ids}
    for e in index()["edges"]:
        if e["strength"] == "hard" and e["post"] in known:
            indeg[e["post"]] += 1
    d = {i: 0 for i in ids}
    queue = [i for i in ids if indeg[i] == 0]
    seen = set(queue)
    while queue:
        cur = queue.pop(0)
        for e in index()["fwd"].get(cur, []):
            if e["strength"] != "hard" or e["post"] not in known:
                continue
            if d[cur] + 1 > d[e["post"]]:
                d[e["post"]] = d[cur] + 1
            indeg[e["post"]] -= 1
            if indeg[e["post"]] <= 0 and e["post"] not in seen:
                seen.add(e["post"])
                queue.append(e["post"])
    return d


# ── 体检 ──────────────────────────────────────────────────────

def _cycles(hard_only: bool) -> list[list[str]]:
    """找环（DFS）。hard_only=True 只走 hard 边——那是**必须**无环的那张图。"""
    from . import knowledge as kb
    ids = [p["id"] for p in kb.all_points()]
    color: dict[str, int] = {}
    found: list[list[str]] = []
    stack: list[str] = []

    def walk(u: str) -> None:
        color[u] = 1
        stack.append(u)
        for e in index()["fwd"].get(u, []):
            if hard_only and e["strength"] != "hard":
                continue
            v = e["post"]
            if color.get(v) == 1:
                found.append(stack[stack.index(v):] + [v])
            elif color.get(v, 0) == 0:
                walk(v)
        stack.pop()
        color[u] = 2

    for i in ids:
        if color.get(i, 0) == 0:
            walk(i)
    # 同一个环可能从不同入口被找到多次，去重（按节点集合规范化）
    uniq: dict[frozenset, list[str]] = {}
    for c in found:
        uniq.setdefault(frozenset(c), c)
    return list(uniq.values())


def audit() -> dict:
    r"""链路体检。`errors` 非空 = 数据有毛病；`warn` = 值得人看一眼。

    规则见 `设计/知识链路.md` 第三节，这里是它的唯一实现。
    """
    from . import knowledge as kb
    pts = kb.all_points()
    idx = index()
    edges = idx["edges"]

    errors: list[dict] = []
    warn: list[dict] = []

    for d in idx["dropped"]:
        errors.append({"code": "dropped", "level": "error",
                       "msg": "剔掉一条边：%s（%s → %s）"
                              % (d["why"], d["edge"].get("pre"), d["edge"].get("post"))})

    hard_cycles = _cycles(hard_only=True)
    for c in hard_cycles:
        errors.append({"code": "hard_cycle", "level": "error", "ids": c,
                       "msg": "硬性前置成环（死锁，永远点不亮）：%s" % " → ".join(c)})

    soft_cycles = [c for c in _cycles(hard_only=False) if frozenset(c) not in
                   {frozenset(x) for x in hard_cycles}]
    for c in soft_cycles:
        warn.append({"code": "cycle", "level": "warn", "ids": c,
                     "msg": "存在环（含 soft 边，语义上可能但请确认）：%s" % " → ".join(c)})

    for e in edges:
        if len(e["reason"]) < 6 or _BOILER.match(e["reason"]):
            warn.append({"code": "weak_reason", "ids": [e["pre"], e["post"]],
                         "msg": "%s → %s 的理由像套话：「%s」"
                                % (e["pre"], e["post"], e["reason"])})

    no_pre = [p["id"] for p in pts if not prereqs_of(p["id"])]
    no_post = [p["id"] for p in pts if not next_of(p["id"])]
    hard_edges = [e for e in edges if e["strength"] == "hard"]
    ratio = (len(hard_edges) / len(edges)) if edges else 0.0
    if edges and ratio > 0.95:
        warn.append({"code": "no_soft", "msg": "hard 边占 %.0f%%，几乎没有 soft——"
                                               "两种强度的区分度可能没做出来" % (ratio * 100)})

    return {
        "ok": not errors,
        "errors": errors,
        "warn": warn,
        "stats": {
            "nodes": len(pts),
            "edges": len(edges),
            "hard": len(hard_edges),
            "soft": len(edges) - len(hard_edges),
            "hard_ratio": round(ratio, 3),
            "roots": len(no_pre),          # 起点（无前置）
            "leaves": len(no_post),        # 末端（无后续）
            "isolated": len([p for p in pts
                             if not prereqs_of(p["id"]) and not next_of(p["id"])]),
            "max_depth": max(depth().values()) if pts else 0,
        },
        # 「待补清单」：体检面板直接展示，不是错误，是还没铺到的位置
        "todo": {"no_pre": no_pre, "no_post": no_post},
    }


def graph() -> dict:
    """整张图 + 节点元信息 + 深度，供 `/api/chain` 一次取走。"""
    from . import knowledge as kb
    d = depth()
    nodes = [{"id": p["id"], "title": kb.title_of(p["id"]), "stars": p["stars"],
              "difficulty": p["difficulty"], "topic": p["topic"], "section": p["section"],
              "depth": d.get(p["id"], 0),
              "n_pre": len(prereqs_of(p["id"])), "n_post": len(next_of(p["id"]))}
             for p in kb.all_points()]
    a = audit()
    return {"version": raw().get("version", 1), "updated": raw().get("updated", ""),
            "drafted": raw().get("drafted", ""),
            "nodes": nodes, "edges": index()["edges"],
            "stats": a["stats"], "errors": a["errors"]}


def node_detail(pid: str) -> dict:
    """单考点：五段式字段 + 直接前置/后续 + 全部祖先/后代。"""
    from . import knowledge as kb
    p = kb.get(pid)
    if not p:
        return {}
    kb_raw = json.loads(kb.KB_PATH.read_text(encoding="utf-8")) if kb.KB_PATH.exists() else {}
    fields = {}
    for t in kb_raw.get("topics", []):
        for s in t.get("sections", []):
            for q in s.get("points", []):
                if q.get("id") == pid:
                    fields = q.get("fields") or {}
    return {
        "id": pid, "title": kb.title_of(pid), "stars": kb.stars_of(pid),
        "difficulty": kb.difficulty_of(pid), "topic": p.get("topic", ""),
        "section": p.get("section", ""), "fields": fields,
        "pre": prereqs_of(pid), "post": next_of(pid),
        "ancestors": closure(pid, "pre"), "descendants": closure(pid, "post"),
    }


# ── 自检 ──────────────────────────────────────────────────────

def _selftest() -> int:
    fails = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + label + (("　" + detail) if detail and not cond else ""))
        if not cond:
            fails += 1

    print("chain 自检")

    # 1. 合成图：A→B(hard)→C(hard)，A→C(soft)，D 悬空，E 自环，重复边取 hard
    known = {"A", "B", "C", "Z"}
    g = _build([
        {"pre": "A", "post": "B", "strength": "hard", "reason": "甲是乙的前提"},
        {"pre": "B", "post": "C", "strength": "hard", "reason": "乙是丙的前提"},
        {"pre": "A", "post": "C", "strength": "soft", "reason": "甲对丙有帮助"},
        {"pre": "C", "post": "C", "strength": "soft", "reason": "自环"},
        {"pre": "A", "post": "Z", "strength": "hard"},                    # 没理由
        {"pre": "A", "post": "C", "strength": "hard", "reason": "重复边取 hard"},
        {"pre": "A", "post": "Q", "strength": "hard", "reason": "库里没有 Q"},
        {"pre": 1, "post": 2, "strength": "hard", "reason": "非字符串 id"},
    ], known)
    check("重复边合并为 hard", [e["strength"] for e in g["edges"] if e["pre"] == "A"
                                and e["post"] == "C"] == ["hard"])
    check("自环 / 悬空 / 无理由 都进 dropped", len(g["dropped"]) == 4,
          str([d["why"] for d in g["dropped"]]))
    check("邻接表只含有向边", g["fwd"]["A"] and g["rev"]["C"] and
          {e["pre"] for e in g["rev"]["C"]} == {"A", "B"})

    # 2. 分层：只用 hard。A=0，B=1，C=2（A→C 是 soft，不该把 C 压成 1）
    def _depth_of(g_, ids_, start_zero=None):
        indeg = {i: 0 for i in ids_}
        for e in g_["edges"]:
            if e["strength"] == "hard":
                indeg[e["post"]] += 1
        d = {i: 0 for i in ids_}
        q = [i for i in ids_ if indeg[i] == 0]
        seen = set(q)
        while q:
            cur = q.pop(0)
            for e in g_["fwd"].get(cur, []):
                if e["strength"] != "hard":
                    continue
                d[e["post"]] = max(d[e["post"]], d[cur] + 1)
                indeg[e["post"]] -= 1
                if indeg[e["post"]] <= 0 and e["post"] not in seen:
                    seen.add(e["post"]); q.append(e["post"])
        return d

    d = _depth_of(g, ["A", "B", "C", "Z"])
    check("hard 分层：A=0 B=1 C=2（soft 不参与）",
          (d["A"], d["B"], d["C"]) == (0, 1, 2), str(d))

    # 3. 闭环必须被检出（hard），soft 环只告警
    g2 = _build([
        {"pre": "A", "post": "B", "strength": "hard", "reason": "甲先于乙"},
        {"pre": "B", "post": "A", "strength": "hard", "reason": "乙先于甲"},
        {"pre": "C", "post": "Z", "strength": "soft", "reason": "丙对 Z 有帮助"},
        {"pre": "Z", "post": "C", "strength": "soft", "reason": "Z 对丙有帮助"},
    ], known)
    check("hard 环被检出", len(_find_cycles(g2, ["A", "B", "C", "Z"], True)) >= 1)
    check("soft 环不被当成 hard 环", not _find_cycles(g2, ["A", "B", "C", "Z"], True)
          or all("C" not in c or "Z" not in c for c in _find_cycles(g2, ["A", "B", "C", "Z"], True)))

    # 4. 真实库（没有链路文件时跳过，不算失败）
    if EDGES_PATH.exists():
        a = audit()
        check("真实库：没有悬空/自环/非法边", a["ok"],
              "；".join(x["msg"] for x in a["errors"][:3]))
        check("真实库：硬性前置无环",
              not [x for x in a["errors"] if x["code"] == "hard_cycle"])
        check("真实库：边数 > 0", a["stats"]["edges"] > 0, str(a["stats"]))
        print("  　%s" % a["stats"])
    else:
        print("  （还没有 知识链路.json，跳过真实库校验）")

    print("chain 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


def _find_cycles(g: dict, ids: list[str], hard_only: bool) -> list[list[str]]:
    """`_cycles()` 的纯函数版：自检喂合成图用。"""
    color: dict[str, int] = {}
    found: list[list[str]] = []
    stack: list[str] = []

    def walk(u: str) -> None:
        color[u] = 1
        stack.append(u)
        for e in g["fwd"].get(u, []):
            if hard_only and e["strength"] != "hard":
                continue
            v = e["post"]
            if color.get(v) == 1:
                found.append(stack[stack.index(v):] + [v])
            elif color.get(v, 0) == 0:
                walk(v)
        stack.pop()
        color[u] = 2

    for i in ids:
        if color.get(i, 0) == 0:
            walk(i)
    uniq: dict[frozenset, list[str]] = {}
    for c in found:
        uniq.setdefault(frozenset(c), c)
    return list(uniq.values())


if __name__ == "__main__":
    raise SystemExit(_selftest())
