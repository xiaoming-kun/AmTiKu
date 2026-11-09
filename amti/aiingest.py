r"""AI 录题：整份 PDF → 结构化题目（源材料 LaTeX）。

## 这条流水线只有四步

    PDF 页 → PNG（PyMuPDF，150dpi）
      → 每 6 页一次调用 DeepSeek（页间重叠 1 页，跨页题靠后一批接住）
      → 模型回 JSON（题干/选项/答案/解析/考点/图决策）
      → 组装成 **exam-zh 源材料**（就是录入框里粘的那种文本）

最后一步是刻意的：产物只填进录入框，**解析/校验/查重/入库仍然走
`amti/ingest.py`**。这样规范器、查重、缺答案闸门、影响面审计全都只有
一份实现（AGENTS.md 第三节）。

## 三条硬规矩

1. **只抄不解**：原文没有答案就留空，缺答案/缺解析的题**不进源材料**
   （进 `pending` 清单，界面上告诉用户"这几道没解析，先别录"）。
   宁可少录十道，也不让模型编一个答案进题库。
2. **图分两种**：简单图让模型写 TikZ（用 `tikzfig` 编译校验，过不了就降级）；
   复杂图给归一化框，**从同一张页图上裁**——模型看的就是这张图，
   坐标没有换算误差。
3. **裁出来的图不直接进 `图片/`**：先落 `数据/缓存/AI图/<任务>/`，
   由 `ingest` 的图片入库（内容寻址）搬进去。用户取消时不会留下孤儿图。
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, CancelledError
from pathlib import Path

import fitz                                     # PyMuPDF：PDF → 页图
from PIL import Image, ImageStat

from . import deepseek
from .paths import ROOT

#: 页图落盘/裁剪用的临时根目录（缓存区，可整目录删）。
CROP_ROOT = ROOT / "数据" / "缓存" / "AI图"

#: 题块分隔靠 `\begin{question}`；解析器只认 exam-zh 这套。
_QTYPE = {
    "single_choice": "single_choice", "单选": "single_choice",
    "multiple_choice": "multi_choice", "multi_choice": "multi_choice",
    "多选": "multi_choice", "multiple": "multi_choice",
    "fill_in_blank": "fill_in_blank", "fill": "fill_in_blank",
    "填空": "fill_in_blank", "fill_blank": "fill_in_blank",
    "detailed_answer": "detailed_answer", "solution": "detailed_answer",
    "解答": "detailed_answer", "解答题": "detailed_answer", "计算": "detailed_answer",
}

_DIFFS = ("简单题", "中档题", "难题")

_FIG = re.compile(r"<<\s*FIG\s*(\d+)\s*>>", re.I)
_BLANK = re.compile(r"<<\s*BLANK\s*>>", re.I)


class Cancelled(RuntimeError):
    """用户在界面上按了取消。

    已经发出去的请求收不回来（API 调用仍会计费），但**不再发新请求**，
    已读到的批次会作为部分结果返回。
    """


# ── 考点白名单 ────────────────────────────────────────────────────────

_POINTS_CACHE: list[dict] | None = None


def _points() -> list[dict]:
    """152 个考点（id + 短标题）。给模型选，**不接受白名单外的 id**。"""
    global _POINTS_CACHE
    if _POINTS_CACHE is None:
        try:
            from . import knowledge
            _POINTS_CACHE = [
                {"id": p["id"], "title": str(p.get("title") or "").split("（")[0].strip()}
                for p in knowledge.all_points()
            ]
        except Exception:                        # noqa: BLE001
            _POINTS_CACHE = []
    return _POINTS_CACHE


def _point_ids() -> set[str]:
    return {p["id"] for p in _points()}


# ── 提示词 ────────────────────────────────────────────────────────────

_PROMPT_HEAD = r"""你是 K12 数学题库的**转录员**。下面给你同一份资料的若干页图片（按顺序）。
你只做**第一遍转录**：把页面上完整的题目抄成 JSON；答案和解析的核对由**第二遍**独立完成。

## 铁律（违反一条，整批作废）
1. **只转录，不许解题、不许补答案**。题页上直接印着答案/解析就原样抄；题页没有就写 ""。
   第二遍会拿答案册原页和答案册原文逐题核对，**不要替它猜一个答案**。
2. 只输出**完整**的题：题干、选项都在你收到的这些页里。
   题干只出现一半（后半截在下一页、而下一页不在这次给你）就跳过，后面的批次会完整看到它。
3. 一道题只出现一次。同一道题在重叠页里出现两次时，只输出最完整的那个。
4. 输出**一个 JSON 对象**，不要解释、不要 markdown 代码块。

## 输出格式
{"title": "卷名（页眉上有就写，如「2024年新高考I卷」；没有就 \"\"）",
 "questions": [
  {"no": "题号（原文的，如 3、12、二.5；看不清给本批顺序号）",
   "type": "single_choice | multiple_choice | fill_in_blank | detailed_answer",
   "page": 本题题干出现在本批第几张图（1 基；跨页写起始页）,
   "stem": "题干（LaTeX）",
   "options": [{"label": "A", "text": "选项内容（LaTeX）"}],
   "answer": "题页上直接印了才抄；没有就 \"\"（选择题写字母，填空写值）",
   "answer_quote": "题页上答案的原话；没有就 \"\"",
   "solution": "题页上直接印了才抄；没有就 \"\"（LaTeX）",
   "difficulty": "简单题 | 中档题 | 难题 | （拿不准就 \"\"）",
   "points": ["考点 id（只能从下面清单里选，1~3 个）"],
   "figures": []
  }
 ]}

## 公式与写法
- 行内公式用 `$...$`，行间用 `\[ ... \]`；分式 `\dfrac`，不等号 `\geqslant` `\leqslant`。
- 数学模式里不写中文（要写就 `\text{...}`）。
- 向量、集合、区间、根式都用 `$...$` 包起来；不要出现裸的 `\overrightarrow`、`\vec`、`\complement`、`\sqrt`。
- 题干/解析里不要写依赖插图的「如图」；题干没有图就删掉这几个字。
- 题干里不要写「（多选）」这类题型说明，题型由 type 表达。
- 填空的空位写 `<<BLANK>>`，有几个空写几个（答案按顺序对应）。
- `stem` 里不要自己加 `\paren[...]`（选择题的作答括号由程序加）。

## 图
- **简单图**（三角形、圆、简单立体图、坐标系里的直线/抛物线、条形图/频率分布直方图这类，
  6~25 行 TikZ 能画准的）：在 stem 里放 `<<FIG1>>` 占位，figures 里给
  {"kind": "tikz", "tikz": "\\begin{tikzpicture}...\\end{tikzpicture}", "width": "6cm"}。
  画不准的线条宁可不画，别画错。
- **复杂图**（组合体、辅助线很多、图像曲线复杂、表格、照片）：给
  {"kind": "crop", "page": 本批第几张图（从 1 开始）, "bbox": [x0, y0, x1, y1], "width": "6cm"}。
  bbox 是**归一化坐标**（0~1，相对整页左上角），只框图形本身，不要把题号/文字框进去。
- 一道题最多两张图。拿不准就 crop——裁下来的图一定忠实，画出来的不一定。
- **有图就必须给 figures，不许省略**：题干里出现「如图」「图1/图2」、或明显配了图形
  （几何体、坐标系、统计图、表格），都算有图。宁可 crop 大一点（多带点白边没关系），
  也不能一道图题交回来没有图。

