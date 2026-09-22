r"""AmTiKu · 逐题订正 —— **题目有问题就直接改题目**

`normalize.py` 管的是**成片**的写法问题：一条规则命中几百道，改法都一样。
但还有一类问题**一道一个样**，写不进规则：

    · 某道题的选项从 PDF 提取时掉了一个根号；
    · 某道题的题干把 `a+b` 印成了 `a-b`；
    · 某道题的选项干脆是另一道题的（PDF 串列）；
    · 某道题的流程图配错了图。

这些只能一道道改。这个模块就是那本「逐题订正账」。

## 三条护栏

1. **凭据 `src`** —— 每条都要写清"凭什么这么改"：原卷、题号，或者
   同一份卷子里另一道**没被提取坏**的孪生题（比如天津卷文理同题）。
   没有凭据的改动不许写进这张表。
2. **前后对照 `expect`** —— 改之前先核对当前值，对不上就**整批拒绝执行**。
   题目后来又被别的规则动过，这里却按老印象去改，是最危险的一种错。
3. **留痕** —— 改完写一份 `变更记录/`，逐条列出改了什么、依据是什么。

## 用法

    python3 -m amti.fixups              # 干跑：只报会改哪些
    python3 -m amti.fixups --yes        # 落盘
    python3 -m amti.fixups --selftest   # 自检（护栏本身也要自证）
"""
from __future__ import annotations

from .paths import ROOT
import argparse
import copy
import datetime as _dt
import json
import re
from pathlib import Path

from . import store
from .schema import Option, Question

PKG = ROOT
CHANGE_DIR = PKG / "变更记录"


# ── 订正账 ────────────────────────────────────────────────────────────
#
# 每条：
#   key     题号
#   why     为什么改（一句话）
#   src     凭据（原卷/孪生题/题面自洽性；**必填**）
#   expect  改之前的现状：字段 → 必须出现的子串（`type` 是精确相等）
#   set     改成什么：字段 → 新值
#
# 可选字段：type / stem / answer / solution / options（[[标签, 文字], …]）
#           / drop_figures（True 表示这道题的配图是错的，撤掉）

# ── 已订正、且其后又被别的订正改过：**注销账目** ─────────────────────
#
# 这些条目当初是对的，但它们 `expect` 记的是"改动前"的样子；题目后来又
# 被后面的订正改过（例如题干被补充完整、题型又被改对），于是这张账
# 既不是"还没改"、也不是"已改成 set 的样子"，全表核对就把它当冲突，
# **整批拒绝执行**（实测：19 条新订正被这 6 条挡住）。
# 历史留在 `变更记录/`，这里只注销账目，不再核对。
RETIRED_KEYS: set[str] = {
    "2027千题册创新拔高册（上）_images/305#16",
    "2027千题册创新拔高册（下）_images/196#50",
    "2027千题册经典重点册（下）_images/020#30",
    "2027 高考数学考前模拟十二套卷_images/030#11",
    "2027千题册经典重点册（上）_images/028#51",
    "2027千题册经典重点册（下）_images/222#52",
}

def _load_patches() -> list[dict]:
    r"""逐题订正台账**从数据目录读**（`数据/订正台账.json`）。

    台账里是**真实题面与答案**——留在代码里，公开仓库就把题库漏出去了。
    文件不在（例如别人 clone 了公开仓库）→ 返回空表：代码照常跑、自检照常过，
    只是没有需要订正的条目。本机台账在 `数据/订正台账.json`（不进 git）。
    """
    if not LEDGER.exists():
        return []
    try:
        d = json.loads(LEDGER.read_text(encoding="utf-8"))
        return d.get("patches") or []
    except Exception:
        log.warning("订正台账读不了（%s），按空表处理", LEDGER, exc_info=True)
        return []


LEDGER = ROOT / "数据" / "订正台账.json"
PATCHES: list[dict] = _load_patches()


