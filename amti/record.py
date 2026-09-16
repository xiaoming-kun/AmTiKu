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


def ask(img: Path, *, timeout: int = 2400, prompt: str = PROMPT) -> str:
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
                {"type": "text", "text": "转录这一页。"},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]},
        ],
        "temperature": 0.1,
        "max_tokens": MAX_TOKENS,
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


# ── 页图 ──────────────────────────────────────────────────────────


def pages_of(pdf: Path, out: Path, *, dpi: int = 200) -> list[Path]:
    r"""一份 PDF → 每页一张图。

    扫描件**直接取内嵌原图**（`extract_image`，不重编码、不掉清晰度）；
    只有真正的矢量页才渲染。**已经抽过就复用**——重跑一份 10 页的卷子
    不该再把 10 张图重抽一遍。
    """
    import fitz                                    # 重依赖，用到才导

    out.mkdir(parents=True, exist_ok=True)
    got: list[Path] = []
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc, 1):
            hit = sorted(out.glob(f"p{i:03d}.*"))
            if hit:
                got.append(hit[0])
                continue
            imgs = page.get_images(full=True)
            big = max(imgs, key=lambda x: x[2] * x[3], default=None)
            if big and big[2] * big[3] > 200_000:      # 整页扫描图
                d = doc.extract_image(big[0])
                p = out / f"p{i:03d}.{d['ext']}"
                p.write_bytes(d["image"])
            else:                                       # 矢量页
                p = out / f"p{i:03d}.png"
                page.get_pixmap(dpi=dpi).save(p)
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
    work = work or WORK / pdf.stem
    imgs = pages_of(pdf, work / "pages")
    cache = work / "scan"
    cache.mkdir(parents=True, exist_ok=True)
    rows: list[dict | None] = [None] * len(imgs)

    def one(i: int, img: Path) -> dict:
        dst = cache / f"p{i:03d}.json"
        if dst.exists() and not force:
            d = json.loads(dst.read_text(encoding="utf-8"))
            d["cached"] = True
        else:
            try:
                d = parse_marked(ask(img))
                d.update(secs=last().get("secs"), finish=last().get("finish"))
                # 原子写：批量与界面可能同时读同一份缓存，半截 JSON 会让对方直接崩
                tmp = dst.with_name(dst.name + ".tmp")
                tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                               encoding="utf-8")
                os.replace(tmp, dst)
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
            if not is_ans_page:
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
                "图": q["fig"] or "（模型没描述）",
                "位置": " ".join(x for x in (q["figpos"].get("y", ""),
                                            q["figpos"].get("x", "")) if x) or "（未标注）",
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
    return _TEXT_MATH.sub(r"\\mathrm{\1}", _BB.sub(r"\\mathbb{\1}", tex))


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
    parts = _split_answers(ans, holes)
    if len(parts) != holes:
        return None
    it = iter(parts)
    return _FILLIN.sub(lambda _m: "\\fillin[%s]" % next(it), stem)


def to_tex(qs: list[dict], *, book: str, label: str, region: str = "",
           year: int | None = None, title: str = "",
           skipped: list | None = None) -> str:
    r"""结构化题目 → exam-zh LaTeX 源（`ingest` 认得的那种）。

    **只写 `key` / `type` / `meta` 三样**，其余字段由 `ingest` 补。
    题干里的答案按规范 §2.2 就地写进 `\paren[…]` / `\fillin[…]`；
    解答题的答案与解析都进 `solution`。

    `skipped` 传一个 list 进来，录不进去的题（空位数与答案段数对不上）
    会以 `{"n", "why"}` 追加进去——**丢掉哪道题必须留痕**，不能默默少一道。
    """
    out: list[str] = []
    for i, q in enumerate(qs, 1):
        n = int(q["n"])
        qtype = TYPE_MAP.get(q["type"], "")
        ans, sol = fixup(q["ans"].strip()), strip_marker(fixup(q["sol"].strip()))
        stem = fixup(q["stem"].strip())
        if qtype in ("single_choice", "multi_choice"):
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
        if region:
            meta["region"] = region
        if year:
            meta["year"] = year
        if title:
            meta["paper_title"] = title
        head = {"key": "%s/%s#%d" % (book, label, n), "type": qtype,
                "meta": meta}
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


