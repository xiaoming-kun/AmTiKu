"""AmTiKu · 数据模型与校验

设计要点（详见 设计/新项目顶层设计.md 第一节）：

1. **什么参与内容指纹，什么不参与**——这是整个系统的基石：
   - 参与：题干 / 选项 / 答案 / 解析 / 图片 / 题型
   - **不参与：考点标签**（← 兑现"改了标签不算改题目"）
   - 不参与：来源/年份等元数据

2. **题型与字段必须自洽**——旧项目里"填空题带着选项""选择题选项为空"
   反复出现，就是因为没有这条硬约束。

3. **本模块不做任何修正**——只判断合法与否。
   旧项目的教训：把"校验"和"自动修正"混在一起，规则越滚越多，
   每加一条就改动存量数据。这里只报错，修不修由人决定。
"""
from __future__ import annotations

import hashlib
import json
import re

from . import knowledge
from dataclasses import dataclass, field, asdict

# ── 常量 ──────────────────────────────────────────────────────────────

QTYPES = ("single_choice", "multi_choice", "fill_in_blank", "detailed_answer")

# 题目来源只分两类：高考题 / 模拟题。**不再区分册子**——
# 千题册、模拟精选、手工录入选进来都是"模拟题"。
# 做成**派生属性而不是存储字段**：存了就会漂移（改了 book 忘了改 kind），
# 派生则永远和 book 一致。
KINDS = ("高考", "模拟")

QTYPE_LABEL = {
    "single_choice": "单选题",
    "multi_choice": "多选题",
    "fill_in_blank": "填空题",
    "detailed_answer": "解答题",
}

OPTION_LABELS = "ABCDEF"

# 内容指纹只算这几个字段，顺序固定（保证可复现）
HASH_FIELDS = ("type", "stem", "options", "answer", "solution", "figures")

FILLIN_RE = re.compile(r"\\fillin(?![a-zA-Z])")
IMG_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")


# ── 数据结构 ──────────────────────────────────────────────────────────

@dataclass
class Option:
    label: str          # A–F
    text: str           # LaTeX

    def __post_init__(self):
        self.label = (self.label or "").strip().upper()


@dataclass
class Figure:
    """题目配图。`id` 是内容寻址的文件名（sha256 前 16 位 + 后缀）。"""
    id: str
    kind: str = "bitmap"        # bitmap | tikz
    width: str = "0.4\\linewidth"
    tikz: str = ""              # kind == "tikz" 时是矢量源码
    source: str = ""            # 来源标注（如 "tikz-original"）


