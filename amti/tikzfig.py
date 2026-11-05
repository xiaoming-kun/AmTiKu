r"""AmTiKu · **把 TikZ 预渲染成矢量图，卷子里只放图**

## 为什么

卷子编译失败是"抽到才炸"的，而炸的原因几乎都是 **TikZ 依赖的渲染环境缺东西**：

    ! Package pgfkeys Error: I do not know the key
      '/tikz/exam statistical histogram'
    ! Package pgf Error: Unknown arrow tip kind 'Stealth'

题本身没问题，是"画它的环境"没配齐。而库里的 TikZ 是从各种真题源码里
抠出来的，各用各的宏包、各用各的自定义样式——**补不完**，补了这个还有那个。

## 怎么办

**把 TikZ 在录入时画一次，存成矢量 PDF；卷子里只 `\includegraphics` 它。**

- 图还是 LaTeX 画的，**长得一模一样**，还是矢量的（缩放到多大都不糊）
- 卷子的导言区不再需要 pgfplots／tikz 库／自定义样式，
  **编译从"可能炸"变成"只会因为图片文件丢了而炸"**——那是能一眼看出的错
- 顺带快很多：不用每出一份卷子就把几十个图重画一遍

同一张图还会**顺手转一份 PNG**（`图片/tikz-<hash>.png`）：试卷用 PDF，
讲解预览是 HTML，`<img>` 只认位图。没有 PNG 的图，预览里仍显示
「【图：请手绘】」占位——不会静默消失，也不会把 TikZ 源码摊出来。

## 数据不动

`figures[].tikz` 里的源码**原样保留**——它是这张图的唯一事实来源，
以后要改图就改它，改完重新渲染一次即可。
缓存按**源码内容的 sha256** 命名：源码变了自然就是新文件，
旧文件不会张冠李戴。
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .export import IMG_DIR

from amti.logutil import get_logger

log = get_logger(__name__)

# 渲染单张图时的导言区。**故意装得宽**——这一步就是为了把"环境依赖"
# 一次性喂饱，之后卷子就不用管了。多装几个包只影响这一次渲染。
#
# ⚠️ 自定义样式**必须复用 `amti/paper.py` 的那几份定义**，不能在这里另抄一份。
# 之前就是抄了一份且只抄了 `exam statistical histogram`，结果 paper 后来补上的
# `exam statistical bar` / `exam statistical line` / `\frequencyylabel` 这边全没有，
# `render-tikz` 至今渲染不出那 2 道——典型的"两处各写一遍必然分叉"。
_PREAMBLE_HEAD = r"""\documentclass[border=2pt]{standalone}
\usepackage{amsmath,amssymb}
\usepackage{siunitx}
\usepackage{xcolor}
\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usetikzlibrary{arrows.meta, calc, angles, quotes, positioning,
                shapes.geometric, patterns, decorations.pathreplacing,
                decorations.markings, intersections, through, fit,
                backgrounds, 3d}
