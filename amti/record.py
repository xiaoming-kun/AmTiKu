r"""AmTiKu · 试卷录题（本地大模型识别）

把**扫描版试卷 PDF**（答案可能另在一个文件里）变成能喂给 `ingest` 的
exam-zh LaTeX。链路：

    PDF → 页图（fitz 原扫描图直取，不重编码）→ 本地 VLM 逐页识别
        → 跨页合并 → 答案/解析配对 → 带图题过滤 → 组装 LaTeX

三条规矩（用户 2026-09-16 定，写死在代码里）：

1. **带图题一律不录**。只有第 8/11/14/18/19 题的带图题**登记原卷位置**
   （哪份 PDF、第几页、图上中下），正文不入库。
2. 题目 ↔ 答案 ↔ 解析**一一对应**；没有解析的写「解析无」。
3. 每题都带出处（如「2026新课标I卷」）与**原卷题号**。

归一化、查重、落盘**都不在这里**——那是 `ingest` 的活。本模块只负责
把「卷面像素」变成「干净、能过 conform 的 LaTeX 文本」。

用法：
    python3 -m amti.record --pdf 试卷.pdf --answers 答案.pdf \\
        --book 模拟题 --label 2026深圳中学摸底 --region 深圳 --year 2026
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
WORK = PKG / "数据" / "录题"
API = "http://127.0.0.1:1234/v1/chat/completions"
MODEL = "qwen/qwen3.8-27b"
MAX_TOKENS = 4000
# 单页图的**像素预算**。LM Studio 里这份模型是按 8192 上下文加载的，
# 而一页扫描图 2266×3358 ≈ 7.6M 像素 ≈ 7900 个图像 token —— 加上提示词
# 和输出直接爆掉，服务端会**默默掐断连接**：实测一批 4 个请求死 3 个，
# 而且不返回任何错误，只留下一堆 CLOSE_WAIT。压到 200 万像素
# （≈2100 token）就稳了。实测 1240×1753 这档的公式识别是准的。
MAX_PIXELS = 2_000_000

# 带图的题只登记这几个位置的（别的直接丢）
FIG_KEEP = {"8", "11", "14", "18", "19"}
TYPE_MAP = {"单选": "single_choice", "多选": "multi_choice",
            "填空": "fill_in_blank", "解答": "detailed_answer"}
NO_SOLUTION = "解析无"

PROMPT = r"""你是高中数学题库录入员。下面是一份高三数学试卷的其中一页扫描图。
你的唯一任务是**忠实转录**：不解答、不翻译、不改写、不补充、不合并。

严格按下面的标记输出，**除标记外不要写任何别的内容**（不要 markdown 标题、不要解说）：

@@PAGE kind=<试题|答案|封面|目录|空白> title=<首页写卷面标题，其余页写 ->

（本页有几道题就写几段下面这样的块）
@@Q n=<卷面题号，纯数字> type=<单选|多选|填空|解答|-> figure=<有|无> continued=<是|否>
@@STEM
<题干原文。行内公式用 $…$；数学里的中文用 \text{}；卷面的作答空位选择题写 \paren[]、
 填空题写 \fillin[]；小题 (1)(2) 直接写在文字里。答案页上的题这里写 ->
@@OPT
<只有选择题写，每行一个：A. 内容 ；不是选择题写 ->
@@FIG
<figure=有时写一句话描述图长什么样；否则写 ->
@@ANS
<这道题的**答案**：选择题只写字母（如 A，多选如 ABD）；填空题只写结果；
 解答题写最终结论。没有写 ->
 ⚠️ 填空题有**多个空**时，用中文分号「；」把各空答案按顺序隔开（如 5；7），
    不要用逗号——逗号是答案内容的一部分（坐标 (1,2) 里就有逗号）。
@@SOL
<这道题的**解析/解答过程**原文（逐字转录，含推理步骤）。没有写 ->
@@ENDQ

另外两种单行标记：
@@KEY 1.A 2.B 3.C
（本页出现「答案速查表 / 参考答案」那种一行一串的表格时用它）
@@FIGPOS n=<题号> y=<上|中|下> x=<左|中|右>
（只在本页有 figure=有 且 题号是 8、11、14、18、19 时写，描述图在页面上的位置）

铁律：
1. 只转录本页看得见的内容，不要凭记忆或上下文补全。
2. 看不清的字写 \text{【?】}，**不要猜**。
3. 数字、符号、上下标、单位一个都不能改。
4. 不要写 \begin{question} 之类的环境，不要加排版。
5. 页眉、页脚、页码、「数学试题 第X页 共Y页」不输出。
6. 一道题跨页时，本页只写看得见的那部分，continued=是。
"""

# ── 模型调用 ──────────────────────────────────────────────────────

# 上一次调用的元信息（耗时/finish_reason）。**按线程存**——
# `workers>1` 时 4 个线程共用一个 dict，谁后写谁赢，
# 记下来的耗时会张冠李戴（"这一页 377 秒"其实是别的页的）。
_TL = threading.local()


def last() -> dict:
    return getattr(_TL, "last", {})


def shrink(img: Path, *, max_px: int = MAX_PIXELS) -> Path:
    r"""把页图压进 token 预算。**超过预算的图不能发给模型**——见 `MAX_PIXELS`。

    缩好的图放 `<work>/small/`，跟 `pages/` 分开：`pages_of` 靠
    `p001.*` 找缓存，缩小图混进去会让它认错文件。
    """
    from PIL import Image

    with Image.open(img) as im:
        w, h = im.size
        if w * h <= max_px:
            return img
        k = (max_px / (w * h)) ** 0.5
        out = img.parent.parent / "small" / (img.stem + ".jpg")
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            im.convert("RGB").resize((max(1, int(w * k)), max(1, int(h * k))),
                                     Image.LANCZOS).save(out, quality=92)
        return out


def ask(img: Path, *, timeout: int = 2400, prompt: str = PROMPT,
        max_tokens: int = MAX_TOKENS, note: str = "转录这一页。") -> str:
    r"""把一页图丢给本地 VLM，返回标记文本。

    ⚠️ **必须用 `reasoning_effort="none"` 关思考。**
    这个模型一共只有 8192 上下文，而它默认会在 `reasoning_content` 里想很久，
    `max_tokens` **把思考和正文一起算**——实测 p002 那一页 4000 个 token
    全烧在思考上（`reasoning_tokens: 3999`），正文**一个字都没有**，
    `finish_reason=length`。转录是抄写不是解题，不需要思考。

    换了几种写法只有这个真管用（拿一道需要推理的题量过）：

        chat_template_kwargs={"enable_thinking": False}  reasoning=141  ← 被忽略
        chat_template_kwargs={"thinking": False}         reasoning=134  ← 被忽略
        system 里加 /no_think                            reasoning=137  ← 被忽略
        reasoning_effort="none"                          reasoning=0    ← ✓
    """
    img = shrink(img)
    mime = "image/png" if img.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(img.read_bytes()).decode()
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                {"type": "text", "text": note},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "reasoning_effort": "none",
    }).encode()
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    ch = d["choices"][0]
    _TL.last = {"secs": round(time.time() - t0, 1),
                "finish": ch.get("finish_reason") or "",
                "usage": d.get("usage") or {}}
    return ch["message"]["content"] or ""


# ── 按题裁剪 ──────────────────────────────────────────────────────
#
# 为什么不一页一喂（用户 2026-09-16 定的方向，实测站得住）：
#   ① 整页图 ~2100 图像 token，把 8192 的上下文吃掉四分之一，正文被挤掉；
#      一道题裁出来只有 ~300 token，同样的槽能塞下多得多的请求。
#   ② 一页一输出，长页会截断（`finish_reason=length`），截断就是静默丢题。
#   ③ 页内的题互相独立，**可以真并发**——这才吃得满 LM Studio 的多个槽。
#   ④ 跨页拼接、答案页重述题干、幽灵题这些坑，本来都出在「一页一坨」上。
#
# 切法**不用模型**，用版式：这 15 份卷子的题干（以及答案页的每条解析）
# 都从卷面**最左的文字列**开始，选项行和小题行是缩进的。逐行求左边界，
# 跟全页最小左边界齐平的行就是题目起点。

HEAD_PROMPT = r"""这是一份高中数学试卷的其中一页扫描图。**只回答两件事，不要转录题目**：

@@PAGE kind=<试题|答案|封面|目录|空白> title=<首页写卷面标题，其余页写 ->
"""


def bands_of(img: Path, *, tol: int | None = None,
             gap: int = 16) -> list[tuple[int, int]]:
    r"""把一页按纵向切成「疑似一道题」的条带，返回 `[(y0, y1), …]`。

    小节标题（「二、选择题：本题共…」）跟题干一样齐左边界，会多切出一块——
    那块交给模型自己说「@@NONE」丢掉，比在几何上区分它们可靠得多。
    页眉页脚一般居中，不齐左边界，天然切不进来。

    ⚠️ **容差要按页宽算，不能给死数。** 同一列的字（题号 `12.`）左边界
    实测散布在 120~136 px（扫描歪一点就差十几像素），而缩进的选项行在
    193 px 起——都是 2400 px 宽的页。给死 `tol=10` 会把一半题干行漏掉，
    于是题被拦腰切成两段。按页宽 1.5%（约 36 px）刚好把两簇分开。
    """
    import numpy as np
    from PIL import Image

    with Image.open(img) as im:
        a = np.asarray(im.convert("L"))
    dark = a < 160
    h, w = dark.shape
    tol = max(12, int(w * 0.015)) if tol is None else tol
    ink = dark.sum(axis=1)

    lines: list[tuple[int, int]] = []
    s = None
    for y, v in enumerate(ink > 2):
        if v and s is None:
            s = y
        elif not v and s is not None:
            if y - s >= 8:                       # 太矮的当噪点
                lines.append((s, y))
            s = None
    if s is not None:
        lines.append((s, h))
    if not lines:
        return []

    lefts = []
    for y0, y1 in lines:
        cols = np.where(dark[y0:y1].any(axis=0))[0]
        lefts.append(int(cols[0]) if len(cols) else 10 ** 6)
    base = min(lefts)
    starts = [k for k, L in enumerate(lefts) if L <= base + tol]

    # ⚠️ **切点必须落在真正的空白行上，不能"行首往上挪固定像素"。**
    # 原来写的是 `lines[k][0] - gap`：两行之间只有 5px 空白时，这 16px 就切进
    # 上一行的字里，把数字切成半个——实测「9.」被切成了「3.」、「10.」成了
    # 「4.」，那几道题的解析整段归错题、等于丢了。
    # 现在往上/往下找最近的空白行，找不到就不切（宁可条带大一点）。
    blank = [(i, i + 1) for i, v in enumerate(ink <= 2) if v]

    def snap_up(y: int) -> int:
        cur = y
        while cur > 0 and ink[cur] > 2:
            cur -= 1
        return max(0, cur)

    def snap_dn(y: int) -> int:
        cur = min(y, h - 1)
        while cur < h - 1 and ink[cur] > 2:
            cur += 1
        return cur

    out = []
    for j, k in enumerate(starts):
        y0 = snap_up(max(0, lines[k][0] - gap))
        y1 = snap_dn(lines[starts[j + 1]][0] - gap) if j + 1 < len(starts) else h
        if y1 - y0 >= 24:
            out.append((y0, min(y1, h)))
    return out


def crop_band(img: Path, band: tuple[int, int], dst: Path) -> Path:
    """裁出条带存成 jpg（比 png 小得多，base64 发出去也快）。"""
    from PIL import Image

    with Image.open(img) as im:
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.crop((0, band[0], im.width, band[1])).convert("RGB").save(
            dst, quality=92)
    return dst


QPROMPT = r"""这是同一份高中数学试卷上**一道题**的裁剪图（上下可能带一点邻题的边角）。

只转录图里这一道题。**如果这张图里根本没有题目**——比如只是
「二、选择题：本题共 3 小题…」这种小节标题，或者页眉页脚——就只输出一行：

@@NONE

否则严格按下面的标记输出，除标记外不要有别的内容：

@@Q n=<卷面题号，纯数字> type=<单选|多选|填空|解答> figure=<有|无>
@@STEM
<题干原文。行内公式用 $…$；数学里的中文用 \text{}；选择题的作答空位写 \paren[]，
 填空题的空位写 \fillin[]；小题 (1)(2) 直接写在文字里。>
@@OPT
<只有选择题写，每行一个：A. 内容 ；不是选择题写 ->
@@FIG
<figure=有时用一句话描述图长什么样；否则写 ->
@@ANS
<答案：选择题只写字母（多选如 ABD）；填空题只写结果；解答题写最终结论。图上没有写 ->
@@SOL
<解析/解答过程原文。图上没有写 ->
@@ENDQ

