#!/usr/bin/env python3
r"""赵礼显《2027届高三数学暑秋讲义》→ 题库格式。

这份 PDF 是**扫描讲义**，不是试卷：全书没有答案（每题下面留白给课上做），
题号在**每讲内部**从 1 连续排，中间夹「题型一：…」这种小节标题。

所以 `amti.record`（按 19 题固定题型录试卷）和 `amti.record2`（按卷切题/配对）
都不适用。这里只复用它们**已经过验证的零件**，不重写：

    amti.record.pages_of      PDF → 页图（dpi 贴合原扫描件、坏 xref 静音）
    amti.record.shrink        页图 → 塞进 VLM 图像 token 预算
    amti.record.ask           一页图 → 标记文本（reasoning_effort=none 关思考）
    amti.record.parse_marked  标记文本 → 结构（题干/选项/图/答案/解析）
    amti.images.sha_name      图片 → 内容寻址名（全项目唯一处理图片的地方）

本脚本自己写的只有三件事：**讲义版提示词**、**题型小节与讲次的还原**、
**组装成题库 LaTeX**。

    python3 脚本/赵礼显讲义录题.py scan            # 逐页转录（可中断续跑）
    python3 脚本/赵礼显讲义录题.py scan --only 20-40
    python3 脚本/赵礼显讲义录题.py figs            # 从扫描页裁插图 → 图片/
    python3 脚本/赵礼显讲义录题.py build           # 组装 .tex 到 数据/录题/赵礼显/out
    python3 脚本/赵礼显讲义录题.py report          # 讲/题型/题数一览

只读原 PDF；**不碰 `题目/*.tex`、不调 ingest**——没有答案，ingest 本来也会整批拒。
"""
from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import record as R                                    # noqa: E402
from amti import images as IMG                                  # noqa: E402
from amti import normalize as N                                 # noqa: E402
from amti.schema import Option, Question as Q                   # noqa: E402

PDF = Path.home() / "Desktop/27年试卷/赵礼显/2027版高中数学.pdf"
WORK = ROOT / "数据/录题/赵礼显"
PAGES = WORK / "pages"
SCAN = WORK / "scan"
FIGDIR = ROOT / "图片"
OUT = WORK / "out"
FIGS = WORK / "figs.json"
SCAN2 = WORK / "boxes"
BOOK = "赵礼显暑秋讲义"
LABEL = "2027届高三数学暑秋讲义"

# 打印页码 = PDF 页码 - OFFSET（验证过：PDF 9/10/11 的页脚是 5/6/7）
OFFSET = 4

# ── 讲义版提示词 ────────────────────────────────────────────────
#
# 与 record.PROMPT 的差别（每一条都有理由）：
# 1. 全书无答案 —— `@@ANS`/`@@SOL` 两段整个删掉，模型不用写，`parse_marked`
#    读不到就是空串。**省下的正是最贵的东西**：一页 800 个输出 token 里
#    有 ~15% 是这个格式壳，340 页就是半小时。
# 2. `@@SEC` 只在**小节变化时**写一行，不每题重复。
# 3. figure=有时**必须**给归一化包围盒 `figbox=` —— 扫描页里图是像素，
#    题库里图必须是 `图片/` 下的文件，只能从原页裁。
PROMPT = r"""你是高中数学题库录入员。下面是一本高三数学讲义（扫描版）的其中一页。
你的唯一任务是**忠实转录**：不解答、不翻译、不改写、不补充、不合并。

严格按下面的标记输出，**除标记外不要写任何别的内容**（不要 markdown、不要解说）：

@@PAGE kind=<正文|讲次扉页|目录|封面|空白|课堂总结|练习> title=<本页顶部的讲次标题，没有写 ->

（本页有几道题就写几段下面这样的块。题目**按卷面题号从小到大**排。）
@@Q n=<卷面题号，纯数字> type=<单选|多选|填空|解答> figure=<有|无> continued=<是|否> figbox=<x0,y0,x1,y1|->
@@STEM
<题干原文。行内公式用 $…$；数学里的中文用 \text{}；卷面的作答空位选择题写 \paren[]、
 填空题写 \fillin[]（**几个空就写几个**）；解答题的 (1)(2) 小问就写在文字里。
 ⚠️ 题干里**不要**抄题号，不要抄分值，不要抄「（本小题满分 X 分）」。
 ⚠️ 题干开头如果印着出处（如「(2025·全国二卷)」「(2026·北京模拟)」），
    照抄下来（含括号），后面接正常题干。
@@OPT
<只有选择题写，每行一个：A. 内容 ；不是选择题写 ->
@@FIG
<figure=有时写一句话描述图长什么样；否则写 ->
@@ENDQ

题型小节：**只在小节标题变化时**，在题块前面单独加一行
@@SEC <小节标题，如「题型一：必须会解的不等式」>
小节没变就不要写这行；跨页延续的小节，在续页的第一道题前要重新写一次。

铁律：
1. 只转录本页看得见的内容，**不要凭记忆补全**，不要给本题写任何解答。
2. 看不清的字写 \text{【?】}，**不要猜**。
3. 数字、符号、上下标、单位一个都不能改。
4. 不要写 \begin{question} 之类的环境，不要加排版。
5. 页眉页脚、页码、「赵礼显数学」logo、广告水印、跑步小人插图**一律不输出**。
6. 一道题跨页时，本页只写看得见的那部分，continued=是（跨页题**不要**重复抄题干）。
7. **题目之间留给学生演算的空白与横线、装订线、章节装饰星号，都不是内容**，不要输出。
8. kind=课堂总结 的整页留白不要输出任何 @@Q。
9. 只有**真实图形/表格/图象**才 figure=有：坐标系、几何图形、统计图表、
   三视图、程序框图、数表。只是文字里提到「如图」时按文字抄，figure=无。
10. figure=有时 `figbox` 必须给：把该图在**整页**里的位置写成本页宽高的
    归一化千分比 `x0,y0,x1,y1`（左上角为原点，0–1000）。**只框图形本身，
    不要框住题干文字**。拿不准就写 -。
"""

# ── 讲次划分：**从转录结果自己推**，不抄目录 ─────────────────────
#
# ⚠️ 为什么不用目录：我先按目录页手抄了一张 `LECTS` 表，结果**目录那一页
# 本身就被截断了**——秋季只列到「第12+13讲：椭圆双曲线进阶」，而书里后面
# 还有第14～22讲（抛物线、圆锥曲线解答题(1)-(5)、新定义探索）以及三节
# 视频赠课。照着抄的后果很隐蔽：第12～22讲的题号各自从 1 开始，
# 全被塞进同一个 `秋季第12+13讲` 里，**29 个题号撞成重号**，
# 而题号连续性检查只会说"完整；重 [...]"。
#
# 好在**每一讲的第一页，页眉就印着讲次标题**，转录时就带回来了
# （`@@PAGE ... title=第N讲：…`）。所以讲次划分直接由数据决定：
# 标题像讲次标题的页 = 一讲的起点，下一页起点之前都归这一讲。
STOP_TITLES = {"-", "->", "练习", "作业", "暑假讲义", "秋季讲义", ""}