"""


def _shared_styles() -> str:
    """`paper.py` 里那份自定义样式——预渲染与出卷**共用同一份**。"""
    from . import paper
    return "\n".join([
        "\\pgfplotsset{",
        *paper.PGFPLOTS_STYLES[1:-1],      # 掐掉 paper 那份自己的 { 和 }
        "}",
        *paper.TIKZ_STYLES,
        paper.freq_label_cmd(),
        "\\begin{document}",
    ]) + "\n"


def _preamble(cjk: bool = False) -> str:
    r"""拼导言区。`cjk=True` 才装 xeCJK（它跟 pgfplots 冲突，见 `_preamble_for`）。

    样式**第一次真要画图时才从 `paper.py` 取**：paper 那边是函数内才 import
    tikzfig 的，模块加载期反向 import 过去有环的风险。取一次就缓存住。
    """
    if cjk not in _CACHE:
        head = _PREAMBLE_HEAD
        if cjk:
            head = head.replace("\\usepackage{tikz}",
                                _CJK_PREAMBLE + "\\usepackage{tikz}", 1)
        _CACHE[cjk] = head + _shared_styles()
    return _CACHE[cjk]


_CACHE: dict[bool, str] = {}


# 中文字体单独抽出来，**按图决定装不装**（见 `_preamble_for`）。
_CJK_PREAMBLE = r"""\IfFileExists{xeCJK.sty}{%
  \usepackage{xeCJK}%
  \setCJKmainfont{Songti SC}%
}{}
"""

# 汉字：中日韩统一表意文字（含扩展 A 与兼容区）+ 假名
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _preamble_for(body: str) -> tuple[str, str]:
    r"""挑导言区，并返回一句警告（没问题就是空串）。

    **历史包袱（已订正）**：这里原来写着「xeCJK 与 pgfplots 的
    `\node at (axis cs:…)` 冲突，会撞 `! Missing \endcsname inserted.`，
    所以带 axis 的图**不装** xeCJK」，实测依据是 2020 天津卷#4 那张直方图。
    2026-10-31 逐张复跑全库 62 张含汉字的图，结论是**这个前提是错的**：
    31 张带 axis 的图里 30 张装了 xeCJK 照样正常编译，唯一真炸的天津卷#4
    不是因为字体——它的 TikZ 源码本身被 OCR 带坏了（`\node[...] at (axis cs:…)`
    的命令头被吃掉，留下 `[line width=0.75pt]{0.64}{0};` 这种无主片段）。
    不装 xeCJK 的代价是 xelatex **把汉字静默丢掉还照样产出"成功"的 PDF**，
    于是全库直方图的纵轴标题「频率/组距」在卷面上凭空消失，
    而 `accept` 层③ 只看图片引用、看不见字形丢失——正是本项目反复踩的
    「构建成功 ≠ 渲染正确」。

    现在的口径：**有汉字就装 xeCJK**（不分有没有 axis）；真装了会炸的图
    由 `render()` 退回不装的那份导言区重画，并在返回的说明里写清楚丢了字。
    """
    has_cjk = bool(_CJK_RE.search(body))
    if has_cjk:
        return _preamble(cjk=True), ""
    return _preamble(), ""


def dropped_cjk(out: str) -> str:
    r"""从 xelatex 的输出里抓「被丢掉的汉字」。

    xelatex 对字体里没有的字形会逐字打
    `Missing character: There is no 频 (U+9891) in font [lmroman10-regular]`，
    **不报错、退出码照样是 0**——所以「编译成功」根本不能证明字画出来了，
    必须回过来查这一行。非汉字的 `Missing character`（pgfplots 测量通路里的
    拉丁字符）不算，那是噪声。
    """
    gone = sorted(set(re.findall(
        r"Missing character: There is no (\S) \(", out or "")))
    return "".join(c for c in gone if _CJK_RE.match(c))


def _key(tikz: str) -> str:
    return "tikz-" + hashlib.sha256(tikz.strip().encode("utf-8")).hexdigest()[:16]


def cached(tikz: str) -> Path | None:
    r"""这张图渲染过没有？渲染过就返回那个 PDF 的路径。"""
    if not (tikz or "").strip():
        return None
    p = IMG_DIR / (_key(tikz) + ".pdf")
    return p if p.is_file() else None


#: PNG 的分辨率。讲解预览是 HTML，`<img>` 只认位图，不认 PDF；220 足够 2 倍屏。
PNG_DPI = 220


def png_path(tikz: str) -> Path:
    return IMG_DIR / (_key(tikz) + ".png")


def png_cached(tikz: str) -> Path | None:
    r"""讲义能用的 PNG 有没有？有就返回路径。

    题目 TikZ 的预渲染产物一直是 PDF（只服务试卷的 LaTeX 导出）。
    讲义走 HTML，需要同一张图的 PNG——内容寻址规则相同，只是扩展名不同。
    """
    if not (tikz or "").strip():
        return None
    p = png_path(tikz)
    return p if p.is_file() else None


def content_box(page):
    r"""PDF 页上**实际画了东西**的包围盒（矢量 ∪ 文字）。

    不能信 `standalone` 的 tightpage 裁切：它给的裁切窗口会偏。
    这里按内容盒自己裁，再留 1pt 边。裁偏了肉眼看不出，只会觉得"图小了"。
    """
    import fitz
    r = None
    for d in page.get_drawings():
        r = d["rect"] if r is None else r | d["rect"]
    for b in page.get_text("blocks"):
        r = fitz.Rect(b[:4]) if r is None else r | fitz.Rect(b[:4])
    if r is None or r.is_empty:
        return page.rect
    return r + (-1, -1, 1, 1)


def pdf_to_png(pdf: Path, *, force: bool = False) -> tuple[Path | None, str]:
    r"""把预渲染的 PDF 转成同名的 PNG（讲义用）。已存在且不比 PDF 旧就跳过。"""
    dst = pdf.with_suffix(".png")
    try:
        if dst.is_file() and not force and dst.stat().st_mtime >= pdf.stat().st_mtime:
            return dst, ""
    except OSError:
        pass
    try:
        import fitz
    except ImportError:
        return None, "缺 PyMuPDF（pip install pymupdf）：PDF 转不了 PNG"
    try:
        doc = fitz.open(pdf)
        try:
            page = doc[0]
            pix = page.get_pixmap(dpi=PNG_DPI, clip=content_box(page))
            dst.parent.mkdir(parents=True, exist_ok=True)
            pix.save(dst)
        finally:
            doc.close()
        return dst, ""
    except Exception as e:                       # noqa: BLE001
        return None, "PDF 转 PNG 失败：%s" % e


def _ensure_png(pdf: Path, *, force: bool = False) -> Path | None:
    r"""渲染/取缓存时顺手把 PNG 备好；失败只记日志，不影响 PDF 与试卷。"""
    p, why = pdf_to_png(pdf, force=force)
    if p is None:
        log.warning("TikZ 图转 PNG 失败（讲义里会显示占位）：%s（%s）", pdf.name, why)
    return p



def render(tikz: str, *, force: bool = False, timeout: int = 120) -> tuple[Path | None, str]:
    r"""画一张图，存进 `图片/`。返回 (路径 或 None, 出错说明)。

    已经画过就直接返回（源码没变就不用重画）。
    """
    tikz = (tikz or "").strip()
    if not tikz:
        return None, "空的 TikZ"
    dst = IMG_DIR / (_key(tikz) + ".pdf")
    if dst.is_file() and not force:
        # 老缓存只有 PDF（历史产物）；顺手补一张 PNG，讲义才画得出来。
        _ensure_png(dst)
        return dst, ""

    body = tikz
    # 有的片段是 `\begin{tikzpicture}`，有的是裸的 `\begin{axis}`。
    # `standalone` 只认一个 tikzpicture，裸 axis 得自己包一层。
    if "\\begin{tikzpicture}" not in body:
        body = "\\begin{tikzpicture}\n" + body + "\n\\end{tikzpicture}"

    work = Path(tempfile.mkdtemp(prefix="amti-tikz-"))
    preamble, warn = _preamble_for(body)
    cjk = "\\usepackage{xeCJK}" in preamble
    try:
        def once(pre: str) -> tuple[bool, str, Path | None]:
            (work / "f.tex").write_text(pre + body + "\n\\end{document}\n",
                                        encoding="utf-8")
            try:
                p = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "f.tex"],
                    cwd=work, capture_output=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                return False, "渲染超时（%d 秒）" % timeout, None
            out = ((p.stdout or b"") + (p.stderr or b"")).decode("utf-8", "ignore")
            pdf = work / "f.pdf"
            if p.returncode != 0 or not pdf.is_file():
                errs = [l for l in out.split("\n") if l.startswith("!")]
                return False, (errs[0][:180] if errs else out[-180:]), None
            return True, out, pdf

        # 成功时 ok=True、out 是整份编译日志；失败时 out 是一句错误摘要
        ok, out, pdf = once(preamble)
        if not ok and cjk:
            # 装了 xeCJK 反而炸的图（源码本身有毛病的才会）退回不装的那份，
            # 保证「改字体策略」不会把原来能出图的图变成出不了图。
            err1 = out
            ok2, out2, pdf2 = once(_preamble())
            if not ok2:
                return None, err1
            log.warning("TikZ 装 xeCJK 编译失败，退回不装重画：%s（%s）",
                        err1[:80], body[:40].replace("\n", " "))
            warn = ("装了 xeCJK 编译不过（%s），已退回不装；"
                    "图里的汉字会被静默丢掉" % err1[:80])
            ok, out, pdf = True, out2, pdf2
        if not ok:
            return None, out
        gone = dropped_cjk(out)
        if gone:
            # 退出码 0、PDF 也生成了，但字没画出来——必须说出来
            warn = (warn + "；" if warn else "") + ("这些汉字没画出来：%s" % gone)
            log.warning("TikZ 丢字（%s…）：%s", body[:36].replace("\n", " "), gone)
        IMG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, dst)
        _ensure_png(dst, force=force)
        return dst, warn
    finally:
        shutil.rmtree(work, ignore_errors=True)


# 题干里嵌着的 tikzpicture 块。**非贪婪到配对的 `\end{tikzpicture}`**——
# tikzpicture 不嵌套，所以第一个 `\end` 就是它的结尾。
_TIKZ_BLOCK = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.S)


def to_image(stem: str, figures, *, width: str = "",
             ext: str = "pdf") -> tuple[str, int]:
    r"""把题干里的 TikZ 换成 `\includegraphics`。返回 (新题干, 换了几处)。

    **只有渲染好的才换**——没渲染过的原样留着走内联 TikZ，
    这样"没跑过 `render-tikz`"不会让卷子变空，只是回到老行为。

    `ext="pdf"`：试卷（LaTeX，矢量）。
    `ext="png"`：讲解预览（HTML，`<img>` 只认位图）。
    """
    done = {f.tikz.strip(): f for f in (figures or [])
            if getattr(f, "kind", "") == "tikz" and (f.tikz or "").strip()}
    if not done:
        return stem, 0

    n = 0

    def sub(m: re.Match) -> str:
        nonlocal n
        code = m.group(0)
        f = done.get(code.strip())
        if f is None:
            return code
        p = png_cached(code) if ext == "png" else cached(code)
        if p is None:
            return code
        n += 1
        # 宽度优先用 figure 上记的（如 `0.4\linewidth`），没记就用 0.9 倍行宽
        w = (getattr(f, "width", "") or width or "").strip()
        # 存的是 `\linewidth` 这种 LaTeX 长度，原样透传
        opt = "[width=%s]" % w if w else ""
        return "\\includegraphics%s{%s}" % (opt, p.name)

    return _TIKZ_BLOCK.sub(sub, stem), n


def render_all(questions=None, *, force: bool = False, verbose: bool = True) -> dict:
    r"""把全库的 TikZ 都渲染一遍。已经渲染过的跳过。"""
    from . import store
    qs = questions if questions is not None else [q for _f, q in store.iter_questions()]
    done = skipped = 0
    fails: list[dict] = []
    warns: list[dict] = []
    for q in qs:
        for f in (q.figures or []):
            if getattr(f, "kind", "") != "tikz" or not (f.tikz or "").strip():
                continue
            if cached(f.tikz) and png_cached(f.tikz) and not force:
                skipped += 1
                continue
            p, why = render(f.tikz, force=force)
            if p is None:
                fails.append({"key": q.key, "why": why})
                if verbose:
                    print("  ✗ %-44s %s" % (q.key[:44], why[:70]), flush=True)
            else:
                done += 1
                # 出图成功但字被吞了——这正是要显出来的那类静默失败
                if why:
                    warns.append({"key": q.key, "warn": why})
                    if verbose:
                        print("  ! %-44s %s" % (q.key[:44], why[:70]), flush=True)
    return {"rendered": done, "skipped": skipped, "fails": fails, "warns": warns}


def _selftest() -> int:
    print("tikzfig 自检")
    fails = 0

    def check(name, ok, extra=""):
        nonlocal fails
        print("  %s %s%s" % ("✓" if ok else "✗", name, ("  " + extra) if extra else ""))
        if not ok:
            fails += 1

    simple = r"\begin{tikzpicture}\draw (0,0) circle (1);\end{tikzpicture}"
    p, why = render(simple)
    check("能渲染最简单的图", p is not None, why)
    check("渲染结果是个 PDF", p is not None and p.suffix == ".pdf")
    check("缓存命中", cached(simple) == p)
    check("源码变了就是另一个文件",
          cached(simple.replace("circle (1)", "circle (2)")) is None)

    # 换个源码 → 换个文件名（不会张冠李戴）
    p2, _ = render(simple.replace("circle (1)", "circle (1.5)"))
    check("不同源码不同文件", p2 is not None and p2 != p)

    stem = "如图，" + simple + " 则……"
    class F:
        kind = "tikz"; tikz = simple; width = "0.5\\linewidth"
    out, n = to_image(stem, [F()])
    check("题干里的 TikZ 被换成图片", n == 1 and "\\includegraphics" in out, out[:60])
    check("没渲染过的保持原样", to_image("如图 " + simple, [])[1] == 0)

    # 中文导言区：**有汉字就装 xeCJK**，带 axis 的也装（旧口径把 axis 图
    # 全排除在外，结果是直方图的「频率/组距」被静默丢掉——见 `_preamble_for`）
    plain = r"\begin{tikzpicture}\node at (0,0) {正视图};\end{tikzpicture}"
    pr, wn = _preamble_for(plain)
    check("纯 tikzpicture 带汉字 → 装 xeCJK", "xeCJK" in pr and wn == "")
    p3, why3 = render(plain, force=True)
    check("汉字节点真能渲染出来（返回的警告里没有丢字）", p3 is not None and why3 == "", why3)
    inaxis = (r"\begin{tikzpicture}\begin{axis}[width=5cm]"
              r"\node at (axis cs:0,1) {直径/mm};"
              r"\addplot coordinates {(0,0) (1,1)};\end{axis}\end{tikzpicture}")
    pr2, wn2 = _preamble_for(inaxis)
    check("axis + 汉字 → 一样装 xeCJK", "xeCJK" in pr2 and wn2 == "")
    p4, why4 = render(inaxis, force=True)
    check("axis + 汉字仍能出图", p4 is not None, why4)
    # force：不重来一遍的话命中的是改动前那份缓存 PDF，等于没测
    check("axis 里的汉字真画出来了（没被静默丢掉）", p4 is not None and why4 == "", why4)
    check("没汉字的图不受影响", "xeCJK" not in _preamble_for(simple)[0])
    # 丢字检测：非汉字的 Missing character（pgfplots 测量通路）不算丢字
    check("拉丁字符的 Missing character 不误报",
          dropped_cjk("Missing character: There is no x (U+78) in font [lmr];") == "")
    check("汉字的 Missing character 抓得到",
          dropped_cjk("Missing character: There is no 频 (U+9891) in font [lmr];") == "频")

    print("tikzfig 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0
