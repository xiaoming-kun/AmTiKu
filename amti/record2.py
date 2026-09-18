#!/usr/bin/env python3
r"""录题 v2：**版面优先 + 模型只做决策 + 校验闸门**。

     PDF ──pagegeom(L0)──▶ 页图 ──ocr(dots.ocr)──▶ 整页文本
          ──27B（**按卷**切题/配对）──▶ 行号区间 + 原文引用
          ──校验闸门──▶ 成品（干净、可溯源）/ 拒收 / 待复核

跟 v1（`record.py`）的根本差别：**v1 是"整页 OCR 一次，再拿正则猜结构"；
v2 是"OCR 只管认字，结构由模型按行号指认，内容一律从原文取"。**
台账 D01–D12 里绝大多数缺陷都出在"猜结构"上。

三条规矩（用户定的，写死在代码里，**不交给模型判**）：

1. **题型按题号定**：1-8 单选、9-11 多选、12-14 填空、15-19 解答。
2. **带图题、带表题一律不录正文**，但**每一道都登记原卷位置**。
   ⚠️ 文字信号（「如图/图象」）**只能当粗筛，不能当判据**——实测纯代数题
   （「图象过点(4,16)」）也会命中。所以粗筛命中的进「待复核」，**先照录**，
   等复核（27B 看图 / 版面检测）有结论再决定，**不许自动跳题**。
3. **题目 ↔ 答案 ↔ 解析一一对应**；没有解析写「解析无」。

两阶段跑（内存不够两个模型同时驻留）：

    python3 -m amti.record2 scan  <一场考试目录>     # 只开 OCR 服务
    python3 -m amti.record2 struct <一场考试目录>    # 只开 27B
    python3 -m amti.record2 run   <一场考试目录>     # 两个都开着时一次跑完
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from . import normalize as N
from . import ocr
from . import pagegeom as G
from . import record as R
from .schema import Option, Question

# ── 规矩：题号 → 题型（用户 2026-09-18 定）──────────────────────────
BY_NO: dict[int, str] = {}
for _i in range(1, 9):
    BY_NO[_i] = "单选"
for _i in range(9, 12):
    BY_NO[_i] = "多选"
for _i in range(12, 15):
    BY_NO[_i] = "填空"
for _i in range(15, 20):
    BY_NO[_i] = "解答"
TYPE_EN = {"单选": "single_choice", "多选": "multi_choice",
           "填空": "fill_in_blank", "解答": "detailed_answer"}

# 粗筛（**不是判据**）：题干提到这些词才可能是图题
FIG_WORD = re.compile(
    r"如图|图中|图象|图像|图形|图所示|如下图|右图|左图|三视图|直观图"
    r"|程序框图|散点图|茎叶图|频率分布直方图|统计图|条形图|扇形图|折线图")
TABLE_WORD = re.compile(r"下表|列联表|统计表|表格|频数分布表|临界值表")

# 清洗用（**只在这里出现一次**，别再散落到别处）
SCORE_HEAD = re.compile(
    r"^\s*(?:[（(]\s*(?:本小题|本题)?\s*(?:满分\s*)?\d{1,3}\s*分\s*[）)]"
    r"|(?:本小题|本题)\s*(?:满分\s*)?\d{1,3}\s*分|满分\s*\d{1,3}\s*分)\s*")
FOOT = re.compile(r"第\s*\d{1,3}\s*页(?:\s*共\s*\d{1,3}\s*页)?")
# 卷面印刷坏字当题号：`f1`、`I`、`|`… **后面必须跟空格、空格后是中文或公式**，
# 才认定是题号。要求空格是关键——`f(x)=…` 这种正常开头没有空格，不会被误剪。
# 末了的 `(?:\s*[0-9]{1,2})?` 是为了 `f 1 已知函数` 这种——OCR 有时在
# 坏字母和数字之间插空格。第一次没写这段，只剪掉了 `f`，产物里留了个孤零零的 1。
BROKEN_HEAD = re.compile(
    r"^\s*[fFlI|£¥1]{1,3}(?:\s*[0-9]{1,2})?\s+(?=[\u4e00-\u9fa5$\\])")
OPT_SPLIT = re.compile(r"(?<![A-Za-z0-9])[ABCD]\s*[.．、]\s*")
# 版面家具（不是题目）：小节标题、卷抬头、答题说明
FURNITURE = re.compile(
    r"^\s*#|^\s*[一二三四五六]\s*[、.．]|^第\s*[ⅠⅡⅢIVX]+\s*卷"
    r"|本试卷分|满分\s*\d+\s*分|考试时间|请在答题卡|全部选对|部分选对|有选错"
    r"|答题前|准考证|贴条形码|超出黑色矩形边框|请在各题目的答题区域内作答")
ANSWER_IN_SOL = re.compile(r"故选\s*[:：]?\s*([A-D]{1,4})")

SYS_ASK = """你在给数学题库做**切题**。输入是一整份试卷的 OCR 文本，每行前面有行号，
页与页之间有一行 `=== 第N页 ===`（那一行没有行号，不属于任何题）。