## 考点清单（points 只能用这里面的 id）
%s
"""

_HEAD_CACHE: list[str] = []


def _head() -> str:
    """提示词要带 152 个考点的白名单。**懒拼一次**——考点表万一读不出来，
    下次调用还能重新试，而不是把空清单永久烧进字符串里。"""
    if not _HEAD_CACHE:
        pts = _points()
        _HEAD_CACHE.append(_PROMPT_HEAD % (
            "\n".join("%s %s" % (p["id"], p["title"]) for p in pts)
            if pts else "（考点表读取失败：points 一律给 []）"))
    return _HEAD_CACHE[0]


def _prompt_for(pages: list[int], total: int, only: list[str] | None = None) -> str:
    head = "本批是试题的第 %s 页（共 %d 页）。" % (
        "、".join(str(p) for p in pages), total)
    tail = "\n只输出本批这些页里完整的题；题干不全的题跳过。直接给 JSON。"
    if only:
        tail += ("\n这次只补读这些题号：%s；只输出这几道，不要输出别的题。"
                 % "、".join(only))
    return _head() + "\n" + head + tail


# ── 答案册：**先读成文字，再当上下文** ──────────────────────────────
#
# 为什么不让每批都啃答案册的图：一页图 ≈ 1024 token，答案册 10 页 × 17 批
# 就是 170 张重复的图。先读一遍变成 JSON 文字（几十 KB），之后每批只带这段
# 文字，钱和延迟都省一个数量级；而且答案册只解析一次，错了能一眼看出来。

_ANSWER_HEAD = r'''这是某份试卷的「答案 / 解析」（可能不止一页）。把每道题的答案和解析**原样抄**成 JSON：
{"title": "卷名（有就写，没有就空串）",
 "questions": [{"no": "题号（原文怎么写就怎么抄，如 12、二.3）",
                "answer": "答案（原文）",
                "solution": "解析（原文整段抄；原文没有就空串）",
                "page": 本批第几张图（1 基；拿不准就 1）,
                "flawed": false,
                "note": "答案册自己的说明（如「原题条件矛盾」）；没有就空串"}]}

规则：
- **只抄不改**。原文没有解析就留空，不要自己写解析、不要自己算答案。
- 连写的答案要拆开：「1-5 CBADC」→ 1:C、2:B、3:A、4:D、5:C；「6-10：ADBCB」同理。
- **答案册自己说这题是错题的**（如「条件矛盾」「无有效答案」「四个选项均不能」），
  `flawed` 写 true，`answer` 留空，`note` 抄原话；不要去猜一个字母。
- `page` 写这道题的答案/解析出现在**本批第几张图**（1 基），后续要把答案页和题目对起来。
- 同一道题只出现一次；题号不同的两条不要合并。
- 只输出 JSON，不要解释、不要代码块。'''


def _norm_no(raw: str) -> str:
    r"""题号归一：`8.`、`（8）`、`第8题`、`一、8` 都认成 `8`。

    *只*做比较用的归并，不改源材料的原题号；带小问的 `17(1)` 原样保留。
    """
    s = str(raw or "").strip()
    s = s.replace("（", "(").replace("）", ")").replace("．", ".")
    s = re.sub(r"^第\s*", "", s)
    s = re.sub(r"\s*题$", "", s)
    s = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", s)
    s = re.sub(r"^[（(]\s*(\d+)\s*[）)]$", r"\1", s)
    return s.strip(" .、。:：")


def _looks_flawed(item: dict) -> bool:
    txt = " ".join(str(item.get(k) or "") for k in ("answer", "solution", "note"))
    return any(k in txt for k in ("错题", "无有效答案", "条件矛盾", "无符合题设",
                                  "四个选项均不能", "无符合条件"))


def _read_answer_batch(pngs: list[bytes], pgs: list[int], total: int,
                       should_stop=None, on_usage=None) -> list[dict]:
    r"""读答案册的一批：**输出截断就对半拆，限流/服务端/超时重试**。"""
    def stop() -> bool:
        try:
            return bool(should_stop and should_stop())
        except Exception:                       # noqa: BLE001
            return False

    def prompt_for(extra: str = "") -> str:
        return (_ANSWER_HEAD + "\n本批是答案册的第 %s 页（共 %d 页）。" % (
            "、".join(str(p) for p in pgs), total)) + extra

    last: Exception | None = None
    extra = ""
    for attempt in range(3):
        if stop():
            raise Cancelled("已取消")
        try:
            raw = deepseek.chat(prompt_for(extra), [pngs[p - 1] for p in pgs],
                                timeout=300, json_mode=True, on_usage=on_usage)
            return list(_parse_json(raw).get("questions") or [])
        except ValueError as e:                  # JSON 坏了：再要一次
            last = e
            extra = ("\n\n上一次的回复不是合法 JSON（%s）。这次只输出 JSON 本体。"
                     % str(e)[:80])
            time.sleep(1.5 * (attempt + 1))
            continue
        except deepseek.AIError as e:
            if "截断" in str(e) and len(pgs) > 1:
                left, right = _split_pages(pgs)
                return (_read_answer_batch(pngs, left, total, should_stop, on_usage)
                        + _read_answer_batch(pngs, right, total, should_stop, on_usage))
            if "限流" not in str(e) and "服务端" not in str(e) and "等太久" not in str(e):
                raise
            last = e
            time.sleep(4 * (attempt + 1))
    raise deepseek.AIError(str(last or "答案册读不出来"))


def _read_answers(pngs: list[bytes], per: int, should_stop=None,
                  on_usage=None) -> dict[str, dict]:
    r"""答案册整份 → `{归一题号: {no, answer, solution, page, flawed, note}}`。

    `page` 是**整份答案册**的页号（1 基），后面核对时把这一页原图一起给模型看，
    保证答案不是"模型记得的"，而是"答案册上印着的"。
    """
    merged: dict[str, dict] = {}
    for pgs in _ranges(len(pngs), per):
        for it in _read_answer_batch(pngs, pgs, len(pngs), should_stop, on_usage):
            if not isinstance(it, dict):
                continue
            raw_no = str(it.get("no") or "").strip()
            no = _norm_no(raw_no)
            if not no:
                continue
            rel = 0
            try:
                rel = int(it.get("page") or 0)
            except (TypeError, ValueError):
                rel = 0
            page = pgs[rel - 1] if 1 <= rel <= len(pgs) else pgs[0]
            answer = str(it.get("answer") or "").strip()
            solution = str(it.get("solution") or "").strip()
            note = str(it.get("note") or "").strip()
            flawed = bool(it.get("flawed")) or _looks_flawed(it)
            new = {"no": no, "raw_no": raw_no, "answer": answer,
                   "solution": solution, "page": page, "flawed": flawed,
                   "note": note}
            cur = merged.get(no)
            if cur is None:
                merged[no] = new
                continue
            keep_flawed = cur["flawed"] or new["flawed"]
            keep_note = new["note"] or cur["note"]
            new_weight = len(answer) + len(solution)
            cur_weight = len(cur["answer"]) + len(cur["solution"])
            if new_weight > cur_weight:
                new["flawed"], new["note"] = keep_flawed, keep_note
                merged[no] = new
            else:
                cur["flawed"], cur["note"] = keep_flawed, keep_note
    return merged


def _ranges(total: int, per: int) -> list[list[int]]:
    """按页切块，**相邻块重叠 1 页**——跨页的题在后一块里是完整的。

    `per=1` 时不能重叠：`start = end` 会让 `start` 永远不前进，
    两页以上的资料直接死循环（实测 `timeout 3` 都退不出来）。
    配置/接口都允许把每批页数设成 1，所以这里必须显式处理。
    """
    out: list[list[int]] = []
    per = max(1, int(per))
    start = 1
    while start <= total:
        end = min(total, start + per - 1)
        out.append(list(range(start, end + 1)))
        if end >= total:
            break
        start = end if per > 1 else end + 1
    return out


def _split_pages(pgs: list[int]) -> tuple[list[int], list[int]]:
    """输出被截断时对半拆，**两半保留 1 页重叠**。

    截断拆分最容易踩的坑：直接把 `[1,2,3,4]` 拆成 `[1,2]` / `[3,4]`，
    跨第 2~3 页的题两半都看不全，就丢了。重叠页让边界上的题至少在
    一半里是完整的。

    两页及以下没法既拆小又重叠，退化成逐页拆（`[1]` / `[2]`）；
    这种情形跨页题本来就只能在两页齐全时读，拆到底也保不住。
    """
    n = len(pgs)
    if n <= 2:
        return pgs[:1], pgs[1:]
    mid = n // 2
    return pgs[:mid + 1], pgs[mid:]


def _stamp_pages(d: dict, pgs: list[int]) -> dict:
    """给这一批读出的每道题记下它**实际看到的页**（1 基），供裁图/原页预览用。

    截断拆批后，模型给的 `figures[].page` 是相对**子批**的；如果上层还拿
    原批 `pgs` 去换算，后半批的图就会静默裁到前半批的页上（实测：本批
    第 2 张图应裁第 4 页，结果裁到了第 2 页，还不报错）。
    """
    for q in d.get("questions") or []:
        if not isinstance(q, dict):
            continue
        # `_pages` 仍是**整批页**：图裁切用的是"本批第几张"，不能换成单页。
        q["_pages"] = list(pgs)
        # `_source_page` 是模型指出的题干所在页：给核对/原页预览用。
        try:
            rel = int(q.get("page") or 0)
        except (TypeError, ValueError):
            rel = 0
        q["_source_page"] = (pgs[rel - 1] if 1 <= rel <= len(pgs)
                             else (pgs[0] if pgs else 0))
    return d


def _page_count(data: bytes) -> int:
    """先数页数（不渲染）——界面上「共 120 页」这句要立刻出来，不能等拆完页。"""
    if data[:5] != b"%PDF-":
        return 1
    try:
        d = fitz.open(stream=data, filetype="pdf")
        n = d.page_count
        d.close()
        return n
    except Exception:                            # noqa: BLE001
        return 0


# ── 页图 ──────────────────────────────────────────────────────────────

def _render(data: bytes, dpi: int, on_page=None) -> list[bytes]:
    """资料 → 每页一张 PNG。150dpi 的 A4 ≈ 1.7MP，正好是 DeepSeek 的图片预算。

    PDF 直接逐页渲；**单张图片（拍照/截图）包成一页 PDF** 再走同一条路——
    客户手里很多时候就是一张照片，没道理让他先自己转 PDF。
    """
    out: list[bytes] = []
    # **按文件头判断，不靠 try**：PyMuPDF 也能"打开图片"，但页面尺寸按 96dpi
    # 折算，出来的页图会比预期大一圈（800px 的图渲成 1250px）。显式分两条路。
    if data[:5] == b"%PDF-":
        doc = fitz.open(stream=data, filetype="pdf")
    else:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = im.size
        pw, ph = w * 72.0 / dpi, h * 72.0 / dpi      # 1pt = 1/72 inch
        doc = fitz.open()
        page = doc.new_page(width=pw, height=ph)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        page.insert_image(fitz.Rect(0, 0, pw, ph), stream=buf.getvalue())
    try:
        for i, page in enumerate(doc, 1):
            pm = page.get_pixmap(dpi=dpi, alpha=False)
            out.append(pm.tobytes("png"))
            if on_page is not None:
                on_page(i)
    finally:
        doc.close()
    return out


# ── JSON ──────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """从模型的回复里捞 JSON。**宽容但不猜**：捞不出来就报错（上层会重试一次）。

    实测模型会包三种东西：markdown 代码块、开头一句"好的，结果如下"、
    以及最外层直接给数组（协议里说对象，它不一定听）。
    """
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()

    def load(x: str):
        try:
            return json.loads(x)
        except ValueError:
            # 常见伤：对象/数组末尾多个逗号、中文引号
            x2 = re.sub(r",\s*([}\]])", r"\1", x).replace("“", '"').replace("”", '"')
            return json.loads(x2)

    try:
        d = load(s)
    except ValueError:
        i = min([k for k in (s.find("{"), s.find("[")) if k >= 0], default=-1)
        j = max(s.rfind("}"), s.rfind("]"))
        if i < 0 or j <= i:
            raise ValueError("模型没回 JSON：" + s[:160])
        d = load(s[i:j + 1])
    if isinstance(d, list):
        d = {"questions": d}
    if not isinstance(d, dict):
        raise ValueError("JSON 顶层既不是对象也不是数组")
    if not isinstance(d.get("questions"), list):
        d["questions"] = []
    return d


# ── 组装 ──────────────────────────────────────────────────────────────

def _strip_paren(stem: str) -> str:
    """模型偶尔自己加作答括号；去掉，由程序统一加。"""
    return re.sub(r"\\paren\[[^\]]*\]\s*$", "", (stem or "").rstrip()).rstrip()


def _norm_answer(raw: str, qtype: str) -> str:
    a = (raw or "").strip()
    if not a:
        return ""
    if qtype in ("single_choice", "multi_choice"):
        letters = re.findall(r"[A-Dａ-ｄ]", a.upper().replace("Ａ", "A"))
        seen: list[str] = []
        for ch in letters:
            ch = ch.upper()
            if ch not in seen:
                seen.append(ch)
        return "".join(sorted(seen))
    return a


_MATH_WRAP_CMDS = {
    "overrightarrow", "vec", "complement", "sqrt", "frac", "dfrac", "tfrac",
    "cdot", "times", "div", "pm", "mp", "le", "leqslant", "ge", "geqslant",
    "ne", "neq", "approx", "infty", "pi", "alpha", "beta", "gamma", "theta",
    "lambda", "mu", "sigma", "omega", "varphi", "sin", "cos", "tan", "cot",
    "log", "ln", "exp", "overline", "underline", "angle", "triangle",
    "parallel", "perp", "because", "therefore", "in", "notin", "subset",
    "subseteq", "cup", "cap", "emptyset", "forall", "exists", "sum", "prod",
    "int", "lim", "to", "rightarrow", "Rightarrow", "Leftrightarrow",
    "quad", "qquad", "mathbb", "mathbf", "mathrm",
}
_MATH_CMD = re.compile(r"\\[A-Za-z]+")


def _cmd_span(s: str, i: int) -> tuple[str, int] | None:
    """从 `s[i]` 的 `\\cmd` 起，吃掉紧跟着的花括号/方括号参数，返回 (命令, 结束下标)。"""
    m = _MATH_CMD.match(s, i)
    if not m:
        return None
    cmd = m.group(0)
    j = m.end()
    while j < len(s):
        if s[j] in " \t":
            j += 1
            continue
        if s[j] in "[{":
            close = "]" if s[j] == "[" else "}"
            depth = 0
            k = j
            while k < len(s):
                if s[k] == "\\":
                    k += 2
                    continue
                if s[k] == s[j]:
                    depth += 1
                elif s[k] == close:
                    depth -= 1
                    if depth == 0:
                        k += 1
                        break
                k += 1
            if depth != 0:
                break
            j = k
            continue
        break
    return cmd, j


def _repair_math(text: str) -> str:
    r"""把**数学模式外**的裸命令包进 `$...$`。

    实测模型会把整段解析写成 `\overrightarrow{AB}=4\overrightarrow{AD}=...`，
    KaTeX/LaTeX 会原样印出反斜杠；`conform` 会拦下，但用户还得手改。
    这里只修**安全的单命令**（向量/根式/分式/希腊字母等），
    `\left`/`\right` 这种需要配对的、`\begin`/`\includegraphics` 这种环境命令跳过。
    """
    s = str(text or "")
    if not s or "\\" not in s:
        return s
    out: list[str] = []
    i = 0
    math = False
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt in "[(":
                math = True
                out.append(s[i:i + 2]); i += 2; continue
            if nxt in "])":
                math = False
                out.append(s[i:i + 2]); i += 2; continue
        if c == "$":
            if i + 1 < n and s[i + 1] == "$":
                math = not math
                out.append("$$"); i += 2; continue
            math = not math
            out.append("$"); i += 1; continue
        if not math and c == "\\":
            got = _cmd_span(s, i)
            if got and got[0][1:] in _MATH_WRAP_CMDS:
                cmd, j = got
                out.append("$" + s[i:j].strip() + "$")
                i = j
                continue
        out.append(c)
        i += 1
    return "".join(out)


def _strip_dangling_tuk(text: str, has_figure: bool) -> tuple[str, bool]:
    """没有图时删掉「如图」——答案册解析里的 `如图` 不能指向一个不存在的图。"""
    if has_figure or "如图" not in (text or ""):
        return text, False
    t = text
    for p in ("（如图）", "(如图)", "如图，"):
        t = t.replace(p, "")
    t = t.replace("如图", "")
    return t, True


def _compose(item: dict, pages_png: list[bytes],
             crop_dir: Path) -> tuple[dict, list[str]]:
    """一道题 → 源材料文本块。返回 (结果, 问题清单)。"""
    problems: list[str] = []
    qtype = _QTYPE.get(str(item.get("type") or "").strip().lower(),
                       _QTYPE.get(str(item.get("type") or "").strip(), ""))
    stem = str(item.get("stem") or "").strip()
    no = str(item.get("no") or "").strip()
    answer = _norm_answer(str(item.get("answer") or ""), qtype)
    solution = str(item.get("solution") or "").strip()
    stem = _repair_math(stem)
    solution = _repair_math(solution)
    answer = _repair_math(answer)
    if not qtype:
        qtype = "detailed_answer" if not item.get("options") else "single_choice"

    # ── 图 ──
    # 模型偶尔把 figures 给成字符串/对象，甚至 [null]；以前这里直接
    # `f.get(...)` 会把整份任务在组装阶段打崩（所有批次已经花钱读完）。
    figs_raw = item.get("figures")
    figs = figs_raw if isinstance(figs_raw, list) else []
    if figs_raw and not figs:
        problems.append("一道题的 figures 不是数组，已按无图处理")
    used: set[int] = set()

    def fig_tex(idx: int) -> str:
        if not (1 <= idx <= len(figs)) or idx in used:
            return "【图：缺失，请手工补】"
        used.add(idx)
        f = figs[idx - 1]
        if not isinstance(f, dict):
            f = {}
        kind = str(f.get("kind") or "").lower()
        # 宽度只放行 LaTeX 长度或 `0.4\linewidth` 这种；模型给怪值会让整卷编译失败
        width = str(f.get("width") or "6cm").strip()
        if not re.fullmatch(r"\d+(?:\.\d+)?(?:cm|mm|pt|in|em)", width) \
                and not re.fullmatch(r"\d*\.?\d*\\linewidth", width):
            width = "6cm"
        if kind == "tikz":
            code = str(f.get("tikz") or "").strip()
            if not code:
                return "【图：缺失，请手工补】"
            try:
                from . import tikzfig
                p, why = tikzfig.render(code)
            except Exception as e:                    # noqa: BLE001
                p, why = None, str(e)
            if p is None:
                problems.append("一道题的 TikZ 没画出来（%s），已标「请补图」"
                                % (why or "编译失败")[:60])
                return "【图：AI 画的图没通过编译，请补图】"
            # 内联源码：`derive_figures` 靠它登记成 tikz 图，
            # 导出时 `to_image` 再用渲染好的 PDF 替换（见 amti/tikzfig.py）。
            return "\n" + code + "\n"
        # crop
        try:
            page_i = int(f.get("page") or 0)
            box = [float(v) for v in (f.get("bbox") or [])][:4]
            if len(box) != 4:
                raise ValueError("bbox 不是 4 个数")
            x0, y0, x1, y1 = box
            x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
            y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
            if x1 - x0 < 0.03 or y1 - y0 < 0.03:
                raise ValueError("框太小（%.3f×%.3f）" % (x1 - x0, y1 - y0))
            if not (1 <= page_i <= len(pages_png)):
                raise ValueError("page=%d 超出本批页数 %d" % (page_i, len(pages_png)))
            im = Image.open(io.BytesIO(pages_png[page_i - 1])).convert("RGB")
            w, h = im.size
            pad = 0.012
            cx0 = int(max(0, (x0 - pad)) * w); cx1 = int(min(1, (x1 + pad)) * w)
            cy0 = int(max(0, (y0 - pad)) * h); cy1 = int(min(1, (y1 + pad)) * h)
            if cx1 - cx0 < 24 or cy1 - cy0 < 24:
                raise ValueError("裁出来只有 %d×%d 像素" % (cx1 - cx0, cy1 - cy0))
            crop = im.crop((cx0, cy0, cx1, cy1))
            # 一片雪白 = 框错了地方
            gray = crop.convert("L")
            if ImageStat.Stat(gray).stddev[0] < 3.0:
                raise ValueError("框里几乎是空白")
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            raw = buf.getvalue()
            name = "ai-%s.png" % hashlib.sha1(raw).hexdigest()[:10]
            crop_dir.mkdir(parents=True, exist_ok=True)
            (crop_dir / name).write_bytes(raw)
            return "\\includegraphics[width=%s]{%s}" % (width, name)
        except Exception as e:                        # noqa: BLE001
            problems.append("一道题的图没裁出来（%s），已标「请补图」" % str(e)[:60])
            return "【图：裁切失败，请补图】"

    def fig_sub(m: re.Match) -> str:
        return fig_tex(int(m.group(1)))

    stem = _FIG.sub(fig_sub, stem)

    # ── 填空 ──
    if qtype == "fill_in_blank":
        blanks = _BLANK.findall(stem)
        ans_parts = [x.strip() for x in re.split(r"[；;]", answer) if x.strip()] if answer else []
        if not blanks:
            problems.append("填空题没标出空位")
        if ans_parts and blanks and len(ans_parts) != len(blanks):
            problems.append("空位 %d 个、答案 %d 个，对不上" % (len(blanks), len(ans_parts)))
        for i, _ in enumerate(blanks):
            val = ans_parts[i] if i < len(ans_parts) else " "
            stem = _BLANK.sub(lambda _m, v=val: "\\fillin[%s]" % v, stem, count=1)
        stem = _BLANK.sub(lambda _m: "\\fillin[ ]", stem)   # 答案不够时留空位

    # ── 选择题：作答括号由程序加 ──
    stem = _strip_paren(stem)
    if qtype in ("single_choice", "multi_choice"):
        if not answer:
            problems.append("选择题没有答案")
        stem = stem.rstrip() + "\\paren[%s]" % (answer or " ")

    # 声明了但题干里没放占位符的图，补到最后（总比丢了强）。
    # **必须放在作答括号之后**：否则选择题的 `\paren[A]` 会贴在图上，
    # 卷面看起来像「图 [A]」而不是题干末尾的作答括号（实测模型常省略占位符）。
    for i in range(1, len(figs) + 1):
        if i not in used:
            stem += "\n" + fig_tex(i)

    # 没有图时，「如图」是悬空引用；答案册解析里很容易带来这几个字。
    has_fig = bool(figs) or bool(used)
    stem, tuk1 = _strip_dangling_tuk(stem, has_fig)
    solution, tuk2 = _strip_dangling_tuk(solution, has_fig)
    if tuk1 or tuk2:
        problems.append("题干/解析里的「如图」没有对应图，已删")

    # ── 元数据行 ──
    pts_raw = item.get("points")
    if isinstance(pts_raw, str):
        pts_raw = [pts_raw]
    pts = [p for p in (pts_raw or [])
           if isinstance(p, str) and p.strip() in _point_ids()]
    pts = list(dict.fromkeys(p.strip() for p in pts))[:3]
    diff = str(item.get("difficulty") or "").strip()
    if diff not in _DIFFS:
        diff = ""
    meta: dict = {}                      # book/label 由录入框的全局字段决定
    if diff:
        meta["difficulty"] = diff
    # `%% @q` 顶层的 type 落库时没人读（ingest 读的是 `meta["type"]`）。
    # 不写进 meta，题型会被 parse_question 按「答案字母数」重判：
    # 多选只有一个正确项 → 存成单选；单选抄成 AB → 存成多选。
    meta["type"] = qtype
    # 原卷题号也写进 meta：`ingest` 会原样保留 meta["source_no"]，
    # 卡片上「原卷题号」和卷面来源都靠它。不写的话，Q8 缺失后 #8
    # 其实是第 9 题，入库后再也看不出原卷编号。
    if no:
        meta["source_no"] = no
    if item.get("verified"):
        meta["verified"] = True
        for k in ("verdict", "answer_source", "solution_source",
                  "answer_quote", "solution_quote", "confidence"):
            v = item.get(k)
            if v not in (None, "", False):
                meta[k] = v
    head = {"type": qtype, "points": pts, "meta": meta}

    body: list[str] = [
        "%% @q " + json.dumps(head, ensure_ascii=False),
        "\\begin{question}",
        stem.strip(),
    ]
    # 模型偶尔把 options 给成 `["A. 5", "B. 6", ...]`（字符串数组）。
    # 以前只认 dict，整组选项静默丢掉，题还会被重判成解答题、报「解答题不该有 paren」。
    opts_raw = item.get("options")
    options: list[dict] = []
    for o in (opts_raw if isinstance(opts_raw, list) else []):
        if isinstance(o, dict):
            options.append(o)
        elif isinstance(o, str) and o.strip():
            text = re.sub(r"^\s*[A-DＡ-Ｄ]\s*[.、．:：]\s*", "", o).strip()
            if text:
                options.append({"text": text})
    if opts_raw and not isinstance(opts_raw, list):
        problems.append("一道题的 options 不是数组，已按无选项处理")
    if qtype in ("single_choice", "multi_choice") and options:
        body.append("\\begin{choices}")
        for o in options:
            body.append("  \\item %s" % str(o.get("text") or "").strip())
        body.append("\\end{choices}")
    if solution:
        body += ["\\begin{solution}", solution.strip(), "\\end{solution}"]
    body.append("\\end{question}")

    return {
        "tex": "\n".join(body),
        "no": no,
        "type": qtype,
        "answer": "见解析" if qtype == "detailed_answer" else answer,
        "solution": solution,
        "unverified": bool(answer) and qtype != "detailed_answer"
                      and not str(item.get("answer_quote") or "").strip(),
        "answer_quote": str(item.get("answer_quote") or ""),
        "solution_quote": str(item.get("solution_quote") or ""),
        "verdict": str(item.get("verdict") or ""),
        "verified": bool(item.get("verified")),
        "answer_source": str(item.get("answer_source") or ""),
        "solution_source": str(item.get("solution_source") or ""),
        "confidence": item.get("confidence"),
    }, problems


# ── 主流程 ────────────────────────────────────────────────────────────

_VERIFY_HEAD = r"""你是 K12 数学题库的**核对员**。这是第二遍：第一遍已经从题页转录了题目；
现在拿题页图片和答案册原文，逐题核对。**只许抄，不许解题、不许补答案。**

