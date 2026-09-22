"""AmTiKu · 组卷导出

把选中的题目渲染成一份 exam-zh 试卷并编译成 PDF。

**旧项目在这里踩过的坑，逐条避掉**：

  1. `question/bottom-sep` 与 `problem/bottom-sep` **是两个键**。
     只写前者 → 解答题的间距永远改不动。
  2. 解答题留白用 `\\vspace*`（带星号），不是 `bottom-sep`。
     `\\vspace` 在分页处会被 LaTeX 丢弃 → 题目落在页底时留白凭空消失。
  3. 大题标题**左对齐**（`\\noindent`），不套 `\\begin{center}`。
  4. 图片路径走 `\\graphicspath`，正文里只写内容寻址的文件名。
  5. 默认文件名 = `类型_时间戳`，避免同名静默覆盖。
  6. 答案显示走 `solution/show-solution`；隐藏时整块不排。
"""
from __future__ import annotations

from .paths import ROOT
import datetime as _dt
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .schema import QTYPE_LABEL, Question
from .render_tex import question_to_tex
from . import paper as _paper
from . import store

PKG = ROOT
IMG_DIR = PKG / "图片"
OUT_DIR = PKG / "试卷"

# 分节顺序（组卷时按这个排）
SECTION_ORDER = ("single_choice", "multi_choice", "fill_in_blank", "detailed_answer")
SECTION_NAME = {
    "single_choice": "一、选择题",
    "multi_choice": "二、多选题",
    "fill_in_blank": "三、填空题",
    "detailed_answer": "四、解答题",
}


# ── 卷面渲染 ──────────────────────────────────────────────────────────

def render_paper(questions: list[Question], *, title: str = "", show_answers: bool = False,
                 answers_at_end: bool = False, show_source: bool = False,
                 bottom_sep: str = "0.6em", problem_blank_cm: float = 0.0,
                 columns: int = 4, mode: str = "gaokao",
                 handout_font: str = _paper.HANDOUT_FONT_DEFAULT) -> str:
    """渲染成完整的 exam-zh 文档。**委托给 `paper.py`。**

    这里早先自己实现过一份，结果 `paper.py` 的两种卷型和「按位置定难度」
    成了**死代码**——界面上导出的卷子永远没有难度标注，也没有考点小字。
    现在只留一份实现，`mode` 取 `gaokao`（高考卷）/ `test`（纯测试题）/
    `handout`（讲义：一题一页 · A4 横版 · 无答案，给 iPad 讲课用）。
    """
    return _paper.render_paper(
        questions, mode=mode, title=title, show_answers=show_answers,
        answers_at_end=answers_at_end, show_source=show_source,
        bottom_sep=bottom_sep, problem_blank_cm=problem_blank_cm,
        columns=columns, graphicspath=str(IMG_DIR),
        handout_font=handout_font)


# ── 编译 ──────────────────────────────────────────────────────────────

# `paper.py` 出的这两行：`\graphicspath{{<图目录>/}}` 与题干里的
# `\includegraphics[width=...]{<图名>}`。编译前要把图目录改写到 ASCII 临时目录。
_GPATH_RE = re.compile(r"\\graphicspath\{\{([^}]*)\}\}")
_IMGRE_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")