@dataclass
class Question:
    key: str                    # 自然键，如 "高考真题汇编/2025/全国II卷#4"
    type: str                   # QTYPES 之一
    stem: str = ""
    options: list[Option] = field(default_factory=list)
    answer: str = ""
    solution: str = ""
    figures: list[Figure] = field(default_factory=list)
    meta: dict = field(default_factory=dict)     # 来源/年份… 不参与指纹
    points: list[str] = field(default_factory=list)   # 考点标签，**不参与指纹**

    # ── 分类 ──────────────────────────────────────────

    @property
    def kind(self) -> str:
        r"""高考题 / 模拟题。由 `meta.book` 派生，不存储。

        判据只看书名里有没有「高考真题」——录入时由来源决定，
        之后不会因为改标签、改元数据而变。
        """
        book = self.meta.get("book") or ""
        return "高考" if "高考真题" in book else "模拟"

    # ── 难度与考点（全部派生，不存储） ─────────────────

    @property
    def difficulty(self) -> str:
        r"""难度等级。

        优先级：题目自带的 > **主考点的难度** > 空。
        旧库的 difficulty 字段 20,706 道里 16,655 道是空的，而考点库
        153 个考点的难度是齐的——从主考点派生能把覆盖率从 20% 提到
        有标签题的 100%。
        """
        own = (self.meta.get("difficulty") or "").strip()
        if own:
            return own
        if self.points:
            return knowledge.difficulty_of(self.points[0])
        return ""

    @property
    def stars(self) -> int:
        """星级（1–3）。同样优先用题目自带的。"""
        own = self.meta.get("stars")
        if isinstance(own, int) and own > 0:
            return own
        if self.points:
            return knowledge.stars_of(self.points[0])
        return 0

    @property
    def point_titles(self) -> list[str]:
        """考点**名称**（不是编号）——试卷小字部分要显示的是这个。"""
        return [knowledge.title_of(p) for p in self.points if knowledge.title_of(p)]

    # ── 内容指纹 ──────────────────────────────────────

    def content_hash(self) -> str:
        r"""内容指纹。**只算 HASH_FIELDS**——标签和元数据变化不影响它。

        这直接兑现承诺：给一道题补标签，它的"身份"不变，
        任何"内容变更"检测都不会因此误报。
        """
        payload = {
            "type": self.type,
            "stem": _norm(self.stem),
            "options": [[o.label, _norm(o.text)] for o in self.options],
            "answer": _norm(self.answer),
            "solution": _norm(self.solution),
            "figures": sorted(f.id for f in self.figures),
        }
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    # ── 完整性（缺什么，不是错） ───────────────────────

    def missing(self) -> list[str]:
        r"""缺哪些可选内容。**不算错误**——用于筛选"待补"的题。

        与 `problems()` 的分工：
          * `problems()` → 结构不合法，必须修，否则题是坏的
          * `missing()`  → 结构合法但内容不全（没答案/没解析），可以后补
        """
        gaps: list[str] = []
        if not self.answer.strip() and self.type in (
                "single_choice", "multi_choice", "fill_in_blank"):
            gaps.append("答案")
        if not self.solution.strip():
            gaps.append("解析")
        if not self.points:
            gaps.append("考点")
        return gaps

    # ── 校验 ──────────────────────────────────────────

    def problems(self) -> list[str]:
        r"""返回所有不合法之处。**空列表 = 合法**。

        只报告，不修正。修不修由人决定——这是与旧项目最大的区别。
        """
        bad: list[str] = []

        if self.type not in QTYPES:
            bad.append(f"题型非法：{self.type!r}（只能是 {QTYPES}）")
            return bad      # 题型都不对，后面的约束没意义

        if not self.stem.strip():
            bad.append("题干为空")

        # 题型 ↔ 选项
        n = len(self.options)
        if self.type in ("single_choice", "multi_choice"):
            if not 2 <= n <= 6:
                bad.append(f"{QTYPE_LABEL[self.type]}必须有 2–6 个选项，实际 {n} 个")
            labels = [o.label for o in self.options]
            if labels != list(OPTION_LABELS[:n]):
                bad.append(f"选项标号必须从 A 连续，实际 {labels}")
            # 选项是图片、而图没抽出来的题：**标记过就放行**。
            # 题目本身是好的（题干、其他选项都在），缺的是 OCR 没提取到的图。
            # 不标的话，一本 700 道的书会因为 6 道读图题**整本进不来**。
            if not self.meta.get("figure_missing"):
                for o in self.options:
                    if not o.text.strip():
                        bad.append("选项 %s 内容为空" % o.label)
        else:
            if n:
                bad.append(f"{QTYPE_LABEL[self.type]}不该有选项，实际 {n} 个")

        # 题型 ↔ 答案
        #
        # **答案为空不算错**——那是"数据不完整"，不是"结构有问题"。
        # 旧库有 9,595 道题没答案（OCR 的书源文件里就没有），它们仍是合法的题目，
        # 只是待补。把两者混为一谈会让一半的库报"非法"，人就再也不看这个报告了。
        # 「缺什么」由 `missing()` 单独回答。
        ans = self.answer.strip()
        if ans and self.type in ("single_choice", "multi_choice"):
            letters = "".join(sorted(set(ans.upper())))
            if any(c not in OPTION_LABELS[:n] for c in letters):
                bad.append(f"{QTYPE_LABEL[self.type]}的答案必须是 A–{OPTION_LABELS[n-1]}，实际 {ans!r}")
            elif self.type == "single_choice" and len(letters) != 1:
                bad.append(f"单选题答案只能 1 个字母，实际 {ans!r}")
            elif self.type == "multi_choice" and len(letters) < 2:
                bad.append(f"多选题答案至少 2 个字母，实际 {ans!r}")

        # 题型 ↔ 题干特征
        has_fillin = bool(FILLIN_RE.search(self.stem))
        if self.type == "fill_in_blank" and not has_fillin:
            bad.append("填空题的题干里必须有 \\fillin{}")
        # 解答题里出现 `\fillin` 通常意味着**题型判错了**（本该是填空题），
        # 所以拦一下。但有一种合法情形：题目要求「填写下面的列联表」，
        # 空格是**表格单元格**，不是作答位。
        # 实测：2024 全国甲卷（文）#18、（理）#17 就中过这个假阳性。
        if self.type == "detailed_answer" and has_fillin and not _fillin_in_table(self.stem):
            bad.append("解答题的题干里不该有 \\fillin{}")

        # 图片：`figures` 是**从正文推导**的（见 latex_ir.parse_question），
        # 所以两个方向都要成立，而且两边必须扫**同一批字段**：
        #   正文有 \includegraphics → figures 里就该有  ← 少了它，导出时图会丢
        #   figures 里有位图        → 正文就该引用它     ← 多出来的，是脏数据
        #
        # TikZ 例外：它的 id 是 `tikz-<hash>`，正文里是 `\begin{tikzpicture}`，
        # 本来就不出现在 `\includegraphics` 里。
        #
        # 早先这里只扫 stem+options、漏了 solution，于是"解析里带图的题"
        # 被判成"登记了图却没引用"——16 道假违规。**扫描范围不一致，
        # 校验必然自相矛盾。**
        refs: set[str] = set()
        for f in (self.stem, self.solution, *(o.text for o in self.options)):
            refs.update(IMG_RE.findall(f or ""))
        declared = {f.id for f in self.figures if f.kind != "tikz"}
        for p in sorted(declared - refs):
            bad.append(f"figures 里登记了 {p}，但正文没有引用（这张图会丢）")
        for p in sorted(refs - declared):
            bad.append(f"正文引用了 {p}，但 figures 里没有它")

        return bad