# ── 2026-09-19：录题时把**多选题**记成了单选（26 道） ────────────────────
#
# 判据（**逐题看过**，不是按规则批改）：
#   · 题干是「（多）说法正确的有（ ）」这种**一问多项**的问法；
#   · 四个选项是**互相独立**的命题，不是同一个量的四个取值；
#   · 求解模型逐项判定（A 错、B 对、C 对、D 错）后给出**多字母答案**，
#     而库里的 `single_choice` 只收一个字母，`collect` 于是整批拦下。
#
# ⚠ **故意没收进来**的：`2027千题册创新拔高册（上）_images/303#11`——
#   它是真单选（问「最小值与最大值之和为」），是模型的答案串了题
#   （答案写成 `$-2<x<1$`、解析讲的是另一道奇函数题），改题型就改反了。
_MULTI_AS_SINGLE: list[tuple[str, str, str]] = [
    (r"2026 高考数学全国模拟精选_images/005#5", r"在正三棱柱", "ACD"),
    (r"2026 高考数学全国模拟精选_images/006#6", r"满足当", "AD"),
    (r"2026 高考数学全国模拟精选_images/015#20", r"公差", "ACD"),
    (r"2026 高考数学全国模拟精选_images/015#21", r"的前 $n$ 项和", "AC"),
    (r"2026 高考数学全国模拟精选_images/025#9", r"命题正确的是", "BC"),
    (r"2026 高考数学全国模拟精选_images/046#6", r"\ln(\cos x)", "ABD"),
    (r"2026 高考数学全国模拟精选_images/048#10", r"\frac{1}{n},", "ACD"),
    (r"2026 高考数学全国模拟精选_images/051#18", r"所有棱长均为 2", "BCD"),
    (r"2026 高考数学全国模拟精选_images/054#25", r"项积为", "AD"),
    (r"2026 高考数学全国模拟精选_images/055#28", r"三角形的面积为 2", "ABCD"),
    (r"2026 高考数学全国模拟精选_images/078#24", r"连续投掷", "ABD"),
    (r"2026 高考数学全国模拟精选_images/114#8", r"2py", "ACD"),
    (r"2026 高考数学全国模拟精选_images/115#10", r"光学性质", "ABC"),
    (r"2026 高考数学全国模拟精选_images/115#9", r"的一条直径", "ABD"),
    (r"2026 高考数学全国模拟精选_images/116#11", r"x^2 = 4y", "ACD"),
    (r"2026 高考数学全国模拟精选_images/116#12", r"点 $Q$ 在圆", "ABD"),
    (r"2026 高考数学全国模拟精选_images/122#24", r"2026)", "ACD"),
    (r"2026 高考数学全国模拟精选_images/124#28", r"ma_n^2", "ACD"),
    (r"2027 高考数学考前模拟十二套卷_images/025#10", r"为母线的圆柱", "BC"),
    (r"2027 高考数学考前模拟十二套卷_images/030#9", r"Cobb", "ABD"),
    (r"2027 高考数学考前模拟十二套卷_images/036#9", r"a\sin x", "AC"),
    (r"2027 高考数学考前模拟十二套卷_images/042#10", r"点 $A(1,3)$", "BCD"),
    (r"2027 高考数学考前模拟十二套卷_images/042#9", r"文创大赛", "BD"),
    (r"2027 高考数学考前模拟十二套卷_images/048#10", r"上的点", "AB"),
    (r"2027 高考数学考前模拟十二套卷_images/048#11", r"已知正方体", "AC"),
    (r"2027千题册经典重点册（下）_images/289#123", r"两个箱子", "BC"),
]



# ── 2026-09-19：这四道是**求解模型自己判出「单选标错」**的 ────────────────
#
# 它们的答案栏被写成「题面有误」，其实题干是「…正确的是（ ）」+ 四个独立命题，
# 模型逐项算完发现**不止一个正确项**，而题干标的是单选，于是拒绝作答。
# 下面每个选项我都**重新算了一遍**，结论与模型一致：
#   · `054#10` 长方体：B、D 对（A 错在 $a=b=1$ 就是正方体；C 算得 $\frac29$）
#   · `054#9`  数列：A、B、D 对（C 数出来是 3 个 $n$，不是 5 个）
#   · `058#9`  集合：A、C 对（$B\subseteq C$、$A\subseteq B$ 都不必然）
#   · `手工录入/001#11` 数据：B、C 对（众数是 3、中位数是 4）


