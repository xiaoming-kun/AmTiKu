r"""AmTiKu · 按考点重排的讲义（讲解 + 分层选题 → LaTeX）

## 这是什么

把两样本来各管各的东西**按考点拼成一份讲义**：

    知识清单书（amti/klist.py，讲解内容源）
    题库 30,040 道（amti/store.py，选题内容源）
        │
        ├── 知识清单映射.json：152 考点 → 书节点（人工核定）
        └── 知识点.json：考点五要素 + 星级
        ↓
    讲义/考点重排/
        ├── points/1.1.3-集合的基本运算.tex   ← 每个考点一份（正文，无导言区）
        ├── main.tex                          ← 唯一导言区 + \include 全部考点
        └── 缺口报告.md                        ← 每考点三档库存、实取、缺多少

每个考点一份的结构固定：**考点档案 → 五要素 → 知识讲解 → 常考题型 →
二级结论 → 易错警示 → 知识主线 → 分层训练（简单 20／中档 40／难 40）**。

## 难度从哪儿来（本模块最大的一处设计）

题库**不给逐题难度**：`Question.difficulty` 优先用题目自带的 `meta.difficulty`，
没有就**从主考点的星级派生**（见 `amti/knowledge.py` 顶部说明）。于是同一个
考点下的题难度全一样——「每个考点 20 简单/40 中档/40 难」按存量口径根本凑不出来。

所以这里定**三级信号**，逐级兜底，并且把用了哪一级记进报告：

    ① 题自带        meta.difficulty，全库 3,607 道（人工订过，最可信）
    ② 同卷位置      同一份卷里按题型分组、按卷面题号排序，走
                    `paper.position_difficulty()`（高考卷的难度本来就是位置决定的）。
                    只对 **≥15 题**的卷算——少于这个数多半是教辅书的章节分组，
                    「第 3 题」说明不了难度。
    ③ 考点星级      前两级都没有时，退回考点级难度（点内恒定）

②① 谁优先？①。重叠的 2,691 道里两者**一致 2,008 道（75%）**——位置信号可用，
但不是真相，所以题自带一定压过它；反过来位置覆盖 24,384 道，光靠①只有 12%。

## 选题口径（用户定的四条）

* 范围＝全部 152 个考点；
* **一题只归主考点**（`points[0]`），不做跨考点复用——宁可少出，也不让一道题
  在五份讲义里出现五次；
* **凑不满配额就有多少出多少**，页首与报告都标缺口，不硬凑、不借题；
* 产物＝每考点一份 tex ＋ 总目录。

去重按内容指纹（同考点下 `content_hash` 重复的只留一道），排序＝**高考真题优先 →
年份新→旧 → key 定序**（保证同输入同输出，可复跑对账）。

## 为什么不自己写导言区和题目渲染

AGENTS.md 的唯一入口规矩：导言区只有 `paper._preamble()` 一份（讲义模式当初
另抄一份，漏装自定义 pgfplots 样式，一编译就死）；「TikZ→预渲染图」那步只在
出题时做（写库路径做就等于偷改题干，实测污染过 236 道）。所以本模块：

* 导言区 → `paper.preamble(..., extra=…)`，`extra` 只补知识清单书那几个宏；
* 单题 → `paper.question_tex()`；
* 讲解正文 → `klist.sources()` 的**原文**经 `klist.dialect()`（书方言展开）
  + `klist.substitute_figures()`（图转 PNG，宽度用图清单里的自然厘米数）。

## 五要素的字符坑

`知识点.json` 的字段文本是**带 unicode 数学符号的中文散文**（`aₙ₊₁`、`A∩B=∅`、
`√2`、`α`、`≥`、`★`……共 61 个非中日韩字符）。这些直接进 LaTeX 正文，轻则豆腐块，
重则 `! Missing $ inserted` 停编译。`u2tex()` 把「含符号的一段」整体转成数学式。
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from . import klist, knowledge, paper, store
from .export import IMG_DIR
from .render_tex import source_tag
from .logutil import get_logger
from .paths import ROOT

log = get_logger(__name__)

# ── 路径与配额 ───────────────────────────────────────────────────────

OUT = ROOT / "讲义" / "考点重排"
POINT_DIR = OUT / "points"
QUOTA = {"简单题": 20, "中档题": 40, "难题": 40}
ORDER = ("简单题", "中档题", "难题")
MIN_PAPER = 15                 # 少于此题量的「卷」不按位置推难度（见模块说明）

SRC_OWN, SRC_POS, SRC_POINT = "题自带", "同卷位置", "考点星级"


def _texname(s: str) -> str:
    """文件名安全：去掉 LaTeX/文件系统里别扭的字符，中文留着。"""
    s = re.sub(r"[\\/:*?\"<>|]", "-", s or "")
    return re.sub(r"\s+", "", s)


# ── 一、逐题难度：三级信号 ────────────────────────────────────────────

_KEY_NO = re.compile(r"^(?P<paper>.+)#(?P<no>\d+)$")


def _idof(q) -> str:
    return "%s|%s" % (q.key, q.content_hash())


def position_map(pool: list) -> dict[str, str]:
    r"""「同卷位置」这一级信号：`_idof(题) -> 难度档`。

    排序用**卷面题号**：`meta.source_no` 是原卷印的那个号，key 里的 `#N` 只是
    新库入库顺序（见 `render_tex.source_tag` 的说明）。原卷号缺了才退回 `#N`。
    """
    groups: dict[str, list] = defaultdict(list)
    for q in pool:
        m = _KEY_NO.match(q.key or "")
        if not m:
            continue
        raw = str(q.meta.get("source_no") or "").strip()
        no = int(raw) if raw.isdigit() else int(m.group("no"))
        groups[m.group("paper")].append((no, q))
    out: dict[str, str] = {}
    for items in groups.values():
        if len(items) < MIN_PAPER:
            continue
        items.sort(key=lambda t: (t[0], t[1].key))
        bytype: dict[str, list] = defaultdict(list)
        for _no, q in items:
            bytype[q.type].append(q)
        for t, lst in bytype.items():
            for i, q in enumerate(lst):
                out[_idof(q)] = paper.position_difficulty(t, i, len(lst))
    return out


# ── 二、选题 ──────────────────────────────────────────────────────────

class Selection:
    """一个考点的选题结果。`taken` 是分档题目，`short` 是缺的档位数量。"""

    def __init__(self, pid: str):
        self.pid = pid
        self.stock: Counter = Counter()        # 三档库存（去重后）
        self.source: Counter = Counter()       # 三档各来自哪级信号
        self.taken: dict[str, list] = {}
        self.short: Counter = Counter()
        self.broken = 0                        # 因数据缺陷跳过的题（作答位没闭合/吞卷尾）
        self.broken_keys: list[str] = []       # 具体是哪几道，报告里要列出来给人订正
        self.pool = 0                          # 主考点口径的原始题量

    @property
    def given(self) -> int:
        return sum(len(v) for v in self.taken.values())

    @property
    def want(self) -> int:
        return sum(QUOTA.values())

    def as_dict(self) -> dict:
        return {"point": self.pid, "pool": self.pool, "broken": self.broken,
                "stock": dict(self.stock), "source": dict(self.source),
                "taken": {k: len(v) for k, v in self.taken.items()},
                "short": dict(self.short), "given": self.given}


def _year_of(q) -> int:
    y = str(q.meta.get("year") or "").strip()
    return int(y) if y.isdigit() else 0


def _rank(q):
    """同档内的取题顺序：高考真题优先 → 年份新→旧 → key（定序、可复跑）。"""
    return (0 if q.kind == "高考" else 1, -_year_of(q), q.key)


def select_all(*, refresh: bool = False) -> dict[str, Selection]:
    r"""全 152 个考点一次选完（结果挂在题库对象上）。

    一趟扫库建索引（`points[0]` 口径），比逐考点各扫一遍 30,040 道快一个量级。
    缓存的理由很具体：`build`／`single`／`stats`／自检都要拿同一份选题，
    重算一次是 30,040 次内容指纹 + 一次全库分组，实测 2 秒。
    键里带 `store.load_cached()` 返回的列表对象 id——`cache_clear()` 之后对象会换，
    拿不到过期结果。
    """
    global _SEL_CACHE, _SEL_KEY
    pool = store.load_cached()
    key = (id(pool), len(pool))
    if not refresh and _SEL_CACHE is not None and _SEL_KEY == key:
        return _SEL_CACHE
    out = _select_pool(pool)
    _SEL_CACHE, _SEL_KEY = out, key
    return out


_SEL_CACHE: dict[str, Selection] | None = None
_SEL_KEY: tuple | None = None
_IDX_CACHE: dict | None = None
_IDX_KEY: tuple | None = None

QTYPES = ("single_choice", "multi_choice", "fill_in_blank", "detailed_answer")


def _pool_index(*, refresh: bool = False) -> dict:
    r"""一趟扫库：`{考点: [(题, 难度档, 依据)]}` ＋ `{考点: [被跳过的题 key]}`。

    这是「主考点口径 + 三级信号 + 缺陷题闸门」的**唯一一处**落地：
    选题（`select_all`）和界面画像（`point_view`）都从这里取，
    两边各自数一遍就会数出两个答案。
    """
    global _IDX_CACHE, _IDX_KEY
    pool = store.load_cached()
    key = (id(pool), len(pool))
    if not refresh and _IDX_CACHE is not None and _IDX_KEY == key:
        return _IDX_CACHE

    pos = position_map(pool)
    bypoint: dict[str, list] = defaultdict(list)
    for q in pool:
        if q.points:
            bypoint[q.points[0].strip()].append(q)

    tagged: dict[str, list] = {}
    broken: dict[str, list] = {}
    counts: dict[str, int] = {}
    for pid, qs in bypoint.items():
        counts[pid] = len(qs)
        seen: set[str] = set()
        rows, bad = [], []
        for q in sorted(qs, key=_rank):
            h = q.content_hash()
            if h in seen:
                continue
            seen.add(h)
            if not paper.blank_args_ok(q.stem):
                # 作答位没闭合/吞了卷尾噪声：出卷必炸或印出来是垃圾，宁缺勿错
                bad.append(q.key)
                continue
            own = (q.meta.get("difficulty") or "").strip()
            if own:
                rows.append((q, own, SRC_OWN))
            else:
                d = pos.get(_idof(q))
                rows.append((q, d or (q.difficulty or "中档题"),
                             SRC_POS if d else SRC_POINT))
        tagged[pid] = rows
        if bad:
            broken[pid] = bad

    out = {"tagged": tagged, "broken": broken, "counts": counts}
    _IDX_CACHE, _IDX_KEY = out, key
    return out


def select_all(*, refresh: bool = False) -> dict[str, Selection]:
    """按配额分档取题。缓存见 `_pool_index`（重算一次要扫全库，实测 2 秒）。"""
    global _SEL_CACHE, _SEL_KEY
    pool = store.load_cached()
    key = (id(pool), len(pool))
    if not refresh and _SEL_CACHE is not None and _SEL_KEY == key:
        return _SEL_CACHE
    idx = _pool_index(refresh=refresh)
    out: dict[str, Selection] = {}
    for p in knowledge.all_points():
        pid = p["id"]
        sel = Selection(pid)
        sel.pool = idx["counts"].get(pid, 0)
        sel.broken_keys = list(idx["broken"].get(pid, []))
        sel.broken = len(sel.broken_keys)
        buckets: dict[str, list] = defaultdict(list)
        for q, diff, src in idx["tagged"].get(pid, []):
            sel.source[src] += 1
            if diff in QUOTA:
                buckets[diff].append(q)
        for k in ORDER:
            sel.stock[k] = len(buckets.get(k, []))
            sel.taken[k] = buckets.get(k, [])[:QUOTA[k]]
            sel.short[k] = max(0, QUOTA[k] - len(sel.taken[k]))
        out[pid] = sel
    _SEL_CACHE, _SEL_KEY = out, key
    return out


# ── 三、讲解：书节点 → 可编译 LaTeX ────────────────────────────────────

ROLES = [("11-", "常考题型与解法"), ("12-", "二级结论与常用模型"),
         ("13-", "易错警示"), ("14-", "补充专题"), ("15-", "知识主线")]
ROLE_ORDER = ["知识讲解", "常考题型与解法", "二级结论与常用模型",
              "易错警示", "补充专题", "知识主线"]


def role_of(nid: str) -> str:
    base = nid.split("/", 1)[0]
    for prefix, name in ROLES:
        if base.startswith(prefix):
            return name
    return "知识讲解"


_NODE_CACHE: dict[str, tuple[str, int, int]] = {}
_NODE_KEY: int | None = None


def node_latex(nid: str) -> tuple[str, int, int]:
    r"""节点原文 → 应用方言 + 图转 PNG。返回 (LaTeX, 换了几张图, 还缺几张)。

    挂缓存的理由：映射里**共享节点很多**（一条「知识主线」挂在 30 个考点上），
    不缓存同一段 `dialect()` 就要跑 30 遍。缓存跟着 `klist.sources()` 的对象走，
    书重解析过就不会拿到旧结果。
    """
    src_all = klist.sources()
    global _NODE_KEY
    if _NODE_KEY != id(src_all):
        _NODE_CACHE.clear()
        _NODE_KEY = id(src_all)
    if nid in _NODE_CACHE:
        return _NODE_CACHE[nid]
    src = src_all.get(nid)
    if not src:
        return "", 0, 0
    body = klist.dialect(src["body"])
    body, done, pend = klist.substitute_figures(body)
    # 书里的 `\ang x'Oy'` 换成 `\angle x'Oy'`：exam-zh 自己有个 `\ang{…}`（角度
    # 走 siunitx 解析），签名对不上就是 «siunitx Error: Invalid number 'x'»。
    # 题库 18,612 处用的本来就是 `\angle`，所以不覆盖 exam-zh 的宏，
    # 在生成期把书里那两处换掉。图已在上面换成 PNG，不会误伤图里的 `\ang`。
    body = re.sub(r"\\ang(?![a-zA-Z])\s*", lambda m: "\\angle ", body)
    # 书把 `\vec` 重定义成了 `\overrightarrow`（`\vec{AB}` 要画成带长箭头的向量），
    # 讲解正文里 663 处。只改**讲解**这一份：题目那边 exam-zh 的 `\vec` 是短箭头，
    # 现有组卷卷面就长那样，不跟着改——那是另一件事。
    body = re.sub(r"\\vec(?![a-zA-Z])\s*", lambda m: "\\overrightarrow ", body)
    out = (plain_symbols(body).strip(), done, pend)
    _NODE_CACHE[nid] = out
    return out


def mapped(pid: str) -> list[tuple[str, list[tuple[str, str]]]]:
    r"""考点映射 → `[(角色, [(节点 id, 节点标题)])]`，按 `ROLE_ORDER` 排好。

    只留**真带内容**的节点——书里的章节标题节点正文是空的，内容都在子节点身上，
    跟着映射进来就是一个个空标题。
    角色划分与「空节点」判据只写这一处：出 LaTeX（`commentary`）和给界面画
    （`point_view`）都从这里取，否则两边各判一遍，早晚不一致。
    """
    groups: dict[str, list] = defaultdict(list)
    for nid in klist.load_map().get(pid, []):
        tex, _done, _pend = node_latex(nid)
        if len(re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", tex)) < 12:
            continue
        groups[role_of(nid)].append((nid, (klist.sources().get(nid) or {}).get("title") or ""))
    return [(r, groups[r]) for r in ROLE_ORDER if groups.get(r)]


def commentary(pid: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """讲解的 LaTeX 出口：`[(角色, [(节点标题, LaTeX)])]`。"""
    return [(role, [(title, node_latex(nid)[0]) for nid, title in items])
            for role, items in mapped(pid)]


# ── 四、五要素里的 unicode 数学符号 → LaTeX ────────────────────────────

_SYM = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "θ": r"\theta",
    "λ": r"\lambda", "μ": r"\mu", "π": r"\pi", "σ": r"\sigma",
    "ω": r"\omega", "φ": r"\varphi", "Δ": r"\Delta", "Σ": r"\Sigma",
    "Ω": r"\Omega", "∀": r"\forall", "∃": r"\exists",
    "∈": r"\in", "∉": r"\notin", "⊆": r"\subseteq", "⊊": r"\subsetneq",
    "⊇": r"\supseteq", "∪": r"\cup", "∩": r"\cap", "∅": r"\varnothing",
    "∁": r"\complement", "≥": r"\geq", "≤": r"\leq", "≠": r"\neq",
    "≈": r"\approx", "∥": r"\parallel", "⊥": r"\perp", "△": r"\triangle",
    "½": r"\frac{1}{2}", "Ā": r"\bar{A}",
    "→": r"\to", "←": r"\leftarrow", "↔": r"\leftrightarrow",
    "⇒": r"\Rightarrow", "⇐": r"\Leftarrow", "⇔": r"\Leftrightarrow",
    "±": r"\pm", "∓": r"\mp", "×": r"\times", "÷": r"\div",
    "·": r"\cdot", "−": r"-", "…": r"\ldots", "★": r"\star",
    "⟨": r"\langle", "⟩": r"\rangle", "⋅": r"\cdot", "∞": r"\infty",
    "°": r"^{\circ}", "′": "'", "″": "''",
}
_SUP = {"¹": "1", "²": "2", "³": "3", "⁰": "0", "ⁿ": "n", "⁺": "+",
        "⁻": "-", "ˣ": "x", "ᵖ": "p", "ʸ": "y", "ᵐ": "m", "ᵏ": "k"}
_SUB = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5",
        "₆": "6", "₇": "7", "₈": "8", "₉": "9", "₊": "+", "₋": "-",
        "ₙ": "n", "ₘ": "m", "ₚ": "p", "ₛ": "s", "ᵢ": "i", "ⱼ": "j",
        "ₖ": "k", "ₗ": "l", "ₜ": "t", "ᵤ": "u", "ᵥ": "v", "ₐ": "a",
        "ₑ": "e", "ₒ": "o", "ₓ": "x", "ₕ": "h", "ᵣ": "r"}
_CIRCLED = {chr(0x2460 + i): str(i + 1) for i in range(20)}      # ① → 1
_MATHSET = set(_SYM) | set(_SUP) | set(_SUB) | {"√", "̄"}
# 一段数学式里能跟着走的普通字符。⚠️ 不收 `"`（数学模式里它是变音记号）、
# 不收空格（空格由 `_runs` 单独判断，别把中文散文粘进数学式）。
_ASCII_MATH = set("+-*/=^_()[]{}<>|.,0123456789"
                  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!'")


# 数学式里坏事的字符。`^`/`_` 不带下标时（后面不是字母数字）也走这里。
# ⚠️ `<` `>` **不转义**：这一段本来就在 `$…$` 里，原样交给数学模式才对；
# 换成 `\lt`/`\gt` 是 exam-zh 里没有的宏，42 处 «Undefined control sequence»
# 全这么来的（第一次全量编译抓到）。正文里的那两个字符走 `_escape_text`。
_ESC_MATH = {"%": r"\%", "#": r"\#", "&": r"\&", "{": r"\{", "}": r"\}",
             "$": r"\$", "_": r"\_", "^": r"\^",
             "~": r"\text{\textasciitilde{}}", "\\": r"\textbackslash{}"}


def _brace_group(s: str, i: int) -> int:
    """`s[i] == '{'` 时返回配平 `}` 的下标，找不到返回 -1。"""
    if i >= len(s) or s[i] != "{":
        return -1
    depth = 0
    j = i
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _mathrun(s: str) -> str:
    r"""把一段「有符号」的字符流转成数学式：`aₙ₊₁` → `$a_{n+1}$`。

    上下标按**连续一段**收拢（`x²¹` → `$x^{21}$`），单独一个也带花括号，
    免得 `$x^n+1$` 这种把 `+1` 吃进上标。

    ⚠️ 特殊字符必须**边扫边转义**：`^{}` 这些花括号是本函数自己生成出来的，
    等扫完再整体转义会把它们一起转掉。
    """
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch in _SUP or ch in _SUB:
            kind = "^" if ch in _SUP else "_"
            table = _SUP if ch in _SUP else _SUB
            run = []
            while i < len(s) and (s[i] in table):
                run.append(table[s[i]])
                i += 1
            out.append("%s{%s}" % (kind, "".join(run)))
            continue
        if ch == "√":
            j = i + 1
            while j < len(s) and (s[j].isalnum() or s[j] == " "):
                j += 1
            arg = s[i + 1:j].strip()
            if s[i + 1:i + 2] == "(":                       # √(x+1)
                close = s.find(")", i + 1)
                arg = s[i + 2:close] if close > 0 else ""
                j = close + 1
            out.append(r"\sqrt{%s}" % (arg or "{\\cdot}"))
            i = j
            continue
        if ch == "̄":                                 # 结合号：跟在字母上 → \bar{a}
            for k in range(len(out) - 1, -1, -1):
                if out[k]:
                    if out[k][-1].isalpha():
                        letter, out[k] = out[k][-1], out[k][:-1]
                        out.append(r"\bar{%s}" % letter)
                    else:
                        out.append(r"\bar{\ }")
                    break
            i += 1
            continue
        if ch in _SYM:
            cmd = _SYM[ch]
            # ⚠️ 命令名后必须断开：TeX 读控制序列吃到**最后一个字母**，
            # `A∩B` 直译成 `\capB` 就是个未定义命令（页面直接停在 ! Undefined）。
            # 数学模式里多个空格不排版，所以一律补一个空格最省事。
            out.append(cmd + " " if cmd[-1].isalpha() else cmd)
            i += 1
            continue
        if ch in "^_" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == "{":
                # 已经带了花括号（`a^{n-k}`）→ 整个组**原样**带走。
                # 早先这里按「下一个字符」处理，等于又包一层括号，
                # 生成出 `_{{}k=0\}` 这种鬼东西（`{` `}` 随后还被转义了）。
                close = _brace_group(s, i + 1)
                if close > 0:
                    out.append(ch + s[i + 1:close + 1])
                    i = close + 1
                    continue
            elif nxt.isalnum():
                out.append("%s{%s}" % (ch, nxt))         # ASCII 写法 x^2 / a_i
                i += 2
                continue
            elif nxt == "(":
                # `a^(n-k)` 这种纯文本写法：括号里的整段就是上标/下标
                close = s.find(")", i + 2)
                if close > 0:
                    out.append("%s{%s}" % (ch, s[i + 2:close]))
                    i = close + 1
                    continue
        out.append(_ESC_MATH.get(ch, ch))
        i += 1
    return "".join(out)


def _escape_plain(s: str) -> str:
    """正文里的 LaTeX 特殊字符转义（`_` `%` `&` `#` `{}` 那一套走 paper）。"""
    return paper.esc_text(s)


def _mathy(ch: str) -> bool:
    """这个字符是不是「数学符号」（含上下标与根号）。

    带圈数字 ①② 不算——`\textcircled` 是文本命令，塞进 `$…$` 会报
    «invalid in math mode»，它走 `_plain_seg` 那条路。
    """
    return ch in _MATHSET


def _runs(s: str) -> list[tuple[bool, str]]:
    r"""散文切成 `[(是候选数学段, 文本)]`。

    一段＝连续的字母数字／算符／符号，中间**允许夹一个后面还接着数学字符的空格**
    （`A ∩ B` 要成一整段）。是候选段还不够，得真带符号才转数学式——
    纯 `x=2` 留成正文，满篇 `$x=2$` 会把中文行距挤乱。
    """
    out: list[tuple[bool, str]] = []
    buf = ""
    i, n = 0, len(s)

    def cut():
        nonlocal buf
        if buf:
            out.append((any(_mathy(c) for c in buf), buf))
            buf = ""

    while i < n:
        ch = s[i]
        if ch in _ASCII_MATH or _mathy(ch):
            buf += ch
            i += 1
            continue
        if ch in " 　" and buf:
            j = i
            while j < n and s[j] in " 　":
                j += 1
            if j < n and (s[j] in _ASCII_MATH or _mathy(s[j])):
                buf += ch                       # 空格夹在两段数学字符中间 → 算同一段
                i += 1
                continue
        cut()
        out.append((False, ch))
        i += 1
    cut()
    return out


def _plain_seg(seg: str) -> str:
    out: list[str] = []
    for isrun, txt in _runs(seg):
        if not isrun:
            out.append(_escape_text(txt))
            continue
        core = txt.strip()
        lead = txt[:len(txt) - len(txt.lstrip())]
        tail = txt[len(txt.rstrip()):]
        out.append(lead + "$" + _mathrun(core) + "$" + tail)
    return "".join(out)


def _escape_text(txt: str) -> str:
    r"""正文（非数学段）→ LaTeX。

    `paper.esc_text` 管 `_ % & # {}` 那一套；这里再补两条它不管的：
      * `<` `>` —— 不转义时 XeLaTeX 下不保证有字形（`1<x<2` 就排成 `1¡x¡2`）；
      * ①② —— 带圈数字换成正文里的 `\textcircled`，混进数学式会报
        «invalid in math mode»，所以**不能**跟着数学段一起裹进 `$…$`。
    """
    out: list[str] = []
    buf = ""

    def cut():
        nonlocal buf
        if buf:
            out.append(paper.esc_text(buf)
                       .replace("<", r"\textless{}")
                       .replace(">", r"\textgreater{}"))
            buf = ""

    for ch in txt:
        if ch in _CIRCLED:
            cut()
            out.append(r"\textcircled{%s}" % _CIRCLED[ch])
        else:
            buf += ch
    cut()
    return "".join(out)


_MATHSPAN = re.compile(r"\$[^$]*\$")


def u2tex(s: str) -> str:
    r"""散文 → LaTeX。

    已有的 `$…$` **原样保留**（`知识点.json` 的解析字段里本来就写好了 LaTeX，
    里面还有 `\hat` `\frac` 和 `x_i` 这种下标——重转一遍只会转坏）；
    其余按 `_runs` 切段，带符号的段转数学式，普通段转义。
    """
    out: list[str] = []
    i = 0
    for m in _MATHSPAN.finditer(s):
        out.append(_plain_seg(s[i:m.start()]))
        out.append(m.group(0))
        i = m.end()
    out.append(_plain_seg(s[i:]))
    return "".join(out)


def unmapped(s: str) -> set[str]:
    """没进映射表的非 ASCII 字符（自检用来发现「表格该长了」）。"""
    return {c for c in s if ord(c) > 127
            and not (0x4E00 <= ord(c) <= 0x9FFF)
            and not (0x3000 <= ord(c) <= 0x303F)
            and not (0xFF00 <= ord(c) <= 0xFFEF)
            and c not in _MATHSET and c not in _CIRCLED
            and c not in "—–“”‘’《》（）、。，；：？！"}


# 正文里裸着的 unicode 数学符号（题库有 959 道题这么写：`M⊆N`、`a≤-2`、`α`…）。
# 不包 `$…$` 就是 «Missing character: There is no ⊆ in font NewCM10-Book»——
# 编译不报错，但**页面上那个符号直接没了**，属于静默出错。
# 排除掉三类：`…`（中文省略号，23,527 处是标点不是运算）、
# `°′″`（Latin-1 里有字形，且 `^{\circ}` 脱离基数字会飘）。
_TEXT_SYM = {c for c in _SYM if c not in "…°′″"}
_TEXT_SYM_RUN = re.compile("[" + re.escape("".join(sorted(_TEXT_SYM))) + "]+")


def plain_symbols(tex: str) -> str:
    r"""把**正文模式**里裸着的 unicode 数学符号包成 `$…$`。

    走 `paper.map_text_mode`：数学式、公式环境、图环境一个字不动——
    不判模式就动手，会把 `$x_i$` 改成 `$x\_i$`，公式当场塌成下划线。
    """
    return paper.map_text_mode(
        tex, lambda c: _TEXT_SYM_RUN.sub(
            lambda m: "$" + _mathrun(m.group(0)) + "$", c))


# ── 五、拼一份考点 tex ────────────────────────────────────────────────

# 五要素的键名各考点不统一（`核心概念`/`概念`/`定义`、`核心公式`/`公式`…），
# 所以按**前缀**排优先级，认不出的键按数据原序挂在最后。
_FIELD_PREFIX = ("核心概念", "概念", "定义", "核心公式", "公式", "性质",
                 "常用方法", "方法", "用法", "思路", "思想",
                 "常考题型", "题型", "应用", "最值", "标准方程", "几何性质",
                 "易错点")


def _field_rank(k: str) -> tuple[int, int]:
    for i, p in enumerate(_FIELD_PREFIX):
        if k.startswith(p):
            return (0, i)
    return (1, 0)


def fields_tex(pid: str) -> str:
    """考点五要素 → LaTeX。"""
    f = knowledge.fields_of(pid)
    if not f:
        return ""
    out = [r"\section*{考点五要素}"]
    keys = sorted(f, key=_field_rank)
    for k in keys:
        vals = f.get(k) or []
        if isinstance(vals, str):
            vals = [vals]
        if not vals:
            continue
        out.append(r"\subsection*{%s}" % _escape_plain(k))
        out.append(r"\begin{itemize}")
        for v in vals:
            out.append(r"  \item " + u2tex(str(v).strip()))
        out.append(r"\end{itemize}")
    return "\n".join(out) + "\n"


def profile_tex(pid: str, sel: Selection) -> str:
    """考点档案：板块／小类／星级／库存／本次选题／缺口。"""
    p = knowledge.get(pid)
    stars = int(p.get("stars") or 0)
    star = r"$\star$" * stars if stars else "—"
    rows = []
    for k in ORDER:
        rows.append("%s 库存 %d，取 %d%s" % (
            k, sel.stock[k], len(sel.taken[k]),
            "（缺 %d）" % sel.short[k] if sel.short[k] else ""))
    src = "／".join("%s %d 道" % (k, v) for k, v in
                    sorted(sel.source.items(), key=lambda kv: -kv[1]))
    out = [r"\section*{%s（%s）}" % (u2tex(knowledge.title_of(pid) or pid), pid),
           r"\begin{itemize}",
           r"  \item 板块：%s ｜ 小类：%s" % (u2tex(p.get("topic") or "—"),
                                             u2tex(p.get("section") or "—")),
           r"  \item 考点星级：%s（%s）" % (star, u2tex(p.get("difficulty") or "未定")),
           r"  \item 库存 %d 道 ｜ 本次选 %d 道（目标 %d）：%s"
           % (sel.pool, sel.given, sel.want, "；".join(rows)),
           r"  \item 难度信号来源：%s" % src,
           r"\end{itemize}"]
    return "\n".join(out) + "\n"


def commentary_tex(pid: str) -> str:
    out = []
    for role, items in commentary(pid):
        out.append(r"\section*{%s}" % role)
        for title, tex in items:
            if title:
                out.append(r"\subsection*{%s}" % _escape_plain(title))
            out.append(tex)
        out.append("")
    return "\n".join(out) + "\n"


def training_tex(sel: Selection) -> str:
    """分层训练：三档各一节，题走 `paper.question_tex()`（带答案与解析）。"""
    out = [r"\section*{分层训练}"]
    for k in ORDER:
        qs = sel.taken[k]
        if not qs:
            out.append(r"\subsection*{%s（本考点库存 0，缺 %d 道）}" % (k, sel.short[k]))
            continue
        head = r"\subsection*{%s（取 %d 道／配额 %d%s）}" % (
            k, len(qs), QUOTA[k], "，缺 %d" % sel.short[k] if sel.short[k] else "")
        out.append(head)
        out.append(r"\examsetup{question/index = 1}")   # 每档题号从 1 起
        for q in qs:
            out.append(r"\needspace{5\baselineskip}")
            out.append(plain_symbols(paper.question_tex(q, show_answers=True)))
        out.append("")
    return "\n".join(out) + "\n"


def point_body(pid: str, sel: Selection) -> str:
    parts = ["%% 考点 %s ｜ 由 AmTiKu 生成，请勿手改（改数据后重跑本生成器）" % pid]
    parts.append(profile_tex(pid, sel))
    parts.append(fields_tex(pid))
    parts.append(commentary_tex(pid))
    parts.append(training_tex(sel))
    return "\n".join(p for p in parts if p).replace("\r\n", "\n")


def _pkg(name: str, opts: str = "") -> str:
    r"""装包前先问一嘴装没装过——exam-zh 已经带了大半，重复 `\usepackage` 会撞选项。"""
    return (r"\makeatletter\@ifpackageloaded{%s}{}{\usepackage%s{%s}}\makeatother"
            % (name, ("[%s]" % opts) if opts else "", name))


EXTRA_HEAD = [
    # 讲解正文（知识清单书）用到的环境/表格包
    _pkg("longtable"), _pkg("multirow"), _pkg("tabularx"), _pkg("colortbl"),
    _pkg("booktabs"), _pkg("mathtools"), _pkg("enumitem"),
    # 书里的自定义列型（表格头一格常用 `C{2.4cm}`）。扫宏的时候看不见它们——
    # 列型不是控制序列，是 array 的前导令牌，漏了就是
    # «Illegal pream-token (C)» 直接停编译。
    r"\newcolumntype{C}[1]{>{\centering\arraybackslash}m{#1}}",
    r"\newcolumntype{L}[1]{>{\raggedright\arraybackslash}m{#1}}",
]


def document_head(title: str) -> list[str]:
    return paper.preamble(title=title, graphicspath=paper.texpath(IMG_DIR),
                          show_answers=True, columns=2,
                          first_line="%% 按考点重排的知识清单 · 由 AmTiKu 生成",
                          extra=EXTRA_HEAD)


def single_tex(pid: str, sel: Selection) -> str:
    """一份能单独编译的完整文档（调试／抽查用）。"""
    doc = document_head("%s %s" % (pid, knowledge.title_of(pid)))
    return "\n".join(doc + [r"\begin{document}", r"\maketitle",
                            point_body(pid, sel), r"\end{document}", ""])


def main_tex(rows: list[tuple[str, str, str]]) -> str:
    r"""总目录。`rows = [(考点id, 文件名, 标题)]`。

    `\include` 而不是 `\input`：每个考点单独起页，配合 `main.tex` 顶部那句
    `\includeonly{}` 就能**只编译其中几节**（要改哪节就打开哪节，省一半时间）。

    ⚠️ 但**别真拿它出整本 PDF**：152 个考点 10,357 道题排下来是 5,000 多页，
    XeTeX 在 `main memory size=5000000` 上会 «TeX capacity exceeded» 直接断掉
    （实测第二遍就死在这儿）。整本请编译分卷出来的 `卷NN-*.tex`。
    """
    doc = document_head("知识清单 · 按考点重排")
    body = [r"\begin{document}", r"\maketitle", r"\tableofcontents", ""]
    last_topic = None
    for pid, fname, title in rows:
        topic = knowledge.get(pid).get("topic") or ""
        if topic != last_topic:
            body.append(r"\part{%s}" % _escape_plain(topic))
            last_topic = topic
        body.append(r"\include{points/%s}" % fname)
    body += [r"\end{document}", ""]
    return ("%% 要只编译其中几节，就解开下一行并填文件名（不带 .tex）\n"
            "%% \\includeonly{points/1.1.3-集合的基本运算}\n"
            + "\n".join(doc + body))


def volumes_tex(rows: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    r"""按板块分卷：`[(文件名, 整份文档)]`，10 卷。

    为什么要分卷——整本 5,000 多页会撑爆 XeTeX 的 main memory（«TeX capacity
    exceeded»，实测第二遍死在这儿）；一卷 400–700 页则一次过。
    板块顺序按 `知识点.json` 的 topic 原序，文件名前缀补零好排序。
    """
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for row in rows:
        groups.setdefault(knowledge.get(row[0]).get("topic") or "其他", []).append(row)
    out = []
    for i, (topic, items) in enumerate(groups.items(), 1):
        fname = "卷%02d-%s" % (i, _texname(topic))
        doc = document_head("知识清单 · 按考点重排 · %s" % topic)
        body = [r"\begin{document}", r"\maketitle", r"\tableofcontents", ""]
        for pid, pf, title in items:
            body.append(r"\include{points/%s}" % pf)
        body += [r"\end{document}", ""]
        out.append((fname, "\n".join(doc + body)))
    return out


# ── 六、报告与生成 ────────────────────────────────────────────────────

def report_md(sels: dict[str, Selection], *, n_fig: int) -> str:
    total = sum(s.given for s in sels.values())
    broken = sum(s.broken for s in sels.values())
    need = sum(s.want for s in sels.values())
    full = sum(1 for s in sels.values() if s.given >= s.want)
    lines = [r"# 按考点重排 · 选题账",
             "",
             "生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
             "",
             "- 考点 %d 个，目标 %d 道（每考点 100），**实际选出 %d 道**（%d 个考点取满）"
             % (len(sels), need, total, full),
             "- 生成物引用 PNG 图 %d 张（讲解图与题目配图，按文件名去重；全是预渲染，无内联 TikZ）" % n_fig,
             "- 难度信号：① 题自带 ② 同卷位置（≥%d 题的卷）③ 考点星级兜底" % MIN_PAPER,
             "- **选题期跳过的数据缺陷题：%d 道**（作答位 `\\fillin[` 没闭合，或答案位"
             "吞进了「四、解答题…」「第 3 页（共 7 页）」这类卷尾噪声）——"
             "这些题出卷必炸或印出来是垃圾，正解是在题库里逐题订正（`fixups.py`）"
             % broken,
             "",
             "| 考点 | 名称 | 星级 | 库存 | 简单 | 中档 | 难题 | 实取 | 缺口 | 信号（自带/位置/星级） |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for pid in sorted(sels, key=lambda x: tuple(int(i) for i in x.split("."))):
        s = sels[pid]
        p = knowledge.get(pid)
        lines.append("| %s | %s | %s | %d | %d/%d | %d/%d | %d/%d | %d | %d | %s |" % (
            pid, (p.get("title") or "")[:22], "★" * int(p.get("stars") or 0),
            s.pool,
            len(s.taken["简单题"]), s.stock["简单题"],
            len(s.taken["中档题"]), s.stock["中档题"],
            len(s.taken["难题"]), s.stock["难题"],
            s.given, sum(s.short.values()),
            "%d/%d/%d" % (s.source[SRC_OWN], s.source[SRC_POS], s.source[SRC_POINT])))
    broken_rows = [(pid, k) for pid in sels for k in sels[pid].broken_keys]
    if broken_rows:
        lines += ["", "## 选题期跳过的题（数据缺陷，逐题订正才能出得来）", "",
                  "| 考点 | 题 key |", "|---|---|"]
        lines += ["| %s | %s |" % (pid, k) for pid, k in sorted(broken_rows)]
    return "\n".join(lines) + "\n"


def build(*, only: tuple[str, ...] = (), out: Path = OUT,
          verbose: bool = True) -> dict:
    r"""生成全部产物。返回汇总数字（给测试和自检用）。"""
    sels = select_all()
    pdir = out / "points"
    pdir.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str, str]] = []
    written = 0
    figs: set[str] = set()          # 按**文件名**去重：一个节点挂在两个考点上不能算两张
    n_q = 0
    for pid in sorted(sels, key=lambda x: tuple(int(i) for i in x.split("."))):
        if only and pid not in only:
            continue
        sel = sels[pid]
        title = knowledge.title_of(pid) or pid
        fname = "%s-%s" % (pid, _texname(title))
        body = point_body(pid, sel)
        figs.update(re.findall(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}", body))
        n_q += sel.given
        (pdir / (fname + ".tex")).write_text(body, encoding="utf-8")
        rows.append((pid, fname, title))
        written += 1
        if verbose and written % 20 == 0:
            log.info("已生成 %d 个考点", written)

    (out / "main.tex").write_text(main_tex(rows), encoding="utf-8")
    vols = volumes_tex(rows)
    for fname, tex in vols:
        (out / (fname + ".tex")).write_text(tex, encoding="utf-8")
    (out / "缺口报告.md").write_text(report_md(sels, n_fig=len(figs)), encoding="utf-8")
    summary = {"points": written, "questions": n_q, "volumes": len(vols),
               "want": sum(s.want for s in sels.values()),
               "full": sum(1 for s in sels.values() if s.given >= s.want),
               "figures": len(figs), "out": str(out)}
    if verbose:
        log.info("写了 %d 份考点 tex，选题 %d/%d 道，图 %d 张 → %s",
                 summary["points"], summary["questions"], summary["want"],
                 summary["figures"], out)
    return summary


def single(pid: str, *, out: Path = OUT) -> Path:
    """写一份单独可编译的考点文档到 `_单点-<pid>.tex`。"""
    sels = select_all()
    if pid not in sels:
        raise KeyError("没有这个考点：%s" % pid)
    path = out / ("_单点-%s.tex" % pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(single_tex(pid, sels[pid]), encoding="utf-8")
    return path


# ── 七、给界面的聚合口 ─────────────────────────────────────────────────

PREVIEW = 6        # 每档在界面上预览几道题（全量 100 道不必一次画完）


def points_tree() -> list[dict]:
    r"""考点树（板块 → 小类 → 考点），每个考点带两个数：讲节点数、本次选题数。

    左栏要按题库自己的层级排（不是书的章节顺序），但「哪个考点有哪几节讲解」
    是映射说了算——所以这一份只读 `knowledge` + `mapped()` + `_pool_index()`，
    不在前端再拼一遍树。
    """
    idx = _pool_index()
    sels = select_all()
    topics: dict[str, dict] = {}
    for p in knowledge.all_points():
        pid = p["id"]
        t = topics.setdefault(p.get("topic") or "其他",
                              {"title": p.get("topic") or "其他", "sections": [],
                               "by_id": {}})
        sec = t["by_id"].get(p.get("section") or "")
        if sec is None:
            sec = {"title": p.get("section") or "", "points": []}
            t["by_id"][p.get("section") or ""] = sec
            t["sections"].append(sec)
        sel = sels.get(pid)
        sec["points"].append({
            "id": pid, "title": knowledge.title_of(pid),
            "stars": p.get("stars", 0), "difficulty": p.get("difficulty", ""),
            "pool": sel.pool if sel else 0, "given": sel.given if sel else 0,
            "short": sum(sel.short.values()) if sel else 0,
            "n_node": sum(len(items) for _r, items in mapped(pid)),
        })
    return [{k: v for k, v in t.items() if k != "by_id"} for t in topics.values()]


def point_view(pid: str) -> dict:
    r"""一个考点的全貌（界面用）：五要素 + 讲解 IR + 题库画像 + 分层选题预览。

    两个刻意的设计：

    * 讲解给的是**块级 IR**（前端与题目共用 `lib/render.tsx`），不是 LaTeX——
      LaTeX 那份是 `point_body()` 出讲义用的。两个出口走同一份 `mapped()`，
      所以「界面上讲的」和「导出的讲义」不可能变成两套内容。
    * **不含先修关系**：`/api/chain/{pid}` 已经在管这件事，再抄一份就是两份真相。
    """
    p = knowledge.get(pid)
    if not p:
        return {}
    rows = _pool_index()["tagged"].get(pid, [])
    srcof = {q.key: s for q, _d, s in rows}
    sel = select_all().get(pid)
    comm = []
    for role, items in mapped(pid):
        nodes = []
        for nid, title in items:
            n = klist.get_node(nid)
            if n:
                nodes.append({"id": nid, "title": title,
                              "blocks": n.get("blocks", []),
                              "n_fig": n.get("n_fig", 0),
                              "n_table": n.get("n_table", 0)})
        if nodes:
            comm.append({"role": role, "nodes": nodes})
    years = Counter(str(q.meta.get("year")) for q, _d, _s in rows
                    if str(q.meta.get("year") or "").isdigit())
    return {
        "point": {"id": pid, "title": knowledge.title_of(pid), "raw_title": p.get("title", ""),
                  "stars": p.get("stars", 0), "difficulty": p.get("difficulty", ""),
                  "topic": p.get("topic", ""), "section": p.get("section", ""),
                  "fields": knowledge.fields_of(pid)},
        "commentary": comm,
        "bank": {
            "pool": sel.pool if sel else len(rows),
            "broken": sel.broken_keys if sel else [],
            "given": sel.given if sel else 0,
            "want": sel.want if sel else sum(QUOTA.values()),
            "stock": dict(sel.stock) if sel else {},
            "taken": {k: len(sel.taken[k]) for k in ORDER} if sel else {},
            "short": dict(sel.short) if sel else {},
            "by_type": {t: sum(1 for q, _d, _s in rows if q.type == t) for t in QTYPES},
            "by_kind": dict(Counter(q.kind for q, _d, _s in rows)),
            "by_source": dict(Counter(s for _q, _d, s in rows)),
            "years": sorted(((y, n) for y, n in years.items()), reverse=True)[:6],
        },
        "pick": {k: [{"key": q.key, "type": q.type, "kind": q.kind,
                      "tag": source_tag(q), "src": srcof.get(q.key, ""),
                      "has_fig": bool(q.figures)}
                     for q in (sel.taken[k][:PREVIEW] if sel else [])]
                 for k in ORDER},
    }


# ── 八、自检 ──────────────────────────────────────────────────────────

def _selftest() -> int:
    ok = True
    def chk(name, cond, note=""):
        nonlocal ok
        print("%-46s %s %s" % (name, "OK" if cond else "FAIL", note))
        ok = ok and bool(cond)

    pool = store.load_cached()
    pos = position_map(pool)
    chk("位置信号只给 ≥%d 题的卷" % MIN_PAPER, len(pos) > 20000, "%d 道" % len(pos))
    own = {q.key for q in pool if (q.meta.get("difficulty") or "").strip()}
    chk("题自带难度已覆盖一批", len(own) > 3000, "%d 道" % len(own))

    sels = select_all()
    chk("考点全覆盖", len(sels) == len(knowledge.all_points()), "%d 个" % len(sels))
    chk("每档不超过配额",
        all(len(v) <= QUOTA[k] for s in sels.values() for k, v in s.taken.items()))
    chk("缺口=配额-实取",
        all(s.short[k] == max(0, QUOTA[k] - len(s.taken[k]))
            for s in sels.values() for k in ORDER))
    dup = [s.pid for s in sels.values()
           for k, v in s.taken.items()
           if len({q.content_hash() for q in v}) != len(v)]
    chk("同档内无重复题", not dup, str(dup[:3]))

    body = point_body("1.1.3", sels["1.1.3"])
    chk("考点正文非空", len(body) > 2000, "%d 字符" % len(body))
    chk("正文里没有没展开的书方言宏",
        not re.search(r"\\(?:numline|thead|makecell|dg|cu|para|abs|srcgap)\b", body))
    left = set()
    for s in sels.values():
        left |= unmapped(json.dumps(knowledge.fields_of(s.pid), ensure_ascii=False))
    chk("五要素里的符号全都进了映射表", not left, str(sorted(left))[:80])

    tex = single_tex("1.1.3", sels["1.1.3"])
    chk("单独一份含导言区与 document", r"\documentclass" in tex
        and r"\begin{document}" in tex)
    chk("导言区只有一份（走 paper.preamble）",
        r"\usepackage{exam-zh}" not in tex and r"{exam-zh}" in tex)
    n_q = sum(len(v) for v in sels["1.1.3"].taken.values())
    chk("印出去的题数 == 选题数",
        tex.count(r"\begin{question}") + tex.count(r"\begin{problem}") == n_q,
        "%d 道" % n_q)
    print("考点重排自检：" + ("全过" if ok else "有失败"))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="amti pointbook",
                                 description="按考点重排的知识清单讲义生成器")
    ap.add_argument("cmd", nargs="?", default="build",
                    choices=["build", "single", "stats", "check"])
    ap.add_argument("--only", default="", help="只生成这些考点（逗号分隔）")
    ap.add_argument("--pid", default="1.1.3", help="single：出哪一份单独文档")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        return _selftest()
    if args.cmd == "single":
        print("写了 %s" % single(args.pid))
        return 0
    if args.cmd == "stats":
        print(report_md(select_all(), n_fig=0))
        return 0
    build(only=tuple(x for x in args.only.split(",") if x))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