def run(pdf: Path, *, answers: Path | None = None, book: str = "模拟题",
        label: str = "", region: str = "", year: int | None = None,
        workers: int = 1, force: bool = False, on_event=None) -> dict:
    r"""一份（或两份）PDF → 可入库的 LaTeX + 一张交代清楚的账。

    `answers` 是**单独的答案卷**（Z20+ 那种）。它和试卷走同一条识别链路，
    合并时只贡献 ANS/SOL/KEY——`merge()` 靠页面的 `@@PAGE kind=答案` 区分，
    所以答案卷放前放后都行。
    """
    label = label or guess_label(pdf)
    year = year or guess_year(pdf)
    scans = scan_pdf(pdf, workers=workers, force=force, on_event=on_event)
    if answers:
        if on_event:
            on_event({"type": "stage", "text": "识别答案卷 %s" % answers.name})
        scans += scan_pdf(answers, workers=workers, force=force, on_event=on_event)
    title = next((s["page"]["title"] for s in scans
                  if s["page"].get("title") not in ("", "-")), "")
    qs = merge(scans)
    keep, drop, reg = split_figures(qs, src=pdf.name)
    lose: list[dict] = []                    # 录不进去的题（空位对不上答案）
    tex = to_tex(keep, book=book, label=label, region=region, year=year,
                 title=title, skipped=lose)
    bad = [s["no"] for s in scans if s.get("error")]
    stats = {
        "卷": label, "出处": "%s%s" % (year or "", label), "标题": title,
        "页数": len(scans), "识别到": len(qs),
        "录入": len(keep) - len(lose), "带图丢弃": len(drop),
        "带图登记位置": len(reg), "空位对不上": len(lose),
        "无解析": sum(1 for q in keep if not q["sol"].strip()),
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
    consumed: set[Path] = set()
    rows = []
    for pdf in sorted(folder.glob("*.pdf")):
        if pdf in consumed:
            continue
        ans = pair_answer(pdf)
        if ans:
            consumed.add(ans)
        r = run(pdf, answers=ans, **kw)
        rows.append(r)
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / (r["label"] + ".tex")).write_text(r["tex"], encoding="utf-8")
            (out_dir / (r["label"] + ".json")).write_text(
                json.dumps({"book": kw.get("book", "模拟题"),
                            "label": r["label"], "year": r["year"],
                            "region": kw.get("region", ""),
                            "stats": r["stats"], "register": r["register"],
                            "dropped": [{"n": q["n"],
                                         "pages": q["exam_pages"] or q["pages"],
                                         "fig": q["fig"]}
                                        for q in r["dropped"]],
                            "lost": r["lost"]},
                           ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


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
           "| 年份 | 卷 | 页数 | 识别 | 录入 | 带图丢弃 | 登记位置 | 空位对不上 | 无解析 | 失败页 |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    tot = {"识别到": 0, "录入": 0, "带图丢弃": 0, "带图登记位置": 0,
           "空位对不上": 0, "无解析": 0}
    for year, label, s in rows:
        for k in tot:
            tot[k] += s.get(k, 0)
        out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            year or "", label, s.get("页数", 0), s.get("识别到", 0),
            s.get("录入", 0), s.get("带图丢弃", 0), s.get("带图登记位置", 0),
            s.get("空位对不上", 0), s.get("无解析", 0),
            "、".join(str(x) for x in s.get("失败页", [])) or "—"))
    out.append("| | **合计** | | %d | %d | %d | %d | %d | %d | |" % (
        tot["识别到"], tot["录入"], tot["带图丢弃"], tot["带图登记位置"],
        tot["空位对不上"], tot["无解析"]))

    out += ["", "## 二、带图题位置登记（只有第 8/11/14/18/19 题）", "",
            "**这些题的正文没有入库**，下面是它们在原卷上的位置，照这个去补图。", ""]
    if regs:
        out += ["| 卷 | 题号 | 页码 | 图上位置 | 图长什么样 |", "|---|---|---|---|---|"]
        out += ["| %s | %s | %s | %s | %s |" % (
            label, r["题号"], "、".join(str(x) for x in r["页码"]),
            r["位置"], r["图"]) for label, r in regs]
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

    out += ["", "## 四、空位数与答案对不上、没有录入的题", "",
            "填空位个数和答案段数对不上时**宁可少录一道**，也不录一道答案错位的题"
            "（`conform` 的「填空位数」会拦下这种题，而 `ingest` 一发现违规"
            "是整份卷子都不录）。这几道要人工看一眼。", ""]
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
    a = ap.parse_args(argv)
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