# ── 2026-09-19：**题号漂移**导致答案写错（千题册（上）303–305 这四道） ──
#
# 怎么发现的：中档题回收时，`303#11` 的答案 `$-2<x<1$`（填空题的解）被单选题
# 的校验拦下。顺着查下去，发现**批文件里的题号与库里的题号错开了**：
#
#   批文件（导出时的库）        现在库里的同号题          批里那道题真正的家
#   303#10 f(x)+f(x-1/2)>1     303#10 奇函数 f(2-x²)     库 302#9（答案已对）
#   303#11 奇函数 f(2-x²)      303#11 曼哈顿距离          库里无答案
#   304#14 曼哈顿距离          304#14 2a²-b²=1           答案被写成了曼哈顿的 B
#   305#16 2a²-b²=1            305#16 不等式整数解个数     答案被写成了前一道的 C
#
# 根因：回收**只认 `题号：` 那一行**（`exchange.collect` 用 key 对上号），
# 一旦两道题之间插/删过题，号就整体错位，解析会**悄悄写到别人头上**。
# 所以这里按**题干**重新认领：每道题的答案都是重新算过的，不是照抄批文件。
# 全库 2175 条比过一遍，错位只有这一段（其余都对得上）。


# ── 2026-09-19：**图题**没作答，但库里就有它的孪生题（原卷是真题选集） ──────
#
# 千题册/十二套卷其实是**真题选集**（书上每题都印着来源，如「2020新课标三」），
# 所以这些「缺图 / 题干被截断」的题，往往在 `高考真题汇编` 或别的模拟册里
# **有同一道题的完整版本**。做法：拿题干去全库比（相似度 > 0.9 才算），
# 逐条核对题干与选项逐字一致后，用孪生题的官方答案与解析。
# 这样比"我照着图重新算"可靠——原卷答案就是权威。


# ── 2026-09-19：翻原卷补的两道「图像可能是」题（经典重点（上）070、071） ──
#
# 这两道原来都指着同一张**张冠李戴**的图（`146996bfe8afda1f.png`），071 的四个
# 选项还全是空的。按原卷（`经典重点（上）_images/033.png`、`034.png`，书上印的
# 是 070、071，来源标注了某市二诊/某省七市二模）重裁图、
# 走 `images.ingest_question` 入库换成内容寻址名，答案是自己按定义域/渐近线判的。


# ── 2026-09-19：翻原卷补的第三道图题（经典重点（上）055） ────────────────


# ── 2026-09-19：十二套卷 030#11（抛物线多选）——自己算，答案 ACD ────────
#
# 这道**没有原卷可翻**（`十二套卷_images` 源目录已不在磁盘上），但不需要图：
# 逐项算出来 A、C、D 都对、B 不对，所以是**多选**而不是库里标的单选，
# 当初求解模型正是被"单选只能填一个字母"卡住才判了「题面有误」。


# ── 2026-09-19：028#51 的自变量抄错了（把 $3^{\frac23}$ 抄成了 $\frac23$） ──


# ── 2026-09-19：191#19 题干被截断，按原卷补全（2022 西安二检） ──────────


# ── 2026-09-19：经典重点（下）最后四道图题（051/052/005/006） ──────────
#
# 都是"求解模型读不了图"卡住的。按原卷判图/算：
#   · 051 涂色（原卷 206 页）：矩形两条对角线分成 4 块，A、C 不共边、B、D 不共边，
#     邻接关系正好是一个 4-环 → 3 色正常染色的个数 = 2^4+2 = 18（选 D）。
#     库里四个选项被录坏了（只剩三个、文字还串进了题干），一并修正。
#   · 052 最短路（原卷 207 页）：4 列 × 3 行的方格，封掉的是 (1,1)→(2,1) 那一段。
#     不封时 C(7,3)=35；经过被封段的有 C(2,1)×1×C(4,2)=12 → 35-12=23（选 B）。
#   · 005 直方图（原卷 218 页）：四个柱高 0.005、0.01、0.015、0.02（和为 0.05，
#     正好使总面积为 1），低于 60 分的频率 = 20×(0.005+0.01) = 0.3 → 15/0.3 = 50（选 B）。
#   · 006 直方图（原卷 219 页）：一等品 [25,30)、二等品 [20,25)∪[30,35)，
#     三等品 = [10,15)∪[15,20)∪[35,40)；由图 h1=h6=0.0125、h2=0.025，
#     频率 = 5×0.05 = 0.25 → 200×0.25 = 50（选 D）。
# 005 与 006 原来**共用同一张图**（明显不对），已按原页各自重裁入库。


