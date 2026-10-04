from __future__ import annotations

import argparse
import importlib.util
import json
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "脚本"))

from amti import record as R                                    # noqa: E402

# ── 端口 ─────────────────────────────────────────────────────────
# `amti/record.py` 把 API 地址写死成 1234，而 **LM Studio 常年占着 1234**
# （监听进程名是 `LM Studio` 而不是 `llama-server`，所以 `pkill -f llama-server`
# 根本打不到它——实测踩过，起了新服务却连回旧服务，扫出来全是别的模型的结果）。
# 与其把用户正在用的 LM Studio 杀掉，不如**自己另起一个 1235**：
# 在驱动里覆盖这一个常量即可，不动共享模块。
# 跑批脚本用同一个端口，两边靠 `AMTI_API_PORT` 对齐。
API_PORT = int(__import__("os").environ.get("AMTI_API_PORT", "1235"))
R.API = "http://127.0.0.1:%d/v1/chat/completions" % API_PORT


def _load_zlx():
    r"""把 `脚本/赵礼显讲义录题.py` 当模块导入，复用它的提示词与解析/组装。

    为什么不复制一份：那份文件里 51KB 有相当一部分是**调提示词调出来的经验**
    （讲义版提示词、`@@` 标记的边角、"练习跨页"的判法、`finalize` 里
    "先补作答位再规范化"的顺序）。复制一份 = 两个真相，
    以后改一处忘一处，正是 AGENTS.md 里明令避免的。
    """
    p = ROOT / "脚本" / "赵礼显讲义录题.py"
    spec = importlib.util.spec_from_file_location("_zlx", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


Z = _load_zlx()

SRC = Path.home() / "Desktop/27年试卷/其他杂项"
WORK = ROOT / "数据/录题/其他杂项"
DOCX_PDF = WORK / "docx"          # docx 转出来的 PDF
PAGES = WORK / "pages"            # pages/<slug>/pNNN.png
SCAN = WORK / "scan"              # scan/<slug>/pNNN.txt
BOXES = WORK / "boxes"            # boxes/<slug>/pNNN.txt
OUT = WORK / "out"                # out/<slug>.tex
FIGS = WORK / "figs"              # figs/<slug>.json
FIGDIR = ROOT / "图片"            # 全库共用的配图目录（内容寻址命名）

BOOK = "27年试卷其他杂项"
LEC = "初升高衔接讲义"

NODE = ("/Applications/DeepSeek Harness.app/Contents/Resources/runtime/"
        "primary-runtime/dependencies/node/bin/node")
LO_CLI = ("/Applications/DeepSeek Harness.app/Contents/Resources/app.asar.unpacked/"
          "dsh/node_modules/@deepseek-ai/libreoffice-kit/lib/cli.js")


# ── 源文件清单 ────────────────────────────────────────────────────
def slugify(name: str) -> str:
    r"""文件名 → 目录名/键名用的短名。**保留中文**（题库里本来就用中文 key）。

    只去掉在 **zip / Windows / JSON 键**里会惹麻烦的字符：
    `：` `《》` `•` 空格 `/` 等。赵礼显那次用中文讲次名当 key 是没问题的。
    """
    s = name
    for ch in "：:《》•　 　/\\?*\"<>|()（）【】":
        s = s.replace(ch, "")
    s = re.sub(r"\s+", "", s)
    return s.strip()


def _match(files: list[dict], pat: str) -> list[dict]:
    r"""`--file` 选文件。**先精确比 slug，再退回子串**。

    为什么要精确优先：`第1讲` 是 `第10讲`、`第11讲`… 的子串，
    纯子串匹配会一口气选中 12 个文件——而跑批脚本每块都要重启一次服务，
    选错就是白烧一小时。实测这批文件里 `第1讲` 到 `第21讲` 全中。
    """
    if not pat:
        return files
    exact = [f for f in files if f["slug"] == pat or f["label"] == pat]
    if exact:
        return exact
    return [f for f in files if pat in f["slug"] or pat in f["label"]]


def _norm_cmp(s: str) -> str:
    r"""粗归一化，用来比"标题像不像某个文件名"。

    要治的实例：模型给的 `title=第01讲：数与式`（补了前导零）
    对上文件名 `第1讲：数与式(教师版)`（没有前导零）——
    不归一化就**一个字都比不中**，防线等于没有。
    """
    s = re.sub(r"0+(\d)", r"\1", s)              # 第01讲 → 第1讲
    return re.sub(r"[^\w\u4e00-\u9fff]", "", s)   # 去标点/空格/括号


def list_files() -> list[dict]:
    r"""27 个要处理的文件。**只取教师版**（学生版跳过——用户明确只要教师版）。"""
    out: list[dict] = []

    # ① 顶层 6 个 PDF
    for p in sorted(SRC.glob("*.pdf")):
        out.append({"kind": "pdf", "src": p, "slug": slugify(p.stem),
                    "label": p.stem})

    # ② 21 个教师版 docx（用已转好的 PDF 当源）
    d = SRC / "2026《高中数学•初升高衔接讲义》21讲"
    for p in sorted(d.glob("*教师版*.docx")):
        pdf = DOCX_PDF / (p.stem + ".pdf")
        out.append({"kind": "docx", "src": p, "pdf": pdf,
                    "slug": slugify(p.stem), "label": p.stem})

    # 去重：同一个 slug 撞了就在后面加序号（实测「第14讲：奇偶性  (教师版)」
    # 这种名字里空格数不一样的文件名会被 slugify 成同一个）
    seen: dict[str, int] = {}
    for f in out:
        k = f["slug"]
        if k in seen:
            seen[k] += 1
            f["slug"] = "%s_%d" % (k, seen[k])
        else:
            seen[k] = 1
    return out


def pdf_of(f: dict) -> Path:
    return f.get("pdf") or f["src"]


def use(f: dict) -> None:
    r"""把这一个文件的路径常量指到 `zlx` 模块上。

    ⚠️ `zlx` 里的函数是**在调用时**读这些模块全局的，所以赋值即生效。
    这是"复用而不复制"的代价：得知道它读哪几个全局。实测只有这 8 个。
    """
    # ⚠️ 名字必须和 `赵礼显讲义录题.py` 里**真实存在**的常量逐一对上。
    # 这里踩过一次：boxes 那个常量在模块里叫 `SCAN2`，我写成了 `Z.BOXES`
    # （那个名字根本不存在）—— 于是**静默走了错目录**：`figs` 读的是
    # 赵礼显的旧 boxes、什么框都没有，表现成"模型一个框都没给"，
    # 而日志一切正常。下面那道 `hasattr` 断言就是为这个加的：
    # 名字打错要当场炸，不要静默走错路径。
    _set = {
        "PAGES": PAGES / f["slug"],
        "SCAN": SCAN / f["slug"],
        "SCAN2": BOXES / f["slug"],      # 模块里 boxes 叫 SCAN2
        "WORK": WORK,
        "OUT": OUT,
        "FIGS": FIGS / (f["slug"] + ".json"),
        "FIGDIR": FIGDIR,
        "BOOK": BOOK,
        "LABEL": f["label"],
        "PDF": pdf_of(f),
    }
    for _k, _v in _set.items():
        if not hasattr(Z, _k):
            raise AttributeError(
                "赵礼显讲义录题.py 里没有常量 %r —— 覆盖它等于白设、"
                "会静默走错路径。核对模块里的真实常量名再改。" % _k)
        setattr(Z, _k, _v)
    # ⚠️ `FIGS` 的**父目录必须自己建**：赵礼显那版是 `WORK/figs.json`
    # （直接放根下，没有父目录问题），本驱动改成了 `figs/<文件>.json`，
    # 而 `cmd_figs` 只 `FIGS.write_text(...)`、不建目录 ——
    # 于是裁完图写映射那一刻抛 FileNotFoundError，**图裁出来了、映射没落盘**，
    # 后面 `build` 就以为"一道带图题都没裁到"。实测踩过。
    Z.FIGS.parent.mkdir(parents=True, exist_ok=True)
    Z.FIGDIR = FIGDIR
    Z.BOOK = BOOK
    Z.LABEL = f["label"]
    # 一个文件就是一"讲"：不抄目录、不让模型判讲次（赵礼显那本抄目录抄出过
    # 29 个撞号，这里没有目录可抄，直接整本归一讲，从根上避开）。
    Z.lecture_map = lambda scans: [(f["slug"], f["label"], 1, 10 ** 9)]


# ── convert：docx → PDF ──────────────────────────────────────────
def cmd_convert(a) -> int:
    DOCX_PDF.mkdir(parents=True, exist_ok=True)
    did = skip = fail = 0
    for f in list_files():
        if f["kind"] != "docx":
            continue
        out = f["pdf"]
        if out.exists() and not a.force:
            skip += 1
            continue
        r = subprocess.run([NODE, LO_CLI, "convert",
                            "--input", str(f["src"]), "--output", str(out)],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and out.exists():
            did += 1
            m = re.search(r'"missingFonts":\[([^\]]*)\]', r.stdout or "")
            fonts = (m.group(1) if m else "").strip()
            print("  ✓ %s%s" % (f["label"], ("  缺字体 " + fonts) if fonts else ""))
        else:
            fail += 1
            print("  ✗ %s\n    %s" % (f["label"], (r.stderr or r.stdout or "")[-300:]))
    print("docx→PDF：新转 %d，已缓存 %d，失败 %d" % (did, skip, fail))
    return 1 if fail else 0


# ── list ────────────────────────────────────────────────────────
def cmd_list(a) -> int:
    import fitz
    tot = 0
    for i, f in enumerate(list_files(), 1):
        p = pdf_of(f)
        n = fitz.open(p).page_count if p.exists() else -1
        tot += max(n, 0)
        flag = "" if p.exists() else "   ← PDF 还没生成（先跑 convert）"
        print("  %2d. %-6s %-4s %4d 页  %s%s"
              % (i, f["kind"], "", n, f["label"], flag))
    print("  合计 %d 页" % tot)
    return 0


# ── scan ────────────────────────────────────────────────────────
def cmd_scan(a) -> int:
    files = list_files()
    if a.file:
        files = _match(files, a.file)
        if not files:
            print("没有匹配 --file 的文件"); return 1
    grand_todo = grand_done = 0
    bad_all: list[tuple[str, str]] = []
    t0 = time.time()
    for f in files:
        use(f)
        pdf = pdf_of(f)
        if not pdf.exists():
            print("✗ %s：PDF 不存在，先跑 convert" % f["label"]); continue
        Z.PAGES.mkdir(parents=True, exist_ok=True)
        Z.SCAN.mkdir(parents=True, exist_ok=True)
        if not list(Z.PAGES.glob("p*.png")):
            R.pages_of(pdf, Z.PAGES, dpi=300)
        imgs = sorted(Z.PAGES.glob("p*.png"))
        if a.only:
            lo, hi = Z._range(a.only)
            imgs = [p for p in imgs if lo <= int(p.stem[1:]) <= hi]
        todo = [p for p in imgs
                if a.force or not (Z.SCAN / (p.stem + ".txt")).exists()]
        print("\n══ %s（%d 页，待转录 %d）" % (f["label"], len(imgs), len(todo)))
        if not todo:
            continue
        grand_todo += len(todo)
        done = [0]

        def one(p: Path) -> None:
            dst = Z.SCAN / (p.stem + ".txt")
            last = ""
            for attempt in range(3):
                try:
                    txt = R.ask(p, prompt=Z.PROMPT, max_tokens=4500,
                                note="转录这一页。")
                    if len(txt) < 20:
                        raise RuntimeError("产物过短（%d 字）" % len(txt))
                    dst.write_text(txt, encoding="utf-8")
                    done[0] += 1
                    print("  %s ✓ %.0fs  (%d/%d)"
                          % (p.stem, R.last().get("secs", 0), done[0], len(todo)))
                    return
                except Exception as e:                      # noqa: BLE001
                    last = "%s: %s" % (type(e).__name__, e)
                    time.sleep(5)
            bad_all.append(("%s/%s" % (f["slug"], p.stem), last))
            print("  %s ✗ %s" % (p.stem, last))

        # ⚠️ **有界队列**，不是 ThreadPoolExecutor.map——后者把几百个请求一次性
        # 全压给 llama-server，客户端被杀时服务端仍会把已入队的生成完，
        # 实测让下一批的头 4 页等了 968 秒。见 赵礼显 README 坑 2。
        q: "queue.Queue[Path]" = queue.Queue()
        for p in todo:
            q.put(p)

        def worker() -> None:
            while True:
                try:
                    p = q.get_nowait()
                except queue.Empty:
                    return
                one(p)

        ths = [threading.Thread(target=worker, daemon=True)
               for _ in range(a.workers)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        grand_done += done[0]
    print("\n本次完成 %d / %d 页，失败 %d，用时 %.1f 分"
          % (grand_done, grand_todo, len(bad_all), (time.time() - t0) / 60))
    for k, e in bad_all:
        print("  失败：%s %s" % (k, e))
    return 1 if bad_all else 0


# ── boxes / figs：直接复用 zlx ───────────────────────────────────
def _each(a, fn) -> int:
    files = _match(list_files(), a.file)
    rc = 0
    for f in files:
        use(f)
        if not Z.SCAN.exists() or not list(Z.SCAN.glob("p*.txt")):
            continue
        print("\n══ %s" % f["label"])
        rc |= fn(a)
    return rc


def cmd_boxes(a) -> int:
    return _each(a, Z.cmd_boxes)


def cmd_figs(a) -> int:
    return _each(a, Z.cmd_figs)


# ── 小节名：从页顶的 `title=` 顺延 ────────────────────────────────
# `collect_questions` 只认 `@@SEC` 标记，而对这几份合集模型基本不给 ——
# 于是产物里**一个小节标题都没有**，可源材料明明是分节的
# （节与节之间题号还重新起编，正是"撞号"的来源）。
# 页顶的 `@@PAGE title=` 里其实写着节名。实测 2026概率：
#   p003「一、分布列和期望」 p041「六、公平与占优」 p044「七、几何分布」
#   p053「八、马尔科夫链」   p093「十七、约瑟夫问题」
#
# ⚠️ **只认「中文数字 + 、」开头的那种**，其余当页眉、不认。
# 实测教训：`五改Ⅱ` 的 p012 页顶写着「高中数学课程体系说明」——
# 那是**页眉**不是小节名；照单全收会把后面 296 页全标成那一节。
_SEC_NUM = re.compile(r"^[一二三四五六七八九十百千]+、")


def propagate_section(rows: list[dict], scans: dict) -> int:
    r"""把"当前小节"按**文档顺序**往下传。两个信号合成一条线：

    * 页顶的 `@@PAGE title=`（只认「中文数字 + 、」开头的那种，见上）
    * 页内模型给的 `@@SEC` 标记 —— **它也往后传**

    ⚠️ 第一版是错的：我让 `@@SEC` **只管自己那一道题**、不往后传，
    于是后面的题又掉回粗粒度的页小节，产物里小节**来回跳**：

        一、分布列和期望   ← 页小节（p003 的 title）
        二、错排问题      ← 某道题自己的 `@@SEC`
        一、分布列和期望   ← 又掉回来了（错）
        三、概率比大小
        一、分布列和期望   ← 又掉回来了（错）

    `@@SEC` 的语义本来就是"从这里开始换节"，它必须往后传。
    **凡"只在原地生效"的标记，都是这种 bug 的温床。**
    """
    cur, page_sec = "", {}
    for n in sorted(scans):
        t = (scans[n]["page"].get("title") or "").strip()
        if _SEC_NUM.match(t):
            cur = t
        # 页内最后一个 `@@SEC` 决定**页尾**属于哪一节（一页里可能换节）
        secs = [q.get("sec") for q in scans[n]["questions"]
                if q.get("sec") not in (None, "", "-")]
        if secs:
            cur = secs[-1]
        page_sec[n] = cur
    n = 0
    for r in rows:
        if r.get("sec") and r["sec"] not in ("-", ""):
            continue                      # 模型已经给了 `@@SEC`，以它为准
        t = page_sec.get(r["pdf_page"], "")
        if t:
            r["sec"] = t
            n += 1
    return n


# ── 跨页题：只在**两个信号一致**时才并 ──────────────────────────
#
# 这批和赵礼显那本不一样：**确实出现了跨页题**（实测 2026概率 p009→p010）。
# 两种情况都实测到了，而且**模型的两个字段各自都不可靠**：
#
#   p010  `n=1  continued=是`   ← **真是续页**（p009 第 7 题的 (1)(2)(3) 部分），
#                                 但续页上看不到印着的题号，模型从 1 重编，
#                                 于是和真正的第 1 题**撞 key**
#   p004  `n=2  continued=是`   ← **根本不是续页**，是一道全新的完整题
#                                 （甲、乙两名同学闯关），模型标错了
#
# 两类都错不起，但**代价不对称**：
#   · 错并 → 一道题被吞进另一道，**内容没了**，而且看不出来
#   · 不并 → 变成两段，**都在文件里**，肉眼可见、可事后修
# 按「宁缺勿错」只在**两个信号一致**时才并：`continued=是` **且**
# 上一题的题干**看起来没写完**（结尾是 `：`/`，`/`、`/`；` 这种，
# 而不是 `。`）。实测这条规则把 p010 并了、把 p004 放过了，两条都对。
#
# 存疑但不并的，记进 `meta.continued_suspect`，留个明账。
# 实测出来的两条信号（见 README「跨页题」一节）：
#   ① 模型把 `continued=是` 标在**跨页题的两半上**（p008 与 p009 的第 17 题都标了），
#      它表达的是"这道题跨页了"，不是"我是上一题的续页"；
#   ② 跨页断点**可能在词中间**（p010 末尾「…并结合非负」+ p011 开头「数的意义…」），
#      所以"上一题结尾没有句末标点"才是通用判据，只看 `：` 会漏。
_TERMINATOR = tuple("。．.！!？?")

# 本次 build 并了哪些续页（只用于打印，让人知道哪几道是拼起来的）
_MERGED_INFO: list[str] = []


def _unfinished(stem: str) -> bool:
    r"""题干看起来**没写完**：结尾不是句末标点。

    纯函数，单独拎出来是为了能被自检覆盖——这条判错一次，
    后果是**两道题被错误地并成一道**（内容没了且看不出来），
    而不并只是变成两段（都还在，肉眼可见）。
    """
    return not stem.rstrip().endswith(_TERMINATOR)


def key_of(r: dict) -> str:
    r"""转发到 `Z.key_of`（它按 `Z.BOOK` + `r["lect"]` + 题号拼）。

    不自己重写一份：key 的拼法是题库标识的一部分，复制一份就是两个真相。
    """
    return Z.key_of(r)


def merge_continued(rows: list[dict]) -> list[dict]:
    r"""按「`continued=是` 且上一题没写完」把续页并回上一题。"""
    out: list[dict] = []
    for r in rows:
        prev = out[-1] if out else None
        # 四个条件缺一不可：两道都标了 `continued=是`、**不在同一页**
        # （同一页里连着两道都标是 = 模型标错了，实测 p010 的 n=3 和 n=19
        #   都标是，但它们并不是同一题）、且上一题确实没写完。
        if (r.get("continued") and prev is not None
                and prev["lect"] == r["lect"]
                and prev.get("continued")
                and prev["pdf_page"] != r["pdf_page"]
                and _unfinished(prev["stem"])):
            prev["stem"] = (prev["stem"].rstrip() + "\n" + r["stem"].lstrip()).strip()
            if not prev["options"] and r["options"]:
                prev["options"] = r["options"]
            prev["fig_stem"] = list(prev.get("fig_stem") or []) + \
                list(r.get("fig_stem") or [])
            for k, v in (r.get("fig_opts") or {}).items():
                prev.setdefault("fig_opts", {}).setdefault(k, v)
            if r.get("fig_desc") and not prev.get("fig_desc"):
                prev["fig_desc"] = r["fig_desc"]
            prev["figure"] = prev.get("figure") or r.get("figure")
            prev["continued"] = True          # 跨三页的题要继续链下去
            prev.setdefault("merged_pages", []).append(r["pdf_page"])
            _MERGED_INFO.append("%s p%d 第%s题 ← 并进上一题（第%s题）"
                                % (r["lect"], r["pdf_page"], r["n"], prev["n"]))
            continue
        out.append(r)
    return out


def dedup_keys(rows: list[dict]) -> int:
    r"""**兜底**：并完之后还撞 key 的，把**小节**（没有就页码）挂进 key。

    撞 key 的原因不止续页：这批合集的题号**按小节重新起编**
    （实测 2026概率：p3–p40 排 1..N，p41 又从 1 开始），
    而模型的 `@@SEC` 常常只给 `-`。

    ⚠️ **优先挂小节、不是页码。** 第一版一律挂页码，于是 84 道里有
    20 道变成 `<slug>·p17#1` 这种 —— 唯一是唯一了，但看不出它属于哪一节。
    现在小节已经可靠（见 `propagate_section`），挂小节能让 key 自解释：
    `…·二、错排问题#1`。同节同号（一页里真有两道同号）再退回页码。
    """
    import collections as _c

    def sec_of(r: dict) -> str:
        sec = (r.get("sec") or "").strip()
        return sec if sec not in ("-", "") else ""

    n = 0
    for r in rows:
        if _c.Counter(key_of(x) for x in rows)[key_of(r)] > 1:
            r["lect"] = "%s·%s" % (r["lect"], sec_of(r) or ("p%d" % r["pdf_page"]))
            n += 1
    # 仍然撞（同一节里真的有两道同号）→ 再挂页码
    for r in rows:
        if _c.Counter(key_of(x) for x in rows)[key_of(r)] > 1:
            r["lect"] = "%s·p%d" % (r["lect"], r["pdf_page"])
    # ⚠️ **最后一道兜底：加序号，把唯一性钉死。**
    # 实测漏网形态：**同页、同小节、同题号**的两道题 —— 第一遍挂小节、
    # 第二遍挂页码，两个 key 变成**一模一样**（`·典型例题·p264#1`），
    # 唯一性根本没保证住（verify 报出 5 处，分布在 3 个文件里）。
    # 前两遍都是"按内容区分"，遇到内容真的相同就无解；序号是**按位置**区分，
    # 一定能分开。
    seen: dict[str, int] = {}
    for r in rows:
        k = key_of(r)
        if k in seen:
            seen[k] += 1
            r["lect"] = "%s·%d" % (r["lect"], seen[k])
        else:
            seen[k] = 0
    return n


# ── build：一个文件一个 .tex ─────────────────────────────────────
def cmd_build(a) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = _match(list_files(), a.file)
    fired: dict[str, int] = {}
    tot = nfile = 0
    for f in files:
        use(f)
        if not Z.SCAN.exists() or not list(Z.SCAN.glob("p*.txt")):
            continue
        scans = Z.load_scans()
        rows = merge_continued(Z.collect_questions(scans))
        nsec = propagate_section(rows, scans)
        ndup = dedup_keys(rows)
        if not rows:
            print("  – %s：没有题" % f["label"]); continue
        lines = [
            "%%%% %s" % f["label"],
            "%%%% 27年试卷/其他杂项 · 正文转录（**无答案**，待补）",
            "%%%% 源文件：%s" % f["src"].name,
            "%%%% 生成：脚本/其他杂项录题.py build",
            "",
        ]
        cur = None
        for r in sorted(rows, key=lambda x: (x["pdf_page"], x["n"])):
            if r["sec"] and r["sec"] not in ("-", cur):
                lines.append("%%%% ── %s ──" % r["sec"])
                cur = r["sec"]
            lines.extend(Z.block_of(r, LEC, f["label"], fired))
        (OUT / (f["slug"] + ".tex")).write_text("\n".join(lines) + "\n",
                                                encoding="utf-8")
        nfile += 1
        tot += len(rows)
        nfig = sum(1 for r in rows if r["fig_stem"] or r["fig_opts"])
        extra = ("  并了 %d 段续页" % sum(1 for r in rows if r.get("merged_pages"))) \
            if any(r.get("merged_pages") for r in rows) else ""
        extra += ("  补了 %d 道的小节名" % nsec) if nsec else ""
        extra += ("  ⚠ 题号撞号 %d 道已按小节/页码区分" % ndup) if ndup else ""
        print("  ✓ %-40s %3d 道（带图 %d）%s"
              % (f["label"][:38], len(rows), nfig, extra))
    print("\n写出 %d 个 .tex，共 %d 道题" % (nfile, tot))
    if fired:
        print("规范化生效（normalize ENTRY）：")
        for k, v in sorted(fired.items(), key=lambda x: -x[1]):
            print("  %-28s %d 道" % (k, v))
    return 0


# ── report ──────────────────────────────────────────────────────
def cmd_report(a) -> int:
    files = list_files()
    tot_p = tot_s = tot_q = tot_f = tot_c = 0
    print("  %-44s %5s %5s %5s %5s %5s" % ("文件", "页", "已录", "题", "带图", "跨页"))
    for f in files:
        use(f)
        npages = len(list(Z.PAGES.glob("p*.png"))) if Z.PAGES.exists() else 0
        nscan = len(list(Z.SCAN.glob("p*.txt"))) if Z.SCAN.exists() else 0
        rows = []
        if nscan:
            _sc = Z.load_scans()
            rows = merge_continued(Z.collect_questions(_sc))
            propagate_section(rows, _sc)
            dedup_keys(rows)
        nfig = sum(1 for r in rows if r["fig_stem"] or r["fig_opts"])
        ncont = sum(1 for r in rows if r["continued"])
        tot_p += npages; tot_s += nscan; tot_q += len(rows)
        tot_f += nfig; tot_c += ncont
        print("  %-44s %5d %5d %5d %5d %5d"
              % (f["label"][:42], npages, nscan, len(rows), nfig, ncont))
    print("  %-44s %5d %5d %5d %5d %5d"
          % ("合计", tot_p, tot_s, tot_q, tot_f, tot_c))
    if tot_p:
        print("  进度 %.1f%%" % (100.0 * tot_s / tot_p))
    return 0


# ── verify ──────────────────────────────────────────────────────
def cmd_verify(a) -> int:
    from amti import conform as CF
    problems: list[str] = []
    orphans: list[str] = []          # 多出 ENDQ 的孤儿块（良性，只报不拦）

    # ── 跨文件串页防线 ────────────────────────────────────────────
    # 2026-10-02 实测过一次**静默串页**：`amti/record.py` 的缩小图缓存
    # 写成 `parent.parent / "small"`，27 个源文件共用一个 `pages/small/`
    # 且只按 `pNNN` 命名 —— 第二份文件的 p001 直接复用了第一份的 p001，
    # 模型照着错的图转录，**产物格式完全正常**，只是内容属于另一个文件
    # （`2026概率大题合集` 的封面被答成「第01讲：数与式」）。
    # 根因已修并加了回归用例；这里再加一道**产物级**的独立防线：
    # 不同源文件的同名页，产物不该逐字相同；标题也不该写着别的文件的名字。
    sig_seen: dict[str, str] = {}
    labels = {f["slug"]: f["label"] for f in list_files()}
    for f in list_files():
        use(f)
        if not Z.SCAN.exists():
            continue
        for sp in sorted(Z.SCAN.glob("p*.txt")):
            t = sp.read_text(encoding="utf-8", errors="replace").strip()
            if len(t) < 100:
                continue
            # ⚠️ **只有含真题的页才算串页嫌疑。** 实测：`五改Ⅱ` 与 `四改Ⅰ`
            # 的 p003 逐字相同 —— 那是两本书**同一篇「前言」**，正当相同、
            # 无害。不加这条会把正常的前言/目录页全报成串页。
            if "@@Q" not in t:
                continue
            sig = "%s|%s" % (sp.stem, t[:500])
            if sig in sig_seen:
                problems.append(
                    "跨文件串页嫌疑：%s 与 %s 的 %s 产物逐字相同"
                    % (f["label"], sig_seen[sig], sp.stem))
            else:
                sig_seen[sig] = f["label"]
            # ── 截断检测 ──────────────────────────────────────────
            # 项目里记着「截断就是静默丢题」：一页输出撞到 `max_tokens`
            # 会**从中间断掉**，`finish_reason=length`，而产物看上去仍像
            # 正常标记文本。判据很直接：`@@Q` 与 `@@ENDQ` 必须一样多，
            # 最后一个块必须收尾。断了的页**必须重扫**，不能进 build。
            nq_open = len(re.findall(r"^@@Q\b", t, re.M))
            nq_done = len(re.findall(r"^@@ENDQ\b", t, re.M))
            # ⚠️ **两个方向要分开报**（实测两种都出现过）：
            #   `@@Q > @@ENDQ` → 末块没收尾，**可能真被截断**（要重扫）
            #   `@@Q < @@ENDQ` → 多出孤儿 `@@ENDQ`，通常是**讲解段没写
            #                   `@@Q` 头**（模型对纯讲解页就是这么干的）。
            #                   那段内容**已经被丢掉**，一般无需处理。
            # 第一版不分方向、一律说"像是被截断"，实测 3 条里 3 条都是
            # 孤儿块 —— **措辞不改会让人白找一通**。
            if nq_open > nq_done:
                problems.append(
                    "%s 的 %s 末块没收尾：@@Q %d 个、@@ENDQ %d 个 —— "
                    "**可能真被截断，值得重扫这一页**"
                    % (f["label"], sp.stem, nq_open, nq_done))
            elif nq_open < nq_done:
                orphans.append("%s 的 %s：@@Q %d 个、@@ENDQ %d 个"
                               % (f["label"], sp.stem, nq_open, nq_done))
            elif nq_open and not t.rstrip().endswith("@@ENDQ"):
                problems.append(
                    "%s 的 %s 末尾不是 @@ENDQ，可能被截断" % (f["label"], sp.stem))

            m = re.search(r"^@@PAGE.*?title=(.+)$", t, re.M)
            title = (m.group(1).strip() if m else "")
            if title and title not in ("-", "->"):
                for other_slug, other_label in labels.items():
                    if other_slug == f["slug"]:
                        continue
                    _t, _o = _norm_cmp(title), _norm_cmp(other_label)
                    if _t and _o and (_t in _o or _o in _t):
                        problems.append(
                            "%s 的 %s 标题写着别的文件：title=%r（像 %s）"
                            % (f["label"], sp.stem, title, other_label))

    # ── figs 映射 ↔ 正文引用 一致性 ────────────────────────────────
    # 两个方向都要查：登记了没引用（图在白占地方）、引用了没登记（漏了一步）。
    # 这条是 2026-10-02 实测出来的：我拿真页做合成测试时，`figs` 直接
    # 往**全库共用的 `图片/`** 里写了图，而那次没进正式的 figs 映射 ——
    # 于是 `图片/` 里留下两张 12 万字节的孤儿图，谁也不引用。
    # `图片/` 是全库共用的目录，**测试不要往那儿写**；这条检查是兜底。
    for f in _match(list_files(), a.file):
        use(f)
        tex = OUT / (f["slug"] + ".tex")
        if not tex.exists() or not Z.FIGS.exists():
            continue
        try:
            reg = set()
            for v in json.loads(Z.FIGS.read_text(encoding="utf-8")).values():
                reg |= set(v.get("stem") or [])
                reg |= set((v.get("opts") or {}).values())
        except Exception:                                   # noqa: BLE001
            continue
        used = set(re.findall(
            r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}",
            tex.read_text(encoding="utf-8")))
        for n in sorted(reg - used):
            problems.append("%s：%s 登记在 figs 里但正文没引用" % (f["label"], n))
        for n in sorted(used - reg):
            problems.append("%s：正文引用了 %s 但 figs 没登记" % (f["label"], n))
        for n in sorted(used):
            if not (FIGDIR / n).is_file():
                problems.append("%s：正文引用了 %s，但 图片/ 里没有这个文件"
                                % (f["label"], n))

    nq = 0
    # ⚠️ `orphans` 在**函数开头**就初始化了（收集循环在那里）。
    # 这里**不能**再初始化一次 —— 第一版在这里又写了一遍，正好在收集循环
    # **之后**、把刚收的东西全清空了，于是"孤儿块"一条都报不出来，
    # 而检测逻辑本身是对的（直接跑那段逻辑能报出 3 条）。
    for f in list_files():
        use(f)
        tex = OUT / (f["slug"] + ".tex")
        if not tex.exists():
            continue
        text = tex.read_text(encoding="utf-8")
        # ① 每个 `\begin{question}` 都要有 `\end{question}`
        b = text.count("\\begin{question}")
        e = text.count("\\end{question}")
        if b != e:
            problems.append("%s：question 环境不配对（%d 开 %d 闭）" % (f["label"], b, e))
        # ② 题号是否重复
        keys = re.findall(r'"key":\s*"([^"]+)"', text)
        dup = {k for k in keys if keys.count(k) > 1}
        if dup:
            problems.append("%s：题号重复 %d 个（例 %s）"
                            % (f["label"], len(dup), sorted(dup)[:3]))
        # ③ 空位/选项数与题型对得上
        for m in re.finditer(r'"key":\s*"([^"]+)"[^\n]*', text):
            nq += 1
        # ④ 走项目唯一的规范审查
        from amti.schema import Question as QQ, Option as OO
        qs = []
        for m in re.finditer(r"^%% @q (\{.*\})$", text, re.M):
            d = json.loads(m.group(1))
            qs.append(QQ(key=d["key"], type=d["type"], stem=d["stem"],
                         answer=d.get("answer", ""), solution=d.get("solution", ""),
                         options=[OO(label=o["label"], text=o["text"])
                                  for o in d.get("options") or []],
                         figures=d.get("figures") or [], meta=d.get("meta") or {}))
        for v in CF.run(qs):
            problems.append("%s：%s（%s/%s）"
                            % (f["label"], v["why"], v["check"], v["field"]))
    print("体检：%d 道题" % nq)
    if orphans:
        print("ℹ 多出 @@ENDQ 的孤儿块 %d 处（讲解段没写 @@Q 头，内容已被丢弃、"
              "一般无需处理）：" % len(orphans))
        for x in orphans[:10]:
            print("   · %s" % x)
    if problems:
        print("✗ %d 个问题：" % len(problems))
        for p in problems[:40]:
            print("   ·", p)
        return 1
    print("✓ 全部规范")
    return 0


# ── audit：要人工看哪些 ─────────────────────────────────────────
def cmd_audit(a) -> int:
    r"""出一份**给人看的明账**：机器转录必然有拿不准的地方，把它们列清楚。

    为什么值得单独出一份：`verify` 只报**硬错**（截断/串页/不合规范），
    而真正需要人眼的往往是**软缺口** —— 图没裁到、题号撞了、跨页并了。
    这些不影响"能不能编译"，但决定"能不能用"。项目一贯的做法是
    「留个明账」：宁可列一张清单让人来看，也不要一个看着正常、
    其实缺东西的产物。
    """
    import collections as _c
    lines = ["# 其他杂项 · 转录明账", ""]
    tot = _c.Counter()
    per_file: list[tuple] = []
    fig_todo: list[str] = []
    merged: list[str] = []
    deduped: list[str] = []
    suspect: list[str] = []
    for f in _match(list_files(), a.file):
        use(f)
        if not Z.SCAN.exists() or not list(Z.SCAN.glob("p*.txt")):
            continue
        scans = Z.load_scans()
        rows = merge_continued(Z.collect_questions(scans))
        nsec = propagate_section(rows, scans)
        ndup = dedup_keys(rows)
        npage = len(list(Z.PAGES.glob("p*.png"))) if Z.PAGES.exists() else 0
        nscan = len(list(Z.SCAN.glob("p*.txt")))
        nfig = sum(1 for r in rows if r["fig_stem"] or r["fig_opts"])
        nneed = sum(1 for r in rows if r["figure"])
        ncont = sum(1 for r in rows if r["continued"])
        if ndup:
            for r in rows:
                if "·p" in r["lect"]:
                    deduped.append("%s 第%s题（p%s）" % (f["label"], r["n"], r["pdf_page"]))
        # "存疑的跨页标记"：标了 `continued=是`，但**既没并进上一题、
        # 也没有下一题并进来**。可能是模型标错（实测 p010 的 n=3 就是），
        # 也可能续页缺了。这是真正需要人眼的一条。
        for i, r in enumerate(rows):
            if not r.get("continued") or r.get("merged_pages"):
                continue
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            merged_into_it = bool(nxt and nxt.get("merged_pages"))
            if not merged_into_it:
                suspect.append("%s p%s 第%s题：尾巴=%r"
                               % (f["label"], r["pdf_page"], r["n"],
                                  r["stem"].rstrip()[-22:]))
        per_file.append((f["label"], npage, nscan, len(rows), nfig, nneed, ncont, ndup))
        tot["page"] += npage; tot["scan"] += nscan; tot["q"] += len(rows)
        tot["fig"] += nfig; tot["needfig"] += nneed; tot["cont"] += ncont
        figs_done = Z.FIGS.exists()          # figs 跑过才谈得上"裁到没裁到"
        for r in rows:
            if figs_done and r["figure"] and not (r["fig_stem"] or r["fig_opts"]):
                fig_todo.append("%s p%s 第%s题：%s"
                                % (f["label"], r["pdf_page"], r["n"],
                                   (r.get("fig_desc") or "")[:60]))
            if r.get("merged_pages"):
                merged.append("%s 第%s题 ← 并了 p%s"
                              % (f["label"], r["n"], r["merged_pages"]))
    lines += ["## 总量", "",
              "| 项 | 数 |", "|---|---|",
              "| 已渲染页图 | %d |" % tot["page"],
              "| 已转录页 | %d |" % tot["scan"],
              "| 出题 | %d |" % tot["q"],
              "| 卷面标了「有图」的题 | %d |" % tot["needfig"],
              "| 已裁到图的题 | %d |" % tot["fig"],
              # 注意：这个数**包含已经并好的**（合并时会把 continued 保留下来，
              # 好让跨三页的题继续链）。真正要看的是下面「存疑的跨页标记」那节。
              "| 标了 continued 的题（含已并好的） | %d |" % tot["cont"], ""]
    lines += ["## 逐文件", "",
              "| 文件 | 页图 | 已录 | 题 | 有图 | 已裁图 | 跨页 | 撞号 |",
              "|---|---|---|---|---|---|---|---|"]
    for (lab, np_, ns, nq, nf, nn, nc, nd) in per_file:
        lines.append("| %s | %d | %d | %d | %d | %d | %d | %d |"
                     % (lab, np_, ns, nq, nn, nf, nc, nd))
    lines.append("")
    def sect(title: str, items: list[str], note: str) -> None:
        lines.extend(["## %s" % title, "", note, ""])
        if items:
            # ⚠️ 这里**必须** `extend`，不能写 `lines += [...]`：
            # 增量赋值会让 `lines` 变成 `sect` 的**局部变量**，
            # 于是上一行的 `lines.extend` 直接 `UnboundLocalError`。
            lines.extend(["- " + x for x in items[:200]])
            if len(items) > 200:
                lines.append("- …（还有 %d 条）" % (len(items) - 200))
        else:
            lines.append("（无）")
        lines.append("")
    sect("待裁的图（figure=有 但没裁到）", fig_todo,
         "**只有在 `figs` 跑过之后这一节才有意义**：`boxes`（第二遍找选项图）"
         "和 `figs` 会把大部分补上。跑完 `finish` 再看这一节，剩下的才是真缺口"
         "（`figbox` 越界或模型没给框 —— `figs` 会跳过、不猜像素）。"
         "这些题的图**需要人工裁**，或回原页确认那是不是真图。")
    sect("跨页合并", merged, "这些是**并起来**的续页（判据见 README）。")
    sect("存疑的跨页标记（标了 continued 但两头都没并）", suspect,
         "可能是模型标错（实测 p010 的 n=3 就是：它是一道新题却标了"
         "`continued=是`），也可能续页真的缺了。**值得逐条看原文**。")
    sect("撞号（已按页码区分）", deduped,
         "同一份材料里出现了重复题号（合集常按小节重新起编，"
         "而模型 `@@SEC` 常只给 `-`）。key 已保证唯一，但**卷面题号值得核一眼**。")
    # ── 疑似解析混入 ────────────────────────────────────────────────
    # 这几份是**「解析版」合集**：题目和解析在同一份 PDF 里，而模型
    # 会把解析段落也标成 `@@Q`（实测 2026概率 p19：题干写成
    # 「当 $X_4=1$ 时，$P(X_4=1)=\frac{2C_4^1}{A_4^4}=\frac{1}{3}$」）。
    # 实测比例不高（45 道里 1 道，2%），但**必须列出来** ——
    # 这些是"看着像题、其实是解答"的条目，混进题库就是脏数据。
    # 判据只看**题干开头**（看整段会大面积误报），宁可漏几条。
    # 这一节是**给人核对的清单**，所以宁可误报（多一行看一眼）也不要漏。
    # 实测那个真案例是「当 $X_4=1$ 时，$P(X_4=1)=…$」—— 光看"解/由题意"
    # 这类词是抓不到的，得把「当 … 时，」这种**算式型开场**也算进来。
    _SL = re.compile(
        r"^\s*(?:解[：:]|【解】|【解答】|【解析】|由题可知|由题意|由已知|"
        r"所以|故|因为|证明[：:]|答案[：:]|解析[：:]|则\s*\$|"
        r"当\s*\$[^$]{1,24}\$\s*时[，,]|（\d+）\s*(?:由|当|则|因为|所以))")
    sol_like: list[str] = []
    for f in _match(list_files(), a.file):
        tex = OUT / (f["slug"] + ".tex")
        if not tex.exists():
            continue
        for m in re.finditer(r"^%% @q (\{.*\})$", tex.read_text(encoding="utf-8"), re.M):
            try:
                d = json.loads(m.group(1))
            except Exception:                               # noqa: BLE001
                continue
            if _SL.match(d.get("stem") or ""):
                sol_like.append("%s 第%s题（p%s）：%s"
                                % (f["label"], d["meta"].get("source_no"),
                                   d["meta"].get("origin_pdf_page"),
                                   (d["stem"] or "")[:70].replace("\n", " / ")))
    sect("疑似解析混入（题干开头像解答）", sol_like,
         "这些是**「解析版」合集**里被模型当成题目的解答段落。判据只看题干"
         "开头，宁可漏几条；**逐条核对原文**，是解答的应当删掉。")

    # ── 疑似非题目：书的**前置说明/图例**被当成题 ────────────────────
    # 实测（五改Ⅱ p13）：书的开篇有一整页说明表 ——「对应难度：★、★★★…」
    # 「能力要求：」「对应课程学期：」「不同阶段特点：」「解决方案：」——
    # 模型把它整段标成了一个 `@@Q`，1410 字、没有任何空位、`type=填空`。
    # `_answer_slot` 还会替它补一个空位，于是**看着像一道填空题**。
    #
    # 判据只认这几个**说明表专有的字段名**：实测精确（命中 1 条，
    # 就是那页垃圾，零假阳性）。
    # ⚠️ 试过更"通用"的判据（"填空/选择但原始题干里没有空位"）——
    # **全是假阳性**：第1讲 19 道里 13 道命中，因为那本的作答位印成
    # `( )` 全角括号、模型照抄，`_answer_slot` 再补 `\paren[]`。
    # 判据越"通用"越容易误报，这一节是给人核对的，宁可窄。
    _FRONT = re.compile(r"对应难度|能力要求|对应课程学期|思维要求|不同阶段特点")
    # 第二种：小节名本身像**讲解**（`@@SEC 知识梳理`），模型会把紧跟着的
    # 讲解段落写成 `@@Q`。实测（五改Ⅱ p17）：「等差数列的基本概念与公式
    # (1) 等差数列的通项公式 如果等差数列…」—— 是课本正文，不是题。
    # 量过影响面：`@@SEC` 换得很勤（下一节紧跟 `6.1.1.1 …`、`中项的性质`），
    # 所以这条命中很少（当时全批就 1 道），不会把整本卷进来。
    _EXPO = re.compile(r"知识梳理|考点梳理|知识讲解|知识回顾|【知识|【考点")
    nonq: list[str] = []
    for f in _match(list_files(), a.file):
        use(f)
        if not Z.SCAN.exists() or not list(Z.SCAN.glob("p*.txt")):
            continue
        _sc = Z.load_scans()
        for r in merge_continued(Z.collect_questions(_sc)):
            raw = r["stem"] or ""
            why = ""
            if _FRONT.search(raw):
                why = "像书的前置说明"
            elif _EXPO.search(r.get("sec") or ""):
                why = "挂在「%s」小节下，像讲解" % (r.get("sec") or "")[:16]
            if why:
                nonq.append("%s p%s 第%s题（%d 字，%s）：%s"
                            % (f["label"], r["pdf_page"], r["n"], len(raw), why,
                               raw[:60].replace("\n", " / ")))
    sect("疑似非题目（前置说明 / 讲解段落被当成题）", nonq,
         "两种形态：**书的开篇说明页**（难度图例、能力要求、学期划分），"
         "和**挂在「知识梳理」这类讲解小节下的课本正文**。"
         "判据都取得很窄（说明表专有字段名、小节名本身像讲解）—— "
         "**逐条确认后删掉**。")

    # ── 疑似解答混入（**最重要的一条**）──────────────────────────────
    # 这几份「解析版」合集里题目和解答在同一份 PDF 里，模型会把**解答**
    # 也标成 `@@Q`。实测（2026概率，84 道）：**35 道（42%）** 的题干开头是
    # 算式或解答语（`$E(X)=4-[…`、`列式求解：`、`\begin{enumerate}\item 该厂商…`），
    # 最长的 2759 字 —— 那根本不是题干，是解析。
    #
    # ⚠️ 目标要的是「**没有答案的**」。这些混进来就是脏数据，
    # **必须逐条核掉**。
    #
    # 前一版判据只看题干**开头几个字**（`^解：`/`^由题可知`），
    # 实测只抓到 1/45 —— 因为解答往往**以数学式开头**。
    # 现在改成"解答语 + 超长"两个信号取或，宁可多报几条给人看。
    # 判据来自**实测的开头形态**（2026概率 的解答片段都长这样）：
    #   `\begin{enumerate} \item 依题意…`、`(2) 定义随机变量…`、
    #   `算得到 $E(X_i)=…$`、`值为 $0,2,3$…`、`列式求解：`、`$E(X)=4-[…`
    # 也就是"**解答式开场**"。前两版分别只看"解/由题可知"这类词、
    # 和"解答语 + 超长"，都漏掉一大批 —— 因为解答**常常直接以数学式
    # 或 `(2)` 开头**，开头那几个字里根本没有"解"。
    _SOL = re.compile(
        r"故选|综上|解得|故答案为|列式求解|见解析|【解析】|【答案】|"
        r"因此|解析[：:]|答案[：:]|依题意|算得|^\s*值为|布列见|"
        r"^\s*\\begin\{enumerate\}|"
        r"^\s*\(\s*\d+\s*\)|"
        r"^\s*\$[^$]{2,60}\$\s*=")
    sols: list[str] = []        # 含**解答语**：比较确定是解答
    longs: list[str] = []       # 只是**超长**：长真题也在这，得人看
    for f in _match(list_files(), a.file):
        use(f)
        tex = OUT / (f["slug"] + ".tex")
        if not tex.exists():
            continue
        for m in re.finditer(r"^%% @q (\{.*\})$", tex.read_text(encoding="utf-8"), re.M):
            try:
                d = json.loads(m.group(1))
            except Exception:                               # noqa: BLE001
                continue
            stem = d.get("stem") or ""
            item = "%s 第%s题（p%s）：%s" % (
                f["label"], d["meta"].get("source_no"),
                d["meta"].get("origin_pdf_page"), stem[:60].replace("\n", " / "))
            if _SOL.search(stem):
                sols.append(item)
            elif len(stem) > 600:
                # ⚠️ 超长**不等于**是解答：实测第2题（621 字）是真题、
                # 只是情景背景长；第9题（709 字）同样。所以单列一节给人看，
                # 别和"含解答语"混在一起 —— 混了就会把真题也当脏数据删掉。
                longs.append("%s…（%d 字）" % (item, len(stem)))
    sect("超长题干（不一定是解答，需人看）", longs,
         "**超长不是判定依据**：实测里有真题只是情景背景长（「甲、乙两名同学…」"
         "621 字、「在全球抗击新冠肺炎疫情…」709 字）。列出来只为让人过一眼。")
    sect("疑似解答混入（目标要的是「没有答案的」）", sols,
         "这些是**「解析版」合集里被模型当成题目的解答段落** —— "
         "题干以算式或解答语开头，最长的近三千字。"
         "**目标明确要无答案的产物，这些应当逐条核掉。**"
         "判据取「解答语 + 超长」的或，宁可多报几条给人看。")

    # ── 可疑碎片：小问被拆成独立的"题" ──────────────────────────────
    # 实测（五改Ⅱ p44）：同一道题的 ②③④ 小问各被标成一个 `@@Q`，
    # 每段只有 30–60 字（`② $a_1=1$，$a_2=2$，$a_{n+2}=4a_{n+1}-4a_n$；`）。
    # 它们**标了 `continued=是`，但在同一页** —— 而合并规则要求跨页
    # （那条护栏是为了避开 p010 那种"同页连着两个假续页"，实测必须留），
    # 所以同页碎片不并。
    # 结果不是数据丢失（碎片都在、顺序也对），但是**噪声**：
    # 一道题被拆成三道。列出来让人合并。
    frags: list[str] = []
    for f in _match(list_files(), a.file):
        use(f)
        tex = OUT / (f["slug"] + ".tex")
        if not tex.exists():
            continue
        for m in re.finditer(r"^%% @q (\{.*\})$", tex.read_text(encoding="utf-8"), re.M):
            try:
                d = json.loads(m.group(1))
            except Exception:                               # noqa: BLE001
                continue
            stem = (d.get("stem") or "").strip()
            # ⚠️ **只对解答题报短题干。** 选择题/填空题本来就短 ——
            # 内容在选项里或空位上（实测「式子 $(a-b)(a^2+b^2)$ 可恒等变形为
            # \paren[]」只有 35 字，却是**完整**的选择题）。不区分的话
            # 第一版 6 条里 4 条是假阳性。
            if len(stem) < 45 and d["type"] == "detailed_answer" \
                    and d["meta"].get("source_no"):
                frags.append("%s 第%s题（p%s，%d 字）：%s"
                             % (f["label"], d["meta"].get("source_no"),
                                d["meta"].get("origin_pdf_page"), len(stem),
                                stem.replace("\n", " / ")))
    sect("可疑碎片（小问被拆成独立的题）", frags,
         "同一道题的小问被拆成多个 `@@Q`（实测五改Ⅱ p44 的 ②③④）。"
         "它们标了 `continued=是` 但**在同一页**，而合并规则要求跨页"
         "（那条护栏是为了避开「同页连着两个假续页」，实测必须留）。"
         "**不是数据丢失**，是噪声 —— 逐条并回上一题即可。"
         "（判据只对**解答题**报短题干：选择题/填空题本来就短，"
         "内容在选项里或空位上。）")

    out = WORK / "明账.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("写出 %s（%d 个文件、%d 道题、%d 张待裁图）"
          % (out, len(per_file), tot["q"], len(fig_todo)))
    return 0


# ── finish：终点一条龙 ──────────────────────────────────────────
def cmd_finish(a) -> int:
    r"""扫描跑完之后的**一条龙**：boxes → figs → build → verify。

    为什么固化成一个命令：这一步的顺序**错了就白做**——
    `figs` 要读 `boxes` 的结果（没有框就一张图都裁不出来，而且日志只报
    "0 道带图题没裁到图"、看着像正常）；`build` 要读 `figs` 写下的映射
    （第一版漏了落盘那一步，`build` 于是把所有带图题都当成"还没裁"）。
    人手工敲三次很容易漏一次，固化下来就不会。

    `boxes` 需要本地模型服务在跑（它要问模型"图在哪"）；
    `figs`/`build`/`verify` 是纯本地、不需要服务。
    跑完会打印剩下两步（KaTeX 与出 PDF）的命令。
    """
    rc = 0
    for name, fn in (("boxes（找带图页的包围盒，需要模型服务）", cmd_boxes),
                     ("figs（裁图 → 图片/）", cmd_figs),
                     ("build（一个源文件一个 .tex）", cmd_build),
                     ("verify（体检：截断/串页/规范）", cmd_verify)):
        print("\n" + "═" * 64 + "\n══ %s" % name)
        rc |= fn(a)
    print("\n" + "═" * 64)
    print("收尾两步（不在这条链里，因为它们依赖别的东西）：")
    print("  node 脚本/赵礼显讲义KaTeX.mjs 数据/录题/其他杂项/out")
    print("  python3 脚本/赵礼显讲义出卷.py --work 数据/录题/其他杂项 --compile")
    print("  python3 脚本/其他杂项录题.py audit      # 出一份《要人工看哪些》的明账")
    return rc


# ── selftest ────────────────────────────────────────────────────
def cmd_selftest(a) -> int:
    r"""回归用例。**只测纯函数**——不碰模型、不碰服务、不写任何文件。

    盯的是**判错一次就会静默毁数据**的那几处：跨页合并的判据、
    撞号兜底、串页防线的归一化比较。四条跨页用例全部来自**实测**
    （第1讲 p008→p009、p010→p011 该并；p010 的 n=3、p012 的 n=20 不该并）。
    """
    fails = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    # ── `_unfinished`：题干看起来没写完 ──────────────────────────────
    check("结尾是「：」→ 没写完", _unfinished("(25-26 高一上·四川成都) 计算："))
    check("断在词中间 → 没写完", _unfinished("…这种方法常被用到代数式的变形中，并结合非负"))
    check("结尾是「。」→ 写完了", not _unfinished("求 $x$ 的值。"))
    check("结尾是「.」→ 写完了", not _unfinished("求 $\\sqrt{ab+bc+ac}$ 的值."))

    def row(pg, n, cont, stem, lect="L"):
        return {"pdf_page": pg, "n": n, "lect": lect, "stem": stem,
                "continued": cont, "options": [], "fig_stem": [], "fig_opts": {},
                "fig_desc": "", "figure": False, "sec": "-", "type": "解答",
                "source_in_stem": ""}

    # ── 跨页合并：**四条实测用例** ──────────────────────────────────
    # 实测 第1讲：p008 Q17「…计算：」+ p009 Q17 → 是一道题，该并
    a = [row(8, 17, True, "(25-26 高一上·四川成都) 计算："),
         row(9, 17, True, "(1) $\\sqrt{32}-2\\sqrt{12}$")]
    got = merge_continued(list(a))
    check("跨页续页并回上一题（p008+p009 第17题）",
          len(got) == 1 and "计算：" in got[0]["stem"] and "sqrt{32}" in got[0]["stem"],
          str(len(got)))
    check("并完保留 continued，好让跨三页的题继续链",
          bool(got) and got[0].get("continued") is True)
    check("并完记下合并页码", bool(got) and got[0].get("merged_pages") == [9])

    # 实测 p010 的 n=3 标了 continued=是，但上一题（p009 Q18）标的是"否"
    # → 它不是续页，是一道新题，**不能并**
    b = [row(9, 18, False, "$a+b+c=6$，求 $\\sqrt{ab+bc+ac}$ 的值."),
         row(10, 3, True, "已知 $a-b=\\sqrt{2}+1$")]
    check("上一题没标 continued → 不并（实测 p010 的 n=3）",
          len(merge_continued(list(b))) == 2)

    # 实测 p010 同一页里 n=3 和 n=19 **都**标了 continued=是
    # → 同页连着两个"是"是模型标错了，**不能并**
    c = [row(10, 3, True, "已知 $a-b=\\sqrt{2}+1$"),
         row(10, 19, True, "配方法是数学中重要的思想方法之一")]
    check("同一页连着两个 continued → 不并（实测 p010 的 n=3 与 n=19）",
          len(merge_continued(list(c))) == 2)

    # 实测 p011 Q1 是 p010 Q19 的续文（断在"非负"+"数的意义"词中间）
    # 而它**自己结尾是完整的「并说明理由.」** —— 判据看的是**上一题**写没写完
    d = [row(10, 19, True, "…并结合非负"),
         row(11, 1, True, "数的意义来解决一些问题. (1) …并说明理由.")]
    gd = merge_continued(list(d))
    check("断在词中间的续页也能并（p010+p011 第19题）",
          len(gd) == 1 and "数的意义" in gd[0]["stem"], str(len(gd)))

    # 上一题**写完了**（结尾「。」）→ 即使两个都标了"是"也不并
    e = [row(9, 5, True, "求 $x$ 的值。"), row(10, 6, True, "已知 $y=1$")]
    check("上一题已收尾（。）→ 不并", len(merge_continued(list(e))) == 2)

    # ── 撞号兜底 ────────────────────────────────────────────────────
    f = [row(3, 1, False, "甲"), row(10, 1, False, "乙"),
         row(11, 2, False, "丙")]
    n = dedup_keys(f)
    keys = [key_of(r) for r in f]
    # 注意：`dedup_keys` **每轮重新计数**，所以第一个改名之后第二个就不撞了，
    # 只改一个也够 —— 断言的是**唯一性**，不是改了几个。
    check("撞号被页码区分开（key 必须唯一）",
          n >= 1 and len(set(keys)) == 3, "%d %s" % (n, keys))
    check("没撞的那道 key 不动", "#2" in keys[2] and "·p" not in keys[2], str(keys))

    # ── 串页防线的归一化：第01讲 要能对上 第1讲 ──────────────────────
    check("前导零归一化（第01讲 ↔ 第1讲）",
          _norm_cmp("第01讲：数与式") in _norm_cmp("第1讲：数与式(教师版)"),
          "%r vs %r" % (_norm_cmp("第01讲：数与式"),
                        _norm_cmp("第1讲：数与式(教师版)")))
    check("正常标题不误报",
          _norm_cmp("高考数学统计概率解答题专项") not in
          _norm_cmp("第1讲：数与式(教师版)"))

    print("\n自检 %s（%d 项失败）" % ("通过" if fails == 0 else "**未通过**", fails))
    return 0 if fails == 0 else 1


# ── main ────────────────────────────────────────────────────────
def _main() -> int:
    ap = argparse.ArgumentParser(description="其他杂项 → 题库 LaTeX")
    ap.add_argument("cmd", choices=["convert", "list", "scan", "boxes", "figs",
                                    "build", "report", "verify", "selftest",
                                    "finish", "audit"])
    ap.add_argument("--file", default="", help="只处理文件名/短名里含这个字串的")
    ap.add_argument("--only", default="", help="页码区间，如 1-5")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    return {"convert": cmd_convert, "list": cmd_list, "scan": cmd_scan,
            "boxes": cmd_boxes, "figs": cmd_figs, "build": cmd_build,
            "report": cmd_report, "verify": cmd_verify,
            "selftest": cmd_selftest,
            "finish": cmd_finish, "audit": cmd_audit}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(_main())