第一遍转录（JSON）：
%s

答案册里这些题号的原文（JSON；没有的题号就是 missing）：
%s

题页：前 %d 张，对应原卷页 %s。
答案册页：后 %d 张，对应答案册页 %s。
逐题核对：
1. 题干、选项、题型是否与题页一致；不一致就按题页改。
2. 答案、解析是否与答案册原文一致；不一致就按答案册原文改。
3. `answer_quote` / `solution_quote` 必须抄答案册原话（或题页上直接印的原话）；
   抄不到就留空。答案册没有这题时，不要自己解。
4. 答案册自己说「错题 / 无有效答案 / 条件矛盾」→ `verdict` 用 `flawed`；
   答案册没有这题 → `missing`；拿不准 → `uncertain`。
5. 返回的题目顺序、题号要和输入一致；不要新增输入里没有的题。
输出 JSON：
{"questions":[{"no":"...", "verdict":"ok|corrected|missing|flawed|uncertain",
 "stem":"...", "options":[{"label":"A","text":"..."}], "type":"...",
 "answer":"...", "answer_quote":"...", "solution":"...", "solution_quote":"...",
 "problems":["..."], "confidence":0.0}]}
只输出 JSON，不要解释，不要代码块。"""


def _verify_batch(questions: list[dict], answer_map: dict[str, dict],
                  pngs: list[bytes], apngs: list[bytes], *,
                  on_usage=None, should_stop=None) -> list[dict]:
    r"""第二遍：把转录题、题页、答案册原文和答案页一起交给模型核对。

    不写库；返回核对后的题目（含 verdict / answer_quote / solution_quote）。
    输出被截断就对半拆——和第一遍一样，不能整份任务因为一页解析太长而丢。
    """
    def stop() -> bool:
        try:
            return bool(should_stop and should_stop())
        except Exception:                       # noqa: BLE001
            return False

    if not questions:
        return []
    qpages = sorted({int(p) for q in questions for p in (q.get("_pages") or [])
                     if 1 <= int(p) <= len(pngs)})
    entries: list[dict] = []
    apages: set[int] = set()
    for q in questions:
        no = _norm_no(q.get("no"))
        e = answer_map.get(no) or {}
        entries.append({"no": no, "answer": e.get("answer") or "",
                        "solution": e.get("solution") or "",
                        "flawed": bool(e.get("flawed")),
                        "note": e.get("note") or ""})
        try:
            ap = int(e.get("page") or 0)
            if 1 <= ap <= len(apngs):
                apages.add(ap)
        except (TypeError, ValueError):
            pass
    apages_sorted = sorted(apages)
    images = ([pngs[p - 1] for p in qpages]
              + [apngs[p - 1] for p in apages_sorted])
    slim = [{"no": q.get("no"), "type": q.get("type"), "stem": q.get("stem"),
             "options": q.get("options") or [], "answer": q.get("answer") or "",
             "solution": q.get("solution") or ""} for q in questions]
    prompt = _VERIFY_HEAD % (
        json.dumps({"questions": slim}, ensure_ascii=False),
        json.dumps(entries, ensure_ascii=False),
        len(qpages), "、".join(str(p) for p in qpages) or "无",
        len(apages_sorted), "、".join(str(p) for p in apages_sorted) or "无")

    last: Exception | None = None
    for attempt in range(3):
        if stop():
            raise Cancelled("已取消")
        try:
            raw = deepseek.chat(prompt, images, timeout=300, json_mode=True,
                                on_usage=on_usage)
            return list(_parse_json(raw).get("questions") or [])
        except ValueError as e:                  # JSON 坏了/截断成半截
            last = e
            if len(questions) > 1:
                mid = len(questions) // 2
                return (_verify_batch(questions[:mid], answer_map, pngs, apngs,
                                      on_usage=on_usage, should_stop=should_stop)
                        + _verify_batch(questions[mid:], answer_map, pngs, apngs,
                                        on_usage=on_usage, should_stop=should_stop))
            time.sleep(1.5 * (attempt + 1))
        except deepseek.AIError as e:
            if "截断" in str(e) and len(questions) > 1:
                mid = len(questions) // 2
                return (_verify_batch(questions[:mid], answer_map, pngs, apngs,
                                      on_usage=on_usage, should_stop=should_stop)
                        + _verify_batch(questions[mid:], answer_map, pngs, apngs,
                                        on_usage=on_usage, should_stop=should_stop))
            if "限流" not in str(e) and "服务端" not in str(e) and "等太久" not in str(e):
                raise
            last = e
            time.sleep(4 * (attempt + 1))
    raise deepseek.AIError(str(last or "答案核对不出来"))


def _verified_ok(item: dict) -> bool:
    """严格闸门：**只有第二遍明确 ok/corrected、答案/解析和原文引用齐全**才入库。"""
    if str(item.get("verdict") or "") not in ("ok", "corrected"):
        return False
    ans = str(item.get("answer") or "").strip()
    sol = str(item.get("solution") or "").strip()
    # 解答题的答案栏规范写法是「见解析」，核对员回空也算通过；解析必须有。
    if not sol or (not ans and str(item.get("type") or "") != "detailed_answer"):
        return False
    if not str(item.get("solution_quote") or "").strip():
        return False
    if str(item.get("type") or "") in ("single_choice", "multi_choice",
                                       "fill_in_blank") \
            and not str(item.get("answer_quote") or "").strip():
        return False
    return True


def _no_key(no: str) -> tuple:
    s = _norm_no(no)
    m = re.match(r"^(\d+)(.*)$", s)
    return (0, int(m.group(1)), m.group(2)) if m else (1, 0, s)


def _coverage(expected: dict[str, dict], transcribed: list[dict],
              verified: list[dict]) -> dict:
    exp = {_norm_no(n) for n in expected}
    tr = {_norm_no(q.get("no")) for q in transcribed if _norm_no(q.get("no"))}
    vf = {_norm_no(q.get("no")) for q in verified if _norm_no(q.get("no"))}
    flawed = sorted((n for n, e in expected.items() if e.get("flawed")), key=_no_key)
    missing = sorted((n for n in exp if n not in tr
                      and not (expected.get(n) or {}).get("flawed")), key=_no_key)
    extra = sorted(tr - exp, key=_no_key) if exp else []
    return {
        "expected": len(exp),
        "transcribed": len(tr),
        "verified": len(vf),
        "missing": missing,
        "flawed": flawed,
        "extra": extra,
        "unverified": sorted(tr - vf, key=_no_key),
    }


def _save_pages(pngs: list[bytes], prefix: str, page_dir: Path) -> list[str]:
    page_dir.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for i, raw in enumerate(pngs, 1):
        name = "%s-%d.png" % (prefix, i)
        (page_dir / name).write_bytes(raw)
        names.append(name)
    return names


def run(data: bytes, *, name: str = "资料.pdf",
        answer_data: bytes | None = None, answer_name: str = "",
        dpi: int = deepseek.DEFAULT_DPI,
        pages_per_call: int | None = None, workers: int | None = None,
        on_progress=None, should_stop=None) -> dict:
    r"""两遍流水线：**第一遍只转录，第二遍核对答案**，只放行核对通过的题。

    * 答案册先读成 `{题号: 答案/解析/页/错题标记}`；
    * 第一遍按页转录题干/选项/图/考点，**不把整份答案册塞进每批 prompt**；
    * 第二遍把「转录 + 题页图 + 答案册原文 + 答案页图」交给核对员，
      返回 ok/corrected/missing/flawed/uncertain；
    * 只有 `ok/corrected`、答案/解析和原文引用都齐全的题才进源材料；
    * 题号覆盖：答案册有、第一遍没转录的有效题会定向补读一次；
      答案册标注错题的进 pending，用户能看到原因，不会被静默丢掉。

    `should_stop()` 返回 True 时不再发新请求；已读到的题作为部分结果返回。
    """
    cfg = deepseek.load()
    per = max(1, min(12, int(pages_per_call or cfg["pages_per_call"])))
    par = max(1, min(4, int(workers or cfg["workers"])))
    if not cfg["api_key"]:
        raise deepseek.AIError("还没填 API Key —— 点「大模型录题」里的设置，填一次就行")

    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
             "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 0}
    usage_lock = threading.Lock()
    calls = [0]

    def add_usage(u: dict) -> None:
        with usage_lock:
            calls[0] += 1
            for k in usage:
                try:
                    usage[k] += int((u or {}).get(k) or 0)
                except (TypeError, ValueError):
                    pass

    def stopped() -> bool:
        try:
            return bool(should_stop and should_stop())
        except Exception:                        # noqa: BLE001
            return False

    if stopped():
        raise Cancelled("已取消")

    def say(done: int, total: int, msg: str) -> None:
        if on_progress:
            try:
                on_progress(done, total, msg)
            except Exception:                    # noqa: BLE001
                pass

    t0 = time.time()
    declared = _page_count(data)
    say(0, declared, "共 %d 页，正在拆页…" % declared)

    def on_page(n: int) -> None:
        if stopped():
            raise Cancelled("已取消")
        if declared and (n % 5 == 0 or n == declared):
            say(0, declared, "正在拆页 %d / %d…" % (n, declared))

    pngs = _render(data, dpi, on_page)
    total = len(pngs)
    if not total:
        raise deepseek.AIError("这份 PDF 里没有页面")
    if stopped():
        raise Cancelled("已取消")

    job = "job-%s" % time.strftime("%Y%m%d-%H%M%S")
    crop_dir = CROP_ROOT / job
    page_dir = crop_dir / "pages"
    try:
        _save_pages(pngs, "q", page_dir)
    except OSError:
        page_dir = None

    # ── 答案册：先读成结构化映射（不是把整份原文塞进每批 prompt）──
    answer_map: dict[str, dict] = {}
    apngs: list[bytes] = []
    answer_pages = 0
    if answer_data:
        apngs = _render(answer_data, dpi)
        answer_pages = len(apngs)
        if apngs:
            if page_dir is not None:
                try:
                    _save_pages(apngs, "a", page_dir)
                except OSError:
                    pass
            say(0, total, "正在读答案册（%d 页）…" % answer_pages)
            answer_map = _read_answers(apngs, per, should_stop=stopped,
                                       on_usage=add_usage)
            if not answer_map:
                say(0, total, "答案册里没读到答案，继续转录…")
    if stopped():
        raise Cancelled("已取消")

    ranges = _ranges(total, per)
    lock = threading.Lock()
    done = [0]
    title = [""]
    results: dict[int, dict] = {}
    cancelled = False

    def one(i: int, pgs: list[int], only: list[str] | None = None) -> dict:
        """第一遍转录：只抄题页；题页上没有答案就留空，不猜。"""
        if stopped():
            raise Cancelled("已取消")
        images = [pngs[p - 1] for p in pgs]
        prompt = _prompt_for(pgs, total, only)
        with lock:
            if only:
                say(done[0], total, "正在补读第 %s 题…" % "、".join(only))
            else:
                say(done[0], total, "正在转录第 %d–%d 页…" % (pgs[0], pgs[-1]))
        last: Exception | None = None
        for attempt in range(3):
            if stopped():
                raise Cancelled("已取消")
            try:
                raw = deepseek.chat(prompt, images, timeout=300, json_mode=True,
                                    on_usage=add_usage)
                return _stamp_pages(_parse_json(raw), pgs)
            except ValueError as e:                  # JSON 坏了：再要一次
                last = e
                prompt = _prompt_for(pgs, total, only) + \
                    "\n\n上一次的回复不是合法 JSON（%s）。这次只输出 JSON 本体。" % str(e)[:80]
                time.sleep(1.5 * (attempt + 1))
            except deepseek.AIError as e:
                if "截断" in str(e) and len(pgs) > 1:
                    left, right = _split_pages(pgs)
                    a = one(i, left, only)
                    b = one(i, right, only)
                    return {"title": a.get("title") or b.get("title"),
                            "questions": list(a.get("questions") or [])
                                         + list(b.get("questions") or [])}
                if "限流" not in str(e) and "服务端" not in str(e) and "等太久" not in str(e):
                    raise
                last = e
                time.sleep(4 * (attempt + 1))
        raise deepseek.AIError(str(last or "调用失败"))

    # ── 第一遍：按批转录 ──
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=par) as pool:
        futs = {pool.submit(one, i, pgs): i for i, pgs in enumerate(ranges)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                d = fut.result()
            except (Cancelled, CancelledError):
                cancelled = True
                for f in futs:
                    f.cancel()
                with lock:
                    say(done[0], total, "正在取消…")
                continue
            except Exception as e:                   # noqa: BLE001
                failures.append("第 %s 页转录失败：%s" % (
                    "、".join(str(p) for p in ranges[i]), str(e)[:120]))
                with lock:
                    say(done[0], total, "有一批没转录成，继续其余页…")
                continue
            with lock:
                results[i] = d
                done[0] += len(ranges[i])
                say(min(done[0], total), total,
                    "已转录 %d / %d 页" % (min(done[0], total), total))
            if stopped():
                cancelled = True
                for f in futs:
                    f.cancel()
    if stopped():
        cancelled = True

    title[0] = ""
    for i in sorted(results):
        t = str(results[i].get("title") or "").strip()
        if t:
            title[0] = t
            break

    if not results and not cancelled:
        raise deepseek.AIError("所有批次都没转录成：%s"
                               % ("；".join(failures[:3]) or "调用失败"))

    # ── 第一遍组装 + 去重（题目还没有答案，先按题干+选项去重）──
    ordered: list[str] = []
    by_key: dict[str, dict] = {}
    for i in sorted(results):
        for item in (results[i].get("questions") or []):
            if not isinstance(item, dict):
                continue
            opts = item.get("options")
            opt_text = "|".join(
                (o.get("text") if isinstance(o, dict) else str(o)) or ""
                for o in (opts if isinstance(opts, list) else []))
            key = hashlib.sha1(
                re.sub(r"\s+", "", str(item.get("stem") or "") + "\x00" + opt_text)
                .encode("utf-8")).hexdigest()
            weight = (len(str(item.get("stem") or "")) + len(opt_text)
                      + len(str(item.get("solution") or "")))
            if key not in by_key:
                by_key[key] = item
                ordered.append(key)
            elif weight > (len(str(by_key[key].get("stem") or ""))
                           + len(str(by_key[key].get("solution") or ""))):
                by_key[key] = item
    transcribed = [by_key[k] for k in ordered]
    if not transcribed and not cancelled:
        raise deepseek.AIError("第一遍没有转录出任何完整题目")

    # ── 题号覆盖：答案册有、第一遍没转录的有效题，定向补读 ──
    tr_nos = {_norm_no(q.get("no")) for q in transcribed}
    if answer_map:
        missing_valid = [n for n, e in answer_map.items()
                         if not e.get("flawed") and n not in tr_nos]
        if missing_valid and not stopped() and total <= 12:
            try:
                say(done[0], total, "答案册有、第一遍缺的题：%s，定向补读一次"
                    % "、".join(missing_valid))
                extra = one(-1, list(range(1, total + 1)), missing_valid)
                for item in (extra.get("questions") or []):
                    if not isinstance(item, dict):
                        continue
                    n = _norm_no(item.get("no"))
                    if n not in missing_valid:
                        continue
                    opts = item.get("options")
                    opt_text = "|".join(
                        (o.get("text") if isinstance(o, dict) else str(o)) or ""
                        for o in (opts if isinstance(opts, list) else []))
                    key = hashlib.sha1(
                        re.sub(r"\s+", "", str(item.get("stem") or "") + "\x00" + opt_text)
                        .encode("utf-8")).hexdigest()
                    if key not in by_key:
                        by_key[key] = item
                        ordered.append(key)
                        tr_nos.add(n)
            except Cancelled:
                raise
            except Exception as e:                   # noqa: BLE001
                failures.append("定向补读失败：%s" % str(e)[:120])
    transcribed = [by_key[k] for k in ordered]

    # ── 第二遍：核对答案；按批核对，未通过/不确定的逐题重核一次 ──
    verified: list[dict] = []
    pending: list[dict] = []
    verifier_failed: list[str] = []
    chunk_size = max(1, min(6, per))
    chunks = [transcribed[i:i + chunk_size]
              for i in range(0, len(transcribed), chunk_size)]
    for ci, chunk in enumerate(chunks):
        if stopped():
            cancelled = True
            break
        say(done[0], total, "正在核对答案（第 %d / %d 批）…" % (ci + 1, len(chunks)))
        vlist: list[dict] = []
        try:
            vlist = _verify_batch(chunk, answer_map, pngs, apngs,
                                  on_usage=add_usage, should_stop=stopped)
        except Cancelled:
            cancelled = True
            break
        except Exception as e:                   # noqa: BLE001
            verifier_failed.append("第 %d 批核对失败：%s" % (ci + 1, str(e)[:120]))
        vmap = {_norm_no(v.get("no")): v for v in vlist if isinstance(v, dict)}
        for q in chunk:
            n = _norm_no(q.get("no"))
            v = vmap.get(n)
            if not v or str(v.get("verdict") or "") not in ("ok", "corrected"):
                # 批核对没通过/不确定：单独再核一次，仍不行才 pending
                if not stopped():
                    try:
                        one_v = _verify_batch([q], answer_map, pngs, apngs,
                                              on_usage=add_usage,
                                              should_stop=stopped)
                        v = one_v[0] if one_v else v
                    except Cancelled:
                        cancelled = True
                        break
                    except Exception as e:           # noqa: BLE001
                        verifier_failed.append("第 %s 题单独核对失败：%s"
                                               % (n, str(e)[:100]))
            if not v:
                pending.append({"no": n, "type": q.get("type"),
                                "reason": "第二遍没有返回核对结果",
                                "verdict": "", "tex": "",
                                "answer_quote": "", "solution_quote": ""})
                continue
            entry = answer_map.get(n) or {}
            merged = dict(q)
            merged.update({k: v.get(k) for k in
                           ("stem", "options", "type", "answer", "answer_quote",
                            "solution", "solution_quote", "verdict", "problems",
                            "confidence") if v.get(k) is not None})
            merged["_pages"] = q.get("_pages") or []
            src = "answer_sheet" if entry and not entry.get("flawed") else "inline"
            merged["answer_source"] = src
            merged["solution_source"] = src
            merged["verified"] = _verified_ok(merged)
            if not merged["verified"]:
                reason = "第二遍未通过"
                if str(v.get("verdict")) == "flawed":
                    reason = "答案册标注错题" + (("：" + str(v.get("note") or entry.get("note") or ""))[:80]
                                             if (v.get("note") or entry.get("note")) else "")
                elif str(v.get("verdict")) == "missing":
                    reason = "答案册没有这道题的答案"
                elif not str(v.get("answer") or "").strip():
                    reason = "缺答案"
                elif not str(v.get("solution") or "").strip():
                    reason = "缺解析"
                elif not str(v.get("solution_quote") or "").strip():
                    reason = "解析没有原文引用"
                elif not str(v.get("answer_quote") or "").strip() \
                        and str(v.get("type")) in ("single_choice", "multi_choice",
                                                   "fill_in_blank"):
                    reason = "答案没有原文引用"
                pending.append({"no": n, "type": merged.get("type"),
                                "reason": reason, "verdict": v.get("verdict") or "",
                                "tex": "", "answer_quote": v.get("answer_quote") or "",
                                "solution_quote": v.get("solution_quote") or "",
                                "problems": v.get("problems") or []})
                continue
            verified.append(merged)

    # 取消时，已经转录但没来得及第二遍核对的题放进 pending，让用户能看到/手工补
    if cancelled:
        v_nos = {_norm_no(q.get("no")) for q in verified}
        p_nos = {_norm_no(p.get("no")) for p in pending}
        for q in transcribed:
            n = _norm_no(q.get("no"))
            if n and n not in v_nos and n not in p_nos:
                pending.append({"no": n, "type": q.get("type"),
                                "reason": "已取消：未完成第二遍核对",
                                "verdict": "cancelled", "tex": "",
                                "answer_quote": "", "solution_quote": ""})

    # 答案册标注错题、第一遍也没转录出来的题，也要让用户看到原因
    if answer_map:
        seen_nos = {_norm_no(q.get("no")) for q in transcribed}
        pending_nos = {p.get("no") for p in pending}
        for n, e in answer_map.items():
            if e.get("flawed") and n not in seen_nos and n not in pending_nos:
                note = str(e.get("note") or "").strip()
                pending.append({"no": n, "type": "",
                                "reason": "答案册标注错题" + (("：" + note[:80]) if note else ""),
                                "verdict": "flawed", "tex": "",
                                "answer_quote": "", "solution_quote": ""})

    # ── 组装源材料；只放核对通过的题 ──
    blocks: list[str] = []
    items: list[dict] = []
    problems: list[str] = []
    pending_items: list[dict] = []
    for q in verified:
        pages = [int(p) for p in (q.get("_pages") or []) if 1 <= int(p) <= len(pngs)]
        try:
            comp, probs = _compose(q, [pngs[p - 1] for p in pages], crop_dir)
        except Exception as e:                   # noqa: BLE001
            problems.append("第 %s 题组装失败（%s），已跳过"
                            % (q.get("no") or "?", str(e)[:60]))
            continue
        problems += probs
        block = len(blocks)
        blocks.append(comp["tex"])
        entry = answer_map.get(_norm_no(q.get("no"))) or {}
        ap = []
        if entry.get("page"):
            ap = [int(entry["page"])]
        src_page = int(q.get("_source_page") or (pages[0] if pages else 0))
        items.append({
            "block": block, "no": comp.get("no") or q.get("no") or "",
            "type": comp["type"], "source_no": comp.get("no") or q.get("no") or "",
            "pages": [src_page] if src_page else pages, "answer_pages": ap,
            "answer": comp["answer"], "answer_quote": comp["answer_quote"],
            "solution_quote": comp["solution_quote"],
            "verdict": comp["verdict"] or q.get("verdict") or "",
            "verified": comp["verified"], "answer_source": comp["answer_source"],
            "solution_source": comp["solution_source"],
            "confidence": comp["confidence"],
            "problems": list(probs) + list(q.get("problems") or []),
            "points": q.get("points") or [], "difficulty": q.get("difficulty") or "",
        })
    for p in pending:
        q = next((x for x in transcribed
                  if _norm_no(x.get("no")) == _norm_no(p.get("no"))), None)
        tex = ""
        if q is not None:
            try:
                comp, _probs = _compose(q, [pngs[int(x) - 1] for x in (q.get("_pages") or [])
                                            if 1 <= int(x) <= len(pngs)], crop_dir)
                tex = comp["tex"]
            except Exception:                    # noqa: BLE001
                tex = ""
        pending_items.append({**p, "tex": tex})
    pending = pending_items
    coverage = _coverage(answer_map, transcribed, verified)
    coverage["uncertain"] = sorted(
        (p.get("no") for p in pending
         if p.get("verdict") in ("", "uncertain") and p.get("no") not in coverage["flawed"]),
        key=_no_key)
    cost_cny = deepseek.cost_cny(cfg["model"], usage)

    if not blocks and not cancelled:
        msg = "第二遍核对后没有可入库的题。"
        if coverage["flawed"]:
            msg += "答案册标注错题：%s；" % "、".join(coverage["flawed"][:5])
        if coverage["missing"]:
            msg += "答案册有、题页没转录出来：%s；" % "、".join(coverage["missing"][:5])
        if coverage["uncertain"]:
            msg += "核对未通过：%s；" % "、".join(coverage["uncertain"][:5])
        if failures:
            msg += "转录失败：%s" % "；".join(failures[:2])
        raise deepseek.AIError(msg)

    tex = ""
    if blocks:
        if title[0]:
            tex += "\\title{%s}\n\n" % title[0]
        tex += "\n\n".join(blocks) + "\n"

    warnings = list(failures) + list(verifier_failed)
    if cancelled:
        warnings.append("任务已取消，已保留核对通过的部分")
    say(total, total,
        "已取消：保留已核对 %d 道题" % len(blocks) if cancelled
        else "读完了：%d 道题通过第二遍核对" % len(blocks))
    return {
        "ok": True, "latex": tex, "title": title[0], "cancelled": cancelled,
        "crop_dir": str(crop_dir) if crop_dir.is_dir() else "",
        "page_dir": str(page_dir) if page_dir is not None and page_dir.is_dir() else "",
        "items": items, "coverage": coverage,
        "pending": pending, "problems": problems, "warnings": warnings,
        "stats": {
            "pages": total, "answer_pages": answer_pages,
            "calls": calls[0], "ok": len(blocks), "pending": len(pending),
            "verified": len(blocks), "failed": len(warnings),
            "cancelled": cancelled,
            "figures": len(list(crop_dir.glob("*.png"))) if crop_dir.is_dir() else 0,
            "seconds": int(time.time() - t0), "model": cfg["model"],
            "usage": usage, "cost_cny": cost_cny,
        },
    }


def cleanup(job_dir: str) -> None:
    """删掉某次任务留下的临时裁图（缓存，随时可删）。"""
    p = Path(job_dir or "")
    try:
        if p.is_dir() and str(p).startswith(str(CROP_ROOT)):
            shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass


# ── 自检（不碰网络、不碰 LaTeX）─────────────────────────────────────

def _selftest() -> int:
    """守四件事：JSON 能不能从脏回复里捞出来、答案怎么归一、
    图占位怎么落、填空/选择题的正文长什么样。

    **一个 DeepSeek 请求都不发**——否则验收就变成"必须先有网有 key"。
    """
    import tempfile
    ok = 0
    bad = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal ok, bad
        if cond:
            ok += 1
            print("  ✓ %s" % name)
        else:
            bad += 1
            print("  ✗ %s %s" % (name, extra))

    # ① JSON 从各种脏回复里捞
    for raw, want in [
        ('{"questions": [{"no": "1"}]}', 1),
        ('```json\n{"questions": [{"no": "1"}, {"no": "2"}]}\n```', 2),
        ('好的，结果如下：\n{"questions": []}\n希望有帮助', 0),
        ('[{"no": "1"}]', 1),
    ]:
        d = _parse_json(raw)
        check("JSON 解析 %r" % raw[:24], len(d["questions"]) == want, str(d))

    # ② 答案归一
    check("答案小写转大写", _norm_answer("c", "single_choice") == "C")
    check("多选排序去重", _norm_answer("B,A,B", "multi_choice") == "AB")
    check("填空答案原样保留", _norm_answer(" 5 ", "fill_in_blank") == "5")

    # ③ 组装：选择题 + 裁剪图
    page = _render(_png_of_triangle(), 150)[0]
    tmp = Path(tempfile.mkdtemp(prefix="amti-ai-test-"))
    item = {
        "no": "1", "type": "single_choice",
        "stem": "则 $A\\cap B=$<<FIG1>>",
        "options": [{"label": "A", "text": "$\\{1\\}$"}, {"label": "B", "text": "$\\{2\\}$"}],
        "answer": "b", "answer_quote": "答案：B",
        "solution": "故选 B。", "solution_quote": "故选 B。",
        "verdict": "ok", "verified": True, "answer_source": "answer_sheet",
        "difficulty": "简单题", "points": ["1.1.1"],
        "figures": [{"kind": "crop", "page": 1, "bbox": [0.1, 0.1, 0.6, 0.6], "width": "5cm"}],
    }
    comp, probs = _compose(item, [page], tmp)
    tex = comp["tex"]
    check("选择题：作答括号由程序加", "\\paren[B]" in tex, tex[:80])
    check("选择题：选项进 choices", "\\begin{choices}" in tex and "\\end{choices}" in tex)
    check("裁剪图：生成了 png", any(tmp.glob("*.png")), str(list(tmp.glob("*"))))
    check("裁剪图：正文里是 includegraphics", "\\includegraphics[width=5cm]" in tex)
    check("裁剪图：没有报问题", not probs, str(probs))
    check("考点：白名单内的留下", '"points": ["1.1.1"]' in tex, tex[:80])
    check("原卷题号写进 meta", '"source_no": "1"' in tex, tex[:100])
    check("核对结果写进 meta", '"verified": true' in tex
          and '"answer_quote": "答案：B"' in tex and comp["verified"],
          tex[:180])
    comp_rep, _ = _compose({
        "type": "detailed_answer", "stem": "向量运算", "answer": "",
        "solution": r"\overrightarrow{AB}=4\overrightarrow{AD}",
        "answer_quote": "", "solution_quote": "略", "verdict": "ok",
        "verified": True,
    }, [], tmp)
    check("解析裸向量自动包 $...$",
          "$\\overrightarrow{AB}$" in comp_rep["tex"]
          and "$\\overrightarrow{AD}$" in comp_rep["tex"],
          comp_rep["tex"][:180])
    tuk, hit = _strip_dangling_tuk("如图，则 $x=1$", False)
    check("无图时删悬空「如图」", hit and "如图" not in tuk, tuk)
    tuk2, hit2 = _strip_dangling_tuk("如图，则 $x=1$", True)
    check("有图时保留「如图」", not hit2 and tuk2 == "如图，则 $x=1$", tuk2)
    ok_item = {"verdict": "ok", "type": "single_choice", "answer": "B",
               "answer_quote": "B", "solution": "略", "solution_quote": "略"}
    check("核对通过：ok + 两侧引用", _verified_ok(ok_item))
    check("核对不通过：缺解析引用",
          not _verified_ok({**ok_item, "solution_quote": ""}))
    check("核对不通过：flawed",
          not _verified_ok({**ok_item, "verdict": "flawed"}))
    check("解答题：见解析 + 解析引用",
          _verified_ok({**ok_item, "type": "detailed_answer",
                        "answer": "见解析", "answer_quote": ""}))
    check("解答题：答案空也按「见解析」放行",
          _verified_ok({**ok_item, "type": "detailed_answer",
                        "answer": "", "answer_quote": ""}))
    cov = _coverage({"1": {"flawed": False}, "2": {"flawed": False},
                     "3": {"flawed": True}},
                    [{"no": "1"}, {"no": "2"}], [{"no": "1"}])
    check("覆盖：错题单列、缺转录/未核对分清",
          cov["expected"] == 3 and cov["flawed"] == ["3"]
          and cov["missing"] == [] and cov["unverified"] == ["2"], str(cov))

    # ④ 填空：两个空、两个答案
    comp2, _ = _compose({
        "type": "fill_in_blank", "stem": "$a=$<<BLANK>>，$b=$<<BLANK>>",
        "answer": "1；2", "solution": "略。", "points": [],
    }, [], tmp)
    check("填空：按顺序填答案",
          "\\fillin[1]" in comp2["tex"] and "\\fillin[2]" in comp2["tex"], comp2["tex"][:120])

    # ⑤ 图缺失：标出来，不静默
    comp3, _ = _compose({"type": "detailed_answer", "stem": "如图<<FIG2>>",
                         "answer": "", "solution": "", "figures": []}, [], tmp)
    check("缺图：正文里能看见「请手工补」", "请手工补" in comp3["tex"], comp3["tex"][:80])

    # ⑥ 单张图片能包成一页
    check("图片 → 一页", len(_render(_png_of_triangle(), 150)) == 1)

    # ⑦ 分页：per=1 不许死循环，重叠页不能变
    #
    # **这条测试本身之前会把 accept 挂死**（per=1 → start 不前进），
    # 所以 _ranges 里现在显式 `per = max(1, ...)`，并且 per=1 不重叠。
    for total, per, want in [
        (1, 1, [[1]]),
        (2, 1, [[1], [2]]),
        (3, 1, [[1], [2], [3]]),
        (3, 2, [[1, 2], [2, 3]]),
        (5, 3, [[1, 2, 3], [3, 4, 5]]),
        (2, 6, [[1, 2]]),
    ]:
        got = _ranges(total, per)
        check("分页 %d 页 / 每批 %d" % (total, per), got == want, str(got))
    check("拆批 4 页保留 1 页重叠",
          _split_pages([1, 2, 3, 4]) == ([1, 2, 3], [3, 4]),
          str(_split_pages([1, 2, 3, 4])))
    check("拆批 2 页退化为逐页", _split_pages([1, 2]) == ([1], [2]),
          str(_split_pages([1, 2])))

    # ⑧ 截断拆分后，图必须按**子批页列表**裁（整份第 4 页是蓝，第 2 页是红）
    import contextlib

    def verify_from_prompt(prompt: str) -> str:
        """自检用的第二遍：从核对 prompt 里取回转录和答案册条目，按规则回一个 JSON。

        **不是模型**；只模拟核对员的"ok/missing/flawed"判定，以及原文引用。
        """
        m1 = re.search(r"第一遍转录（JSON）：\n(\{.*?\})\n\n答案册里", prompt, re.S)
        m2 = re.search(r"答案册里这些题号的原文（JSON；没有的题号就是 missing）：\n(\[.*?\])\n\n题页：", prompt, re.S)
        try:
            qs = (json.loads(m1.group(1)) if m1 else {}).get("questions") or []
            entries = json.loads(m2.group(1)) if m2 else []
        except ValueError:
            qs, entries = [], []
        em = {_norm_no(e.get("no")): e for e in entries if isinstance(e, dict)}
        out = []
        for q in qs:
            if not isinstance(q, dict):
                continue
            no = _norm_no(q.get("no"))
            e = em.get(no) or {}
            flawed = bool(e.get("flawed"))
            ans = str(e.get("answer") or q.get("answer") or "").strip()
            sol = str(e.get("solution") or q.get("solution") or "").strip()
            typ = str(q.get("type") or "")
            if typ == "detailed_answer" and sol and not ans:
                ans = "见解析"
            verdict = "flawed" if flawed else ("ok" if (ans and sol) else "missing")
            out.append({
                **{k: q.get(k) for k in ("no", "type", "stem", "options")},
                "answer": ans, "answer_quote": ans,
                "solution": sol, "solution_quote": sol,
                "verdict": verdict, "problems": [], "confidence": 1.0,
            })
        return json.dumps({"questions": out}, ensure_ascii=False)

    @contextlib.contextmanager
    def fake_ai(chat):
        """假 key + 假 chat + 临时裁图根目录；一个网络请求都不发。"""
        old_load, old_chat, old_sleep = deepseek.load, deepseek.chat, time.sleep
        old_root = globals()["CROP_ROOT"]
        root = Path(tempfile.mkdtemp(prefix="amti-ai-root-"))
        deepseek.load = lambda: {
            "api_key": "selftest", "base_url": "https://example.invalid",
            "model": "fake", "pages_per_call": 6, "workers": 2,
        }

        def wrapped(prompt, images=None, **kw):
            cb = kw.get("on_usage")
            if cb is not None:
                try:
                    cb({"prompt_tokens": 100, "completion_tokens": 20,
                        "total_tokens": 120})
                except Exception:                # noqa: BLE001
                    pass
            if "核对员" in prompt:
                return verify_from_prompt(prompt)
            return chat(prompt, images, **kw)

        deepseek.chat = wrapped
        time.sleep = lambda *_a, **_k: None
        globals()["CROP_ROOT"] = root
        try:
            yield root
        finally:
            deepseek.load, deepseek.chat, time.sleep = old_load, old_chat, old_sleep
            globals()["CROP_ROOT"] = old_root
            shutil.rmtree(root, ignore_errors=True)

    colors = [(0, 0.78, 0), (0.86, 0, 0), (0.86, 0.7, 0), (0, 0, 0.86)]
    doc = fitz.open()
    for c in colors:
        p = doc.new_page(width=595, height=842)
        p.draw_rect(fitz.Rect(60, 60, 240, 240), color=c, fill=c)
    pdf = doc.tobytes()
    doc.close()

    seen: list[list[int]] = []

    def chat_split(prompt, images=None, **kw):
        m = re.search(r"第 ([\d、]+) 页", prompt)
        pgs = [int(x) for x in m.group(1).split("、")] if m else []
        seen.append(pgs)
        if len(pgs) > 2:
            raise deepseek.AIError(
                "这一批输出被截断了（max_tokens 用完）——把「每批页数」调小再试")
        if pgs == [3, 4]:
            # 模型看到的「本批第 2 张」= 整份第 4 页（蓝）
            return json.dumps({"title": "拆批测试", "questions": [{
                "no": "1", "type": "detailed_answer", "stem": "求阴影面积。",
                "answer": "", "answer_quote": "", "solution": "略。",
                "figures": [{"kind": "crop", "page": 2,
                             "bbox": [0.08, 0.05, 0.45, 0.32], "width": "6cm"}],
            }]})
        return json.dumps({"questions": []})

    with fake_ai(chat_split):
        res = run(pdf, pages_per_call=4, workers=1)
        pngs = list(Path(res["crop_dir"]).glob("*.png"))
        rgb = (0, 0, 0)
        if pngs:
            im = Image.open(pngs[0]).convert("RGB")
            rgb = im.getpixel((im.width // 2, im.height // 2))
        check("拆批后图裁对页（蓝，不是红）",
              bool(pngs) and rgb[2] > 150 and rgb[0] < 100, str(rgb))
        check("拆批后仍能出题", res["stats"]["ok"] == 1, json.dumps(res["stats"]))
        check("拆批后原页图已保存",
              bool(list(Path(res["page_dir"]).glob("q-*.png"))), res["page_dir"])
        check("条目带原页/核对结果",
              bool(res["items"]) and res["items"][0]["pages"] == [3]
              and res["items"][0]["verified"],
              json.dumps(res["items"][:1], ensure_ascii=False))
        check("usage/费用已记账",
              (res["stats"]["usage"].get("total_tokens") or 0) > 0
              and res["stats"]["cost_cny"] > 0,
              json.dumps(res["stats"], ensure_ascii=False))
    check("截断拆分确实发生过", [1, 2, 3, 4] in seen and [3, 4] in seen, str(seen))

    # ⑨ 答案册：截断对半拆 + 限流重试
    ans_calls: list[list[int]] = []

    def chat_ans(prompt, images=None, **kw):
        m = re.search(r"答案册的第 ([\d、]+) 页", prompt)
        pgs = [int(x) for x in m.group(1).split("、")] if m else []
        ans_calls.append(pgs)
        if len(pgs) > 1:
            raise deepseek.AIError(
                "这一批输出被截断了（max_tokens 用完）——把「每批页数」调小再试")
        return json.dumps({"questions": [{
            "no": str(pgs[0]), "answer": "答案%s" % pgs[0], "solution": "解析。",
        }]})

    with fake_ai(chat_ans):
        ans_items = list(_read_answers([b"p1", b"p2"], 2).values())
    check("答案册截断后对半拆",
          len(ans_items) == 2 and {x["no"] for x in ans_items} == {"1", "2"},
          str(ans_items))
    check("答案册截断拆分确实发生", [1, 2] in ans_calls and [1] in ans_calls,
          str(ans_calls))

    hits = {"n": 0}

    def chat_429(prompt, images=None, **kw):
        hits["n"] += 1
        if hits["n"] == 1:
            raise deepseek.AIError(
                "请求太频繁被限流 —— 等十几秒再试（或把「并发」调成 1）")
        return json.dumps({"questions": [{
            "no": "1", "answer": "A", "solution": "略。",
        }]})

    with fake_ai(chat_429):
        one_item = list(_read_answers([b"p1"], 1).values())
    check("答案册限流会重试", hits["n"] == 2 and len(one_item) == 1,
          "calls=%s items=%s" % (hits["n"], one_item))

    # ⑩ 同题干、不同选项不能再被去重吃掉
    def q_choice(no: str, d: str) -> dict:
        return {
            "no": no, "type": "single_choice", "stem": "下列说法正确的是",
            "options": [{"label": "A", "text": "1"}, {"label": "B", "text": "2"},
                        {"label": "C", "text": "3"}, {"label": "D", "text": d}],
            "answer": "D", "answer_quote": "D", "solution": "略。",
        }

    def chat_dup(prompt, images=None, **kw):
        return json.dumps({"title": "T", "questions": [
            q_choice("1", "4"), q_choice("2", "5")]})

    with fake_ai(chat_dup):
        dup = run(_png_of_triangle(), pages_per_call=1, workers=1)
    check("同题干不同选项不被去重吃掉", dup["stats"]["ok"] == 2,
          json.dumps(dup["stats"], ensure_ascii=False))

    # ⑪ 坏 figures / 字符串 options：不崩整份，且能救回来
    def chat_badfig(prompt, images=None, **kw):
        return json.dumps({"title": "T", "questions": [{
            "no": "1", "type": "single_choice", "stem": "如图<<FIG1>>",
            "options": [{"label": "A", "text": "1"}, {"label": "B", "text": "2"}],
            "answer": "A", "answer_quote": "A", "solution": "略。",
            "figures": "not-a-list",
        }]})

    with fake_ai(chat_badfig):
        badfig = run(_png_of_triangle(), pages_per_call=1, workers=1)
    check("坏 figures 不崩整份", badfig["stats"]["ok"] == 1,
          json.dumps(badfig["stats"], ensure_ascii=False))
    check("坏 figures 有可见提示", any("figures" in p for p in badfig["problems"]),
          str(badfig["problems"]))

    def chat_stropts(prompt, images=None, **kw):
        return json.dumps({"title": "T", "questions": [{
            "no": "1", "type": "single_choice", "stem": "下列正确的是",
            "options": ["A. 5", "B. 6", "C. 7"], "answer": "B",
            "answer_quote": "B", "solution": "略。",
        }]})

    with fake_ai(chat_stropts):
        stropts = run(_png_of_triangle(), pages_per_call=1, workers=1)
    check("字符串 options 不再整组丢",
          "\\begin{choices}" in stropts["latex"] and "\\item 5" in stropts["latex"],
          stropts["latex"][:120])

    # ⑫ 题型写进 meta：多选只有一个正确项时不能被答案字母数重判成单选
    comp_m, _ = _compose({
        "no": "1", "type": "multi_choice", "stem": "下列正确的是",
        "options": [{"label": "A", "text": "1"}, {"label": "B", "text": "2"},
                    {"label": "C", "text": "3"}, {"label": "D", "text": "4"}],
        "answer": "A", "answer_quote": "A", "solution": "略。",
    }, [], tmp)
    from amti import ingest as _ing
    parsed_m = _ing.parse_source(comp_m["tex"], book="测试卷", label="自检", year=2026)
    check("题型落库不被答案重判",
          parsed_m["questions"] and parsed_m["questions"][0].type == "multi_choice",
          parsed_m["questions"][0].type if parsed_m["questions"] else "no q")

    over_m = _ing.parse_source(comp_m["tex"], book="测试卷", label="自检", year=2026,
                               items=[{"block": 0, "qtype": "single_choice"}])
    check("手改题型不被 meta 翻回去",
          over_m["questions"] and over_m["questions"][0].type == "single_choice"
          and over_m["questions"][0].meta.get("type") == "single_choice",
          over_m["questions"][0].meta.get("type") if over_m["questions"] else "no q")

    # ⑬ 「请补图」占位必须在结构闸被拦下
    from amti import latex_ir as _lir
    q_marker = _lir.parse_question(
        "\\begin{question}如图【图：缺失，请手工补】\\end{question}")
    marker_errs = _ing._structure_errors([q_marker]) if q_marker else []
    check("缺图占位被结构闸拦下",
          any("请补图" in e["reason"] for e in marker_errs), str(marker_errs))

    # ⑭ 单批失败保留已读题；标题取第一页，不取先跑完的那批
    def valid_detail(no: str) -> dict:
        return {"no": no, "type": "detailed_answer", "stem": "题 %s" % no,
                "answer": "", "answer_quote": "", "solution": "略。"}

    def chat_part(prompt, images=None, **kw):
        m = re.search(r"第 ([\d、]+) 页", prompt)
        pgs = [int(x) for x in m.group(1).split("、")] if m else []
        if pgs and pgs[0] == 1:
            return json.dumps({"title": "第一页卷名", "questions": [valid_detail("1")]})
        raise deepseek.AIError("API Key 不对或已失效 —— 去控制台重新复制")

    with fake_ai(chat_part):
        part = run(pdf, pages_per_call=2, workers=1)
    check("单批失败保留已读题",
          part["stats"]["ok"] == 1 and len(part["warnings"]) >= 1,
          json.dumps({"ok": part["stats"]["ok"], "warn": part["warnings"]},
                     ensure_ascii=False))

    gate = threading.Event()

    def chat_title(prompt, images=None, **kw):
        m = re.search(r"第 ([\d、]+) 页", prompt)
        pgs = [int(x) for x in m.group(1).split("、")] if m else []
        if pgs and pgs[0] == 1:
            gate.wait(1.0)
            return json.dumps({"title": "第一页卷名", "questions": [valid_detail("1")]})
        gate.set()
        return json.dumps({"title": "第三页页眉", "questions": []})

    with fake_ai(chat_title):
        titled = run(pdf, pages_per_call=2, workers=2)
    check("标题取第一页，不取先跑完的批", titled["title"] == "第一页卷名",
          repr(titled["title"]))

    # ⑯ 答案册结构化映射 + 覆盖 + 第二遍核对（页/引用/错题/费用）
    def chat_map(prompt, images=None, **kw):
        if "本批是答案册" in prompt:
            return json.dumps({"title": "答案映射测试", "questions": [
                {"no": "1", "answer": "B", "solution": "解析一。", "page": 1},
                {"no": "2", "answer": "A", "solution": "解析二。", "page": 1},
                {"no": "3", "answer": "", "solution": "", "page": 1,
                 "flawed": True, "note": "原题条件矛盾"},
            ]}, ensure_ascii=False)
        return json.dumps({"title": "答案映射测试", "questions": [
            q_choice("1", "4"), q_choice("2", "5"),
        ]}, ensure_ascii=False)

    with fake_ai(chat_map):
        amap = _read_answers([_png_of_triangle()], 1)
        mapped = run(_png_of_triangle(), answer_data=_png_of_triangle(),
                     pages_per_call=6, workers=1)
        page_files = sorted(x.name for x in Path(mapped["page_dir"]).glob("*.png")) \
            if mapped.get("page_dir") else []
    check("答案册映射：页号 / 错题 / 原话",
          amap.get("1", {}).get("page") == 1
          and amap.get("3", {}).get("flawed")
          and "条件矛盾" in amap.get("3", {}).get("note", ""), str(amap))
    check("覆盖：3 应有 / 2 转录 / 2 核对 / 3 是错题",
          mapped["coverage"]["expected"] == 3
          and mapped["coverage"]["transcribed"] == 2
          and mapped["coverage"]["verified"] == 2
          and mapped["coverage"]["flawed"] == ["3"]
          and mapped["coverage"]["missing"] == []
          and mapped["stats"]["ok"] == 2,
          json.dumps({"coverage": mapped.get("coverage"),
                      "stats": mapped.get("stats")}, ensure_ascii=False))
    check("错题进 pending 且带原因",
          any(p.get("no") == "3" and "错题" in str(p.get("reason"))
              for p in mapped["pending"]),
          json.dumps(mapped.get("pending"), ensure_ascii=False))
    check("条目带答案页 / 答案出处",
          bool(mapped["items"])
          and mapped["items"][0]["answer_pages"] == [1]
          and mapped["items"][0]["answer_quote"] == "B"
          and mapped["items"][0]["verified"],
          json.dumps(mapped["items"][:1], ensure_ascii=False))
    check("原页 + 答案页图都已保存",
          "q-1.png" in page_files and "a-1.png" in page_files, str(page_files))
    check("映射测试也有 usage/费用",
          (mapped["stats"]["usage"].get("total_tokens") or 0) > 0
          and mapped["stats"]["cost_cny"] > 0,
          json.dumps(mapped["stats"], ensure_ascii=False))

    # ⑮ 取消：不再发新请求；已读到的批次保留
    never_calls: list[int] = []

    def chat_never(prompt, images=None, **kw):
        never_calls.append(1)
        return json.dumps({"questions": []})

    with fake_ai(chat_never):
        try:
            run(_png_of_triangle(), pages_per_call=1, workers=1,
                should_stop=lambda: True)
            stopped_before = False
        except Cancelled:
            stopped_before = True
    check("取消：还没开始就不发请求", stopped_before and not never_calls,
          "stopped=%s calls=%s" % (stopped_before, len(never_calls)))

    cancel_calls: list[int] = []

    def chat_cancel(prompt, images=None, **kw):
        cancel_calls.append(1)
        return json.dumps({"title": "取消测试", "questions": [valid_detail("1")]})

    with fake_ai(chat_cancel):
        part_cancel = run(pdf, pages_per_call=1, workers=1,
                          should_stop=lambda: len(cancel_calls) >= 1)
    check("取消：保留已读但未核对的题",
          part_cancel.get("cancelled") is True
          and part_cancel["stats"]["ok"] == 0
          and part_cancel["coverage"]["transcribed"] >= 1
          and any(p.get("verdict") == "cancelled" for p in part_cancel["pending"]),
          json.dumps({"cancelled": part_cancel.get("cancelled"),
                      "ok": part_cancel["stats"]["ok"],
                      "coverage": part_cancel.get("coverage"),
                      "pending": part_cancel.get("pending")},
                     ensure_ascii=False))

    try:
        shutil.rmtree(tmp, ignore_errors=True)
    except OSError:
        pass
    print("\n  %d 项通过，%d 项失败" % (ok, bad))
    return 1 if bad else 0


def _png_of_triangle() -> bytes:
    """自检用：一张白底、画了个三角的 PNG。"""
    from PIL import ImageDraw
    im = Image.new("RGB", (600, 400), (255, 255, 255))
    ImageDraw.Draw(im).line([(60, 320), (300, 320), (60, 120), (60, 320)],
                            fill=(0, 0, 0), width=3)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
    raise SystemExit(0)