def _prepare_ascii_build(tex_path: Path) -> Path:
    r"""把 .tex 和它**引用到的**图片拷进一个纯 ASCII 路径的临时目录，返回临时 .tex。

    为什么非要在 ASCII 路径下编译：
    Windows 上 kpathsea 遇到非 ASCII 的目录会直接 fatal —— 实测报的就是

        (null): fatal: Can't get long name for D:\?? ??\AmTiKu.

    （英文区域设置的 Windows，ANSI 代码页表示不了中文，`GetLongPathName` 拿回来是
    `??`；中文 Windows 上恰好能过，所以这个问题只在部分机器上露头）。用户把程序
    解压到「桌面\高中数学题库」是常态，所以不能要求安装路径必须是英文——
    编译搬到 %TEMP% 下做，编完再把 PDF 搬回原目录。

    同一趟还顺手解决了"中文文件名喂给 xelatex"的问题（见下面的注释）。
    只拷**题里真的引用的**图：整个图片库有三千多张、190 MB，全拷一遍不现实。
    """
    text = tex_path.read_text(encoding="utf-8")
    build = Path(tempfile.mkdtemp(prefix="amti_build_"))   # mkdtemp 在 %TEMP%，纯 ASCII
    m = _GPATH_RE.search(text)
    if m:
        src_img = Path(m.group(1).rstrip("/\\"))
        names = {n.strip() for n in _IMGRE_RE.findall(text) if n.strip()}
        if names:
            (build / "images").mkdir(exist_ok=True)
            for n in names:
                s = src_img / n
                if s.is_file():
                    shutil.copy2(s, build / "images" / Path(n).name)
        # 用 paper._texpath 转正斜杠：Windows 上反斜杠在 TeX 里是命令前缀
        text = text.replace(m.group(0),
                            r"\graphicspath{{" + _paper._texpath(str(build / "images")) + "/}}")
    build_tex = build / "main.tex"
    build_tex.write_text(text, encoding="utf-8")
    return build_tex


def compile_tex(tex_path: Path, *, passes: int = 2, timeout: int = 240) -> tuple[bool, str]:
    r"""xelatex 编译。跑两遍（第二遍才能定页码/交叉引用）。

    **编译在 ASCII 临时目录里做**（见 `_prepare_ascii_build`），原因有两个，
    都是只在 Windows 上才露头的坑：

    1. 安装路径里有中文 → kpathsea fatal（`Can't get long name for ...`）；
    2. 文件名是中文（卷子标题就是文件名）→ xelatex.exe 的 `main()` 拿到的是
       **ANSI 代码页**的 argv，中文名变乱码，立刻"找不到文件"。

    编完把 `main.pdf` 搬回 `tex_path` 同名的 .pdf，用户看不出区别；
    留给用户的 .tex 仍是中文名、仍指向原来的图片目录。
    """
    if not shutil.which("xelatex"):
        return False, ("找不到 xelatex —— 导出 PDF 需要 LaTeX 引擎。\n"
                      "安装方法见项目根目录的《TeXLive安装.md》（含国内镜像与常见报错处理）。\n"
                      "不装不影响浏览、编辑、组卷与预览。")
    try:
        build_tex = _prepare_ascii_build(tex_path)
    except OSError as e:
        return False, f"准备编译目录失败：{e}"

    build_dir = build_tex.parent
    log = ""
    try:
        for _ in range(passes):
            r = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
                 build_tex.name],
                cwd=build_dir, capture_output=True, text=True,
                # 显式指定 UTF-8：默认按系统 locale 解码（英文 Windows 是 cp1252），
                # 而 xelatex 的输出里有中文（标题、路径、题目），strict 解码直接抛
                # UnicodeDecodeError，把"导出失败"变成一段看不懂的异常。
                encoding="utf-8", errors="replace", timeout=timeout)
            log = r.stdout + r.stderr
            if r.returncode != 0:
                # **失败时把完整日志留一份**到用户的 试卷/ 目录：界面上只显示前几条错，
                # 临时目录又要删掉，不留原文的话远端排查只能靠猜（今天卡了好几轮就是
                # 因为日志被自己过滤没了）。
                try:
                    src_log = build_dir / "main.log"
                    if src_log.exists():
                        shutil.copy2(src_log, tex_path.with_suffix(".log"))
                except OSError:
                    pass
                return False, log
        produced = build_dir / "main.pdf"
        if not produced.exists():
            return False, log
        shutil.move(str(produced), str(tex_path.with_suffix(".pdf")))
        return True, log
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)   # 临时目录整个删掉


def first_errors(log: str, n: int = 5) -> list[str]:
    out, seen = [], set()
    for m in re.finditer(r"^(?:!|.*:\d+:)\s*(.+)$", log, re.M):
        line = m.group(0).strip()
        if line not in seen:
            seen.add(line)
            out.append(line)
        if len(out) >= n:
            break
    return out