**只判断每道题的边界**，不要改写、补全、解答或纠正原文。

只输出一个 JSON 对象（不要代码块、不要解释）：
{"questions":[{"n":1,"start":5,"end":12,"options":{"A":7,"B":8,"C":9,"D":10},
  "quote":"已知全集为U, 若B∩(C_UA)=∅"}]}

* start/end：**整份卷子连续编号**的行号（含两端），题干和选项都要包进去。
  一道题如果**跨页**（题在某页末尾、选项在下页开头），start/end 要**跨过页标记**，不要切断。
* options：选项字母 → 行号；一行里并排几个选项就都指向那一行；定位不到给 {}，不要编。
* quote：从原文**逐字**摘 10-25 字作为题头，改一个字就算错。
* 考试说明、页脚、答题卡提示、小节标题**都不是题目**。
* 按题号（1~19）给全，**不要漏、不要合并**。
"""

SYS_ANS = """你在给数学题库做**答案与解析的配对**。输入是一整份**答案卷**的 OCR 文本，
每行前面有行号，页与页之间有 `=== 第N页 ===`（没有行号）。

只输出一个 JSON 对象（不要代码块、不要解释）：
{"items":[{"n":15,"answer":"60","start":12,"end":30,"quote":"由正弦定理得"}]}

* n：题号（1~19）。
* answer：这道题的**答案本身**，要短——填空题就是那个值（如 `60`、`√3`），
  选择题就是字母（如 `A`、`CD`）。**答案就是解析开头那串字母/数字时也要单独摘出来。**
  解答题（15~19）没有单一答案就给 ""。找不到明确答案也给 ""，不要拿整段解析充数。