# ── 执行 ──────────────────────────────────────────────────────────────

_FIELDS = ("type", "stem", "answer", "solution", "options", "meta")


def _cur_value(q: Question, field: str):
    if field == "options":
        return [o.text for o in q.options]
    return getattr(q, field)


def _check_expect(q: Question, expect: dict) -> list[str]:
    r"""核对现状。返回不匹配的说明列表（空表 = 全部对上）。

    `type` 精确相等；其余字段是**子串**包含。`options` 里每个子串
    只要在**任一**选项文字里出现就算命中——表里写的就是选项原文，
    阅读起来最直观，也不必把四个选项全抄一遍。
    """
    bad: list[str] = []
    for field, want in expect.items():
        if field == "type":
            got = q.type
            if got != want:
                bad.append("type 现在是 %r，表里写的是 %r" % (got, want))
            continue
        got = _cur_value(q, field)
        if field == "options":
            texts = [t or "" for t in got]
            for w in (want if isinstance(want, list) else [want]):
                if not any(_canon(w) in _canon(t) for t in texts):
                    bad.append("选项里找不到 %r" % w)
            continue
        if not isinstance(got, str) or _canon(want) not in _canon(got):
            bad.append("%s 里找不到 %r（现在是 %r）"
                       % (field, want, (got or "")[:60]))
    return bad


def _matches_target(q: Question, spec: dict, by_key: dict) -> bool:
    r"""当前值是不是**已经是**订正后的样子。

    这张账要**幂等**：跑过一次之后再跑，应该说「已订正、跳过」，
    而不是因为 `expect` 对不上就报错——`expect` 描述的是**改之前**的样子，
    改完当然对不上了。

    有了这一条，「对不上就拒绝」才真正只在**漂移**时触发：
    既不是改前的样子、也不是改后的样子，才需要人来看。
    """
    st = spec["set"]
    if "_adopt" in st:
        src = by_key.get(st["_adopt"])
        if src is None:
            return False
        return (q.stem == src.stem and q.answer == src.answer
                and [o.text for o in q.options] == [o.text for o in src.options])
    for field in ("type", "stem", "answer", "solution"):
        if field not in st:
            continue
        if field == "type":
            if q.type != st[field]:
                return False
            continue
        # 题干/答案/解析/选项都按 `_canon` 比：**只差空白或中英标点不算漂移**。
        # 读回来的时候这些都会被规整（`normalize` 的「句末半角句点改中文句号」
        # 就在 ENTRY 段），拿原样文本比会永远报「对不上」，这张账就没法再跑。
        if _canon(getattr(q, field) or "") != _canon(st[field]):
            return False
    if "options" in st:
        if ([_canon(o.text) for o in q.options]
                != [_canon(t) for _l, t in st["options"]]):
            return False
    if "meta" in st:
        for k, v in st["meta"].items():
            if (q.meta or {}).get(k) != v:
                return False
    return True


# 中英标点归一表（只用于比对，见 `_canon`）
_PUNCT = str.maketrans({
    "。": ".", "，": ",", "、": ",", "；": ";", "：": ":",
    "！": "!", "？": "?", "（": "(", "）": ")", "．": ".",
    "～": "~", "－": "-",
})