铁律：
1. 只转录图上看得见的，不要凭记忆或上下文补全。
2. 看不清的字写 \text{【?】}，**不要猜**。
3. 数字、符号、上下标、单位一个字都不能改。
4. 图里若带着上一题的尾巴（半道题、孤立的选项行），**不要输出它**。
5. 填空有多个空时，答案用中文分号「；」按顺序隔开（如 5；7），不要用逗号。
"""


# 扫描件上的水印/推广字样。**必须滤掉**——实测洛阳那份的解析被写进了
# 「小红书号: 9693853293」，还有「……6分」之类的页脚混进来。
_WATERMARK = re.compile(
    r"小红书|抖音|微信|公众号|扫描全能王|CamScanner|夸克|百度文库"
    r"|https?://|www\.|号\s*[:：]\s*\d{4,}")


def strip_watermark(text: str) -> str:
    """逐行滤掉水印/推广；整行命中才删，避免误伤正文。"""
    return "\n".join(l for l in text.splitlines()
                     if not _WATERMARK.search(l))


def _atomic(dst: Path, obj) -> None:
    """原子写 json：批量与界面可能同时读同一份缓存，半截文件会让对方直接崩。"""
    tmp = dst.with_name("%s.%d.tmp" % (dst.name, threading.get_ident()))
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, dst)


def scan_page(img: Path, cache: Path, no: int, *, force: bool = False) -> dict:
    r"""一页 → 该页的题目。

    **转录引擎换了（2026-09-16 实测对拍）**：交给 PaddleOCR-VL（0.9B，跑在
    独立的 llama.cpp 服务上），不再用 27B 转录。

    | | PaddleOCR-VL 0.9B | Qwen 27B |
    |---|---|---|
    | 一条题裁剪 | **0.2～2.3 秒** | 14～78 秒 |
    | 一页 10 条 | **8.9 秒** | 60～300 秒 |
    | 数学 LaTeX | 对 | 对 |
    | 执行指令 | **完全无视** | 会听话 |

    它是**纯 OCR 模型**——给什么指令都只照抄图里的字。所以三件事要另想办法：

    1. **页类型**不问模型，直接看文本里有没有「【答案】/【解析】」。
    2. **切题**仍用几何（`bands_of`），但 OCR 完要**拼回整页再按题号切**：
       答案页的解析段落也齐左边界，几何上会被切碎。
    3. **判有没有图**用「正则粗筛 + 27B 复核」（见 `check_figure`）。
    """
    # ① **文本走整页 OCR**，不做几何切分。
    #    实测按条带裁会把题号切坏（「9.」读成「3.」、「10.」读成「4.」，
    #    那几道题的解析整段归错题、等于丢了）；整页一次读就没有这个问题，
    #    而且更快（一页 5～18 秒，`finish=stop` 不截断）。
    res = cache / f"p{no:03d}.txt"
    if res.exists() and not force:
        text = res.read_text(encoding="utf-8")
    else:
        text = strip_watermark(ocr_page(img))
        tmp = res.with_name("%s.%d.tmp" % (res.name, threading.get_ident()))
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, res)

    is_ans = len(re.findall(r"【(?:答案|解析|详解)】", text)) >= 2
    page = {"kind": "答案" if is_ans else "试题", "title": _first_line(text)}
    _atomic(cache / f"p{no:03d}.head.json", page)

    blocks = split_by_number([(1, text)])
    if not blocks and text.strip():
        blocks = [("", text, 1, 1, "")]

    # ② **条带只用来定位**（判图要回图上问），不再参与文本解析。
    bands = bands_of(img)
    band_txt: list[str] = []
    for bi, band in enumerate(bands, 1):
        crop = cache.parent / "crops" / f"p{no:03d}_{bi:02d}.jpg"
        if not crop.exists():
            crop_band(img, band, crop)
        bt = cache / f"p{no:03d}_{bi:02d}.txt"
        if bt.exists() and not force:
            band_txt.append(bt.read_text(encoding="utf-8"))
        else:
            t = ask_ocr(crop)
            tmp = bt.with_name("%s.%d.tmp" % (bt.name, threading.get_ident()))
            tmp.write_text(t, encoding="utf-8")
            os.replace(tmp, bt)
            band_txt.append(t)

    qs = []
    for n, block, b0, b1, sec in blocks:
        q = parse_block(n, block, sec)
        if q is None:
            continue
        q["pages_bands"] = [b0, b1]
        q["figure"] = bool(check_figure_on(img, bands, band_txt,
                                           q["stem"] + " " + " ".join(
                                               o[1] for o in q["options"])))
        qs.append(q)
    return {"page": page, "key": {}, "figpos": {}, "questions": qs,
            "text": text}


def ocr_page(img: Path, *, depth: int = 0) -> str:
    r"""整页 OCR。**截断了就对半再切**（而不是按题号几何切）。

    整页输出的是一整段文本，题号切分在文本层做（`split_by_number`），
    所以不存在"切在数字上"的问题。真遇到超长页（`finish_reason=length`），
    沿**空白行**对半切开分别识别再拼起来——几何切分只在"兜底"时出现，
    而且切在空白处，不会伤到字。
    """
    b64 = base64.b64encode(shrink(img).read_bytes()).decode()
    body = json.dumps({
        "model": OCR_MODEL,
        "messages": [{"role": "system", "content": OCR_SYS},
                     {"role": "user", "content": [
                         {"type": "text", "text": "转录这一页。"},
                         {"type": "image_url",
                          "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
        "temperature": 0.0, "max_tokens": 8000}).encode()
    req = urllib.request.Request(OCR_API, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read().decode())
    ch = d["choices"][0]
    txt = (ch["message"]["content"] or "").strip()
    if ch.get("finish_reason") != "length" or depth >= 3:
        return txt
    top, bot = split_half(img)
    return ocr_page(top, depth=depth + 1) + "\n" + ocr_page(bot, depth=depth + 1)


def split_half(img: Path) -> tuple[Path, Path]:
    """沿**最靠近中间的空白行**把页图切成上下两半。"""
    import numpy as np
    from PIL import Image

    with Image.open(img) as im:
        a = np.asarray(im.convert("L"))
        h, w = a.shape
        ink = (a < 160).sum(axis=1)
        mid = h // 2
        cut = next((y for off in range(h // 2)
                    for y in (mid - off, mid + off)
                    if 0 < y < h and ink[y] <= 2), mid)
        top = img.with_name(img.stem + "_top.png")
        bot = img.with_name(img.stem + "_bot.png")
        im.crop((0, 0, w, cut)).save(top)
        im.crop((0, cut, w, h)).save(bot)
    return top, bot


def check_figure_on(img: Path, bands: list, band_txt: list[str],
                    text: str) -> bool:
    r"""判这道题有没有配图——**只对题干里提到「图」的题**去问 27B。

    条带只用来定位：谁的文字跟这道题的题干最像，谁就是它的区域。
    这样即使条带 OCR 把某个数字读坏了（实测有），也能靠相似度对上。
    """
    if not _FIG_WORD.search(text or ""):
        return False
    key = re.sub(r"\s|\\[a-zA-Z]+|[{}$\\]", "", text)[:40]
    best, score = None, 0.0
    for bi, bt in enumerate(band_txt, 1):
        b = re.sub(r"\s|\\[a-zA-Z]+|[{}$\\]", "", bt)
        if not b:
            continue
        from difflib import SequenceMatcher
        r = SequenceMatcher(None, key, b[:max(len(key), 80)]).ratio()
        if r > score:
            best, score = bi, r
    if not best:
        return True                      # 定位不到也不能当"没有"
    crop = img.parent.parent / "crops" / ("%s_%02d.jpg" % (img.stem, best))
    if not crop.exists():
        return True
    return ask_figure(crop)


def ask_figure(crop: Path) -> bool:
    """问 27B：这张图里除了文字，还有几何图形/函数图象/统计图表吗。"""
    b64 = base64.b64encode(crop.read_bytes()).decode()
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": FIG_SYS},
                     {"role": "user", "content": [
                         {"type": "text", "text": "看图回答。"},
                         {"type": "image_url",
                          "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
        "temperature": 0.0, "max_tokens": 10,
        "reasoning_effort": "none",     # 不关思考，10 个 token 全烧在推理上
    }).encode()
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode())
    except Exception:                                      # noqa: BLE001
        return True                     # 问不出来就按"有图"处理，宁可少录
    return "有" in (d["choices"][0]["message"]["content"] or "")


def _first_line(s: str) -> str:
    return (s.strip().splitlines() or [""])[0][:80]


# ── OCR 文本 → 结构 ───────────────────────────────────────────────

OCR_API = "http://127.0.0.1:1235/v1/chat/completions"
OCR_MODEL = "paddleocr"
OCR_SYS = ("你是数学题库录入员。忠实转录图中全部数学内容，行内公式用 $…$ 表示，"
           r"看不清的字写 \text{【?】}，不要解答、不要改写、不要补充。")
# 题干里提到这些词才值得去问 27B「有没有图」。**是粗筛不是判据**——
# 实测「为了得到 y=cos2x 的图象」这种纯代数题也会命中，所以必须复核。
_FIG_WORD = re.compile(
    r"如图|图中|图象|图像|图形|图所示|如下图|右图|左图|统计图|直方图|茎叶图"
    r"|程序框图|直观图|三视图|散点图|条形图|扇形图|折线图|频率分布|坐标系")
# 题号。**不能只认行首**：答案页常把几个小题的答案挤在一行
# （实测 `12. $\sqrt{6}$  13. $\frac{\pi}{2}$  14. 24`），只认行首会漏掉一半答案。
# 放宽到「行首或空白之后」，再由 `split_by_number` 用**题号递增**把它筛干净。
# ⚠️ 末尾那个 `(?!\d)` 是**排除小数点**：统计表格和参考数据里全是
# `0.1`、`0.05`、`3.841` 这种，没有它就会被读成题号 `0.`
# （实测银川一中第 16 题的列联表把整页切成了 13 个假题）。
_QNUM = re.compile(r"(?:^|[ \t])(\d{1,2})[ \t]*[.．、][ \t]*(?!\d)", re.M)
_MARK = re.compile(r"【(答案|解析|详解|分析|解|点评)】")
# 选项标号。**不能只认行首**：实测同一行的 `A. 极差是10  B. 平均数是6` 很常见。
_LAB = re.compile(r"([A-D])[ \t]*[.．、][ \t]*")
# 小节标题：「二、选择题：本题共3小题…」。题型判定看它，不看正文猜。
_SECTION = re.compile(r"^[ \t]*[一二三四五六七八九十][ \t]*[、.][ \t]*(.{0,40})", re.M)


def split_options(text: str) -> tuple[str, list[tuple[str, str]]]:
    r"""把题干和选项拆开。选项可能一行一个，也可能挤在同一行。

    只认**从 A 开始**的那一串标号，其它字母（比如解答题里的 $A$、$B$）
    不会被误当成选项。
    """
    ms = list(_LAB.finditer(text))
    ms = [m for m in ms if m.group(1) == "A"][:1] + []
    if not ms:
        return text.strip(), []
    rest = text[ms[0].start():]
    head = text[:ms[0].start()].strip()
    marks = list(_LAB.finditer(rest))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(rest)
        out.append((m.group(1), rest[m.end():end].strip()))
    return head, out


def guess_type(section: str, stem: str, opts: list) -> str:
    r"""题型：**先看小节标题**，标题没有才看结构。

    看标题是规矩（`设计/识图录入提示词.md`：类型判定看分节标题，不看正文猜）
    ——多选和单选光看正文分不出来，标题里那句「有多项符合题目要求」才是依据。
    """
    # **小节标题跟结构矛盾时，以结构为准。**
    # 整页 OCR 会漏掉小节标题（实测 A9 那份漏了「三、填空题」），
    # 于是填空/解答题继承了上一节的「选择题」，被按"选项不足 2 个"丢掉——
    # 一次漏标题丢了 4 道题。选项数是最硬的证据：没有两个以上选项就不是选择题。
    if "选择" in section and len(opts) >= 2:
        return "多选" if "多项" in section else "单选"
    for k, v in (("填空", "填空"), ("解答", "解答"), ("证明", "解答")):
        if k in section:
            return v
    if len(opts) >= 2:
        return "单选"
    if re.search(r"▲|＿|_{3,}|\\underline|\\fillin|\\underline\{\\hspace", stem):
        return "填空"
    return "解答"


# 卷首的「考试说明」——**它们也带 1. 2. 3. 的编号**，会被当成题目切进来，
# 而且占掉 1~4 的题号，把真题挤掉（真题编号不递增就被序列过滤器丢了，
# 正文并进说明块）。实测 13 份卷子里 10 份中招，24 道假题入库。
# 判据三条一起用：命中这些词 + 没有选项 + 没有任何数学记号。
# ⚠️ 名字别叫 `_NOISE` —— 下面卷名清洗那儿**已经有一个 `_NOISE`** 了，
# 同名会被后定义的覆盖掉，`is_noise` 就永远不生效（这个坑真踩过：
# 过滤加了、测试没加，跑完一遍才发现说明文字还在库里）。
_INSTRUCTION = re.compile(
    r"答题卡|准考证|考生|2B\s*铅笔|考试时间|答卷前|涂黑|条形码|考试结束"
    r"|本试卷共|满分\s*\d+|本题共\s*\d+\s*小?题|只有一项是符合题目要求")


def is_noise(block: str, opts: list) -> bool:
    """这段是不是「考试说明 / 小节标题 / 答案表头」而不是一道题或一段解析。"""
    if _TABLE_ROW.search(block):        # 「题号 | 1 | 2 …」这种速查表
        return True
    if opts or "$" in block or "\\(" in block:
        return False
    return bool(_INSTRUCTION.search(block))


def parse_block(n: str, block: str, section: str = "") -> dict | None:
    r"""一道题的 OCR 文本 → 结构化字段。

    两种块都吃：

    * 试卷页：`12. 二项式 $(x+1)^6$ 展开式中第 4 项系数是 ▲ .（用数字作答）`
    * 答案页：`12. 【答案】20 【解析】第 4 项对应 $k=3$，系数为 …`
    """
    marks = list(_MARK.finditer(block))
    ans = sol = ""
    stem = block
    if marks:
        stem = block[:marks[0].start()].strip()
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(block)
            seg = block[m.end():end].strip()
            if m.group(1) == "答案":
                ans = seg
            elif seg:
                sol = (sol + "\n" + seg).strip()
    stem, opts = split_options(stem)
    if not stem and not ans and not sol:
        return None
    if is_noise(block, opts):
        return None
    return {"n": n, "type": guess_type(section, stem, opts),
            "figure": None, "continued": False, "raw": block,
            "stem": stem, "options": opts, "fig": "", "ans": ans, "sol": sol}


def ask_ocr(crop: Path, *, timeout: int = 600) -> str:
    r"""一条题目裁剪图 → 转写文本。走独立的 PaddleOCR-VL 服务（端口 1235）。

    它是纯 OCR 模型，**系统提示词基本只影响公式定界符**（给 `$…$` 它就写
    `$…$`，不给就写 `\(…\)`），别的一概不听。所以提示词力求短——
    写长了它反而会漏内容（实测长提示词下整条输出为空）。
    """
    b64 = base64.b64encode(crop.read_bytes()).decode()
    mime = "image/png" if crop.suffix.lower() == ".png" else "image/jpeg"
    body = json.dumps({
        "model": OCR_MODEL,
        "messages": [{"role": "system", "content": OCR_SYS},
                     {"role": "user", "content": [
                         {"type": "text", "text": "转录这一道题。"},
                         {"type": "image_url",
                          "image_url": {"url": f"data:{mime};base64,{b64}"}}]}],
        "temperature": 0.0, "max_tokens": 2000,
    }).encode()
    req = urllib.request.Request(OCR_API, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return (d["choices"][0]["message"]["content"] or "").strip()


FIG_SYS = ("这道数学题里，除了文字还有几何图形、函数图象或统计图表吗？"
           "只回答一个字：有 或 无。")


def check_figure(crop: Path, text: str) -> bool:
    r"""这道题有没有配图。

    **两步走，两边的好处都要：**

    * 纯靠文字判 → 实测 5 处误报（`为了得到 y=\cos 2x 的图象` 是纯代数题）
    * 全靠 27B 判 → 准（6/6），但一道 2～27 秒，一页 19 道就是好几分钟

    所以先用正则粗筛（题干提到「图」才可能带图），**只对候选**去问 27B。
    一页也就一两道候选，代价可以忽略。

    ⚠️ 宁可多问不可漏判：漏判会把带图的题**录进库**（违反「带图题一律不录」），
    误判只是少录一道并留痕。所以粗筛要宽、问不出来时按"有图"处理。
    """
    if not _FIG_WORD.search(text or ""):
        return False
    if not crop.exists():
        return True                     # 图没裁出来也不能当"没有"
    b64 = base64.b64encode(crop.read_bytes()).decode()
    mime = "image/png" if crop.suffix.lower() == ".png" else "image/jpeg"
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": FIG_SYS},
                     {"role": "user", "content": [
                         {"type": "text", "text": "看图回答。"},
                         {"type": "image_url",
                          "image_url": {"url": f"data:{mime};base64,{b64}"}}]}],
        "temperature": 0.0, "max_tokens": 10,
        "reasoning_effort": "none",     # 不关思考，10 个 token 全烧在推理上
    }).encode()
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode())
    except Exception:                                      # noqa: BLE001
        return True                     # 问不出来就按"有图"处理，宁可少录
    return "有" in (d["choices"][0]["message"]["content"] or "")


def split_by_number(parts: list[tuple[int, str]]) -> list[tuple[str, str, int, int, str]]:
    r"""整页文本按**题号**切块，返回 `[(题号, 文本, 起条带, 止条带), …]`。

    为什么"拼回整页再切"而不是"一条带当一道题"：**答案页的解析段落也齐
    左边界**，几何上会被切碎（实测一页解析被切成 7 段，每段都不是完整解析）。
    拼回整页后按行首 `12.` 这种题号切，才是真的按题分块。

    条带范围要留着——判图得回到图上问，文本里看不出有没有图。
    """
    cands: list[tuple[int, int, str]] = []           # (字符偏移, 条带号, 题号)
    off = 0
    for bi, t in parts:
        for m in _QNUM.finditer(t):
            cands.append((off + m.start(1), bi, m.group(1)))
        off += len(t) + 1
    # **只保留题号递增的那一串。** 放宽题号匹配后一定会误命中正文里的数字
    # （「见 3. 的结论」之类），而卷面题号必然是 9,10,11,12… 递增的——
    # 用这条硬约束筛，比调正则稳得多。
    # 接受三种情况：
    #   last+1  —— 正常往下走
    #   last    —— 同一题号又出现（答案页常见）
    #   1       —— **题号回到 1 就是新的一组**。卷首「考试说明」也带 1. 2. 3.
    #              编号，不放行的话真题 1、2、3 会被判"不递增"丢掉，
    #              正文并进说明块（实测 13 份里 10 份中招）。
    # 跳号（v > last+1）不接受：那多半是正文里的数字，不是题号。
    # 允许**小跳跃**：答案页常常只给部分题写解析（选择题只给个字母、
    # 或者干脆跳过），`8.` 缺席就把 `9. 10.` 整条链判死、全丢。
    # 跳号仍然不许太大（>3 的多半是正文里的数字，不是题号）。
    starts: list[tuple[int, int, str]] = []
    last = None
    for pos, bi, n in cands:
        v = int(n)
        if v == 0:                       # 题号从 1 起；`0.` 一定是小数或表格
            continue
        if last is None or last < v <= last + 3 or v == last or v == 1:
            starts.append((pos, bi, n))
            last = v
    # **从「题号 1」重新起头，而且取最长的那条递增链。**
    # 卷首的「考试说明」也带 1、2、3 编号，实测华师联盟第 1 页切出来是
    # `1,2,3,1,2,3,…`（前三个是说明、后面才是真题）。只取"第一个 1"会
    # 取到说明上，题号整体错位、答案全对不上；比较每条从 1 起的链谁长，
    # 长的那条才是真题。
    best, best_len = 0, -1
    for k, (_p, _b, n) in enumerate(starts):
        if n != "1":
            continue
        ln, prev = 1, 1
        for _q, _r, m in starts[k + 1:]:
            if int(m) != prev + 1:
                break            # **必须连续**：不 break 的话，断点后面
                # 接上的 4,5,6,7 会被算进同一条链，说明文字的链也报长度 7，
                # 于是永远挑中说明那条（实测踩过）
            ln, prev = ln + 1, int(m)
        if ln > best_len:
            best, best_len = k, ln
    starts = starts[best:]
    if not starts:
        return []
    full = "\n".join(t for _b, t in parts)
    secs = [(m.start(), m.group(1)) for m in _SECTION.finditer(full)]
    out = []
    # **第一个题号之前的正文不能丢。** 答案页的解析常常从上一页续下来，
    # 开头一段没有题号；原来直接从第一个题号开始切，这段就没了
    # （实测 9月阶段练习第 8、12、14、15 题的解析就是这么丢的）。
    # 提成一块、题号留空，交给 `classify_pages` 接到上一题上。
    head = full[:starts[0][0]].strip()
    if len(head) >= 12:
        out.append(("", head, parts[0][0], starts[0][1], ""))
    for k, (pos, bi, n) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(full)
        body = _QNUM.sub("", full[pos:end], count=1)
        b1 = starts[k + 1][1] if k + 1 < len(starts) else parts[-1][0]
        # 最近一个**在本题之前**的小节标题，用来定题型
        sec = next((t for p0, t in reversed(secs) if p0 < pos), "")
        out.append((n, body.strip(), bi, b1, sec))
    return out


# ── 页图 ──────────────────────────────────────────────────────────


def pages_of(pdf: Path, out: Path, *, dpi: int | None = None) -> list[Path]:
    r"""一份 PDF → 每页一张图。**已经抽过就复用**。

    ⚠️ **一律渲染，不再去抽内嵌图**（原来为了"不重编码、不掉清晰度"走
    `extract_image`，实测是错的）。这批卷子里有好几份 **PDF 的 xref 是坏的**
    （MuPDF 一路报 `cannot find object in xref`），`get_images()` 给出的
    xref 会解析到**别的页**上去，于是好几页抽成同一张图：

        武汉9调 9 页：p001==p002、p003==p004、p005~p009 全同
        → 一整份卷子只切出 7 道题（应该有 19 道），而且答案是错位的

    渲染是按页来的，永远对。DPI 按内嵌图的实际分辨率算（`img宽 ÷ 页宽英寸`），
    所以清晰度跟原扫描件一致，不会因为"渲染"而变糊。
    """
    import fitz                                    # 重依赖，用到才导

    # 这批卷子里有好几份 xref 是坏的，MuPDF 会往 stderr 刷几百行
    # `cannot find object in xref`，把真正的日志淹掉。渲染本身是好的，静音。
    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except Exception:                                      # noqa: BLE001
        pass
    out.mkdir(parents=True, exist_ok=True)
    got: list[Path] = []
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc, 1):
            hit = sorted(out.glob(f"p{i:03d}.*"))
            if hit:
                got.append(hit[0])
                continue
            d = dpi
            if d is None:                              # 贴着原扫描件的分辨率
                imgs = page.get_images(full=True)
                big = max(imgs, key=lambda x: x[2] * x[3], default=None)
                w_in = max(page.rect.width, 1) / 72.0
                d = int(round(big[2] / w_in)) if big and big[2] else 200
                d = max(120, min(300, d))
            p = out / f"p{i:03d}.png"
            page.get_pixmap(dpi=d).save(p)
            got.append(p)
    return got


# ── 标记文本 → 结构 ────────────────────────────────────────────────

_ATTR = re.compile(r"(\w+)=(\S+)")
_SEC = re.compile(r"^@@(STEM|OPT|FIG|ANS|SOL|ENDQ)\s*$")
_OPT = re.compile(r"^\s*([A-H])\s*[.、．:：]\s*(.*)$")
_KEY = re.compile(r"(\d+)\s*[.、．:：]\s*([A-H]{1,6})(?=\s|$)")


def parse_marked(text: str) -> dict:
    r"""解析模型吐的 @@ 标记。**认不出的部分一律丢掉，不猜。**

    分两趟：先拿页级信息（kind/title/@@KEY/@@FIGPOS），再切题目块。
    """
    page = {"kind": "", "title": ""}
    m = re.search(r"^@@PAGE\s+(.*)$", text, re.M)
    if m:
        # title 里有空格（「某卷 数学」），所以不能拿 `\S+` 去捞——单独解析。
        line = m.group(1)
        k = re.search(r"kind\s*=\s*(\S+)", line)
        t = re.search(r"title\s*=\s*(.+?)\s*$", line)
        page = {"kind": k.group(1) if k else "",
                "title": t.group(1) if t else ""}

    key: dict[str, str] = {}
    m = re.search(r"^@@KEY\s+(.*)$", text, re.M)
    if m:
        key = {n: v for n, v in _KEY.findall(m.group(1))}

    figpos: dict[str, dict] = {}
    for m in re.finditer(r"^@@FIGPOS\s+(.*)$", text, re.M):
        a = dict(_ATTR.findall(m.group(1)))
        if a.get("n"):
            figpos[a["n"]] = a

    qs = []
    for blk in re.split(r"^@@Q\s+", text, flags=re.M)[1:]:
        head, _, body = blk.partition("\n")
        a = dict(_ATTR.findall(head))
        secs: dict[str, list[str]] = {}
        cur = None
        for line in body.splitlines():
            mm = _SEC.match(line.strip())
            if mm:
                cur = mm.group(1)
                if cur == "ENDQ":
                    break
                secs.setdefault(cur, [])
                continue
            if cur:
                secs[cur].append(line)
        get = lambda k: "\n".join(secs.get(k, [])).strip()      # noqa: E731
        opts = [(_OPT.match(l).group(1), _OPT.match(l).group(2).strip())
                for l in secs.get("OPT", []) if _OPT.match(l)]
        qs.append({
            "n": a.get("n", ""), "type": a.get("type", ""),
            "figure": a.get("figure") == "有", "continued": a.get("continued") == "是",
            "stem": get("STEM"), "options": opts,
            "fig": get("FIG"), "ans": get("ANS"), "sol": get("SOL"),
        })
    return {"page": page, "key": key, "figpos": figpos, "questions": qs}


# ── 逐页识别（带缓存 + 并发） ──────────────────────────────────────


def ocr_alive() -> bool:
    r"""OCR 服务通不通。

    **服务没起来时必须大声报错，不能伪装成「这份卷子没有题」。**
    实测踩过：OCR 服务挂了，`scan_page` 的兜底把连接异常吞成
    `questions: []`，于是整份卷子"识别出 0 道题"、脚本还高高兴兴把
    空产物写了出去——看上去像卷子有问题，其实是服务没开。
    """
    import urllib.error
    try:
        with urllib.request.urlopen(
                OCR_API.replace("/v1/chat/completions", "/health"),
                timeout=5) as r:
            return r.status == 200
    except Exception:                                      # noqa: BLE001
        return False


def llm_alive() -> bool:
    """打标用的本地 27B（1234）通不通。**打标是它干的，挂了就等于全都没考点。**"""
    try:
        with urllib.request.urlopen(
                API.replace("/v1/chat/completions", "/v1/models"),
                timeout=5) as r:
            return r.status == 200
    except Exception:                                      # noqa: BLE001
        return False


def scan_pdf(pdf: Path, *, work: Path | None = None, workers: int = 1,
             force: bool = False, on_event=None) -> list[dict]:
    r"""一份 PDF → 每页一份识别结果。

    **一页一个 json 落在磁盘上**：本地模型一页要一两分钟，跑一半崩了
    不该从头再来。`force=True` 才重跑已缓存的页。

    ⚠️ **`workers` 默认 1（串行），不是 4。** LM Studio 那份模型是按
    `context=8192, parallel=4` 加载的，**上下文是 4 个槽平分的**——
    每槽只剩 2048 token，连一页扫描图的图像 token（约 2100）都装不下。
    实测并发 4 路的结果是服务端报
    `failed to find a memory slot` / `failed to process mtmd chunk`，
    15 次请求死掉，而且**客户端什么都收不到，只能干等到超时**。

    而且单卡上并发本来也换不来吞吐：4 路并发只是把一条 GPU 流水线
    切成 4 份，总 token/s 基本不变。真要并发，得先把模型按
    `lms load --context-length 32768` 重新加载（每槽才够 8192）。
    """
    if not ocr_alive():
        raise RuntimeError(
            "OCR 服务连不上（%s）。先起服务再录题：\n"
            "  B=~/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-2.38.0\n"
            "  D=~/.lmstudio/models/PaddlePaddle/PaddleOCR-VL-1.6-GGUF\n"
            "  DYLD_LIBRARY_PATH=$B $B/llama-server -m $D/PaddleOCR-VL-1.6-GGUF.gguf \\\n"
            "    --mmproj $D/PaddleOCR-VL-1.6-GGUF-mmproj.gguf --port 1235 -c 65536 -np 4 -ngl 99\n"
            % OCR_API, )
    work = work or WORK / pdf.stem
    imgs = pages_of(pdf, work / "pages")
    cache = work / "scan"
    cache.mkdir(parents=True, exist_ok=True)
    crops = work / "crops"
    rows: list[dict | None] = [None] * len(imgs)

    def one(i: int, img: Path) -> dict:
        dst = cache / f"p{i:03d}.json"
        if dst.exists() and not force:
            d = json.loads(dst.read_text(encoding="utf-8"))
            d["cached"] = True
        else:
            try:
                d = scan_page(img, cache, i)
                # 页级结果也要落盘：**每页那一堆 OCR 缓存（p002_07.txt）是原料，
                # 这份才是成品**。少了它，重跑虽然不用重新 OCR，却要重跑一遍
                # 题号切分和判图（判图要问 27B，一页好几秒）。
                d.pop("cached", None)
                _atomic(dst, d)
            except Exception as e:                 # noqa: BLE001
                # **一页失败不能拖垮整份卷子。** 失败的页不写缓存，
                # 所以「重跑同一份」天然只重试这几页——其余页命中缓存。
                d = {"page": {"kind": "", "title": ""}, "key": {}, "figpos": {},
                     "questions": [], "error": "%s: %s" % (type(e).__name__, e)}
            d["cached"] = False
        # ⚠️ 页码存 `no`，**不能存 `page`** —— `page` 是 `parse_marked` 给的
        # 页信息字典（kind/title）。拿页码覆盖它，`merge` 收到的就是 int，
        # 一取 `.get("kind")` 当场炸。这个坑真踩过：批量刚跑到第二页就崩。
        d["no"], d["image"] = i, str(img)
        if on_event:
            on_event({"type": "page", "page": i, "total": len(imgs),
                      "secs": d.get("secs"), "cached": d["cached"],
                      "error": d.get("error", ""),
                      "kind": (d.get("page") or {}).get("kind", "")})
        return d

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for i, d in enumerate(ex.map(lambda t: one(*t), enumerate(imgs, 1)), 1):
            rows[i - 1] = d
            done += 1
            if on_event:
                on_event({"type": "progress", "done": done, "total": len(imgs)})
    return [r for r in rows if r]


# ── 合并 + 答案配对 ───────────────────────────────────────────────


def same_question(a: str, b: str) -> bool:
    r"""两段文字是**同一道题的两次转写**，还是**一道题跨页的两半**？

    两者必须分开处理：前者要**取更完整的一份**，后者要**拼起来**。
    分错了的后果实测过——把同一道题接两遍，题干在库里重复出现：

        在 160 和 -5 之间插入 4 个数，……则公比 $q$ 的值为
        在 160 和 $-5$ 之间插入 4 个数，……则公比 $q$ 的值为\paren[A]

    阈值 0.85 是量出来的，两边差得很开：

        「同一题重述」  0.978   （试卷页 vs 答案页，只差两个 `$`）
        「跨页续写」    0.700 / 0.655 / 0.427   （(1)(2) 两小问）

    包含关系直接判同一题，不受阈值影响。
    """
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio() >= 0.85


def parse_answer_table(text: str) -> dict[str, str]:
    r"""答案速查表 → `{题号: 答案}`。

    实测 Z20 的答案是这么排的（PaddleOCR-VL 会带上竖线）：

        | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8
        | C | A | B | B | C | C | C | D
        | 9 | 10 | 11
        | ABD | BC | BCD

    判据是「上一行全是题号、下一行全是字母、个数对得上」——
    对不上就不认，宁可让答案缺着（缺了会在报告里列出来）。
    """
    out: dict[str, str] = {}
    # 紧凑区间格式：`1-8: DCCB CDAB`（实测青岛、很多模拟卷都这么排）。
    # 字母个数必须正好等于区间长度，对不上就不认——宁可缺答案，不给错答案。
    for m in re.finditer(r"(?m)^\s*(\d{1,2})\s*[-–—~至]\s*(\d{1,2})\s*[:：]\s*"
                         r"([A-D][A-D\s]{2,})", text):
        a, b = int(m.group(1)), int(m.group(2))
        lets = re.findall(r"[A-D]", m.group(3))
        if b >= a and len(lets) == b - a + 1:
            for i, l in enumerate(lets):
                out.setdefault(str(a + i), l)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        nums = re.findall(r"\d{1,2}", line)
        if len(nums) < 2:
            continue
        # **题号必须互不相同、而且在合理范围内。**
        # 不加这条，选项行会被当成答案表——实测深圳中学的解析里
        # `A。1-i  B。1+i  C。2i  D。2-2i` 被读出 ['1','1','2','2','2']，
        # 于是第 1 题的答案被贴成了 D（正确答案是 A）。
        # 错答案比没答案危害大得多，所以这里宁可漏认。
        if len(set(nums)) != len(nums) or max(int(x) for x in nums) > 30:
            continue
        # 答案行可能隔着一两行（实测中间夹着 `--- | --- |` 分隔行），
        # 所以往下找三行，跳过纯分隔行再比个数。
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j].strip()
            if nxt and set(nxt) <= set("-|— "):
                continue
            lets = re.findall(r"[A-D]{1,4}", nxt)
            if len(lets) == len(nums):
                for n, l in zip(nums, lets):
                    out.setdefault(n, l)
                break
    return out


# 速查表/小节标题这种块不能拿来当解析——它们是排版，不是解答内容。
_TABLE_ROW = re.compile(r"题号\s*[|｜]|答案\s*[|｜]|^\s*[|｜]|[-—]{3,}\s*[|｜]")


def classify_pages(scans: list[dict]) -> None:
    r"""标出哪些页是**答案页**——靠「题号有没有回头」。

    原来只认「【答案】/【解析】」标记，实测**一大半卷子不用这套标记**：
    Z20 的答案是**表格**（`| 1 | 2 | … | C | A | …`），青岛/武汉的是**纯解析
    段落**。结果 199 道题里 148 道被判「无解析」，而答案其实就在 PDF 后几页。

    真正的结构规律是：**试卷页的题号一路往上走，答案页会从头再来一遍**。
    所以顺序扫页，头一页的题号 ≤ 已见过的最大题号时，从这里起全是答案页。
    """
    # **先把全卷的答案速查表收齐，再往题上贴。**
    # 表在答案页上，题在试卷页上——只在"本页的题"里找表，选择题永远拿不到答案
    # （实测华师联盟 1~10 题全是空的，而表就在第 5 页）。
    # **先到先得**：不能 `table.update(...)`——后面那些页（解析页、正文页）
    # 里也常能"解析"出一些 [题号→字母] 的伪映射，一 update 就把前面
    # 正规答案表里的正确值覆盖了（实测青岛第 1 题：答案表写 D，
    # 被后面某页的 B 盖掉）。
    # **取条目最多的那一页当答案表。**
    # 每页都可能有几处"看着像 [题号→字母]"的东西（来源注、正文选项、页脚），
    # 单条伪映射很难和真表区分；但真答案表一页就有 8~11 条，
    # 伪映射撑不到这个数量。按条目数挑最靠谱。
    table: dict[str, str] = {}
    for sc in scans:
        t = parse_answer_table(
            sc.get("text") or
            "\n".join(q.get("raw", "") for q in sc["questions"]))
        if len(t) > len(table):
            table = t

    maxno, seen = 0, False
    last = ""                                  # **跨页保持**：解析常从上一页续下来
    for sc in scans:
        nums = [int(q["n"]) for q in sc["questions"] if str(q["n"]).isdigit()]
        # **要"整页题号都落后"才算答案页，不能只看第一个数。**
        # 原来写的是 `first <= maxno` —— 页眉或正文里冒出一个游离的小数字，
        # 后面整页就被判成答案页、题干全被清掉，变成一堆空题干幽灵题
        # （实测银川一中 8 道题就是这么没的）。
        if len(nums) >= 2 and max(nums) <= maxno:
            seen = True
        kind = "答案" if seen else (sc.get("page") or {}).get("kind", "试题")
        if (sc.get("page") or {}).get("kind") == "答案":
            kind = "答案"
        sc["page"] = {**(sc.get("page") or {}), "kind": kind}
        if nums:
            maxno = max(maxno, max(nums))
        if kind != "答案":
            if nums:
                last = str(nums[-1])
            continue
        # 答案页回填：**没有【答案】标记的卷子，整块文本就是解析**。
        # 实测一大半卷子不用标记——Z20 用表格，青岛/武汉直接写解析段落，
        # 不回填的话它们全部会被判「无解析」。
        # **没有题号的段落接上一题**：解析常常跨页、而且新段落不重复题号。
        # 不接的话这些内容整块丢掉（`merge` 只认数字题号）。
        # `last` 必须在**页之间**保持——续写的段落往往整页都没有题号，
        # 只在页内的循环里记，第一段就找不到归属。
        for q in sc["questions"]:
            if str(q["n"]).isdigit():
                last = q["n"]
            elif last:
                q["n"] = last
        for q in sc["questions"]:
            q["stem"] = ""                      # 答案页上的题干是重述，不要
            q["options"] = []
            raw = (q.get("raw") or "").strip()
            if _TABLE_ROW.search(raw):
                continue
            # **短块就是"答案"本身，不是解析。** 答案页有两种排法：
            #   ① 速查表 / 紧凑列表：`1. A  2. C  12. $\frac{3}{2}$`
            #   ② 每题一段【答案】【解析】
            # ① 的每块切出来只有一个字母或一个式子，长度很短；当成解析写进去
            # 就是把"A"当解答过程（实测洛阳 7 道题就是这么变的"有解析"）。
            if not q["ans"] and raw and len(raw) <= 80 and "。" not in raw:
                q["ans"] = raw
                continue
            if not q["sol"] and raw:
                q["sol"] = raw
            if not q["ans"] and q["n"] in table:
                q["ans"] = table[q["n"]]
    # **答案表最后说了算。** 它是卷面明写的答案，比其他任何启发式都权威；
    # 中途被别处填错的（实测青岛第 1 题，表明明写 D、字段却是 B）在这里纠回来。
    for sc in scans:
        for q in sc["questions"]:
            if q["n"] in table:
                q["ans"] = table[q["n"]]


def merge(scans: list[dict]) -> list[dict]:
    r"""把逐页结果按**卷面题号**拼成整卷。

    规则：
      * `试题` 页出的 `STEM/OPT/FIG` 按页码顺序**往后接**（跨页的题）
      * `答案` 页**只取 ANS/SOL/KEY**，不碰题干——答案卷经常把题干缩写重排，
        照单全收会把好题干覆盖坏
      * 答案优先级：本题的 `@@ANS` > 答案页的 `@@ANS` > `@@KEY` 表
    """
    order: list[str] = []
    by: dict[str, dict] = {}
    for sc in scans:
        is_ans_page = sc["page"].get("kind") in ("答案",)
        for q in sc["questions"]:
            n = q["n"].strip()
            if not n.isdigit():
                continue
            t = by.get(n)
            if t is None:
                t = by[n] = {"n": n, "type": "", "figure": False,
                             "stem": "", "options": [], "fig": "",
                             "ans": "", "sol": "", "pages": [],
                             "exam_pages": [],
                             "key_ans": sc["key"].get(n, ""),
                             "figpos": sc["figpos"].get(n) or {}}
                order.append(n)
            t["pages"].append(sc["no"])
            # **试卷页**单独记一份。答案页也会出现同一个题号（答案卷常把题干
            # 重述一遍），混在一起的话补图的人会照着答案页的页码去找原图，
            # 找不着。登记位置要的是「这道题在试卷的第几页」。
            if not is_ans_page and sc["no"] not in t["exam_pages"]:
                t["exam_pages"].append(sc["no"])
            if not t["key_ans"]:
                t["key_ans"] = sc["key"].get(n, "")
            if sc["figpos"].get(n) and not t["figpos"]:
                t["figpos"] = sc["figpos"][n]
            if q["type"] in TYPE_MAP and not t["type"]:
                t["type"] = q["type"]
            t["figure"] = t["figure"] or q["figure"]
            if q["fig"] and q["fig"] != "->" and not t["fig"]:
                t["fig"] = q["fig"]
            if is_ans_page:
                if q["ans"] and q["ans"] != "->" and len(q["ans"]) > len(t["ans"]):
                    t["ans"] = q["ans"]
                if q["sol"] and q["sol"] != "->":
                    t["sol"] = (t["sol"] + "\n" + q["sol"]).strip()
                continue
            if q["stem"] and q["stem"] != "->":
                if not t["stem"]:
                    t["stem"] = q["stem"]
                elif same_question(t["stem"], q["stem"]):
                    # 同一题的另一次转写（答案页常把题目重述一遍）：
                    # **取更完整的那份，不拼**——拼了就是题干重复两遍。
                    if len(q["stem"]) > len(t["stem"]):
                        t["stem"] = q["stem"]
                else:
                    t["stem"] = (t["stem"] + "\n" + q["stem"]).strip()
            have = {l for l, _ in t["options"]}
            t["options"] += [o for o in q["options"] if o[0] not in have]
            if q["ans"] and q["ans"] != "->":
                t["ans"] = q["ans"] if len(q["ans"]) > len(t["ans"]) else t["ans"]
            if q["sol"] and q["sol"] != "->":
                t["sol"] = (t["sol"] + "\n" + q["sol"]).strip()
    for n in order:
        t = by[n]
        if not t["ans"]:
            t["ans"] = t["key_ans"]
    return [by[n] for n in order]


def split_figures(qs: list[dict], *, src: str = "") -> tuple[list, list, list]:
    r"""带图题分流。

    返回 `(要录的, 丢掉的, 登记位置的)`。**带图题一律不录正文**；
    只有 8/11/14/18/19 的带图题进第三份，附上原卷位置供人工补。
    """
    keep, drop, reg = [], [], []
    for q in qs:
        if not q["figure"]:
            keep.append(q)
            continue
        drop.append(q)
        if q["n"] in FIG_KEEP:
            reg.append({
                "题号": int(q["n"]), "来源文件": src,
                "页码": q["exam_pages"] or q["pages"],
                "图": q["fig"] or "（OCR 不描述图，打开页图看）",
                "位置": " ".join(x for x in (q["figpos"].get("y", ""),
                                            q["figpos"].get("x", "")) if x) or "（见页图）",
                "页图": "%s/%s/pages/p%03d.*" % (
                    WORK.name, src.replace(".pdf", ""),
                    (q["exam_pages"] or q["pages"] or [0])[0]),
                "题干开头": (q["stem"].splitlines() or [""])[0][:60],
            })
    reg.sort(key=lambda r: (r["来源文件"], r["题号"]))
    return keep, drop, reg


# ── 组装 LaTeX ────────────────────────────────────────────────────

_FILLIN = re.compile(r"\\fillin\s*\[[^\]]*\]")
_UNDERLINE = re.compile(r"_{3,}|\\underline\{\\hspace\{[^}]*\}\}|（\s*）")
_BB = re.compile(r"\\mathbf\{([RNZQC])\}")
_TEXT_MATH = re.compile(r"\\text\{([ei])\}")
# 卷面上的小节标记（「【解析】」「【答案】」），不是内容。库里 0 处，等于噪声。
_LEAD_MARK = re.compile(r"^\s*【(?:解析|答案|详解|分析|解|点评)】\s*")


def fixup(tex: str) -> str:
    r"""把视觉模型惯用的记号拉回库里的写法。

    **只做没有歧义的**（括号里是库内的实际计数，2026-09-16 量的）：

    * `\mathbf{R}` → `\mathbb{R}`：`\mathbb{R}` 4056 处、`\mathbf{R}` 0 处
    * `\text{e}` → `\mathrm{e}`：`\mathrm{e}` 6266 处、`\text{e}` 42 处
      （规范 §2.6 明写「虚数单位写 `\mathrm{i}`，自然底数 `\mathrm{e}`」）

    裸 `i`（该写 `\mathrm{i}`）**不碰**——它可能是虚数单位，也可能是求和
    下标、普通字母，改了就是引入错误。宁可留着给人看。
    """
    tex = _TEXT_MATH.sub(r"\\mathrm{\1}", _BB.sub(r"\\mathbb{\1}", tex))
    # `\(…\)` → `$…$`：规范要求行内公式一律 `$…$`。
    # PaddleOCR-VL 默认就吐 `\(…\)`，而 normalize 的"行内公式统一"规则
    # 兜不住跨行的那种（实测洛阳第 8 题的解析剩了一个 `\(` 配不上对，
    # conform 的「定界符配对」直接把整份卷子拦在库外）。
    # **`%` 必须转义。** LaTeX 里它是注释符：题干「…的80%分位数为\paren[D]」
    # 会把 `%` 后面整段注释掉，连答案括号一起没了
    # （实测青岛第 1 题，conform 报「选择题答案没写进 \paren[…]」）。
    tex = re.sub(r"(?<!\\)%", r"\\%", tex)
    # ⚠️ **必须在 `\(…\)` 归一成 `$…$` 之后再包中文**——先包的话，
    # 那些还是 `\(…\)` 形态的公式根本没被当成数学模式，中文照样漏
    # （实测镇江那份就是这么漏过去的）。
    tex = tex.replace("\\(", "$").replace("\\)", "$")
    tex = fix_math_cjk(tex)
    # `$$…$$` → `$…$`：规范里行间公式是 `\[…\]`，`$$` 块解析器不认
    # （实测华师联盟第 19 题的解析里混了 `$$`，KaTeX 渲染直接失败、四层验收挂掉）。
    # 直接换成单 `$` 最稳：定界符个数不变，永远配平。
    return tex.replace("$$", "$")


def strip_marker(sol: str) -> str:
    r"""去掉解析开头的「【解析】」这类**卷面小节标记**。

    它是排版用的标题，不是解答内容；库里 0 处这样的标记。
    只削开头一个，正文里出现的不管。
    """
    return _LEAD_MARK.sub("", sol)


def _split_answers(ans: str, holes: int) -> list[str]:
    r"""一个答案串按空位个数切开。单空直接给整串。

    分隔符按「先规范、后退让」试：规范要求多空用 `；`，但模型实际会写
    半角 `;`、中文逗号 `，`、半角 `,`（实测 `5, 7` 就是这么来的）。
    **只认能正好切成 N 份的那个分隔符**——切成别的份数说明这不是多空答案，
    而是答案里本来就有逗号（比如坐标 `(1, 2)`），不能瞎切。
    """
    if holes <= 1:
        return [ans]
    for sep in ("；", ";", "，", ","):
        parts = [p.strip() for p in ans.split(sep) if p.strip()]
        if len(parts) == holes:
            return parts
    return []


def fill_blanks(stem: str, ans: str) -> str | None:
    r"""把答案塞进题干里的空位。**对不上就返回 `None`**，表示这道题别录。

    模型被要求把空位写成 `\fillin[]`，但实测它有时照抄卷面的下划线，
    两条路都兜住；一个空位都没找到就把答案接在末尾（排版难看，
    好过答案整条丢掉）。

    ⚠️ **空位数与答案段数对不上时必须拒收**，不能硬塞。`conform` 的
    「填空位数」会拦下这种题，而 `ingest.commit` 的复核**一发现违规就
    整份卷子都不录**——实测河南青桐鸣那道 14 题（两个空、答案 `5, 7`
    切不开）把另外 15 道好题一起拖下水。现在的做法是只丢这一道，
    题号写进报告让人补。
    """
    holes = len(_FILLIN.findall(stem))
    if not holes:
        m = _UNDERLINE.search(stem)
        if not m:
            return stem.rstrip() + ("\\fillin[%s]" % ans if ans else "")
        return stem[:m.start()] + ("\\fillin[%s]" % ans if ans else "") + stem[m.end():]
    if not ans:
        return stem                       # 空位留着，答案等人工补
    if holes == 1:
        # **一个空就没有"多空分隔"这回事**，答案里的 `；` 会让 conform 的
        # 「填空位数」数出 2 段（实测 5 场整卷被拦）。归一成逗号：原意不变。
        return _FILLIN.sub(
            lambda _m: "\\fillin[%s]" % ans.replace("；", "，").replace(";", "，"),
            stem, count=1)
    parts = _split_answers(ans, holes)
    if len(parts) != holes:
        return None
    it = iter(parts)
    return _FILLIN.sub(lambda _m: "\\fillin[%s]" % next(it), stem)


# 模型用来表示「这里没有」的占位符。**不能当内容**——留着它就是一道空壳题，
# 而 ingest 的复核一发现「题干为空」是整份卷子都不录。
_NONE_WORDS = ("->", "-", "—", "－", "无", "/")


def unbalanced(tex: str) -> bool:
    r"""花括号/数学模式定界符配不配平。

    **OCR 会把公式截断**（实测华师联盟第 19 题的解析里 `\sqrt{\left(…`
    写了一半就断了），花括号不闭合的 LaTeX 喂给 KaTeX 直接渲染失败
    ——`conform` 的「定界符配对」只查 `$`，查不出 `{}`，所以要在这一层拦。
    """
    if tex.count("$") % 2:
        return True
    depth = 0
    for i, ch in enumerate(tex):
        if ch == "\\":
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return True
    return depth != 0


# 难度按**原卷题号**定，规则是用户 2026-09-17 给的：
#   简单 = 各小节的头一两道（1,2 单选 / 9 多选 / 12 填空 / 15 解答）
#   难题 = 各小节的压轴（8 单选 / 11 多选 / 14 填空 / 18,19 解答）
#   其余 = 中档
# 纯规则、不用模型——题号是卷面写死的，没什么可"认"的。
EASY_NO = {1, 2, 9, 12, 15}
HARD_NO = {8, 11, 14, 18, 19}


def difficulty_by_no(n) -> str:
    v = int(n) if str(n).isdigit() else 0
    if v in EASY_NO:
        return "简单题"
    if v in HARD_NO:
        return "难题"
    return "中档题"


TAG_SYS = (
    "你是高中数学命题专家。下面给你一份考点清单和一道题，"
    "请选出**最贴切的一个**考点。只输出考点编号（如 1.1.3），不要输出任何别的内容。"
)


def _point_list() -> str:
    from . import knowledge as kb
    return "\n".join("%s %s" % (p.get("id"), kb.title_of(p.get("id")))
                     for p in kb.all_points() if p.get("id"))


def tag_point(q: dict, *, timeout: int = 300) -> str:
    r"""给一道题打一个考点编号（如 `1.1.3`）。

    考点清单 153 条，**全量塞进提示词**——两段式（先选章再选点）要多一次
    往返，而一次往返在这台机器上就是好几秒，省下来的时间不够补误差。
    输出只有五六 token，所以慢的是 prefill，不是生成。

    认不出合法编号就返回空串：**宁可不打标，也不打错标**。
    """
    from . import knowledge as kb
    stem = q.get("stem", "")
    opts = "\n".join("%s. %s" % (a, b) for a, b in q.get("options") or [])
    body = ("考点清单：\n%s\n\n题目（题型 %s）：\n%s%s"
            % (_point_list(), q.get("type", ""), stem, ("\n" + opts) if opts else ""))
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": TAG_SYS},
                     {"role": "user", "content": body}],
        "temperature": 0.0, "max_tokens": 16,
        "reasoning_effort": "none",     # 不关思考，16 个 token 全烧在推理上
    }).encode()
    req = urllib.request.Request(API, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        txt = (d["choices"][0]["message"]["content"] or "").strip()
    except Exception:                                      # noqa: BLE001
        return ""
    m = re.search(r"\d+(?:\.\d+){1,3}", txt)
    pid = m.group(0) if m else ""
    return pid if pid and kb.get(pid) else ""


# 数学模式外**允许**出现的命令（结构性命令，规范里就这么写）
_STRUCT_CMD = {
    "paren", "fillin", "includegraphics", "begin", "end", "item", "textbf",
    "text", "textwidth", "linewidth", "centering", "hspace", "vspace",
    "label", "ref", "caption", "tabular", "array", "hline", "quad", "qquad",
    "qquad", "emph", "underline", "hfill", "par", "noindent", "vskip",
}


_CJK = re.compile(r"[\u4e00-\u9fff]+")
_ENV = re.compile(r"\\(begin|end)\{([a-zA-Z*]+)\}")


def fix_math_cjk(tex: str) -> str:
    r"""数学模式里的裸中文包进 `\text{}`。

    OCR 常把下标写成 `S_{平行四边形}`、`\frac{亩产量}{平均产量}`——
    规范 §2.6 要求数学里的中文必须包 `\text{}`，不包 `conform` 会拦，
    而 `ingest` 是**一票否决**：一道题害得整份卷子进不去（实测 8 场中招）。
    这是纯机械的写法修正，改对了就能进库，不该丢题。
    """
    def one(m):
        parts = re.split(r"(\\text\{[^}]*\})", m.group(1))
        return "$" + "".join(
            x if x.startswith("\\text{") else _CJK.sub(
                lambda mm: "\\text{%s}" % mm.group(0), x)
            for x in parts) + "$"
    return re.sub(r"\$([^$]*)\$", one, tex)


# 小节标题（「四、解答题：本题共5小题…」）。它出现在题干里 = **这一题
# 吞掉了下一节的标题**，实测答案页的紧凑列表会把下一题整段带进来
# （潍坊第 14 题吞了第 15 题 + 「四、解答题」标题，7 场卷子因此进不了库）。
_SEC_IN = re.compile(r"\s*[一二三四五六七八九十]\s*[、.][^\n]{0,30}?"
                     r"(?:选择题|填空题|解答题)[^\n]*")


def normalize_fillin(stem: str) -> str:
    r"""**单空题的 `illin[…]` 里不许有分号。**

    分号是"多空答案"的分隔符；只有一个空时它就是答案内容的一部分
    （`$x-y+1=0$; 2` 这种多半还是 OCR 把下一题带进来了）。
    `conform` 的「填空位数」按分号数段，一个空数出两段就**整份卷子进不去**。
    实测 7 场卡在这。这里统一把单空里的分号归一成逗号。
    """
    if len(_FILLIN.findall(stem)) != 1:
        return stem
    return _FILLIN.sub(
        lambda m: m.group(0).replace("；", "，").replace(";", "，"), stem, count=1)


def cut_section(tex: str) -> str:
    r"""在**第一个小节标题处截断**——把吞进来的下一节内容切掉。

    能救回真题，比整道丢掉好。
    """
    m = _SEC_IN.search(tex or "")
    return (tex[:m.start()].rstrip() if m else tex) or ""


def env_balanced(tex: str) -> bool:
    r"""`\begin{}` / `\end{}` 配不配平（实测有 `\begin{cases}` 没闭合的）。"""
    stack: list[str] = []
    for m in _ENV.finditer(tex or ""):
        if m.group(1) == "begin":
            stack.append(m.group(2))
        elif not stack or stack.pop() != m.group(2):
            return False
    return not stack


def latex_leak(tex: str) -> bool:
    r"""**数学模式外残留的 LaTeX 命令**（`conform` 的「渲染残留」查的就是这个）。

    OCR 常把 `x \in A` 里的 `\in` 落到 `$…$` 外面，渲染出来是一根反斜杠。
    `ingest` 的复核是**一票否决**的：一道题有残留，整份卷子都进不去
    （实测湖北圆创联盟那份，14 道好题被第 19 题拦住）。
    所以在这一层先把它剔出来，题号写进报告。
    """
    # ⚠️ **白名单而不是黑名单。** 题干里的 `\paren[]`、`\fillin[]`、
    # `\includegraphics` 是规范里合法的结构性命令，一刀切会把好题也毙掉
    # （第一版就是这么写的，自检 5 项当场红了）。
    masked = re.sub(r"\$[^$]*\$", "", tex or "")
    return any(m.group(1) not in _STRUCT_CMD
               for m in re.finditer(r"\\([a-zA-Z]{2,})", masked))


def unrenderable(q: dict) -> str:
    r"""这道题能不能成形。能就返回 `""`，不能就返回原因。

    **一道坏题不能让整份卷子进不去。** `ingest.commit` 的复核是一票否决的：
    只要有一道「题干为空」，整份卷子的题全都不录——实测河南青桐鸣、
    青岛各有一道这样的幽灵题（答案页上有 `n=20`，可试卷页的题干没转出来），
    结果 15 道好题跟着一起进不去。所以在这一层就先剔掉，并把题号写进报告。
    """
    if not fixup(q["stem"].strip()) or q["stem"].strip() in _NONE_WORDS:
        return "题干为空（多半是答案页上有题号、试卷页没转出题干）"
    qtype = TYPE_MAP.get(q["type"], "")
    if qtype in ("single_choice", "multi_choice") and len(q["options"]) < 2:
        return "选择题选项不足 2 个（题干没认全）"
    return ""


def to_tex(qs: list[dict], *, book: str, label: str, region: str = "",
           year: int | None = None, title: str = "",
           skipped: list | None = None) -> str:
    r"""结构化题目 → exam-zh LaTeX 源（`ingest` 认得的那种）。

    **只写 `key` / `type` / `meta` 三样**，其余字段由 `ingest` 补。
    题干里的答案按规范 §2.2 就地写进 `\paren[…]` / `\fillin[…]`；
    解答题的答案与解析都进 `solution`。

    `skipped` 传一个 list 进来，录不进去的题会以 `{"n", "why", ...}`
    追加进去——**丢掉哪道题必须留痕**，不能默默少一道。
    """
    out: list[str] = []
    for i, q in enumerate(qs, 1):
        n = int(q["n"])
        why = unrenderable(q)
        if why:
            if skipped is not None:
                skipped.append({"n": n, "why": why,
                                "stem": q["stem"][:60], "ans": q["ans"][:40]})
            continue
        qtype = TYPE_MAP.get(q["type"], "")
        ans, sol = fixup(q["ans"].strip()), strip_marker(fixup(q["sol"].strip()))
        stem = fixup(q["stem"].strip())
        # 吞进来的下一节内容先切掉（题干和解析都要切）
        stem, sol = cut_section(stem), cut_section(sol)
        if not stem:
            if skipped is not None:
                skipped.append({"n": n, "why": "题干只有小节标题（切完就空了）",
                                "stem": q["stem"][:60], "ans": ans[:40]})
            continue
        if unbalanced(stem):
            # 题干坏了就整道丢掉；解析坏了只丢解析（题干好的还能用）
            if skipped is not None:
                skipped.append({"n": n, "why": "题干公式不配平（OCR 截断）",
                                "stem": stem[:60], "ans": ans[:40]})
            continue
        if unbalanced(sol):
            sol = ""
        # 选项也要查——实测有 optC 漏 \infty、optD 漏 \sqrt 把整卷拦下的
        if any(unbalanced(t) or latex_leak(t) or not env_balanced(t)
               for _l, t in q["options"]):
            if skipped is not None:
                skipped.append({"n": n, "why": "选项里的公式不合法",
                                "stem": stem[:60], "ans": ans[:40]})
            continue
        if not env_balanced(stem) or not env_balanced(sol):
            if skipped is not None:
                skipped.append({"n": n, "why": "环境没闭合（begin/end 不配对）",
                                "stem": stem[:60], "ans": ans[:40]})
            continue
        # 数学模式外漏出的 LaTeX：题干坏了整道丢，解析坏了只丢解析
        if latex_leak(stem):
            if skipped is not None:
                skipped.append({"n": n, "why": "题干有 LaTeX 残留（数学模式外）",
                                "stem": stem[:60], "ans": ans[:40]})
            continue
        if latex_leak(sol):
            sol = ""
        # **答案里出现"下一个题号"说明切分吞了下一题**（实测宜昌第 12 题
        # 的答案是 `40: $13.\frac{9}{2};$`——把 13 题也吃进来了）。
        # 这种答案宁可不录，录了就是错的。
        if ans and re.search(r"(?:^|[\s$,])\d{1,2}\s*[.．、]\s*\S", ans):
            if skipped is not None:
                skipped.append({"n": n, "why": "答案里混进了下一题的题号",
                                "stem": stem[:60], "ans": ans[:40]})
            continue
        if latex_leak(ans):          # 答案里漏出 \infty 之类
            ans = ""
        if unbalanced(ans):          # 答案里 `$` 个数是奇数
            ans = ""
        if qtype in ("single_choice", "multi_choice"):
            # **选择题的答案只能是字母。** OCR 有时把打分标记、来源注、
            # 断掉的公式混进答案里（实测洛阳第 1 题答案是 `\)……6`）。
            # 不是干净字母就当没答案——错答案比没答案危害大得多。
            if ans and not re.fullmatch(r"[A-D]{1,4}", ans.replace("$", "").strip()):
                ans = ""
            # **卷面解析里写了「故选 X」就以它为准。**
            # 速查表是 OCR 出来的、会认错行（实测深圳中学第 1 题的答案被贴成 D，
            # 而卷面解析白纸黑字写着选 A）；卷面自己的话最权威。
            # 只在"形状对得上"时覆盖：单选认 1 个字母，多选认 ≥2 个——
            # 多选题解析里冒出来的单个字母多半是别处的，不敢用。
            m = re.search(r"(?:故选|答案为|答案是)\s*\$?\s*([A-D]{1,4})", sol)
            if m:
                good = (qtype == "multi_choice" and len(m.group(1)) >= 2) or \
                       (qtype == "single_choice" and len(m.group(1)) == 1)
                if good:
                    ans = m.group(1)
            stem = re.sub(r"\\paren\s*\[[^\]]*\]\s*$", "", stem).rstrip()
            stem += "\\paren[%s]" % ans
        elif qtype == "fill_in_blank":
            stem = fill_blanks(stem, ans)
            if stem is None:
                if skipped is not None:
                    skipped.append({"n": n, "why": "空位数与答案段数对不上",
                                    "stem": q["stem"][:60], "ans": q["ans"][:40]})
                continue
        if qtype == "detailed_answer" and ans and ans not in sol:
            sol = "\\textbf{答案：}%s\n%s" % (ans, sol)
        if not sol:
            sol = NO_SOLUTION
        meta = {"book": book, "source_label": label, "source_no": n}
        meta["difficulty"] = q.get("diff") or difficulty_by_no(n)
        meta["stars"] = {"简单题": 1, "中档题": 2, "难题": 3}[meta["difficulty"]]
        if region:
            meta["region"] = region
        if year:
            meta["year"] = year
        if title:
            meta["paper_title"] = title
        head = {"key": "%s/%s#%d" % (book, label, n), "type": qtype,
                "points": [q["point"]] if q.get("point") else [],
                "meta": meta}
        stem = normalize_fillin(stem)
        env = "problem" if qtype == "detailed_answer" else "question"
        body = ["\\begin{%s}" % env, stem]
        if q["options"]:
            body.append("\\begin{choices}")
            body += ["  \\item %s" % fixup(t) for _l, t in q["options"]]
            body.append("\\end{choices}")
        body += ["\\begin{solution}", sol, "\\end{solution}",
                 "\\end{%s}" % env]
        out.append("%% @q " + json.dumps(head, ensure_ascii=False)
                   + "\n" + "\n".join(body))
    return "\n\n".join(out) + "\n"


# ── 全流程 ────────────────────────────────────────────────────────

_NOISE = re.compile(r"(参考答案|试卷|试题|及答案|答案|及解析|解析|数学)")


def _clean_stem(name: str) -> str:
    """卷名清洗：去通用词、去日期前缀、去「(1)」重名后缀、去两端杂符。

    `guess_label` 和 `pair_answer` **共用这一个**——两边各写一套的话，
    标签是一个样子、配对又是另一个样子，排查起来会怀疑人生。
    """
    s = _NOISE.sub("", name)
    # 日期前缀：6/8 位（250930 / 20260903）一律去掉；4 位只有**不像年份**时才去，
    # 否则「2027届…」会被削成「届…」。
    m = re.match(r"^(\d{4,8})(?=\D)", s)
    if m and (len(m.group(1)) > 4 or not re.fullmatch(r"(?:19|20)\d{2}", m.group(1))):
        s = s[m.end():]
    s = re.sub(r"[（(]\d+[)）]\s*$", "", s)                  # 「(1)」这种重名后缀
    return s.strip(" _-+和与、,，")


def guess_label(pdf: Path) -> str:
    r"""从文件名猜个出处，**只是个默认值**，界面上可以改。

    实测过的几种卷名：`20260903河南青桐鸣…`（日期前缀）、`260830深圳中学…`、
    `数学_河南…_试卷+答案`（前后缀都是通用词）、`…阶段练习(1)`（重名后缀）。
    猜错不要紧（出处是给人看的标注），所以这里不追求聪明。
    """
    s = _clean_stem(pdf.stem)
    y = guess_year(pdf)
    if y and not re.search(r"20\d{2}", s):    # 名字里没年份才补，补了才是「2026XX卷」
        s = "%d%s" % (y, s)
    return s or pdf.stem


def guess_year(pdf: Path) -> int | None:
    m = re.search(r"(20\d{2})", pdf.stem)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d{2})(\d{2})(\d{2})\b", pdf.stem)     # 260830 这种
    return 2000 + int(m.group(1)) if m else None


_ANS_WORD = re.compile(r"答案|解析|详解|参考|DA|教师版|评分标准|学生版")


def pick_main(pdfs: list[Path]) -> tuple[Path, list[Path]]:
    r"""一个考试文件夹 → `(试题, [答案/解析…])`。

    这批卷子是**一个文件夹一场考试**，里面常放 2~3 个 PDF：
    `…数学试题.pdf` + `…数学答案.pdf`（有时还有「小题详解」第三份）。
    所以不能按"一个 PDF 一场考试"跑——那样答案卷会被当成没有题干的卷子，
    白烧几个小时算力。

    判据用文件名：带「答案/解析/详解/DA/教师版/评分标准」的是答案卷，
    剩下的第一个当试题。**学生版**归答案那侧（它常和教师版配套，
    真试题另有一份）。
    """
    main = next((p for p in pdfs if not _ANS_WORD.search(p.stem)), None)
    if main is None:                       # 整个文件夹都像答案卷，就取第一份
        main = pdfs[0]
    return main, [p for p in pdfs if p != main]


def label_for(pdf: Path) -> str:
    r"""出处：**优先用文件夹名**。

    这批卷子的文件夹名就是考卷全名（如「161.安徽皖江名校联盟2026届高三
    上学期12月质检」），比文件名干净得多——文件名常常是
    「安徽皖江名校联盟2026届高三上学期12月质检数学试题」外加一截噪音。
    开头那个序号（`161.`）要去掉。
    """
    name = pdf.parent.name if pdf.parent.name else pdf.stem
    name = re.sub(r"^\s*\d{1,4}\s*[.、．]\s*", "", name)
    s = _clean_stem(name)
    y = guess_year(pdf) or guess_year_from_text(name)
    if y and not re.search(r"20\d{2}", s):
        s = "%d%s" % (y, s)
    return s or _clean_stem(pdf.stem) or pdf.stem


def guess_year_from_text(name: str) -> int | None:
    m = re.search(r"(20\d{2})", name)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{2})(\d{2})(\d{2})", name)
    return 2000 + int(m.group(1)) if m else None


def pair_answer(pdf: Path, *, floor: float = 0.80) -> Path | None:
    r"""在同一目录里猜这份卷子的**答案卷**。

    只有文件名这一条线索可用（扫描件没文字层，内容也对不齐），所以规则很土：
    清掉「数学/试卷/答案」这类通用词后比相似度，名字里带「答案/解析/参考」的加分。

    `floor=0.80` 是**拿这 15 份真实卷名量出来的**：真配对是 1.00（Z20）和
    0.86（深圳中学摸底 ↔ 广东深圳中学8月摸底试题及解析），而最大的假配对是
    0.71（河南青桐鸣 ↔ 河南高二自测卷，两回事）。卡在 0.80 刚好只留真的。

    配错答案比没有答案危害大得多，所以宁可漏配让用户在界面上手点。
    """
    from difflib import SequenceMatcher

    base = _clean_stem(pdf.stem)
    best, score = None, floor
    for p in sorted(pdf.parent.glob("*.pdf")):
        if p.resolve() == pdf.resolve():
            continue
        r = SequenceMatcher(None, base, _clean_stem(p.stem)).ratio()
        if r < floor:
            continue
        s = r + (0.25 if re.search(r"答案|解析|参考", p.stem) else 0)
        if s > score:
            best, score = p, s
    return best


def run(pdf: Path, *, answers=None, book: str = "模拟题",
        label: str = "", region: str = "", year: int | None = None,
        workers: int = 1, force: bool = False, tag: bool = True,
        on_event=None) -> dict:
    r"""一份（或两份）PDF → 可入库的 LaTeX + 一张交代清楚的账。

    `answers` 是**单独的答案卷**（Z20+ 那种）。它和试卷走同一条识别链路，
    合并时只贡献 ANS/SOL/KEY——`merge()` 靠页面的 `@@PAGE kind=答案` 区分，
    所以答案卷放前放后都行。
    """
    label = label or guess_label(pdf)
    year = year or guess_year(pdf)
    scans = scan_pdf(pdf, workers=workers, force=force, on_event=on_event)
    # 答案卷可以有**多份**（试题 + 答案 + 小题详解是常见的三件套）
    for a in ([answers] if isinstance(answers, (str, Path)) else (answers or [])):
        a = Path(a)
        if not a.exists():
            continue
        if on_event:
            on_event({"type": "stage", "text": "识别答案卷 %s" % a.name})
        scans += scan_pdf(a, workers=workers, force=force, on_event=on_event)
    title = next((s["page"]["title"] for s in scans
                  if s["page"].get("title") not in ("", "-")), "")
    classify_pages(scans)                    # 先分试卷页/答案页，再合并
    qs = merge(scans)
    keep, drop, reg = split_figures(qs, src=pdf.name)
    for q in keep:
        q["diff"] = difficulty_by_no(q["n"])
    if tag:
        from concurrent.futures import ThreadPoolExecutor as _TP
        with _TP(max_workers=workers) as _ex:
            for q, pid in zip(keep, _ex.map(tag_point, keep)):
                q["point"] = pid
    lose: list[dict] = []                    # 录不进去的题（空位对不上答案）
    tex = to_tex(keep, book=book, label=label, region=region, year=year,
                 title=title, skipped=lose)
    bad = [s["no"] for s in scans if s.get("error")]
    stats = {
        "卷": label, "出处": "%s%s" % (year or "", label), "标题": title,
        "页数": len(scans), "识别到": len(qs),
        "录入": len(keep) - len(lose), "带图丢弃": len(drop),
        "带图登记位置": len(reg), "未录入": len(lose),
        "无解析": sum(1 for q in keep if not q["sol"].strip()),
        "已打考点": sum(1 for q in keep if q.get("point")),
        "失败页": bad,
        "题型": {t: sum(1 for q in keep if q["type"] == t)
                 for t in ("单选", "多选", "填空", "解答")},
    }
    return {"tex": tex, "kept": keep, "dropped": drop, "register": reg,
            "lost": lose, "stats": stats, "scans": scans, "label": label,
            "year": year, "title": title}


def batch(folder: Path, *, out_dir: Path | None = None, **kw) -> list[dict]:
    r"""跑完一个目录里的所有试卷，**答案卷自动配对、不重复跑**。

    配对规则是 `pair_answer`（按文件名）。被配走的答案卷本身不再当试卷跑——
    否则一份答案卷会被当成一份没有题干的"试卷"，白烧几个小时算力。
    """
    # **每个含 PDF 的目录 = 一场考试**（这批卷子是 `编号段/考试名/试题.pdf`），
    # 所以先按目录分组，再在每个目录里挑试题、把其余当答案卷。
    dirs = sorted({p.parent for p in folder.rglob("*.pdf")})
    if not dirs:
        dirs = [folder]
    rows = []
    for d in dirs:
        pdfs = sorted(d.glob("*.pdf"))
        if not pdfs:
            continue
        main, ans = pick_main(pdfs)
        kw2 = dict(kw)
        kw2["label"] = kw2.get("label") or label_for(main)
        r = run(main, answers=ans, **kw2)
        rows.append(r)
        if out_dir:
            write_out(r, out_dir, book=kw2.get("book", "模拟题"),
                      region=kw2.get("region", ""))
    return rows


def write_out(r: dict, out_dir: Path, *, book: str = "模拟题",
              region: str = "") -> None:
    r"""把一份卷子的产物写到 `out_dir`（`.tex` + 同名 `.json`）。

    `batch()` 和「只补某几份卷子」共用这一条路径——写两套迟早分叉，
    一处改了另一处没改，产物就会长得不一样。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / (r["label"] + ".tex")).write_text(r["tex"], encoding="utf-8")
    (out_dir / (r["label"] + ".json")).write_text(
        json.dumps({"book": book, "label": r["label"], "year": r["year"],
                    "region": region, "stats": r["stats"],
                    "register": r["register"],
                    "dropped": [{"n": q["n"],
                                 "pages": q["exam_pages"] or q["pages"],
                                 "fig": q["fig"]} for q in r["dropped"]],
                    "lost": r["lost"]}, ensure_ascii=False, indent=1),
        encoding="utf-8")