def _lect_name(season: str, title: str) -> str:
    r"""讲次长标题 → 短名（做 key 和文件名用）。

    有「第N讲」就用它（`秋季第14讲`）；没有的是**视频赠课**，
    书里没编号，就按标题取个短名（`秋季·排列组合方法梳理(1)`）。
    """
    m = re.search(r"第\s*(\d+(?:\s*\+\s*\d+)?)\s*讲", title)
    if m:
        return "%s第%s讲" % (season, re.sub(r"\s+", "", m.group(1)))
    short = re.split(r"[-—－一]+\s*视频赠课|[-—－]+\s*录播", title)[0]
    # 去掉 `+题型拓展` 这类模块词，但**把它后面的 `(1)` 留下来**——
    # 第一版用 `.*$` 一起删了，导数那四讲的短名全变成 `导数常考方法总结`，
    # 四讲撞成一个名字（report 里四行一模一样，1041 页的坑换了个样子又出现）。
    short = re.sub(r"\s*[+＋]\s*(?:题型拓展|经典题型|技巧衍生|技巧大招)"
                   r"\s*((?:[（(]\s*\d+\s*[）)])*)", r"\1", short)
    return "%s·%s" % (season, short.strip(" -—－一"))


def lecture_map(scans: dict[int, dict]) -> list[tuple[str, str, int, int]]:
    r"""[(短名, 长标题, 起始PDF页, 结束PDF页)]，按页序。"""
    starts: list[tuple[int, str, str]] = []      # (页, 短名, 长标题)
    fall_start = 10 ** 9
    for n, pg in sorted(scans.items()):
        t = (pg["page"]["title"] or "").strip()
        if t == "秋季讲义":
            fall_start = n
    for n, pg in sorted(scans.items()):
        t = (pg["page"]["title"] or "").strip()
        if t in STOP_TITLES or len(t) < 4:
            continue
        if pg["page"]["kind"] != "正文":
            continue
        # ⚠️ **只认真正的讲次标题**：要么带「第N讲」，要么是视频赠课/录播那几节。
        # 不卡这一条，模型偶尔会把页面上最大的那行**题型标题**当成 title 回填
        # （实测 `题型二：奔驰定理与三角形四心`、`题型二：直线与圆的位置关系`），
        # 于是凭空多出两"讲"，把秋季第3讲、第11讲从中间劈开。
        if not re.search(r"第\s*\d+.*讲|视频赠课|录播", t):
            continue
        season = "暑假" if n < fall_start else "秋季"
        starts.append((n, _lect_name(season, t), t))
    last = max(scans) if scans else 0     # 最后一讲一直管到最后一页
    out = []
    for i, (n, short, title) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else last
        out.append((short, title, n, end))
    return out


# 打印页码 = PDF 页码 − OFFSET（验证过：PDF 9/10/11 的页脚是 5/6/7）

TYPE_EN = {"单选": "single_choice", "多选": "multi_choice",
           "填空": "fill_in_blank", "解答": "detailed_answer"}


# ══ 标记文本 → 结构 ═══════════════════════════════════════════════

# 题干开头的出处，形如 `(2025·全国二卷)`、`（2026·北京模拟）`，
# 模型还可能写成 `$(2025\cdot$ 全国二卷 $)$`（它把「·」当公式了）——
# 那个形态靠 `inner` 能吃到 `$` 来解决。
#
# ⚠️ **结尾绝对不能写 `\$?`。** 第一版写了，于是
#     `(2025·潍坊二模) $\forall x \in R, …`
# 里的那个**开数学模式的 `$` 被当成出处的尾巴吃掉了**，题干变成
#     `\forall x \in R, …\geqslant 4$，则实数 $a$ …`
# ——`$` 只剩奇数个，整道题坏掉，而且**看起来很像 OCR 漏字**，
# 罪魁其实是自己写的正则（实测 2 道，且都瞒过了最初的人工抽查）。
_SRC_LEAD = re.compile(
    r"^\s*(?P<open>\$)?\s*[（(]\s*(?P<inner>[^（()）]{1,50}?)\s*[）)]\s*")
# 判据：里面有年份、或像考试名。**宁可漏判，不可错删题干**——
# `（1）`、`（多选）`、`（$a>0$）` 都不能当出处。
_SRC_WORD = re.compile(
    r"20\d\d|模拟|一模|二模|三模|联考|质检|期末|期中|调研|诊断|测评"
    r"|招生|卷|考试|测试|统考|统测|竞赛|学业水平|适应性|质量检测")


def _clean_src(inner: str) -> str:
    s = inner.replace("$", "").replace("\\cdot", "·").replace("\\cdots", "·")
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # 模型爱把「2025·全国二卷」写成 `$(2025\cdot$ 全国二卷 $)$`，
    # 去掉 `$` 后中间会留一个空格：「2025· 全国二卷」。收掉它。
    return re.sub(r"·\s+", "·", s)


def split_source(stem: str, qtype: str) -> tuple[str, str, str]:
    r"""题干开头的出处 → (干净题干, 出处, 修正后的题型)。

    `（多选）` 这种题型自述也在这里吃掉（规范 §2.1：题型以题干自述为准）。
    """
    m = _SRC_LEAD.match(stem)
    if not m:
        return stem, "", qtype
    inner = _clean_src(m.group("inner"))
    if inner in ("多选", "多选题"):
        return stem[m.end():].lstrip(), "", "多选"
    if inner in ("单选", "单选题"):
        return stem[m.end():].lstrip(), "", "单选"
    if not _SRC_WORD.search(inner):
        return stem, "", qtype
    rest = stem[m.end():]
    # 模型把出处**整个包进一对 `$…$`** 的两种写法：
    #     `$(2025\cdot$ 保定模拟 $)$ 记 $\max M$ …`   ← inner 里有 `$`
    #     `$(北大自主招生)$ 已知 $a,b,c\in R_+$ …`      ← inner 里没有 `$`
    # 正则吃到 `)` 就停，收尾那个 `$` 留在 rest 开头，要一起吃掉。
    #
    # ⚠️ 判据**只能是"开头的 `$` 在不在"**（`(?P<open>\$)?` 那个组），
    # 不能是"inner 里有没有 `$`"——第一版用后者，第二种写法判不出来，
    # 收尾 `$` 留下 → 奇偶守卫再补一个 `$` → 题干开头变成 `$$`，
    # xelatex 直接报「Display math should end with $$」。
    # 而 `(2025·潍坊二模) $\forall x…` 这种**没有**裹壳的，后面那个 `$`
    # 是下一段公式的开头，绝不能吃——那正是更早一版踩过的坑。
    if m.group("open"):
        rest = re.sub(r"^\s*\$", "", rest, count=1)
    rest = rest.lstrip()
    # 奇偶守卫：出处本身是纯文字（不含 `$`）时，砍掉它不该改变 `$` 的奇偶。
    # 变了就说明正则多吃了一个 `$`——补回来，**宁可留个没洗干净的出处，
    # 也不能把一道题的公式弄坏**。
    if "$" not in m.group("inner") and \
            (rest.count("$") % 2) != (stem.count("$") % 2):
        rest = "$" + rest
    return rest, inner, qtype