* start/end：这道题的**解析**占的行号（含两端）；跨页要跨过页标记。
* quote：从原文**逐字**摘 10-25 字作为这道题的开头，改一个字就算错。
* 按题号给全，**不要漏、不要合并**。
"""


# ── 纯函数（自检覆盖）────────────────────────────────────────────────
def norm(s: str) -> str:
    r"""归一化到可比对的形式（去空白、`$`、反斜杠、花括号）。"""
    return re.sub(r"[\s$\\{}]", "", s or "")


def cut_before_quote(text: str, quote: str) -> tuple[str, str]:
    r"""用**已校验的引用**当锚，剪掉题干开头卷面印坏的题号。返回 `(新文本, 剪掉的)`。

    ⚠️ 用引用而不用正则：引用是逐字核对过、必然在原文里的，
    拿它当锚**不会误剪正文**。`BROKEN_HEAD` 只是引用不可用时的兜底。
    """
    q = norm(quote)
    if len(q) < 6 or not text:
        return text, ""
    lines = text.splitlines()
    head = lines[0]
    k = norm(head).find(q[:8])
    if k <= 0 or k > 8:
        return text, ""
    # 找"扁平化后第 k 个字符"在**原串**里的下标。
    # ⚠️ 是 `k + 1` 不是 `k`：`cnt` 从 1 开始数，而 `k` 是 0 基下标。
    # 写成 `k` 会少剪一个字符——实测把 `f1 已知函数…` 剪成了 `1 已知函数…`，
    # 日志却显示"剪坏字 f"（因为它确实只剪了 f）。
    cnt, cut = 0, -1
    for i, ch in enumerate(head):
        if norm(ch):
            cnt += 1
        if cnt == k + 1:
            cut = i
            break
    if cut <= 0:
        return text, ""
    lines[0] = head[cut:]
    return "\n".join(lines), head[:cut]


def split_stem_options(lines: list[str]) -> tuple[str, dict]:
    r"""段落 → `(题干, {A: 文本, …})`。

    **一行里并排四个选项**（`A. 1  B. 2  C. 3  D. 4`）是常态，必须拆开——
    v1 的"数行首有几个 A."把 4 个选项数成 1 个，我把这个错误又犯过一次。
    """
    stem_lines: list[str] = []
    opts: dict[str, str] = {}
    for ln in lines:
        hits = list(OPT_SPLIT.finditer(ln))
        if len(hits) >= 2:
            head = ln[:hits[0].start()].strip()
            if head:
                stem_lines.append(head)
            for k, m in enumerate(hits):
                end = hits[k + 1].start() if k + 1 < len(hits) else len(ln)
                opts[m.group(0)[0]] = ln[m.end():end].strip()
        elif len(hits) == 1 and hits[0].start() <= 2:
            opts[hits[0].group(0)[0]] = ln[hits[0].end():].strip()
        else:
            stem_lines.append(ln)
    return "\n".join(stem_lines).strip(), opts


def clean_fields(stem: str, solution: str, *, qtype: str, opts: dict,
                 quote: str = "") -> tuple[str, str, dict, list[str]]:
    r"""清洗：去题号 → 去分值 → 剪卷面坏字 → 补缺失选项 → fixup。

    ⚠️ **顺序不能反**：`fixup` 必须在所有"剪"的动作**之后**跑。
    写反过一次——日志里明明写着「剪掉卷面坏字 f1」，产物里那个 `f1` 还在，
    因为 `fixup` 的结果是在剪之前算好、后面一直用的是它。
    """
    notes: list[str] = []
    s = re.sub(r"^\s*\d{1,2}\s*[.．、]\s*", "", stem or "")
    s2 = SCORE_HEAD.sub("", s)
    if s2 != s:
        notes.append("去分值")
    s, cut = cut_before_quote(s2, quote)
    if cut:
        notes.append("剪坏字 %r" % cut.strip())
    else:
        m = BROKEN_HEAD.match(s)
        if m:
            notes.append("剪坏字 %r" % m.group(0).strip())
            s = s[m.end():]
    # 选项标签补全：卷面把 `A.` 印成认不出的符号时，OCR 只能读到 B/C/D
    # （A10 第 11 题原图印的是个「£/匚」样的坏字）。**这不是重扫能解决的——
    # 信息在图上就不存在**，只能靠结构推断：选择题必是 A、B、C、D 四个。
    if qtype in ("single_choice", "multi_choice") and \
            set(opts) == {"B", "C", "D"}:
        tail = [x for x in s.splitlines() if x.strip()]
        if len(tail) >= 2 and not tail[-1].rstrip().endswith(("（ ）", "( )", "（）")):
            opts = dict(opts)
            opts["A"] = re.sub(r"^[^A-Da-d]{1,3}\s*", "", tail[-1]).strip()
            s = "\n".join(tail[:-1])
            notes.append("补回 A 选项")
    stem2 = R.fixup(s)
    sol2 = R.fixup(FOOT.sub("", solution or ""))
    if stem2 != s:
        notes.append("LaTeX修复")
    if sol2 != (solution or ""):
        notes.append("解析去页脚")
    return stem2, sol2, opts, notes


def gate(qtype: str, stem: str, opts: dict, answer: str,
         solution: str) -> list[str]:
    r"""校验闸门：**不过就拒收**，不静默入库。返回问题清单（空 = 通过）。"""
    why: list[str] = []
    if not (stem or "").strip():
        why.append("题干为空")
    # 选择题**必须四个选项 A–D**。写成"少于 2 个"会放过"少了 A 选项"这种
    # 真缺陷——A10 第 11 题就是这么漏过去的。
    if qtype in ("single_choice", "multi_choice") and len(opts) != 4:
        why.append("选项 %d 个（应为 4）" % len(opts))
    if qtype in ("single_choice", "multi_choice", "fill_in_blank") and \
            len((answer or "").strip()) > 40:
        why.append("客观题答案 %d 字（像整段解析）" % len(answer.strip()))
    if qtype in ("single_choice", "multi_choice") and answer and \
            not re.fullmatch(r"[A-D]{1,4}", answer.strip()):
        why.append("选择题答案是 %r（应为字母）" % answer[:12])
    for txt, tag in ((stem, "题干"), (solution, "解析")):
        if (txt or "").count("$") % 2:
            why.append("%s `$` 不成对" % tag)
        if re.search(r"(?<!\\)%", txt or ""):
            why.append("%s 有裸 %%（会注释掉后面）" % tag)
        if FURNITURE.search(txt or ""):
            why.append("%s 里混着版面家具" % tag)
        if FOOT.search(txt or ""):
            why.append("%s 里还有页脚" % tag)
    return why


def covered_pages(lines: list[tuple[int, str, int]], rng) -> list[int]:
    """某道题的行区间覆盖了哪几页（登记位置要用）。"""
    s, e = rng
    return sorted({p for n, _t, p in lines if isinstance(s, int)
                   and isinstance(e, int) and s <= n <= e})


# ── 带模型/文件的部分 ───────────────────────────────────────────────
def _post(url: str, model: str, msgs: list, *, maxtok: int,
          extra: dict | None = None, timeout: int = 3600) -> dict:
    body = {"model": model, "messages": msgs, "temperature": 0.0,
            "max_tokens": maxtok}
    body.update(extra or {})
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def grab_json(s: str):
    """抠 JSON：扛住 ```围栏、前后废话、以及被 max_tokens 截断。"""
    if not s:
        return None
    s = re.sub(r"^\s*```(?:json)?|```\s*$", "", s.strip(), flags=re.M)
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None
    body = m.group(0)
    for cand in (body, body.rstrip().rstrip(",") + "}]}"):
        try:
            return json.loads(cand)
        except ValueError:
            pass
    for key in ("questions", "items"):
        m2 = re.search(r'"%s"\s*:\s*\[(.*)' % key, body, re.S)
        if m2:
            got = []
            for o in re.findall(r"\{[^{}]*\}", m2.group(1)):
                try:
                    got.append(json.loads(o))
                except ValueError:
                    pass
            if got:
                return {key: got}
    return None


def v2_dir(pdf: Path) -> Path:
    """v2 的缓存目录。**跟 v1 的 `pages/`、`scan/` 分开**，免得互相踩。"""
    return R.WORK / pdf.stem / "v2"


def scan_pdf(pdf: Path, *, force: bool = False) -> list[dict]:
    r"""一份 PDF → 每页文本（**按页**）。结果落在 `v2/txt/`，可续跑。"""
    d = v2_dir(pdf)
    (d / "txt").mkdir(parents=True, exist_ok=True)
    imgs = sorted((R.WORK / pdf.stem / "pages").glob("p???.png"))
    if not imgs:
        imgs = R.pages_of(pdf, R.WORK / pdf.stem / "pages")
    pages: list[Path] = []
    for p in imgs:
        pages += G.split_spread(p, d / "pages")
    rows = []
    for i, img in enumerate(pages, 1):
        dst = d / "txt" / ("p%02d_%s.txt" % (i, img.stem))
        if dst.exists() and not force:
            t = dst.read_text(encoding="utf-8")
        else:
            t = ocr.ocr_image(img)
            dst.write_text(t, encoding="utf-8")
        rows.append({"page": i, "img": str(img), "txt": str(dst), "chars": len(t)})
    (d / "pages.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    return rows


def build_doc(rows: list[dict]) -> tuple[str, list[tuple[int, str, int]]]:
    r"""多页文本 → **连续行号的整卷文本**（页标记不占行号）。

    **跨页问题就解决在这里**：题目在页尾、选项在下页开头时，
    模型看到的是连续文本，start/end 自然跨过页标记，不会把选项切掉。
    """
    lines: list[tuple[int, str, int]] = []
    out = []
    for m in rows:
        out.append("=== 第%d页 ===" % m["page"])
        for ln in Path(m["txt"]).read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            lines.append((len(lines) + 1, ln, m["page"]))
            out.append("%3d| %s" % (lines[-1][0], ln))
    return "\n".join(out), lines


def structure(rows: list[dict], role: str, *, save: Path | None = None) -> dict:
    r"""整卷文本 → 模型给的题块/答案块（**带引用，供校验**）。"""
    doc, lines = build_doc(rows)
    d = _post(R.API, R.MODEL,
              [{"role": "system", "content": SYS_ASK if role == "试卷" else SYS_ANS},
               {"role": "user", "content": doc}],
              maxtok=8000, extra={"reasoning_effort": "none"})
    raw = d["choices"][0]["message"].get("content") or ""
    key = "questions" if role == "试卷" else "items"
    items = (grab_json(raw) or {}).get(key) or []
    flat = norm("\n".join(t for _n, t, _p in lines))
    for it in items:
        it["_引用对"] = bool(norm(it.get("quote") or "")) and norm(it["quote"]) in flat
    res = {"role": role, "items": items, "lines": lines,
           "usage": d.get("usage") or {},
           "finish": d["choices"][0].get("finish_reason"), "raw": raw}
    if save:
        save.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def assemble(st_q: dict, st_a: dict, label: str) -> dict:
    r"""题块 + 答案块 → 成品（清洗 + 闸门 + 溯源）。"""
    lines_q = st_q["lines"]
    idx = {n: (t, p) for n, t, p in lines_q}
    idx_a = {n: t for n, t, _p in st_a["lines"]}
    ans_by_n = {}
    for a in st_a["items"]:
        try:
            ans_by_n[int(a.get("n"))] = a
        except (TypeError, ValueError):
            continue
    book, reject, pending, covered = [], [], [], set()
    for q in sorted(st_q["items"], key=lambda x: int(x.get("n") or 0)):
        try:
            n = int(q["n"])
        except (TypeError, ValueError):
            continue
        s, e = q.get("start"), q.get("end")
        good = isinstance(s, int) and isinstance(e, int) and s <= e
        seg = [idx[i][0] for i in range(s, e + 1) if i in idx] if good else []
        if good:
            covered.update(range(s, e + 1))
        pages = covered_pages(lines_q, (s, e))
        stem_raw, opts = split_stem_options(seg)
        a = ans_by_n.get(n) or {}
        asol = []
        if isinstance(a.get("start"), int) and isinstance(a.get("end"), int):
            asol = [idx_a[i] for i in range(a["start"], a["end"] + 1) if i in idx_a]
        qtype = TYPE_EN.get(BY_NO.get(n, ""), "")
        stem, sol, opts, notes = clean_fields(
            stem_raw, "\n".join(asol), qtype=qtype, opts=opts, quote=q.get("quote") or "")
        answer = (a.get("answer") or "").strip()
        # 答案回收：解析里写着「故选 CD」而答案栏是空的（选择题 25.7% 缺答案
        # 就是这条路径没生效）。**只认「故选」后面那一段**，不拿正则从整段抠字母
        # ——`OBB_1O_1` 那种 LaTeX 变量名到处都有，抠出来的"答案"全是错的（台账 D03）。
        if not answer and qtype in ("single_choice", "multi_choice"):
            m = ANSWER_IN_SOL.search(sol)
            if m:
                answer = m.group(1)
                notes.append("从「故选」回收答案")
        why = gate(qtype, stem, opts, answer, sol)
        rec = {"题号": n, "题型": qtype, "页码": pages, "行": [s, e],
               "题干": stem, "选项": opts, "答案": answer, "解析": sol,
               "清洗": notes, "引用对": bool(q.get("_引用对")),
               "答案引用对": bool(a.get("_引用对")),
               "粗筛图": bool(FIG_WORD.search(stem)),
               "粗筛表": bool(TABLE_WORD.search(stem))}
        if why:
            rec["原因"] = why
            reject.append(rec)
            continue
        if rec["粗筛图"] or rec["粗筛表"]:
            # **文字信号只当粗筛**：实测纯代数题（「图象过点(4,16)」）也会命中。
            # 按"疑似就跳过"会把好题丢掉 → 标待复核、**先照录**。
            pending.append({"题号": n, "粗筛命中": "图" if rec["粗筛图"] else "表",
                            "页码": pages, "行": [s, e], "题干开头": stem[:50]})
        book.append(rec)
    orphans = [(n, t, p) for n, t, p in lines_q
               if n not in covered and not FURNITURE.search(t)]
    return {"label": label, "book": book, "reject": reject,
            "pending": pending, "orphans": orphans, "lines": lines_q}


def run(src: Path, *, phase: str = "run", label: str = "") -> dict:
    r"""一场考试跑完 v2。`phase` 决定只扫（scan）/ 只结构化（struct）/ 全跑。"""
    pdfs = sorted(src.glob("*.pdf"))
    paper, answers, sheets = G.pick_pdfs(pdfs)
    label = label or src.name
    out = {"label": label, "试题": paper.name if paper else None,
           "答案": [a.name for a in answers],
           "答题卡": [s.name for s in sheets], "phase": phase}
    if paper is None:
        out["error"] = "没有试题 PDF（只有答案/答题卡）"
        return out
    if phase in ("scan", "run"):
        if not ocr.alive():
            out["error"] = "OCR 服务（1236）连不上"
            return out
        out["页"] = {paper.name: scan_pdf(paper)}
        for a in answers:
            out["页"][a.name] = scan_pdf(a)
    if phase == "scan":
        return out
    if phase in ("struct", "run"):
        d = v2_dir(paper)
        st_q = structure(json.loads((d / "pages.json").read_text(encoding="utf-8")),
                         "试卷", save=d / "struct_试卷.json")
        st_a = {"items": [], "lines": []}
        if answers:
            da = v2_dir(answers[0])
            if (da / "pages.json").exists():
                st_a = structure(json.loads((da / "pages.json").read_text(encoding="utf-8")),
                                 "答案", save=da / "struct_答案.json")
            else:
                out["warning"] = "答案卷没有扫描产物，跳过配对"
        out.update(assemble(st_q, st_a, label))
    return out


def write_output(res: dict, out_dir: Path) -> None:
    """成品 / 登记 / 待复核 / 报告 四份都落盘（人工只看报告）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = re.sub(r"[^\w\u4e00-\u9fa5]+", "_", res.get("label") or "卷")[:60]
    (out_dir / (tag + ".成品.json")).write_text(
        json.dumps(res.get("book") or [], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / (tag + ".待复核.json")).write_text(
        json.dumps(res.get("pending") or [], ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# %s" % res.get("label"), "",
          "| 指标 | 值 |", "|---|---|",
          "| 切出题数 | %d |" % len(res.get("book") or []),
          "| 拒收 | %d |" % len(res.get("reject") or []),
          "| 待复核（图/表粗筛） | %d |" % len(res.get("pending") or []),
          "| 孤儿行 | %d |" % len(res.get("orphans") or []),
          ""]
    for r in res.get("reject") or []:
        md += ["- **拒收 #%s**：%s" % (r["题号"], "；".join(r["原因"])), ""]
    for n, t, p in (res.get("orphans") or [])[:30]:
        md += ["- 孤儿行 p%s 行%d：%s" % (p, n, t[:70])]
    md += ["", "## 逐题", ""]
    for b in res.get("book") or []:
        md += ["### %s. %s（第 %s 页）" % (b["题号"], b["题型"],
                                        ",".join(map(str, b["页码"]))), "",
               b["题干"][:600], ""]
        if b["选项"]:
            md += ["**选项**：" + "　".join("%s. %s" % (k, v)
                                            for k, v in sorted(b["选项"].items())), ""]
        md += ["**答案**：%s" % (b["答案"] or "（无）"), "",
               "**解析**：%s" % (b["解析"][:400] or "（无）"), ""]
    (out_dir / (tag + ".报告.md")).write_text("\n".join(md), encoding="utf-8")


# ── 自检：用例全部取自 A10 试点的**真实脏数据** ──────────────────────
def _selftest() -> int:
    fails = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("record2 自检")

    # 题型按题号（规矩 R1）
    check("题型按题号：1-8 单选", all(BY_NO[i] == "单选" for i in range(1, 9)))
    check("题型按题号：9-11 多选", all(BY_NO[i] == "多选" for i in range(9, 12)))
    check("题型按题号：12-14 填空", all(BY_NO[i] == "填空" for i in range(12, 15)))
    check("题型按题号：15-19 解答", all(BY_NO[i] == "解答" for i in range(15, 20)))

    # 选项切分：**一行并排四个**（A10 的常态）
    stem, opts = split_stem_options(["1. 已知集合 ( )",
                                     "A. $\\{1,2\\}$ B. $\\{0,1\\}$ C. $x$ D. $y$"])
    check("一行四个选项要拆开", set(opts) == {"A", "B", "C", "D"} and
          opts["B"] == "$\\{0,1\\}$", str(opts))
    check("题干与选项分开", stem == "1. 已知集合 ( )", stem)
    stem2, opts2 = split_stem_options(["f1 已知函数 ( )", "I. 函数有相同的极小值",
                                       "B. 若方程有唯一实根", "C. 若 $x_1>0$",
                                       "D. 当 $a>1$ 时"])
    check("坏标签（I.）留在题干里等补全", set(opts2) == {"B", "C", "D"}, str(opts2))

    # 引用锚剪枝：`f1 已知函数…` 要一刀剪掉 **f1 两个字符**（不是只剪 f）
    _t, _c = cut_before_quote("f1 已知函数 $f(x) = xe^x$", "已知函数 $f(x) = xe^x$")
    check("引用锚剪枝：坏字要剪干净", _t.startswith("已知函数") and _c.strip() == "f1",
          "%r / %r" % (_t[:14], _c))
    check("引用锚剪枝：引用不在开头就不动",
          cut_before_quote("已知函数 $f(x)$，求 $f(1)$", "求 $f(1)$")[0]
          == "已知函数 $f(x)$，求 $f(1)$")
    check("引用锚剪枝：引用太短不当锚",
          cut_before_quote("f1 已知函数", "已知")[0] == "f1 已知函数")

    # 清洗：分值 / 页脚 / 卷面坏字，**顺序**是关键
    s, sol, o, notes = clean_fields(
        "15. (13分) 已知函数 $f(x)=x$。", "由题意得 $x=1$。\n\n数学试题 第2页 共4页",
        qtype="detailed_answer", opts={})
    check("去分值：题干", s == "已知函数 $f(x)=x$。", repr(s))
    check("去页脚：解析", "第2页" not in sol and "由题意得" in sol, repr(sol))
    check("记了清洗动作", "去分值" in notes and "解析去页脚" in notes, str(notes))
    # 用例照 A10 第 11 题的**真实现场**写：两行——坏题号那行是题干，
    # 第二行是印坏标签的 A 选项（原图印成「£/匚」样，OCR 读成 `I.`）。
    s2, _sol2, o2, notes2 = clean_fields(
        "f1 已知函数 $f(x) = xe^x$，则下列说法正确的是 ( )\n"
        "I. 函数 $f(x),g(x)$ 有相同的极小值",
        "", qtype="multi_choice", opts={"B": "b", "C": "c", "D": "d"})
    check("剪掉卷面坏字 f1", s2.startswith("已知函数"), repr(s2[:20]))
    check("补回缺失的 A 选项", set(o2) == {"A", "B", "C", "D"} and o2["A"], str(o2))
    check("补回的 A 选项内容对", o2.get("A", "").startswith("函数 $f(x)"), str(o2))
    check("A 那一行已从题干移走", "极小值" not in s2, repr(s2))
    s3, _s3, _o3, _n3 = clean_fields("f(x) = x^2 的最小值是 $0$。", "",
                                     qtype="fill_in_blank", opts={})
    check("正常公式开头**不能**被当坏字剪", s3.startswith("f(x)"), repr(s3))

    # 闸门
    check("闸门：选项只有 3 个 → 拒收",
          any("选项" in w for w in gate("multi_choice", "x ( )",
                                        {"B": "b", "C": "c", "D": "d"}, "BCD", "s")))
    check("闸门：四个选项 → 过",
          not gate("multi_choice", "x ( )", {"A": "a", "B": "b", "C": "c", "D": "d"},
                   "BCD", "故选 BCD"))
    check("闸门：客观题答案是整段解析 → 拒收",
          any("整段解析" in w for w in gate("fill_in_blank", "x = ___", {}, "长" * 50, "")))
    check("闸门：`$` 不成对 → 拒收",
          any("不成对" in w for w in gate("fill_in_blank", "求 $x 的值（", {}, "1", "")))
    check("闸门：`$` 成对就不报", not any(
        "不成对" in w for w in gate("fill_in_blank", "求 $x$ 的值（", {}, "1", "")))
    check("闸门：残留页脚 → 拒收",
          any("页脚" in w for w in gate("fill_in_blank", "求 $x$ 的值。第 3 页 共 8 页",
                                        {}, "1", "")))
    check("闸门：版面家具 → 拒收",
          any("家具" in w for w in gate("fill_in_blank", "一、选择题：本题共8小题",
                                        {}, "1", "")))
    check("闸门：选择题答案是中文 → 拒收",
          any("应为字母" in w for w in gate("single_choice", "x ( )",
                                            {"A": "a", "B": "b", "C": "c", "D": "d"},
                                            "第一", "")))

    # 跨页：一条题的区间跨过页标记时，页码要算两页
    lines = [(1, "8. 题干", 1), (2, "A. 甲", 1), (3, "B. 乙", 2), (4, "C. 丙", 2)]
    check("跨页题覆盖两页", covered_pages(lines, (1, 4)) == [1, 2],
          str(covered_pages(lines, (1, 4))))
    check("单页题只算一页", covered_pages(lines, (3, 4)) == [2], str(covered_pages(lines, (3, 4))))

    # 抠 JSON：围栏 / 前后废话 / 截断
    check("抠 JSON：带 ```json 围栏", grab_json('```json\n{"questions":[{"n":1}]}\n```')
          == {"questions": [{"n": 1}]})
    _cut = grab_json('{"questions":[{"n":1,"start":2},{"n":2,"star')
    check("抠 JSON：被截断也能收下完整的对象",
          (_cut or {}).get("questions") == [{"n": 1, "start": 2}], str(_cut))

    print("record2 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


def _main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    what = sys.argv[1]
    if what == "selftest":
        return _selftest()
    if what == "reassemble":
        # 不重跑模型：拿已落的 struct JSON 重跑清洗+闸门。
        # 改清洗规则时要一遍遍看效果，**每次重跑 27B（3 分钟）太浪费**。
        src = Path(sys.argv[2])
        paper, answers, _sh = G.pick_pdfs(sorted(src.glob("*.pdf")))
        d = v2_dir(paper)
        st_q = json.loads((d / "struct_试卷.json").read_text(encoding="utf-8"))
        st_a = {"items": [], "lines": []}
        if answers:
            fa = v2_dir(answers[0]) / "struct_答案.json"
            if fa.exists():
                st_a = json.loads(fa.read_text(encoding="utf-8"))
        res = assemble(st_q, st_a, src.name)
        write_output(res, R.WORK / "输出_v2")
        print("重装配：%s  成品 %d / 拒收 %d / 待复核 %d / 孤儿 %d"
              % (src.name, len(res["book"]), len(res["reject"]),
                 len(res["pending"]), len(res["orphans"])))
        return 0
    if what in ("scan", "struct", "run"):
        t0 = time.time()
        res = run(Path(sys.argv[2]), phase=what)
        if res.get("error"):
            print("✗ %s" % res["error"])
            return 1
        print("%s：%s  用时 %.0fs" % (what, res.get("label"), time.time() - t0))
        for k in ("book", "reject", "pending", "orphans"):
            if k in res:
                print("  %-9s %d" % (k, len(res[k])))
        if "book" in res:
            write_output(res, R.WORK / "输出_v2")
            print("  产物 → %s" % (R.WORK / "输出_v2"))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