def run_all(folder: Path, *, out_dir: Path | None = None,
            state: Path | None = None, tag: bool = True, workers: int = 8,
            book: str = "模拟题", region: str = "",
            on_event=None) -> dict:
    r"""**一份一份跑、跑完一份立刻入库。** 用户 2026-09-17 定的规矩：

    * 一份一份录入——攒一大批最后一起导，中间一崩就全丢，也没法按份回滚
    * 可中断续跑——这是个通宵的活，断了第二天接着来，不能从头再来

    进度落在 `数据/录题/进度.json`：**每跑完一份就写一次**，所以任何时刻
    拔电，重跑都只补没做完的那些。已经入库且没报错的目录直接跳过。

    依赖：OCR 服务（1235）和本地 27B（1234，打标用）都得活着。
    **这两个都是本地模型，不花任何云端 token。**
    """
    from . import ingest as ig

    state_path = state or (WORK / "进度.json")
    done: dict = {}
    if state_path.exists():
        try:
            done = json.loads(state_path.read_text(encoding="utf-8"))
        except ValueError:
            done = {}
    dirs = sorted({p.parent for p in folder.rglob("*.pdf")})
    todo = [d for d in dirs if not done.get(str(d), {}).get("ok")]
    print("[跑批] 共 %d 场，待跑 %d 场" % (len(dirs), len(todo)), flush=True)
    if not ocr_alive():
        raise RuntimeError("OCR 服务（%s）连不上，先起服务" % OCR_API)
    if tag and not llm_alive():
        raise RuntimeError(
            "打标用的本地 27B（%s）连不上。LM Studio 常常只是**HTTP 服务**"
            "停了而模型还在（`lms ps` 看着是加载的），先 `lms server start`；"
            "模型没加载就 `lms load qwen/qwen3.8-27b --ttl 7200`。" % API)

    stat = {"跑": 0, "新增": 0, "跳过": 0, "失败": 0, "题": 0}
    for i, d in enumerate(todo, 1):
        pdfs = sorted(d.glob("*.pdf"))
        if not pdfs:
            continue
        main, ans = pick_main(pdfs)
        label = label_for(main)
        t0 = time.time()
        try:
            # **label 必须一路传下去。** 不传的话 `run()` 会用文件名猜一个，
            # 而这里入库用的是文件夹名——两套标签不一致，产物文件名就对不上
            # （实测 10 场被判"产物没生成"，其实有，只是名字不同）。
            r = run(main, answers=ans, book=book, region=region, label=label,
                    workers=workers, tag=tag, on_event=on_event)
            if out_dir:
                write_out(r, out_dir, book=book, region=region)
            rep = ig.commit(r["tex"], book=book, label=label,
                            region=region, year=r["year"])
            added = rep.get("added_count")
            ok = added is not None
            done[str(d)] = {"label": label, "ok": ok,
                            "新增": added or 0,
                            "跳过": len(rep.get("skipped") or []),
                            "秒": round(time.time() - t0),
                            "when": time.strftime("%Y-%m-%d %H:%M")}
            stat["跑"] += 1
            stat["新增"] += added or 0
            stat["跳过"] += len(rep.get("skipped") or [])
            stat["题"] += r["stats"]["录入"]
            print("[%d/%d] %-42s %3d题 +%-3s %4.0fs" % (
                i, len(todo), label[:42], r["stats"]["录入"], added,
                time.time() - t0), flush=True)
        except Exception as e:                                 # noqa: BLE001
            stat["失败"] += 1
            done[str(d)] = {"label": label, "ok": False,
                            "err": "%s: %s" % (type(e).__name__, e),
                            "when": time.strftime("%Y-%m-%d %H:%M")}
            print("[%d/%d] %-42s ✗ %s" % (i, len(todo), label[:42], e),
                  flush=True)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_name(state_path.name + ".tmp")
        tmp.write_text(json.dumps(done, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, state_path)
    print("[跑批] 结束：跑 %d，新增 %d 题，跳过 %d，失败 %d" % (
        stat["跑"], stat["新增"], stat["跳过"], stat["失败"]), flush=True)
    return stat


def ingest_dir(out_dir: Path, *, yes: bool = False) -> list[dict]:
    r"""把 `batch()` 产出的 .tex 逐份入库。

    出处/年份从同名 .json 里读（那是 `batch` 自己写的），**不重新猜文件名**——
    再猜一遍就会出现「识别时叫一个名字、入库时叫另一个名字」。

    `yes=False` 只干跑，逐份报「能解析几题 / 规范过没过 / 存量动不动」。
    """
    from . import ingest as ig                       # 延迟导入，别拖慢模块加载

    rows = []
    for tex in sorted(out_dir.glob("*.tex")):
        side = tex.with_suffix(".json")
        info = (json.loads(side.read_text(encoding="utf-8"))
                if side.exists() else {})
        kw = {"book": info.get("book", "模拟题"),
              "label": info.get("label", tex.stem),
              "region": info.get("region", ""), "year": info.get("year")}
        src = tex.read_text(encoding="utf-8")
        rep = ig.commit(src, **kw) if yes else ig.preview(src, **kw)
        rows.append({"卷": kw["label"], "年份": kw["year"],
                     "题数": rep.get("count") or rep.get("added_count"),
                     "新增": rep.get("added_count"),
                     "跳过": len(rep.get("skipped") or []),
                     "规范": (rep.get("spec") or {}).get("ok"),
                     "存量影响": (rep.get("impact") or {}).get("existing_questions")})
    return rows


def report(out_dir: Path) -> str:
    r"""把 `batch()` 的产出汇成一份 markdown 录入报告。

    交代四件事：**每份卷子录了多少 / 带图题丢在哪、8·11·14·18·19 的在哪 /
    哪几页识别失败 / 哪些题没有解析**。后两条是留给人工补的活。
    """
    rows, regs, fails, dropped, lost = [], [], [], [], []
    for side in sorted(out_dir.glob("*.json")):
        info = json.loads(side.read_text(encoding="utf-8"))
        s = info.get("stats", {})
        label = info.get("label", side.stem)
        rows.append((info.get("year"), label, s))
        regs += [(label, r) for r in info.get("register", [])]
        dropped += [(label, d) for d in info.get("dropped", [])]
        lost += [(label, x) for x in info.get("lost", [])]
        fails += ["%s 第 %s 页" % (label, p) for p in s.get("失败页", [])]
    out = ["# 录题报告", "",
           "> 由 `python3 -m amti.record --report 数据/录题/输出` 生成。",
           "> 规矩：**带图题一律不录**；第 8/11/14/18/19 题的带图题只登记位置；",
           "> 没有解析的写「解析无」。", "", "## 一、每份卷子", "",
           "| 年份 | 卷 | 页数 | 识别 | 录入 | 带图丢弃 | 登记位置 | 未录入 | 无解析 | 失败页 |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    tot = {"识别到": 0, "录入": 0, "带图丢弃": 0, "带图登记位置": 0,
           "未录入": 0, "无解析": 0}
    for year, label, s in rows:
        for k in tot:
            tot[k] += s.get(k, 0)
        out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            year or "", label, s.get("页数", 0), s.get("识别到", 0),
            s.get("录入", 0), s.get("带图丢弃", 0), s.get("带图登记位置", 0),
            s.get("未录入", 0), s.get("无解析", 0),
            "、".join(str(x) for x in s.get("失败页", [])) or "—"))
    out.append("| | **合计** | | %d | %d | %d | %d | %d | %d | |" % (
        tot["识别到"], tot["录入"], tot["带图丢弃"], tot["带图登记位置"],
        tot["未录入"], tot["无解析"]))

    out += ["", "## 二、带图题位置登记（只有第 8/11/14/18/19 题）", "",
            "**这些题的正文没有入库**，下面是它们在原卷上的位置，照这个去补图。", ""]
    if regs:
        out += ["| 卷 | 题号 | 页码 | 位置 | 页图（照这个去补图） | 图的说明 |",
                "|---|---|---|---|---|---|"]
        out += ["| %s | %s | %s | %s | `%s` | %s |" % (
            label, r["题号"], "、".join(str(x) for x in r["页码"]),
            r["位置"], r.get("页图", ""), r["图"]) for label, r in regs]
    else:
        out.append("（这一批没有落在 8/11/14/18/19 上的带图题）")

    out += ["", "## 三、全部被丢弃的带图题", "",
            "带图题一律不录。下面**把丢掉的都列出来**——规则只要求登记 8/11/14/18/19 "
            "的位置，但丢掉的是哪些题得能查得到，不然「丢了多少」没人说得清。", ""]
    if dropped:
        out += ["| 卷 | 题号 | 页码 | 图 |", "|---|---|---|---|"]
        out += ["| %s | %s | %s | %s |" % (
            label, d.get("n"), "、".join(str(x) for x in d.get("pages", [])),
            (d.get("fig") or "").replace("\n", " ")[:60]) for label, d in dropped]
    else:
        out.append("（没有带图题）")

    out += ["", "## 四、没能录入的题", "",
            "两种原因：**题干为空**（答案页上有题号、试卷页没转出题干），"
            "或**填空位个数与答案段数对不上**。这两种 `ingest` 的复核都会拦下，"
            "而且是**整份卷子都不录**，所以在这里先剔掉、留痕。这几道要人工看。", ""]
    if lost:
        out += ["| 卷 | 题号 | 题干开头 | 抽到的答案 |", "|---|---|---|---|"]
        out += ["| %s | %s | %s | %s |" % (
            label, x["n"], x.get("stem", "").replace("\n", " "),
            x.get("ans", "")) for label, x in lost]
    else:
        out.append("（无）")

    out += ["", "## 五、识别失败的页", ""]
    out += ["- " + f for f in fails] if fails else ["（无）"]
    out += ["", "## 六、这些题没有解析", "",
            "库里按规矩写的是「解析无」，需要人工补。", ""]
    miss = [(label, s.get("无解析", 0)) for _y, label, s in rows
            if s.get("无解析")]
    out += ["- %s：%d 道" % (l, n) for l, n in miss] if miss else ["（没有，全部带解析）"]
    return "\n".join(out) + "\n"