def _canon(s: str) -> str:
    r"""折成「只按字面意思比」的规范串：去空白 + 中英标点归一到半角。

    只用于**比对**，不写回库里。为什么要这样：
      · 写盘/读取这条路上空白会被规整（`\[\n a\ln` 读回来是 `\[\na\ln`）；
      · `normalize` 的 ENTRY 段有「句末半角句点改中文句号」，会把 `.` 变 `。`。
    拿原样文本比，**已经改好的老账**会一直报「对不上」，`run()` 是
    「一条对不上就整批不执行」，于是这张账再也跑不动（2026-09-19 实测踩到：
    13 条老账只因 `.`/`。` 之差全部报漂移，连带新账一起卡死）。
    """
    return re.sub(r"\s+", "", (s or "").translate(_PUNCT))


def _apply_one(q: Question, spec: dict, by_key: dict) -> list[str]:
    """把一条订正写进 `q`。返回改动说明。"""
    st = spec["set"]
    notes: list[str] = []

    # 「孪生题」式订正：整份照抄另一道没被提取坏的题
    if "_adopt" in st:
        src_q = by_key.get(st["_adopt"])
        if src_q is None:
            raise KeyError("找不到孪生题：%s" % st["_adopt"])
        q.type = src_q.type
        q.stem = src_q.stem
        q.options = [Option(o.label, o.text) for o in src_q.options]
        q.answer = src_q.answer
        q.solution = src_q.solution
        # 配图换掉：原图是错的，孪生题用的是 TikZ
        q.figures = []
        q.meta.pop("figure_missing", None)
        notes.append("采用孪生题 %s 的题干、框图与选项" % st["_adopt"])
        return notes

    if "type" in st:
        notes.append("题型 %s → %s" % (q.type, st["type"]))
        q.type = st["type"]
    for field in ("stem", "answer", "solution"):
        if field in st:
            before = getattr(q, field) or ""
            if before != st[field]:
                notes.append("%s 改写（%d → %d 字）"
                             % ({"stem": "题干", "answer": "答案",
                                 "solution": "解析"}[field],
                                len(before), len(st[field])))
            setattr(q, field, st[field])
    if "options" in st:
        old = [o.text for o in q.options]
        q.options = [Option(lab, txt) for lab, txt in st["options"]]
        diff = [(a, b) for a, b in zip(old, [t for _l, t in st["options"]]) if a != b]
        if diff:
            notes.append("选项改动 %d 处：%s"
                         % (len(diff), "；".join("%s → %s" % (a, b) for a, b in diff)))
    if "meta" in st:
        for k, v in st["meta"].items():
            q.meta[k] = v
        notes.append("meta 写入 %d 项：%s" % (len(st["meta"]), "、".join(st["meta"])))
    if st.get("drop_figures"):
        q.figures = []
        q.meta.pop("figure_missing", None)
        notes.append("撤掉配图")
    return notes


def _is_multi_noise(q: Question) -> bool:
    r"""看起来是「其实是单选、却标成多选」的题。

    **只用来报告，不用来改。** 判据是答案栏写了说明文字而不是字母，
    例如「原卷选项无正确答案」——这类题当初是被「多选题的答案必须是
    A–D」的校验逼着改成了多选，方向改反了。

    为什么不自动改回去：光把题型改回单选，答案栏还是一段说明文字，
    校验照样不过，等于把问题从"题型错"挪成"答案错"。这类题得**一道一道
    查清原卷**，写进上面的 `PATCHES` 才算数——所以这里只列出来给人看。

    ⚠️ 答案栏为空的不能算：还没求解的题答案本来就是空的。
    """
    ans = (q.answer or "").strip()
    return (q.type == "multi_choice"
            and len(q.options) == 4
            and bool(ans)
            and not any(c in ans for c in "ABCD"))