# ── 导出 ──────────────────────────────────────────────────────────────

def export(keys: list[str], *, title: str = "", out: str = "",
           show_answers: bool = False, answers_at_end: bool = False,
           show_source: bool = False,
           bottom_sep: str = "0.6em",
           problem_blank_cm: float = 0.0, do_compile: bool = True,
           mode: str = "gaokao", handout_font: str = _paper.HANDOUT_FONT_DEFAULT) -> dict:
    r"""按 key 列表导出。返回落盘位置（**必须回传，UI 要显示"存到哪了"**）。

    `mode` 取 `gaokao`（高考卷）/ `test`（纯测试题，带考点小字与每题难度）/
    `handout`（讲义，见 `paper._render_handout`）。
    """
    if mode not in ("gaokao", "test", "handout"):
        return {"ok": False, "error": f"未知卷型 {mode!r}", "missing": []}

    qs: list[Question] = []
    missing: list[str] = []
    for k in keys:
        q = store.find(k)
        if q:
            qs.append(q)
        else:
            missing.append(k)
    if not qs:
        return {"ok": False, "error": "没有有效的题目", "missing": missing}

    # 文件名：留空用「类型_时间戳」，避免同名静默覆盖
    if not out.strip():
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
        out = f"{title.strip() or '试卷'}_{stamp}"
    name = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", out).strip("_") or "试卷"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tex_path = OUT_DIR / f"{name}.tex"
    tex_path.write_text(render_paper(qs, title=title, show_answers=show_answers,
                                     answers_at_end=answers_at_end,
                                     show_source=show_source,
                                     bottom_sep=bottom_sep, mode=mode,
                                     problem_blank_cm=problem_blank_cm,
                                     handout_font=handout_font),
                        encoding="utf-8")

    res = {"ok": True, "name": name, "questions": len(qs), "missing": missing,
           "tex_abs": str(tex_path), "pdf_abs": None, "dir_abs": str(OUT_DIR),
           "saved_hint": f"{name} 已保存到 试卷/", "log": ""}
    if do_compile:
        ok, log = compile_tex(tex_path)
        res["ok"] = ok
        if ok:
            res["pdf_abs"] = str(tex_path.with_suffix(".pdf"))
        else:
            # 挑出日志里的报错行；**一行都没挑到就把原文尾巴带上**——
            # 否则界面上只显示"导出失败："后面空着，连"找不到 xelatex"这种
            # 一眼能看懂的提示都被过滤掉了（CI 上就吃过这个闷亏）。
            res["log"] = ("\n".join(first_errors(log, 6))
                          or (log[-800:].strip()
                              or "编译失败，但 LaTeX 没有任何输出（引擎可能没跑起来）"))
            full_log = tex_path.with_suffix(".log")
            if full_log.exists():          # 完整日志（含被过滤掉的那些行）
                res["log"] += f"\n\n完整日志：{full_log}"

    # **存档**：出了什么卷、用了哪些题、什么参数。
    # 不记的话「上次那套卷呢」只能去 试卷/ 翻文件名。
    # 编译失败也存——题目选好了就是成果，编译是另一回事。
    try:
        from . import papers as _papers
        _papers.add(name, [q.key for q in qs], title=title or name, mode=mode,
                    params={"show_answers": show_answers, "bottom_sep": bottom_sep,
                            "problem_blank_cm": problem_blank_cm, "mode": mode},
                    kind="试卷")
        res["archived"] = True
    except Exception as e:
        res["archived"] = False
        res["archive_error"] = str(e)
    return res


if __name__ == "__main__":
    # 自检：拿头 4 道题导一份，验证渲染与编译
    qs = [q for _f, q in store.iter_questions()][:4]
    keys = [q.key for q in qs]
    print("导出题数:", len(keys))
    r = export(keys, title="导出自检", out="自检卷", show_answers=True)
    print("ok      :", r["ok"])
    print("questions:", r["questions"], " missing:", r["missing"])
    print("tex     :", r["tex_abs"])
    print("pdf     :", r["pdf_abs"])
    if not r["ok"]:
        print("错误:\n" + r["log"])