def _main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="试卷录题（本地大模型）")
    ap.add_argument("--pdf")
    ap.add_argument("--dir", help="批量：跑这个目录里所有 PDF（答案卷自动配对）")
    ap.add_argument("--answers")
    ap.add_argument("--book", default="模拟题")
    ap.add_argument("--label", default="")
    ap.add_argument("--region", default="")
    ap.add_argument("--year", type=int)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--ingest-dir", default="",
                    help="把已经跑出来的 --outdir 里的 .tex 逐份入库")
    ap.add_argument("--yes", action="store_true", help="配合 --ingest-dir：真写库")
    ap.add_argument("--report", default="",
                    help="把 --outdir 的产出汇成 markdown 录入报告")
    ap.add_argument("--all", default="",
                    help="通宵跑批：递归跑这个目录，**一份一份跑完立刻入库**，可中断续跑")
    ap.add_argument("--no-tag", action="store_true", help="不打考点（省时间）")
    a = ap.parse_args(argv)
    if a.all:
        run_all(Path(a.all), out_dir=Path(a.outdir) if a.outdir else None,
                tag=not a.no_tag, workers=a.workers, book=a.book,
                region=a.region)
        return 0
    if a.report:
        print(report(Path(a.report)))
        return 0
    if a.ingest_dir:
        rows = ingest_dir(Path(a.ingest_dir), yes=a.yes)
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        print("[干跑] 什么都没写。确认后加 --yes" if not a.yes else "已入库")
        return 0
    if not a.pdf and not a.dir:
        ap.error("要么 --pdf，要么 --dir，要么 --ingest-dir")

    def ev(e):
        if e["type"] == "page":
            print("  第 %d/%d 页 %s%s" % (
                e["page"], e["total"],
                "%.0fs" % e["secs"] if e.get("secs") else "",
                "（缓存）" if e["cached"] else
                ("  ✗ %s" % e["error"] if e.get("error") else "")), flush=True)

    common = dict(book=a.book, region=a.region, workers=a.workers,
                  force=a.force, on_event=ev)
    if a.dir:
        rows = batch(Path(a.dir), label=a.label, year=a.year,
                     out_dir=Path(a.outdir) if a.outdir else None, **common)
        print(json.dumps([r["stats"] for r in rows], ensure_ascii=False, indent=1))
        return 0
    r = run(Path(a.pdf), answers=Path(a.answers) if a.answers else None,
            label=a.label, year=a.year, **common)
    print(json.dumps(r["stats"], ensure_ascii=False, indent=2))
    if a.out:
        Path(a.out).write_text(r["tex"], encoding="utf-8")
        print("写出", a.out)
    return 0