def run(*, yes: bool = False, quiet: bool = False) -> dict:
    r"""跑一遍订正账。**没有 `yes=True` 一律不动盘。**

    先全表核对 `expect`，**有一条对不上就整批不执行**——
    宁可让人来看，也不要改半截。
    """
    qs = store.load_all()
    by_key = {q.key: q for q in qs}
    tgt = {q.key: q for q in qs}

    plan: list[dict] = []
    done: list[str] = []
    problems: list[str] = []
    for spec in PATCHES:
        if spec["key"] in RETIRED_KEYS:      # 账目已注销（见 RETIRED_KEYS 的说明）
            done.append(spec["key"] + "（已注销）")
            continue
        q = tgt.get(spec["key"])
        if q is None:
            problems.append("%s：库里没有这道题" % spec["key"])
            continue
        # 已经是改后的样子 → 跳过（保证这张账幂等，可反复跑）
        if _matches_target(q, spec, by_key):
            done.append(spec["key"])
            continue
        bad = _check_expect(q, spec["expect"])
        if bad:
            problems.extend("%s：%s" % (spec["key"], b) for b in bad)
            continue
        plan.append(spec)

    # 改完之后**还剩哪些**看起来是误标的——只报告，不动手
    leftover = [q.key for q in qs if _is_multi_noise(q)]
    plan_keys = {s["key"] for s in plan}
    leftover = [k for k in leftover if k not in plan_keys]
    results: list[dict] = []

    # **落盘前先过一遍规范审查**。这张表是手写的，写错一个 `$`、
    # 少一个括号，`conform` 立刻能看出来——把校验放在这里，
    # 干跑阶段就拦住，而不是等写进库再回头查。
    # （实测：`$a\\cdot \\sqrt[3]{a}=\\paren[B]` 少了一个 `$`，
    #   就是这一步抓出来的。）
    from . import conform as _cf
    spec_fail: list[str] = []
    for spec in plan:
        probe = copy.deepcopy(tgt[spec["key"]])
        try:
            _apply_one(probe, spec, by_key)
        except Exception as e:
            spec_fail.append("%s：试改失败 %s" % (spec["key"], e))
            continue
        for v in _cf.run([probe]):
            spec_fail.append("%s：改完仍%s（%s/%s）"
                             % (spec["key"], v["why"], v["check"], v["field"]))
    if spec_fail:
        return {"ok": False, "problems": spec_fail + problems,
                "plan": len(plan), "done": done, "changed": [], "written": False}

    if problems:
        return {"ok": False, "problems": problems, "plan": len(plan),
                "done": done, "changed": [], "written": False}
    if not yes:
        return {"ok": True, "dry_run": True, "plan": len(plan),
                "done": done, "leftover": leftover,
                "items": [{"key": s["key"], "why": s["why"], "src": s["src"]}
                          for s in plan],
                "changed": [], "written": False}

    for spec in plan:
        q = tgt[spec["key"]]
        try:
            notes = _apply_one(q, spec, by_key)
        except Exception as e:                       # 孪生题找不到之类
            return {"ok": False, "problems": ["%s：%s" % (spec["key"], e)],
                    "changed": [], "written": False}
        results.append({"key": spec["key"], "why": spec["why"], "src": spec["src"],
                        "notes": notes, "hash": q.content_hash()})

    if not results:
        return {"ok": True, "changed": [], "written": False,
                "note": "没有要改的", "leftover": leftover}

    store.rewrite_all(qs)

    CHANGE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report = CHANGE_DIR / ("%s_逐题订正.md" % stamp)
    lines = [
        "# 逐题订正报告",
        "",
        "- 时间：%s" % _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "- 改动：%d 道（全库 %d 道）" % (len(results), len(qs)),
        "",
        "## 逐条",
        "",
    ]
    for r in results:
        lines.append("### `%s`" % r["key"])
        lines.append("")
        lines.append("- 为什么改：%s" % r["why"])
        lines.append("- 依据：%s" % r["src"])
        for n in r["notes"]:
            lines.append("- 改动：%s" % n)
        lines.append("")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"ok": True, "changed": results, "written": True, "report": str(report)}


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    from .schema import Question as _Q

    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("fixups 自检")

    # 每条都必须有凭据、有说明、有前后对照——没有凭据的改动不许进表
    check("每条都有 key/why/src", all(p.get("key") and p.get("why") and p.get("src")
                                     for p in PATCHES))
    check("每条都有 expect 与 set", all(p.get("expect") and p.get("set")
                                       for p in PATCHES))
    check("题号不重复", len({p["key"] for p in PATCHES}) == len(PATCHES))
    check("set 里没有未知字段",
          all(set(p["set"]) <= set(_FIELDS) | {"_adopt", "drop_figures"}
              for p in PATCHES))

    # `expect` 对不上必须报出来
    q = _Q(key="t/1", type="single_choice", stem="甲", answer="A")
    check("expect 命中时不报错", not _check_expect(q, {"type": "single_choice", "stem": "甲"}))
    check("type 不符报错", bool(_check_expect(q, {"type": "multi_choice"})))
    check("子串不符报错", bool(_check_expect(q, {"stem": "乙"})))
    q2 = _Q(key="t/2", type="single_choice", stem="x",
            options=[Option("A", "$1$"), Option("B", "$2$")])
    check("选项子串命中", not _check_expect(q2, {"options": ["$2$"]}))
    check("选项子串不命中报错", bool(_check_expect(q2, {"options": ["$9$"]})))

    # 标点/空白的规整**不该**让这张账「永远对不上」。
    # 2026-09-19 踩过：13 条老账只因 `.` 被 `normalize` 换成 `。` 就全部报漂移，
    # 而 `run()` 是「一条对不上就整批不执行」——整张账连新账一起卡死。
    check("只差中英标点算同一串",
          _canon("A错。故选B.") == _canon("A错. 故选B。"))
    qp = _Q(key="t/7", type="multi_choice", stem="以下正确的有（ ）",
            answer="AB", solution="由 $x>0$。故选 AB。")
    check("老账已应用 + 标点被规整 ⇒ 判为已订正",
          _matches_target(qp, {"key": "t/7", "set": {
              "type": "multi_choice", "stem": "以下正确的有( )",
              "answer": "AB", "solution": "由 $x>0$. 故选 AB."}}, {}))
    check("expect 的标点也不敏感",
          not _check_expect(qp, {"stem": "以下正确的有( )"}))

    # 误标多选的判据
    check("答案栏写说明文字 ⇒ 判为误标",
          _is_multi_noise(_Q(key="t/3", type="multi_choice", answer="原卷无正确选项",
                             options=[Option(x, "1") for x in "ABCD"])))
    check("答案栏是字母 ⇒ 不算误标",
          not _is_multi_noise(_Q(key="t/4", type="multi_choice", answer="ABD",
                                 options=[Option(x, "1") for x in "ABCD"])))
    check("本来就是单选 ⇒ 不算误标",
          not _is_multi_noise(_Q(key="t/5", type="single_choice", answer="说明",
                                 options=[Option(x, "1") for x in "ABCD"])))
    check("还没求解（答案栏为空）⇒ 不算误标",
          not _is_multi_noise(_Q(key="t/6", type="multi_choice", answer="",
                                 options=[Option(x, "1") for x in "ABCD"])))

    print("fixups 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="逐题订正（默认干跑）")
    ap.add_argument("--yes", action="store_true", help="真的落盘")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()

    r = run(yes=a.yes)
    if not r.get("ok"):
        print("✗ 有题对不上，整批没执行：")
        for p in r["problems"]:
            print("   · %s" % p)
        return 1
    if r.get("dry_run"):
        if r.get("done"):
            print("已订正 %d 道（跳过）：" % len(r["done"]))
            for k in r["done"]:
                print("   · %s" % k)
        print("待订正 %d 道：" % r["plan"])
        for it in r["items"]:
            print("   · %s\n       改什么：%s\n       依据：%s"
                  % (it["key"], it["why"], it["src"]))
        if r.get("leftover"):
            print("\n⚠ 还有 %d 道看起来同为误标，但**没有查清原卷**，这次不动："
                  % len(r["leftover"]))
            for k in r["leftover"]:
                print("   · %s" % k)
        print("\n（干跑。确认无误后加 --yes 落盘）")
        return 0
    for c in r["changed"]:
        print("✓ %s" % c["key"])
        for n in c["notes"]:
            print("     %s" % n)
    if r.get("leftover"):
        print("\n⚠ 还剩 %d 道误标多选没查清原卷：%s"
              % (len(r["leftover"]), "、".join(r["leftover"])))
    print("\n共改 %d 道，报告：%s" % (len(r["changed"]), r.get("report")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