def parse_text(text: str) -> dict:
    r"""一页标记文本 → {page, questions}，每个题块带上它前面的 `@@SEC`。

    题块本体交给 `record.parse_marked` 解析——**同一套标记、同一份解析代码**，
    省得这里再长出一个会跟它分叉的解析器。
    """
    lines = text.splitlines()
    page = {"kind": "", "title": ""}
    for ln in lines:
        if ln.startswith("@@PAGE"):
            k = re.search(r"kind\s*=\s*(\S+)", ln)
            t = re.search(r"title\s*=\s*(.+?)\s*$", ln)
            page["kind"] = k.group(1) if k else ""
            page["title"] = (t.group(1) if t else "").strip()
            break

    qs: list[dict] = []
    sec, cur_sec = "-", "-"
    buf: list[str] | None = None

    def flush() -> None:
        if not buf:
            return
        one = R.parse_marked("\n".join(buf))["questions"]
        if one:
            q = one[0]
            q["sec"] = sec
            # ⚠️ `record.parse_marked` 的标记集是**试卷那一套**（STEM/OPT/FIG/
            # ANS/SOL），它返回的字段是写死的 dict，`figbox` / `image` 这两个
            # 讲义专有的头字段会被它丢掉。别去改共享解析器——在这里把头行
            # 自己再解一遍，补进去。
            head = dict(re.findall(r"(\w+)=(\S+)", buf[0]))
            q["figbox"] = head.get("figbox", "-")
            q["image"] = head.get("image", "-")
            qs.append(q)

    for ln in lines:
        s = ln.strip()
        if s.startswith("@@SEC"):
            cur_sec = s[5:].strip() or "-"
            continue
        if s.startswith("@@Q"):
            flush()
            sec = cur_sec
            buf = [s]
            continue
        if buf is not None:
            buf.append(ln)
    flush()
    return {"page": page, "questions": qs}


def load_scans() -> dict[int, dict]:
    out: dict[int, dict] = {}
    for f in sorted(SCAN.glob("p*.txt")):
        n = int(f.stem[1:])
        out[n] = parse_text(f.read_text(encoding="utf-8"))
    return out


# ══ 讲次归属 ═══════════════════════════════════════════════════════


def lect_of(pdf_page: int, lmap) -> tuple[str, str]:
    """PDF 页码 → (讲次短名, 讲次长标题)。落在所有讲之前的页（封面/目录）返回空。"""
    for name, title, start, end in lmap:
        if start <= pdf_page <= end:
            return name, title
    return "", ""


# ══ scan ══════════════════════════════════════════════════════════