def _selftest() -> int:
    r"""回归用例。**只测纯函数**——不碰模型、不碰题库、不写任何文件。

    盯的是三条规矩和最容易悄悄坏掉的地方：
    跨页拼接、答案页只取答案不覆盖题干、带图题过滤、答案写进作答位、
    没解析要写「解析无」。
    """
    fails = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    RAW = r"""@@PAGE kind=试题 title=某卷 数学
@@Q n=1 type=单选 figure=无 continued=否
@@STEM
已知 $z$ 是复数，则 $z=$\paren[]
@@OPT
A. $1$
B. $2$
@@FIG
->
@@ANS
->
@@SOL
->
@@ENDQ
@@Q n=7 type=解答 figure=无 continued=是
@@STEM
(1) 求 $a$；
@@OPT
->
@@FIG
->
@@ANS
->
@@SOL
->
@@ENDQ
@@Q n=8 type=单选 figure=有 continued=否
@@STEM
如图，四棱锥 $P-ABCD$ 中，则
@@OPT
A. $\frac{1}{12}$
B. $\frac{1}{6}$
@@FIG
四棱锥立体图
@@ANS
->
@@SOL
->
@@ENDQ
@@FIGPOS n=8 y=中 x=右
"""
    NEXT = r"""@@PAGE kind=试题 title=某卷 数学
@@Q n=7 type=解答 figure=无 continued=否
@@STEM
(2) 求 $b$。
@@OPT
->
@@FIG
->
@@ANS
->
@@SOL
->
@@ENDQ
"""
    ANS = r"""@@PAGE kind=答案 title=-
@@KEY 1.A 2.B
@@Q n=1 type=- figure=无 continued=否
@@STEM
->
@@OPT
->
@@FIG
->
@@ANS
A
@@SOL
因为 $z=1+\mathrm{i}$，所以选 A。
@@ENDQ
@@Q n=7 type=- figure=无 continued=否
@@STEM
->
@@OPT
->
@@FIG
->
@@ANS
$a=1$
@@SOL
由题意得 $a=1$。
@@ENDQ
"""

    p1 = parse_marked(RAW)
    check("解析出 3 道题", len(p1["questions"]) == 3, str(len(p1["questions"])))
    check("页信息认出来了", p1["page"] == {"kind": "试题", "title": "某卷 数学"},
          str(p1["page"]))
    check("figure 标记认出来了", p1["questions"][2]["figure"] is True)
    check("选项按标号拆开", p1["questions"][0]["options"] ==
          [("A", "$1$"), ("B", "$2$")], str(p1["questions"][0]["options"]))
    check("FIGPOS 认出来了", p1["figpos"].get("8", {}).get("y") == "中")

    def scan(marked: str, no: int) -> dict:
        d = parse_marked(marked)
        d["no"] = no                      # 与 `scan_pdf` 的返回结构一致
        return d

    qs = merge([scan(RAW, 1), scan(NEXT, 2), scan(ANS, 7)])
    by = {q["n"]: q for q in qs}
    check("跨页的题拼到一起（正序）",
          "(1) 求 $a$；" in by["7"]["stem"] and "(2) 求 $b$。" in by["7"]["stem"]
          and by["7"]["stem"].index("(1)") < by["7"]["stem"].index("(2)"),
          repr(by["7"]["stem"]))
    check("答案页不覆盖题干", by["1"]["stem"].startswith("已知 $z$ 是复数"),
          repr(by["1"]["stem"]))
    check("答案从 @@KEY 补上", by["1"]["ans"] == "A", repr(by["1"]["ans"]))
    check("解析从答案页接上", "选 A" in by["1"]["sol"], repr(by["1"]["sol"]))

    keep, drop, reg = split_figures(qs, src="某卷.pdf")
    check("带图题不进录入", [q["n"] for q in keep] == ["1", "7"],
          str([q["n"] for q in keep]))
    check("带图题被丢掉", [q["n"] for q in drop] == ["8"])
    # 卷首「考试说明」也带 1. 2. 3. 编号，会被当成题、还会挤掉真题号。
    # 这两个用例是补的——过滤写对了但名字撞车，跑完一整轮才发现没生效。
    check("题号→难度（用户定的规则）",
          [difficulty_by_no(n) for n in (1, 2, 9, 12, 15)] == ["简单题"] * 5
          and [difficulty_by_no(n) for n in (8, 11, 14, 18, 19)] == ["难题"] * 5
          and [difficulty_by_no(n) for n in (3, 5, 10, 13, 16, 17)] == ["中档题"] * 6,
          str([difficulty_by_no(n) for n in range(1, 20)]))
    check("考试说明被识别成噪声",
          is_noise("答题前，请将自己的学校、姓名等填写在答题卡上。", []))
    check("小节标题被识别成噪声",
          is_noise("一、选择题：本题共8小题，每小题5分，共40分。", []))
    check("真题不会被误判成噪声",
          not is_noise("已知函数 $f(x)=x^3+\\ln x$，则曲线 $y=f(x)$ 在点 $(1,1)$ 处的切线方程为",
                       [("A", "$y=4x-3$")]))
    check("登记的是**试卷页**，不是答案页",
          split_figures([dict(qs[[q["n"] for q in qs].index("8")],
                              exam_pages=[2])], src="x.pdf")[2][0]["页码"] == [2])
    check("第 8 题的带图题登记了位置",
          len(reg) == 1 and reg[0]["题号"] == 8 and reg[0]["位置"] == "中 右",
          str(reg))

    check("答案写进作答括号", r"\paren[A]" in to_tex([by["1"]], book="模拟题",
                                                label="某卷"),
          to_tex([by["1"]], book="模拟题", label="某卷"))
    fill = {"n": "9", "type": "填空", "figure": False, "stem": "最小值是\\fillin[]。",
            "options": [], "fig": "", "ans": "$3$", "sol": ""}
    tex = to_tex([fill], book="模拟题", label="某卷")
    check("答案写进填空位", r"\fillin[$3$]" in tex, tex)
    check("没有解析就写「解析无」", NO_SOLUTION in tex, tex)
    det = {"n": "17", "type": "解答", "figure": False, "stem": "求 $a$。",
           "options": [], "fig": "", "ans": "$a=1$", "sol": "由题意，两边平方后整理即得。"}
    dtex = to_tex([det], book="模拟题", label="某卷")
    check("解答题用 problem 环境", "\\begin{problem}" in dtex, dtex)
    check("解答题答案写进 solution", "\\textbf{答案：}$a=1$" in dtex, dtex)
    check("答案已在解析里就不重复写",
          "\\textbf{答案：}" not in to_tex(
              [dict(det, sol="由题意得 $a=1$。")], book="模拟题", label="某卷"))
    check("出处与题号写进 key",
          '"source_no": 17' in to_tex([det], book="模拟题", label="2026某卷"),
          to_tex([det], book="模拟题", label="2026某卷").splitlines()[0])

    check("下划线空位也能兜住",
          r"\fillin[$3$]" in fill_blanks("最小值是 ______。", "$3$"),
          fill_blanks("最小值是 ______。", "$3$"))
    check("两个空、答案用逗号也能切开",
          fill_blanks("个数为 \\fillin[]，最少为 \\fillin[]。", "5, 7")
          == "个数为 \\fillin[5]，最少为 \\fillin[7]。",
          repr(fill_blanks("个数为 \\fillin[]，最少为 \\fillin[]。", "5, 7")))
    check("切不开就拒收这道题（不能让整份卷子录不进去）",
          fill_blanks("\\fillin[] 与 \\fillin[]", "5, 7, 9") is None)

    # 幽灵题：答案页有题号、试卷页没题干。留着它整份卷子都录不进去。
    _ghost = {"n": "20", "type": "解答", "figure": False, "stem": "->",
              "options": [], "fig": "", "ans": "$x^2=1$", "sol": ""}
    _skip: list = []
    _t = to_tex([by["1"], _ghost], book="模拟题", label="某卷", skipped=_skip)
    check("题干为空的幽灵题被剔掉且留痕",
          len(_skip) == 1 and _skip[0]["n"] == 20 and "题干为空" in _skip[0]["why"]
          and "#20" not in _t, str(_skip))
    check("剔掉幽灵题不影响同卷其他题", "#1\"" in _t, _t[:80])
    check("卷名清洗", _clean_stem("数学_河南2026-2027年高二上学期开学学情自测卷_试卷+答案")
          == "河南2026-2027年高二上学期开学学情自测卷",
          _clean_stem("数学_河南2026-2027年高二上学期开学学情自测卷_试卷+答案"))
    check("日期前缀不当成年份",
          guess_label(Path("20260903河南青桐鸣2027届高三9月学情调研数学.pdf"))
          == "河南青桐鸣2027届高三9月学情调研",
          guess_label(Path("20260903河南青桐鸣2027届高三9月学情调研数学.pdf")))
    check("没年份的卷名补上年份",
          guess_label(Path("260830深圳中学2027届高三摸底考试数学.pdf"))
          == "深圳中学2027届高三摸底考试",
          guess_label(Path("260830深圳中学2027届高三摸底考试数学.pdf")))

    check(r"\mathbf{R} 拉回 \mathbb{R}",
          fixup(r"$x\in\mathbf{R}$") == r"$x\in\mathbb{R}$", fixup(r"$x\in\mathbf{R}$"))
    check("裸 i 不碰（可能是下标，改了就是错）", fixup("$z=i$") == "$z=i$")
    check(r"\text{e} 拉回 \mathrm{e}", fixup(r"$y=\text{e}^x$") == r"$y=\mathrm{e}^x$",
          fixup(r"$y=\text{e}^x$"))
    check("去掉卷面的【解析】标记",
          strip_marker("【解析】因为所以。") == "因为所以。"
          and strip_marker("因为所以【解析】。") == "因为所以【解析】。")

    # 同一题被转写两次要取更完整的，跨页的两半要拼起来——分错就是题干重复。
    _a = "在 160 和 -5 之间插入 4 个数，使这 6 个数成等比数列，则公比 $q$ 的值为"
    _b = "在 160 和 $-5$ 之间插入 4 个数，使这 6 个数成等比数列，则公比 $q$ 的值为"
    check("同一题的两次转写认得出来", same_question(_a, _b))
    check("跨页的两半不当成同一题",
          not same_question("(1) 求 $a$；", "(2) 求 $b$。")
          and not same_question("如图，在四棱锥 $P-ABCD$ 中，底面 $ABCD$ 是正方形，",
                                "侧面 $PAD$ 是正三角形，且平面 $PAD \\perp$ 平面 $ABCD$。"))
    _dup = merge([scan(RAW, 1), scan(RAW.replace("已知 $z$ 是复数，", "已知 $z$ 是复数"),
                                     5)])
    check("题干不会被接两遍",
          _dup[0]["stem"].count("已知 $z$ 是复数") == 1, repr(_dup[0]["stem"]))

    # `scan_pdf` 的返回契约：页码在 `no`，页信息在 `page`。
    # 一开始把页码写进了 `page`，批量跑到第二页就 AttributeError。
    sc = {"page": {"kind": "试题", "title": "某卷"}, "no": 3,
          "key": {}, "figpos": {}, "questions": p1["questions"]}
    check("页信息与页码是两个字段",
          merge([sc])[0]["pages"] == [3] and merge([sc])[0]["stem"].startswith("已知"))

    print("录题自检：%s" % ("全部通过" if not fails else "%d 项失败" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_selftest() if "--selftest" in sys.argv else _main())