# ── 工具 ──────────────────────────────────────────────────────────────

# `\fillin` 出现在表格环境里 —— 那是让考生填的表，不是作答位
_TABLE_ENV_RE = re.compile(r"\\begin\{(?:tabular|tabularx|longtable|array)\}")


def _fillin_in_table(stem: str) -> bool:
    r"""题干里的 `\fillin` 是不是都在表格里。

    「填写下面的列联表」这类题，空格是**表格单元格**，属于解答题的正文，
    不该被判成「题型错了」。做法：把表格环境挖掉，再看还剩不剩 `\fillin`。
    """
    if not stem:
        return False
    stripped = stem
    # 逐个挖掉 tabular…end{tabular}（不嵌套，够用）
    while True:
        m = _TABLE_ENV_RE.search(stripped)
        if not m:
            break
        env = re.match(r"\\begin\{(\w+)\}", stripped[m.start():]).group(1)
        end = stripped.find("\\end{%s}" % env, m.end())
        if end < 0:
            break
        stripped = stripped[:m.start()] + stripped[end + len("\\end{%s}" % env):]
    return not FILLIN_RE.search(stripped)


def _norm(s: str) -> str:
    """算指纹前的归一：空白折叠。**不做语义归一**——
    语义归一属于迁移规则（MIGRATE 级），不该藏在指纹计算里。"""
    return re.sub(r"\s+", " ", (s or "").strip())


def from_dict(d: dict) -> Question:
    return Question(
        key=d.get("key", ""),
        type=d.get("type", ""),
        stem=d.get("stem", ""),
        options=[Option(**o) if isinstance(o, dict) else Option(*o)
                 for o in (d.get("options") or [])],
        answer=d.get("answer", ""),
        solution=d.get("solution", ""),
        figures=[Figure(**f) if isinstance(f, dict) else Figure(*f)
                 for f in (d.get("figures") or [])],
        meta=d.get("meta") or {},
        points=d.get("points") or [],
    )


def to_dict(q: Question) -> dict:
    d = asdict(q)
    d["hash"] = q.content_hash()
    return d


if __name__ == "__main__":
    # 自检：四类题型各一条合法样例 + 五种典型错误
    samples = [
        (Question(key="t/1", type="single_choice",
                  stem=r"不等式 $\frac{x-4}{x-1}\geqslant 2$ 的解集是（\quad）",
                  options=[Option("A", r"$\{x\mid x\leqslant 1\}$"),
                           Option("B", r"$\{x\mid x<1\}$")],
                  answer="A"), []),
        (Question(key="t/2", type="fill_in_blank", stem=r"$1+1=$\fillin{}."), []),
        (Question(key="t/3", type="detailed_answer", stem="已知函数 $f(x)=x^2$。"), []),
        # 错误样例
        (Question(key="e/1", type="single_choice", stem="x",
                  options=[Option("A", "a")], answer="A"),
         ["必须有 2–6 个选项"]),
        (Question(key="e/2", type="fill_in_blank", stem="没有空"),
         ["必须有 \\fillin{}"]),
        (Question(key="e/3", type="detailed_answer", stem="解答",
                  options=[Option("A", "a"), Option("B", "b")]),
         ["不该有选项"]),
        (Question(key="e/4", type="single_choice", stem="x",
                  options=[Option("A", "a"), Option("B", "b")], answer="AB"),
         ["单选题答案只能 1 个字母"]),
        (Question(key="e/5", type="detailed_answer",
                  stem=r"如图 \includegraphics{a1b2c3d4e5f60718.png} 所示"),
         ["figures 里没有它"]),
    ]
    ok = 0
    for q, want in samples:
        got = q.problems()
        hit = all(any(w in g for g in got) for w in want) if want else not got
        ok += hit
        mark = "✓" if hit else "✗"
        print(f"{mark} {q.key:6} {QTYPE_LABEL.get(q.type, q.type):6} "
              f"{'合法' if not got else got[0][:52]}")
    print(f"\n{ok}/{len(samples)} 通过")

    # 指纹稳定性：改标签不改指纹
    q = samples[0][0]
    h1 = q.content_hash()
    q.points = ["3.2.1", "1.1.1"]
    q.meta["source"] = "改了元数据"
    h2 = q.content_hash()
    print(f"改标签/元数据后指纹不变：{'✓' if h1 == h2 else '✗'}  {h1}")
