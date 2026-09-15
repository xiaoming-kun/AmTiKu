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

# 渲染单张图时的导言区。**故意装得宽**——这一步就是为了把"环境依赖"
# 一次性喂饱，之后卷子就不用管了。多装几个包只影响这一次渲染。
_PREAMBLE = r"""\documentclass[border=2pt]{standalone}
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
% 库里用到的自定义轴样式（原卷预导言区里的东西，见 amti/paper.py 的说明）
\pgfplotsset{
  exam statistical histogram/.style={
    ybar interval,
    bar width=1,
    axis lines=left,
    axis line style={-latex},
    tick align=outside,
    scaled y ticks=false,
    clip=false,
    tick label style={font=\normalsize},
    label style={font=\normalsize},
  },
}
\begin{document}
"""


def _key(tikz: str) -> str:
    return "tikz-" + hashlib.sha256(tikz.strip().encode("utf-8")).hexdigest()[:16]


def cached(tikz: str) -> Path | None:
    r"""这张图渲染过没有？渲染过就返回那个 PDF 的路径。"""
    if not (tikz or "").strip():
        return None
    p = IMG_DIR / (_key(tikz) + ".pdf")
    return p if p.is_file() else None


def render(tikz: str, *, force: bool = False, timeout: int = 120) -> tuple[Path | None, str]:
    r"""画一张图，存进 `图片/`。返回 (路径 或 None, 出错说明)。

    已经画过就直接返回（源码没变就不用重画）。
    """
    tikz = (tikz or "").strip()
    if not tikz:
        return None, "空的 TikZ"
    dst = IMG_DIR / (_key(tikz) + ".pdf")
    if dst.is_file() and not force:
        return dst, ""

    body = tikz
    # 有的片段是 `\begin{tikzpicture}`，有的是裸的 `\begin{axis}`。
    # `standalone` 只认一个 tikzpicture，裸 axis 得自己包一层。
    if "\\begin{tikzpicture}" not in body:
        body = "\\begin{tikzpicture}\n" + body + "\n\\end{tikzpicture}"

    work = Path(tempfile.mkdtemp(prefix="amti-tikz-"))
    try:
        (work / "f.tex").write_text(_PREAMBLE + body + "\n\\end{document}\n",
                                    encoding="utf-8")
        try:
            p = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "f.tex"],
                cwd=work, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, "渲染超时（%d 秒）" % timeout
        pdf = work / "f.pdf"
        if p.returncode != 0 or not pdf.is_file():
            log = (p.stdout or b"").decode("utf-8", "ignore")
            errs = [l for l in log.split("\n") if l.startswith("!")]
            return None, (errs[0][:180] if errs else log[-180:])
        IMG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, dst)
        return dst, ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


# 题干里嵌着的 tikzpicture 块。**非贪婪到配对的 `\end{tikzpicture}`**——
# tikzpicture 不嵌套，所以第一个 `\end` 就是它的结尾。
_TIKZ_BLOCK = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.S)


def to_image(stem: str, figures, *, width: str = "") -> tuple[str, int]:
    r"""把题干里的 TikZ 换成 `\includegraphics`。返回 (新题干, 换了几处)。

    **只有渲染好的才换**——没渲染过的原样留着走内联 TikZ，
    这样"没跑过 `render-tikz`"不会让卷子变空，只是回到老行为。
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
        p = cached(code)
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
    for q in qs:
        for f in (q.figures or []):
            if getattr(f, "kind", "") != "tikz" or not (f.tikz or "").strip():
                continue
            if cached(f.tikz) and not force:
                skipped += 1
                continue
            p, why = render(f.tikz, force=force)
            if p is None:
                fails.append({"key": q.key, "why": why})
                if verbose:
                    print("  ✗ %-44s %s" % (q.key[:44], why[:70]), flush=True)
            else:
                done += 1
    return {"rendered": done, "skipped": skipped, "fails": fails}


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
    print("tikzfig 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(0)