def cmd_scan(a) -> int:
    PAGES.mkdir(parents=True, exist_ok=True)
    SCAN.mkdir(parents=True, exist_ok=True)
    if not list(PAGES.glob("p*.png")):
        print("抽页图…")
        R.pages_of(PDF, PAGES, dpi=300)
    imgs = sorted(PAGES.glob("p*.png"))
    if a.only:
        lo, hi = _range(a.only)
        imgs = [p for p in imgs if lo <= int(p.stem[1:]) <= hi]
    todo = [p for p in imgs
            if a.force or not (SCAN / (p.stem + ".txt")).exists()]
    print("待转录 %d 页（已缓存 %d 页）" % (len(todo), len(imgs) - len(todo)))
    if not todo:
        return 0
    t0, done, bad = time.time(), 0, []

    def one(p: Path) -> None:
        nonlocal done
        dst = SCAN / (p.stem + ".txt")
        last = ""
        for _ in range(3):
            try:
                txt = R.ask(p, prompt=PROMPT, max_tokens=4500,
                            note="转录这一页。")
                if len(txt) < 20:
                    raise RuntimeError("产物过短（%d 字）" % len(txt))
                dst.write_text(txt, encoding="utf-8")
                done += 1
                print("  %s ✓ %.0fs  (%d/%d)"
                      % (p.stem, R.last().get("secs", 0), done, len(todo)))
                return
            except Exception as e:                          # noqa: BLE001
                last = "%s: %s" % (type(e).__name__, e)
                time.sleep(5)
        bad.append((p.stem, last))
        print("  %s ✗ %s" % (p.stem, last))

    # ⚠️ **不能 `ThreadPoolExecutor.map`。** 它会把 339 个任务**一次性全提交**，
    # 于是 339 个 HTTP 请求同时压到 llama-server 上；服务端排着队一个一个生成，
    # 而**客户端一被杀，排队的请求不会跟着消失**——服务端照样把它们生成完。
    # 实测踩过：一个跑批被杀掉之后，下一次跑批的头 4 页等了 **968 秒**，
    # 日志里 task id 已经涨到 2689（页数才 340）。
    # 改成**有界队列**：任何时刻在飞的请求最多 `workers` 个。
    q: "queue.Queue[Path]" = queue.Queue()
    for p in todo:
        q.put(p)
    def worker() -> None:
        nonlocal done
        while True:
            try:
                p = q.get_nowait()
            except queue.Empty:
                return
            one(p)

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(a.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("完成 %d 页，失败 %d 页，用时 %.0f 分"
          % (done, len(bad), (time.time() - t0) / 60))
    for n, e in bad:
        print("  失败：%s %s" % (n, e))
    return 1 if bad else 0


# ══ boxes：第二遍专找「选项图」 ═══════════════════════════════════
#
# 为什么需要第二遍：第一遍的 `@@Q figbox=` 一道题**只给一个框**。
# 于是「下列四个图象中…」这种**选项图**（A/B/C/D 各一张图）只能框到其中一张
# （实测 p027 第 17 题就只框到了题干那张，四个选项图全丢）。
# 选项图在函数/立体几何讲义里很常见，丢了这道题就没法做。
#
# 所以对**有选择题的带图页**再问一遍，只问"图在哪、属于哪一部分"。
BOX_PROMPT = r"""这是一页高中数学讲义扫描图。只做一件事：**找出页面上所有的图形/图象**，
并说明每张图属于哪一道题的哪一部分。

每张图输出一行，**按从上到下、从左到右的顺序**：
@@BOX q=<所属题目在卷面上的题号，纯数字> where=<题干|A|B|C|D> x0,y0,x1,y1

`x0,y0,x1,y1` 是这张图在**整页**里的位置，用本页宽高的千分比表示
（左上角为原点，取值 0–1000）。**只框图形本身**（坐标系、曲线、几何体、
统计图、数表），不要把题目文字、选项文字、页眉页脚框进去。
一张图都没有就什么都不输出。

注意：
* 选择题的四个选项各带一张图时，要输出**四行**：`where=A`、`where=B`、
  `where=C`、`where=D`，依次对应。
* 题干里的图和选项里的图都要框。
* 看不清或拿不准的图不要输出，**不要猜**。
"""


def cmd_boxes(a) -> int:
    r"""对带图页跑第二遍，拿到「题干图 + 每张选项图」的**分项包围盒**。"""
    PAGES.mkdir(parents=True, exist_ok=True)
    SCAN2.mkdir(parents=True, exist_ok=True)
    scans = load_scans()
    todo = []
    for n, pg in sorted(scans.items()):
        if not any(q["figure"] for q in pg["questions"]):
            continue
        if a.only:
            lo, hi = _range(a.only)
            if not (lo <= n <= hi):
                continue
        if not a.force and (SCAN2 / ("p%03d.txt" % n)).exists():
            continue
        todo.append(n)
    print("待找选项图的页：%d" % len(todo))
    if not todo:
        return 0
    q: "queue.Queue[int]" = queue.Queue()
    for n in todo:
        q.put(n)
    bad: list[tuple[int, str]] = []

    def worker() -> None:
        while True:
            try:
                n = q.get_nowait()
            except queue.Empty:
                return
            try:
                txt = R.ask(PAGES / ("p%03d.png" % n), prompt=BOX_PROMPT,
                            max_tokens=2000, note="找出这一页上所有图形的位置。")
                (SCAN2 / ("p%03d.txt" % n)).write_text(txt, encoding="utf-8")
                print("  p%03d ✓ %s" % (n, _box_summary(txt)))
            except Exception as e:                          # noqa: BLE001
                bad.append((n, "%s: %s" % (type(e).__name__, e)))
                print("  p%03d ✗ %s" % (n, e))

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(a.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("完成 %d 页，失败 %d 页" % (len(todo) - len(bad), len(bad)))
    return 1 if bad else 0


def _box_summary(txt: str) -> str:
    hits = parse_boxes(txt)
    return "、".join("%s题%s" % (a, b) for a, b, _ in hits) or "没找到图"


_BOX_LINE = re.compile(r"@@BOX\s+q=(\d+)\s+where=(\S+)\s*(.*)$")


def parse_boxes(text: str) -> list[tuple[str, str, str]]:
    r"""`@@BOX` 行 → `(题号, 部位, "x0,y0,x1,y1")`。

    ⚠️ **坐标的写法不能写死。** 提示词里要的是 `368,458,545,672`，
    模型实际吐的是 `x0=368,y0=458,x1=545,y1=562`——两者都得认。
    所以只做"取这一行剩下的 4 个数字"，不匹配具体形状
    （写死形状的结果是 p027 五张图**一张都没解析出来**，
    而且日志还报"没找到图"，看着像模型没干活）。
    """
    out = []
    for line in text.splitlines():
        m = _BOX_LINE.match(line.strip())
        if not m:
            continue
        # ⚠️ 先剥掉 `x0=` `y0=` 这种标签**再取数字**。不剥的话
        # `x0=368,y0=458,…` 会被读成 `0,368,0,458`——
        # 框出来是一条横线，而且不报错，只表现为"图裁得莫名其妙"。
        tail = re.sub(r"[xyXY]\s*\d?\s*=", "", m.group(3))
        nums = re.findall(r"-?\d+(?:\.\d+)?", tail)
        if len(nums) < 4:
            continue
        out.append((m.group(1), m.group(2).strip(), ",".join(nums[:4])))
    return out


def load_boxes() -> dict[int, list[tuple[str, str, str]]]:
    out: dict[int, list[tuple[str, str, str]]] = {}
    for f in sorted(SCAN2.glob("p*.txt")):
        out[int(f.stem[1:])] = parse_boxes(f.read_text(encoding="utf-8"))
    return out


# ══ figs ══════════════════════════════════════════════════════════


def cmd_figs(a) -> int:
    from PIL import Image
    scans = load_scans()
    boxes = load_boxes()
    FIGDIR.mkdir(exist_ok=True)
    made, skipped, map_ = 0, [], {}
    for n, pg in sorted(scans.items()):
        page_img = PAGES / ("p%03d.png" % n)
        if not page_img.exists():
            continue
        with Image.open(page_img) as im:
            W, H = im.size
            for q in pg["questions"]:
                if not q["figure"]:
                    continue
                key = "%d#%s" % (n, q["n"])
                rec = {"stem": [], "opts": {}}
                # ① 第二遍的分项框优先（能区分题干图 / A–D 选项图）
                for no, where, raw in boxes.get(n, []):
                    if no != q["n"]:
                        continue
                    box = _figbox(raw, W, H)
                    if box is None:
                        continue
                    name = _save(im.crop(box))
                    made += 1
                    if where in ("A", "B", "C", "D"):
                        rec["opts"].setdefault(where, name)
                    else:
                        rec["stem"].append(name)
                # ② 第二遍没覆盖到的，退回第一遍那一个框（题干图）
                if not rec["stem"] and not rec["opts"]:
                    box = _figbox(q.get("figbox"), W, H)
                    if box is None:
                        skipped.append((n, q["n"], q.get("fig", "")[:40]))
                        continue
                    rec["stem"].append(_save(im.crop(box)))
                    made += 1
                map_[key] = rec
    # **映射必须落盘**：`figs` 与 `build` 是两次独立进程，图名只在内存里
    # 传不过去（第一版就漏了这一步，`build` 于是把所有带图题都当成"图还没裁"）。
    old = json.loads(FIGS.read_text(encoding="utf-8")) if FIGS.exists() else {}
    old.update(map_)
    FIGS.write_text(json.dumps(old, ensure_ascii=False, indent=1, sort_keys=True),
                    encoding="utf-8")
    nopt = sum(len(v["opts"]) for v in map_.values())
    print("裁出 %d 张图（其中选项图 %d 张），%d 道带图题没裁到图"
          % (made, nopt, len(skipped)))
    for n, no, desc in skipped:
        print("  待裁：p%03d 第%s题  %s" % (n, no, desc))
    return 0


def _save(crop) -> str:
    data = _png(_trim(crop))
    name = IMG.sha_name(data, ".png")
    (FIGDIR / name).write_bytes(data)
    return name


def load_figs() -> dict[str, dict]:
    return json.loads(FIGS.read_text(encoding="utf-8")) if FIGS.exists() else {}


def _trim(im, *, pad: int = 12):
    r"""裁掉图四周的空白边。

    模型给的包围盒总是**宽大于紧**（它会带上一行题干文字、甚至上面的
    「题型五」标题）。纯去白边治不了"带进了文字"，但能治掉大片空白，
    而且只往回收、不往外扩，是安全的。
    """
    import numpy as np
    a = np.asarray(im.convert("L"))
    ink = a < 200
    if ink.sum() < 50:                  # 整块都白：多半框错了，原样返回
        return im
    ys, xs = np.where(ink)
    x0, y0 = max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad)
    x1 = min(im.width, int(xs.max()) + 1 + pad)
    y1 = min(im.height, int(ys.max()) + 1 + pad)
    return im.crop((x0, y0, x1, y1))


def _figbox(s: str | None, W: int, H: int):
    if not s or s in ("-", ""):
        return None
    nums = re.findall(r"-?\d+(?:\.\d+)?", s)
    if len(nums) != 4:
        return None
    x0, y0, x1, y1 = (float(v) for v in nums)
    if max(x0, y0, x1, y1) <= 1.5:                     # 模型给了 0–1 的比例
        x0, y0, x1, y1 = x0 * 1000, y0 * 1000, x1 * 1000, y1 * 1000
    if x1 <= x0 or y1 <= y0:
        return None
    if (x1 - x0) < 30 or (y1 - y0) < 20:               # 太小的框是噪声
        return None
    pad = 8                                            # 千分比留白，别切掉笔画

    def lo(v, S):
        return max(0, min(S, int((v - pad) / 1000.0 * S)))

    def hi(v, S):
        return max(0, min(S, int((v + pad) / 1000.0 * S)))

    return (lo(x0, W), lo(y0, H), hi(x1, W), hi(y1, H))


def _png(im) -> bytes:
    import io
    b = io.BytesIO()
    im.convert("RGB").save(b, format="PNG", optimize=True)
    return b.getvalue()


# ══ build ═════════════════════════════════════════════════════════


def _norm_stem(stem: str) -> str:
    """题干里的作答空位统一成空答案形态（正文是真相，元数据跟着走）。"""
    stem = re.sub(r"\\paren\s*\{\s*([A-H]{1,4})?\s*\}", r"\\paren[\1]", stem)
    stem = re.sub(r"\\fillin\s*\{\s*([^}]*)\}", r"\\fillin[\1]", stem)
    stem = stem.replace("$$", "$")
    return re.sub(r"[ \t]+", " ", stem).strip()


def collect_questions(scans: dict[int, dict]) -> list[dict]:
    figs = load_figs()
    lmap = lecture_map(scans)
    rows: list[dict] = []
    in_prac: set[str] = set()          # 已经进到「练习」的讲次
    for n, pg in sorted(scans.items()):
        kind = pg["page"]["kind"]
        if kind in ("封面", "目录", "空白", "课堂总结"):
            continue
        lect, ltitle = lect_of(n, lmap)
        # ⚠️ 每讲后面跟着「练习」，**练习的题号从 1 重新开始**——
        # 不分开的话练习第 1 题会和例题第 1 题撞同一个 key（实测前 33 页就撞了 5 组）。
        #
        # ⚠️ 而且**`kind=练习` 只标在练习的第一页**：练习跨页时后面几页
        # 模型会标成 `kind=正文`。只认 `kind` 的话续页会被当成例题，
        # 于是"练习第 5 题"和"例题第 5 题"又撞号
        # （实测秋季第1讲：p173 练习 1–4，p174 标成正文却是练习的 5）。
        # 所以一旦某讲进过练习，**这一讲后面的页都算练习**，直到下一讲开始。
        if kind == "练习":
            in_prac.add(lect)
        part = "练习" if lect in in_prac else "例题"
        for q in pg["questions"]:
            no = (q.get("n") or "").strip()
            if not no.isdigit():
                continue
            stem = _norm_stem(q["stem"])
            stem, src, qtype = split_source(stem, q.get("type") or "")
            if not stem:
                continue
            rows.append({
                "pdf_page": n, "n": int(no), "lect": lect, "lect_title": ltitle,
                "part": part,
                "sec": q.get("sec", "-"), "type": qtype, "stem": stem,
                "options": q["options"], "source_in_stem": src,
                "figure": q["figure"],
                "fig_stem": (figs.get("%d#%s" % (n, no)) or {}).get("stem") or [],
                "fig_opts": (figs.get("%d#%s" % (n, no)) or {}).get("opts") or {},
                "fig_desc": q.get("fig", ""), "continued": q["continued"],
            })
    return rows


def key_of(r: dict) -> str:
    """`书/讲次[练习]#题号`。**练习要单独挂后缀**，否则和例题撞 key。"""
    tail = r["lect"] + ("练习" if r.get("part") == "练习" else "")
    return "%s/%s#%d" % (BOOK, tail, r["n"])


def _answer_slot(stem: str, qtype: str) -> str:
    """按题型把作答位补进题干（题库格式的硬性要求）。"""
    if "\\paren[" in stem or "\\fillin[" in stem:
        return stem
    if qtype in ("单选", "多选"):
        return stem.rstrip() + " \\paren[]"
    if qtype == "填空":
        return stem.rstrip() + " \\fillin[]"
    return stem


def cmd_build(a) -> int:
    scans = load_scans()
    rows = collect_questions(scans)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.tex"):
        f.unlink()
    by_lect: dict[str, list[dict]] = {}
    for r in rows:
        by_lect.setdefault(r["lect"], []).append(r)

    nfile, fired = 0, {}
    for lect, title, _s, _e in lecture_map(scans):
        rs = by_lect.get(lect) or []
        if not rs:
            continue
        nfile += 1
        lines: list[str] = [
            "%%%% %s %s" % (lect, title),
            "%%%% 赵礼显2027届高三数学暑秋讲义 · 正文转录（**无答案**，待补）",
            "%%%% 生成：脚本/赵礼显讲义录题.py build",
            "",
        ]
        cur = None
        for r in sorted(rs, key=lambda x: (x["pdf_page"], x["n"])):
            if r["sec"] and r["sec"] not in ("-", cur):
                lines.append("%%%% ── %s ──" % r["sec"])
            cur = r["sec"]
            lines.extend(block_of(r, lect, title, fired))
        (OUT / ("%s.tex" % lect)).write_text("\n".join(lines) + "\n",
                                             encoding="utf-8")
    idn = sum(1 for r in rows if r["continued"])
    print("写出 %d 个 .tex，%d 道题（其中 %d 道跨页题）" % (nfile, len(rows), idn))
    print("带图题 %d 道，已裁到图 %d 道"
          % (sum(1 for r in rows if r["figure"]),
             sum(1 for r in rows if r["fig_stem"] or r["fig_opts"])))
    if fired:
        print("规范化生效（normalize ENTRY）：")
        for k, v in sorted(fired.items(), key=lambda x: -x[1]):
            print("  %-28s %d 道" % (k, v))
    return 0


def finalize(r: dict, fired: dict | None = None) -> Q:
    r"""一道题 → **规范形态的 `Question`**（就是最后写进 .tex 的那个东西）。

    `build` 和 `verify` **必须共用这一支**：verify 要是自己另造一遍
    `Question`（第一版就是），查的就不是真正落盘的东西——它当时拿"没补作答位、
    没规范化"的毛坯去审查，报了一堆 `空位在数学模式里`、`$ 个数是奇数` 的假阳性，
    而真正该抓的「（ `\paren[]` ）双括号」反而漏了。**检查的输入必须等于产物。**
    """
    q = make_question(r, "", "")
    # ⚠️ **先补作答位，再规范化**，顺序不能反。
    # 卷面上本来就印着「（  ）」，模型又照我们的要求写了个 `\paren[]`——
    # 两个都在的话，印出来是**两个括号**（正是 `去掉残留的空作答括号`
    # 那条规则要治的毛病）。但那条规则的判据是"题干里已经有 `\paren[…]`"，
    # 先跑规范化时还没有，它就什么都不做；等 `_answer_slot` 再补上，
    # 残留的空括号就永远留下了（第一版就是这么错的，96 道里 30 道带双括号）。
    q.stem = _answer_slot(q.stem, r["type"])
    # **规范化走唯一入口 `amti/normalize.py`**，这里不自己写规则。
    # 最主要的收益是「空位落在数学模式里」那条自愈：模型爱写成
    # `则 $\max M$ 的最小值为 $\fillin[]$。`，渲染时是嵌套数学模式。
    for name in N.normalize(q, N.ENTRY):
        if fired is not None:
            fired[name] = fired.get(name, 0) + 1
    # 全书没有答案，规范化里「解答题答案栏写见解析」那条不能留——
    # 解析是空的，写「见解析」是撒谎，也会让后期补答案判成"已有答案"。
    q.answer, q.solution = "", ""
    # 🌟 题库正文才是真相：答案栏必须和卷面一致，所以空答案就要把
    # `\paren[…]`/`\fillin[…]` 里的内容也清掉（正常情况下本来就是空的）。
    q.stem = re.sub(r"\\paren\s*\[[^\]]*\]", r"\\paren[]", q.stem)
    q.stem = re.sub(r"\\fillin\s*\[[^\]]*\]", r"\\fillin[]", q.stem)
    return q


def block_of(r: dict, lect: str, ltitle: str, fired: dict) -> list[str]:
    q = finalize(r, fired)
    stem = q.stem

    meta = {
        "book": BOOK, "label": "%s %s" % (lect, ltitle), "year": 2027,
        "lecture": lect, "lecture_title": ltitle,
        "source_no": r["n"], "origin_pdf_page": r["pdf_page"],
    }
    if r.get("part") == "练习":
        meta["part"] = "练习"
    if r["sec"] and r["sec"] != "-":
        meta["section"] = r["sec"]
    if r["source_in_stem"]:
        meta["source_in_stem"] = r["source_in_stem"]
    if r["continued"]:
        meta["continued"] = True
    figs = list(r["fig_stem"]) + list(r["fig_opts"].values())
    if r["fig_opts"]:
        meta["option_figures"] = sorted(r["fig_opts"])
    if r["figure"] and not figs:
        # 老规矩：带图题**一律登记原卷位置**，漏登记一道后期就漏处理一道
        meta["figure_todo"] = {"pdf_page": r["pdf_page"], "source_no": r["n"],
                               "desc": r["fig_desc"]}
    obj = {
        "key": key_of(r),
        "type": q.type,
        "answer": "",
        "options": [{"label": o.label, "text": o.text} for o in q.options],
        "stem": stem,
        "solution": "",
        "points": [],
        "figures": figs,
        "meta": meta,
    }
    body = ["%% @q " + json.dumps(obj, ensure_ascii=False, sort_keys=True),
            "\\begin{question}", stem]
    if q.options:
        body.append("\\begin{choices}")
        for o in q.options:
            img = r["fig_opts"].get(o.label)
            extra = (" \\includegraphics[width=0.15\\paperwidth]{%s}" % img
                     if img else "")
            body.append("\\item %s%s" % (o.text, extra))
        body.append("\\end{choices}")
    for name in r["fig_stem"]:
        body.append("\\includegraphics[width=0.4\\linewidth]{%s}" % name)
    body += ["\\end{question}", "\\begin{solution}", "\\end{solution}", ""]
    return body


def make_question(r: dict, lect: str = "", ltitle: str = ""):
    qtype_en = TYPE_EN.get(r["type"], "")
    if not qtype_en:                       # 判不出就按卷面有没有选项/空位回推
        if r["options"]:
            qtype_en = "single_choice"
        elif "\\fillin" in r["stem"]:
            qtype_en = "fill_in_blank"
        else:
            qtype_en = "detailed_answer"
    return Q(key=key_of(r), type=qtype_en,
             stem=r["stem"], answer="", solution="",
             options=[Option(label=k, text=v) for k, v in r["options"]])


# ══ report ════════════════════════════════════════════════════════


def cmd_report(a) -> int:
    scans = load_scans()
    rows = collect_questions(scans)
    print("%-18s %5s %5s %5s %5s %5s" % ("讲次", "题数", "单选", "多选", "填空", "解答"))
    for lect, title, _s, _e in lecture_map(scans):
        rs = [r for r in rows if r["lect"] == lect]
        if not rs:
            continue
        c = {t: sum(1 for r in rs if r["type"] == t) for t in TYPE_EN}
        print("%-18s %5d %5d %5d %5d %5d   %s"
              % (lect, len(rs), c["单选"], c["多选"], c["填空"], c["解答"], title))
    todo = sum(1 for r in rows
               if r["figure"] and not (r["fig_stem"] or r["fig_opts"]))
    print("合计 %d 道；带图题 %d 道（其中 %d 道还没裁到图）"
          % (len(rows), sum(1 for r in rows if r["figure"]), todo))
    return 0


def cmd_verify(a) -> int:
    r"""体检：**缺题、坏 LaTeX、格式违规**各查一遍。

    「识别质量」不能靠眼看几页就算数——真正会漏的是**每讲末尾那几道**
    （跨页、被小节标题挤走、模型提前收尾）。所以主检查是**题号连续性**：
    每讲的题号应当是 1..N 一个不缺；缺号就是漏题，逐条报出来。
    """
    scans = load_scans()
    rows = collect_questions(scans)
    problems = 0

    # ① 题号连续性
    print("【题号连续性】")
    lmap = lecture_map(scans)
    for lect, title, start, end in lmap:
      # 讲次还没跑完就不判缺号——**半成品报"缺 13–22"是噪声**，
      # 会把人训练成"看见缺号就跳过"，真的漏题时反而看不见了。
      pages = range(start, min(end, 340) + 1)
      if any(not (SCAN / ("p%03d.txt" % p)).exists() for p in pages):
        print("  %-14s %-4s ——（本讲还有页没跑，不判缺号）" % (lect, "-"))
        continue
      for part in ("例题", "练习"):
        ns = sorted(r["n"] for r in rows
                    if r["lect"] == lect and r.get("part") == part)
        if not ns:
            continue
        miss = sorted(set(range(1, max(ns) + 1)) - set(ns))
        dup = sorted({n for n in ns if ns.count(n) > 1})
        flag = "缺 %s" % miss if miss else "完整"
        if dup:
            flag += "；重 %s" % dup
        if miss or dup:
            problems += len(miss) + len(dup)
        print("  %-14s %-4s 1..%-3d  %s" % (lect, part, max(ns), flag))

    # ② 走项目自己的 LaTeX 解析器（**唯一懂 LaTeX 的那份**）
    print("【LaTeX 解析】")
    from amti import latex_ir
    for lect, title, _s, _e in lmap:
        f = OUT / ("%s.tex" % lect)
        if not f.exists():
            continue
        blocks = latex_ir.split_questions(f.read_text(encoding="utf-8"))
        n_bad = sum(1 for b in blocks if latex_ir.parse_question(b) is None)
        print("  %-14s %d 块，解析失败 %d" % (lect, len(blocks), n_bad))
        if n_bad:
            problems += n_bad
            print("  ✗ %s 有解析不出来的块" % lect)

    # ③ 规范审查（conform 的纯文本检查，不吃答案/图片缺失那几项）
    print("【规范审查】")
    from amti import conform
    qs = [finalize(r) for r in rows]
    hits = conform.run(qs, image_resolver=lambda n: (FIGDIR / n).exists())
    for h in hits[:40]:
        print("  %s  %s" % (h["key"], h["why"]))
    if len(hits) > 40:
        print("  … 其余 %d 处" % (len(hits) - 40))
    problems += len(hits)

    # ④ 空产物 / 可疑页 / 输出被截断
    print("【可疑页】")
    for n, pg in sorted(scans.items()):
        if pg["page"]["kind"] in ("封面", "目录", "空白", "课堂总结",
                                  "讲次扉页"):
            continue          # 讲次扉页本来就没有题，不算"可疑"
        if not pg["questions"]:
            print("  p%03d kind=%s 一题都没识别出来" % (n, pg["page"]["kind"]))
            problems += 1

    # ⑤ 截断：正常一页的输出应当停在 `@@ENDQ`。
    # 停不住就是被 `max_tokens` 掐了——**这种漏题最阴**，题号连续性看不出来
    # （缺的是本页最后一道），只有看收尾标记才抓得到。
    print("【输出收尾】")
    for f in sorted(SCAN.glob("p*.txt")):
        lines = [x.strip() for x in f.read_text(encoding="utf-8").splitlines()
                 if x.strip()]
        if not lines:
            continue
        last = lines[-1]
        if not (last.startswith(("@@ENDQ", "@@PAGE", "@@SEC"))
                or last == "-"):
            print("  %s 没有正常收尾（末行：%s）" % (f.stem, last[:50]))
            problems += 1
    # ⑥ 模型自己标了「看不清」的地方——**必须人工过一遍**，不能静默放过
    unclear = [f.stem for f in sorted(SCAN.glob("p*.txt"))
               if "【?】" in f.read_text(encoding="utf-8")]
    if unclear:
        print("  含「看不清」标记的页（%d）：%s" % (len(unclear), unclear))
        problems += len(unclear)

    print("\n合计问题 %d 处" % problems)
    return 1 if problems else 0


def cmd_selftest(a) -> int:
    r"""自检：**先证明这几条踩过坑的判据还管用**，再说"跑批没问题"。

    每一条都对应本脚本真实踩过的一个坑，不是凑数：
      `split_source` 的三种出处写法 + 「`$` 不能被吃掉」的反例、
      `parse_text` 的题型小节跟随与 figbox 透传、
      `_figbox` 的两种坐标制、`lect_of` 的打印页码偏移。
    """
    fails = []

    def check(name, cond, extra=""):
        if cond:
            print("  ✓ %s" % name)
        else:
            fails.append(name)
            print("  ✗ %s  %s" % (name, extra))

    print("赵礼显讲义录题 自检")

    # 出处：三种真实写法都要能摘干净，且 `$` 的奇偶不变
    for raw, want_src, want_head in [
        (r"$(2025\cdot$ 保定模拟 $)$ 记 $\max M$ 为最大数", "2025·保定模拟",
         r"记 $\max M$ 为最大数"),
        (r"(2025·潍坊二模) $\forall x \in R, |x-1|\geqslant 4$，则 $a$ 的范围"
         r"是 \fillin[]。", "2025·潍坊二模",
         r"$\forall x \in R, |x-1|\geqslant 4$，则 $a$ 的范围是 \fillin[]。"),
        (r"(2013·湖北) $x$ 为实数。", "2013·湖北", r"$x$ 为实数。"),
        (r"$(2026\cdot$ 天津期末 $)$ 已知正实数 $a, b, c$", "2026·天津期末",
         r"已知正实数 $a, b, c$"),
    ]:
        stem, src, _ = split_source(raw, "单选")
        check("出处 %r" % raw[:14], src == want_src and stem == want_head,
              "src=%r stem=%r" % (src, stem))

    # 第二种裹壳写法：`$(北大自主招生)$`（inner 里**没有** `$`）。
    # 第一版按"inner 里有没有 `$`"判断，这种判不出来 → 收尾 `$` 留下 →
    # 奇偶守卫再补一个 → 题干开头变成 `$$`（xelatex 直接报错）。
    stem, src, _ = split_source(
        r"$(北大自主招生)$ 已知 $a, b, c \in R_+$ 且 $a+b+c=1$，则 $x$ 最大。", "填空")
    check("出处 `$(X)$`（inner 无 `$`）也要摘干净、且不出 `$$`",
          src == "北大自主招生" and "$$" not in stem
          and stem.startswith("已知"), "src=%r stem=%r" % (src, stem))
    # 反例：`$` 的奇偶变了就是吃错了——这是 `(2025·潍坊二模) $\forall…`
    # 被改成 `\forall…` 那次事故的守卫
    for raw in [r"(2025·潍坊二模) $\forall x \in R, |x-1|\geqslant 4$，则 $a$ 是 \fillin[]。",
                r"$(2026\cdot$ 安徽滁州一模 $)$ 若 $x \in (0, +\infty)$，则 $\paren[]$"]:
        stem, _, _ = split_source(raw, "单选")
        check("出处摘完 `$` 仍成对 %r" % raw[:12], stem.count("$") % 2 == 0,
              repr(stem))
    # 反例：`（1）`、`（多选）` 不是出处
    stem, src, t = split_source("（多选）下列正确的是 \\paren[]", "单选")
    check("「（多选）」改判题型、不当出处", src == "" and t == "多选"
          and stem.startswith("下列"), "%r %r" % (src, stem))
    stem, src, _ = split_source("（1）求 $f(x)$ 的单调区间；", "解答")
    check("「（1）」不是出处", src == "" and stem.startswith("（1）"), repr(stem))

    # parse_text：题型小节要跟着题走，figbox 要透传
    text = ("@@PAGE kind=正文 title=-\n\n"
            "@@SEC 题型一：基本不等式\n"
            "@@Q n=3 type=单选 figure=有 continued=否 figbox=120,300,700,600\n"
            "@@STEM\n则 $x+y$ 的最小值为 $\\paren{}$\n@@OPT\nA. $1$\nB. $2$\n"
            "@@FIG\n一条抛物线\n@@ENDQ\n"
            "@@Q n=4 type=填空 figure=无 continued=否 figbox=-\n"
            "@@STEM\n则 $a=$ $\\fillin{}$。\n@@OPT\n-\n@@FIG\n-\n@@ENDQ\n")
    pg = parse_text(text)
    qs = pg["questions"]
    check("parse_text 认两题", len(qs) == 2, str(len(qs)))
    check("题型小节跟着题走", all(q["sec"] == "题型一：基本不等式" for q in qs),
          str([q["sec"] for q in qs]))
    check("figbox 透传（record.parse_marked 会丢它）",
          qs[0]["figbox"] == "120,300,700,600" and qs[1]["figbox"] == "-",
          str([q["figbox"] for q in qs]))
    check("figure 标志与选项", qs[0]["figure"] is True
          and [k for k, _ in qs[0]["options"]] == ["A", "B"],
          str(qs[0]["options"]))

    # _figbox：千分比 / 0–1 比例 / 坏值
    box = _figbox("100,200,900,800", 1000, 1000)
    check("_figbox 千分比", box is not None and box[0] < 100 and box[2] > 900,
          str(box))
    check("_figbox 收 0–1 比例", _figbox("0.1,0.2,0.9,0.8", 1000, 1000) == box,
          str(_figbox("0.1,0.2,0.9,0.8", 1000, 1000)))
    for bad in ("-", "", "1,2,3", "900,800,100,200", "0,0,10,10"):
        check("_figbox 拒收 %r" % bad, _figbox(bad, 1000, 1000) is None)

    # lecture_map / lect_of：讲次由**页眉标题**决定，不由目录页码决定
    fake = {9: {"page": {"kind": "正文", "title": "第1讲：不等式(1)"}, "questions": []},
            16: {"page": {"kind": "正文", "title": "第2讲：不等式(2)"}, "questions": []},
            163: {"page": {"kind": "讲次扉页", "title": "秋季讲义"}, "questions": []},
            164: {"page": {"kind": "正文", "title": "第1讲：平面向量"}, "questions": []},
            264: {"page": {"kind": "正文", "title": "第14讲：抛物线进阶"}, "questions": []},
            317: {"page": {"kind": "正文", "title": "排列组合方法梳理(1) —视频赠课"},
                  "questions": []},
            340: {"page": {"kind": "正文", "title": "-"}, "questions": []}}
    lm = lecture_map(fake)
    check("讲次由页眉标题推出（不是目录页码）",
          [x[0] for x in lm] == ["暑假第1讲", "暑假第2讲", "秋季第1讲",
                                 "秋季第14讲", "秋季·排列组合方法梳理(1)"],
          str([x[0] for x in lm]))
    check("讲次区间首尾相接", lm[0][3] == 15 and lm[1][2] == 16 and lm[-1][3] == 340,
          str([(x[2], x[3]) for x in lm]))
    check("PDF 9 → 暑假第1讲", lect_of(9, lm)[0] == "暑假第1讲", lect_of(9, lm)[0])
    check("PDF 300 → 秋季第14讲（不是被目录截断的第12+13讲）",
          lect_of(300, lm)[0] == "秋季第14讲", lect_of(300, lm)[0])
    check("封面页不属于任何讲", lect_of(3, lm)[0] == "", lect_of(3, lm)[0])

    # key：练习必须和例题分开（撞 key 是实测事故）
    a = {"lect": "暑假第1讲", "n": 1, "part": "例题"}
    b = {"lect": "暑假第1讲", "n": 1, "part": "练习"}
    check("练习与例题 key 不同", key_of(a) != key_of(b),
          "%s / %s" % (key_of(a), key_of(b)))

    print("\n自检 %s（%d 项失败）"
          % ("通过" if not fails else "**未通过**", len(fails)))
    return 1 if fails else 0


def _range(spec: str) -> tuple[int, int]:
    a, _, b = spec.partition("-")
    return int(a), int(b or a)


def _main() -> int:
    ap = argparse.ArgumentParser(description="赵礼显讲义 → 题库格式")
    ap.add_argument("cmd", choices=["scan", "boxes", "figs", "build",
                                    "report", "verify", "selftest"])
    ap.add_argument("--only", default="", help="页码区间，如 20-40")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    return {"scan": cmd_scan, "boxes": cmd_boxes, "figs": cmd_figs,
            "build": cmd_build,
            "report": cmd_report, "verify": cmd_verify,
            "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(_main())
