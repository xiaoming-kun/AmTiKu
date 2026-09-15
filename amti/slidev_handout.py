#!/usr/bin/env python3
"""Slidev 讲义导出（AmTiKu 模块）

把题库的题转成 Slidev 讲义并导出 PDF。

与 `amti/export.py` 的区别：
  export.py  → LaTeX/elegantbook，A4 印刷讲义
  本模块     → Slidev，16:9 / A4 / 4:3 幻灯片讲义（可批注、低密度）

依赖 MiniMaxH3 的 Slidev 项目（含自定义样式与字体）。
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

# Slidev 渲染工程（复用已验证的环境，避免重复 486MB 的 node_modules）
SLIDEV_PROJ = Path("/Users/ximing/MiniMaxH3")
SLIDEV_STYLES = SLIDEV_PROJ / "styles" / "index.css"
NODE_BIN = Path.home() / ".local" / "node24" / "bin"
AMTIKU = Path.home() / "Documents" / "AmTiKu"
OUT_DIR = AMTIKU / "试卷"
PUBLIC_IMG = SLIDEV_PROJ / "public" / "img"

# 单次 Slidev 导出的硬上限。
# ⚠️ 后端审查报告 Critical #1：这里原本**没有 timeout**。
# FastAPI 的同步路由跑在有界线程池（默认 40 个 worker）里，子进程一旦卡死
# （Slidev/Playwright 卡住是已知现象），worker 永远不归还 → 请求永不返回，
# 重复几次就耗光线程池，服务"看着活着但所有接口排队"。
EXPORT_TIMEOUT_SEC = 900      # 15 分钟：大讲义留足，但绝不无限等      # 讲义引用的图片放这里

# 页面比例（Slidev 的 aspectRatio 语法）
RATIOS = {
    "16:9": "16/9",      # 讲课、录屏
    "a4": "210/297",     # 打印、发学生
    "4:3": "4/3",        # 老式投影
}

# 密度档位：控制留白多少
DENSITIES = {
    "tight": "",            # 紧凑，题多
    "normal": "p-space",    # 标准
    "loose": "p-space-lg",  # 宽松，留白多，方便手写
}


# ══════════════════════════════════════════════════════════════
#  LaTeX 转换规则（全部经 500 道随机题压测验证）
# ══════════════════════════════════════════════════════════════


from amti.logutil import get_logger

log = get_logger(__name__)

def normalize_delims(text: str) -> str:
    r"""R1: \[...\] → $$...$$，\(...\) → $...$"""
    text = re.sub(r"\\\[(.+?)\\\]", lambda m: "$$" + m.group(1).strip() + "$$",
                  text, flags=re.S)
    text = re.sub(r"\\\((.+?)\\\)", lambda m: "$" + m.group(1).strip() + "$",
                  text, flags=re.S)
    return text


def tighten_math(text: str) -> str:
    r"""修掉会让 markdown-it 拒绝解析的数学定界符。

    ⚠️ markdown-it 的 inline math 规则：**闭 `$` 前不能是空格**，
    否则整段不渲染、原样显示 LaTeX 源码。

    题库里大量题目以 `= \paren[D]` 结尾，剥离答案后正好变成 `= $`
    —— 闭合 `$` 前有空格 → 整道题公式全变源码。

    实现思路：把文本按 `$` 切段。
      · 偶数段是正文（原样保留，**包括首尾空格**）
      · 奇数段是公式内容（去掉首尾空格）
    这样既修好了 `= $`，又不会动正文里跟公式相邻的空格。
    `$$` 块级公式先剔除，不参与切分。
    """
    # Ⓩ tikz / pgfplots 图形：KaTeX 渲染不了，换成占位提示。
    #    老师自己画图（用户明确说图形自己处理）。
    #    直接留源码会显示一大段 \begin{tikzpicture}...，很难看。
    text = re.sub(r"\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}",
                  "【图：请手绘】", text)
    text = re.sub(r"\\begin\{axis\}(\[[^\]]*\])?[\s\S]*?\\end\{axis\}",
                  "【图：请手绘】", text)
    text = re.sub(r"\\begin\{scope\}(\[[^\]]*\])?[\s\S]*?\\end\{scope\}", "", text)

    # ⓐ minipage 外壳（可能藏在 tabular 单元格里，转换顺序导致漏网）
    text = re.sub(r"\\begin\{minipage\}(\[[^\]]*\])?\{[^}]*\}", "", text)
    text = text.replace(r"\end{minipage}", "")

    # 用占位符保护 $$...$$ 块，避免被当成两个单 $
    blocks: list[str] = []

    def stash_block(m: re.Match) -> str:
        blocks.append(m.group(0))
        return f"\x01B{len(blocks) - 1}\x01"

    text = re.sub(r"\$\$[\s\S]+?\$\$", stash_block, text)

    out = []
    for line in text.split("\n"):
        if line.count("$") < 2:
            out.append(line)
            continue
        segs = line.split("$")
        # split 后：segs[0] 正文, segs[1] 公式, segs[2] 正文, segs[3] 公式, …
        # 拼接时每段公式前后各补一个 $，正文原样保留（含空格）
        rebuilt = [segs[0]]
        for k in range(1, len(segs)):
            if k % 2 == 1:
                rebuilt.append("$" + segs[k].strip() + "$")
            else:
                rebuilt.append(segs[k])
        line2 = "".join(rebuilt)
        # 最后一个 $ 后面没内容时（公式未闭合），去掉多余的结尾 $
        if len(segs) % 2 == 0:
            line2 = line2[:-1]
        out.append(line2)

    text = "\n".join(out)

    # 还原 $$ 块
    for i, b in enumerate(blocks):
        text = text.replace(f"\x01B{i}\x01", b)
    return text


def convert_enumerate(text: str) -> str:
    r"""enumerate 环境 → （1）（2）…。

    ⚠️ 用**栈式解析**处理嵌套，不用正则。
    题库里有嵌套 enumerate（大题的小问下还有小问），正则无论贪婪
    还是非贪婪都会错配 \end（实测 242 道题受影响）——正则数不了括号。

    层级样式：第 1 层 （1）（2），第 2 层 ①②③，第 3 层 a. b.
    """
    BEGIN = r"\begin{enumerate}"
    END = r"\end{enumerate}"

    def render(items: list[str], depth: int) -> str:
        marks = "①②③④⑤⑥⑦⑧⑨⑩"
        out = []
        for i, it in enumerate(items):
            it = it.strip()
            if depth == 0:
                label = f"（{i + 1}）"
            elif depth == 1:
                label = marks[i] if i < len(marks) else f"({i + 1})"
            else:
                label = f"{chr(97 + i)}. "
            out.append("\n" + "　" * depth + label + it)
        return "".join(out) + "\n"

    out_parts: list[str] = []
    pos = 0
    # 栈：每层记录 (开始位置, 该层已收集的 item, 当前 item 的文本)
    stack: list[dict] = []

    while pos < len(text):
        ib = text.find(BEGIN, pos)
        ie = text.find(END, pos)

        if ib < 0 and ie < 0:
            tail = text[pos:]
            if stack:
                stack[-1]["cur"].append(tail)
            else:
                out_parts.append(tail)
            break

        if ib >= 0 and (ie < 0 or ib < ie):
            # 进入一层
            chunk = text[pos:ib]
            if stack:
                stack[-1]["cur"].append(chunk)
            else:
                out_parts.append(chunk)
            # 跳过 \begin{enumerate} 与可能的 [选项]
            j = ib + len(BEGIN)
            if text.startswith("[", j):
                k = text.find("]", j)
                if k >= 0 and k - j < 40:
                    j = k + 1
            stack.append({"items": [], "cur": []})
            pos = j
        else:
            # 结束一层
            chunk = text[pos:ie]
            if stack:
                stack[-1]["cur"].append(chunk)
            else:
                out_parts.append(chunk)

            if not stack:                       # 多余的 \end，跳过
                pos = ie + len(END)
                continue

            top = stack.pop()
            body = "".join(top["cur"])
            # 按 \item 切分成条目（第一个 \item 之前的内容丢弃）
            pieces = re.split(r"\\item\b", body)
            for piece in pieces[1:]:
                if piece.strip():
                    top["items"].append(piece)
            rendered = render(top["items"], len(stack))
            if stack:
                stack[-1]["cur"].append(rendered)
            else:
                out_parts.append(rendered)
            pos = ie + len(END)

    return "".join(out_parts)


def _match_brace(text: str, start: int) -> int:
    r"""从 text[start]=='{' 开始，返回配对 '}' 的下标；失败返回 -1。

    ⚠️ 不能用 `\{[^}]*\}` 这种简单正则 —— 题库里有
    `\begin{tabular}{c}原料 & 肥料 & ...` 这种列格式后面直接跟内容的写法，
    简单正则会错配（实测 10 道题受影响）。
    """
    if start >= len(text) or text[start] != "{":
        return -1
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "\\":          # 跳过转义
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _extract_tabular(text: str) -> list[tuple[int, int, str]]:
    r"""找出所有 tabular 块，返回 [(start, end, body), ...]，**按从内到外排序**。

    ⚠️ 必须用**栈**配对 \begin/\end —— 题库里有嵌套 tabular
    （外层 2 列放两个数阵，数阵本身又是 tabular）。
    用 str.find 找第一个 \end 会匹配到内层的，导致外层错配
    （实测 10 道题受影响）。
    """
    BEGIN = r"\begin{tabular}"
    END = r"\end{tabular}"
    blocks: list[tuple[int, int, str]] = []
    stack: list[int] = []          # 记录每层 begin 的下标
    bodies: list[int] = []         # 记录每层 body 的起始下标

    pos = 0
    while pos < len(text):
        ib = text.find(BEGIN, pos)
        ie = text.find(END, pos)

        if ib < 0 and ie < 0:
            break
        if ib >= 0 and (ie < 0 or ib < ie):
            j = ib + len(BEGIN)
            while j < len(text) and text[j] in " \t":
                j += 1
            if j < len(text) and text[j] == "[":          # 可选 [位置]
                k = text.find("]", j)
                j = k + 1 if 0 < k - j < 60 else j
            if j < len(text) and text[j] == "{":          # 列格式（配对花括号）
                k = _match_brace(text, j)
                j = k + 1 if k > 0 else j
            stack.append(ib)
            bodies.append(j)
            pos = j
        else:
            if stack:
                bi = stack.pop()
                bstart = bodies.pop()
                blocks.append((bi, ie + len(END), text[bstart:ie]))
            pos = ie + len(END)

    # 只保留**最外层**的块：嵌套的交给 convert_tabular 递归处理
    # （否则内层的位置替换会破坏外层的下标）
    blocks.sort(key=lambda x: (x[0], -x[1]))
    outer: list[tuple[int, int, str]] = []
    last_end = -1
    for st, en, body in blocks:
        if st >= last_end:
            outer.append((st, en, body))
            last_end = en
    return outer


def convert_tabular(text: str) -> str:
    r"""LaTeX 表格环境 → markdown 表格。

    题库里 364 道题用 \begin{tabular}（多在 \begin{center} 里）。

    嵌套处理：**内层先转成占位符**，转完外层再还原。
    直接把内层转成 markdown 会让它的换行破坏外层的行解析
    （实测：外层 2 列放两个数阵的题，转出来是乱的）。
    """
    # 去 center / minipage 外壳（内容保留，表格本身居中显示）
    text = re.sub(r"\\begin\{center\}(.*?)\\end\{center\}",
                  lambda m: m.group(1), text, flags=re.S)
    text = re.sub(r"\\begin\{minipage\}\{[^}]*\}", "", text)
    text = text.replace(r"\end{minipage}", "")

    cache: dict[str, str] = {}

    def stash(body: str) -> str:
        """把 tabular 的 body 转成 markdown，返回**占位符**。

        ⚠️ 顺序很重要：
          ① 先把 body 里**嵌套的** tabular 换成占位符
          ② 再按 \\ 和 & 解析外层（此时 body 是单行安全的）
          ③ 最后把占位符还原成真正的 markdown 表格
        反过来做（先转成 markdown 再解析外层）会让内层的换行
        破坏外层的行结构 —— 实测外层套数阵的题转出来是乱的。
        """
        # ① 嵌套表格 → 占位符
        for k, v in list(cache.items()):
            body = body.replace(k, v)          # 已 stash 过的（极少）
        for st, en, inner in reversed(_extract_tabular(body)):
            ph = stash(inner)
            body = body[:st] + ph + body[en:]

        md = to_md(body)

        # ③ 还原占位符
        for _ in range(8):
            hit = False
            for k in list(cache.keys()):
                if k in md:
                    md = md.replace(k, cache.pop(k))
                    hit = True
            if not hit:
                break
        return md

    def to_md(body: str) -> str:
        rows: list[list[str]] = []
        for line in body.split(r"\\"):
            line = line.strip()
            if not line:
                continue
            line = line.replace(r"\hline", "").strip()
            if not line:
                continue
            cells = [c.strip() for c in line.split("&")]
            if any(cells):
                rows.append(cells)
        if not rows:
            return "\n"
        ncol = max(len(r) for r in rows)
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        out = ["", "| " + " | ".join(rows[0]) + " |", "|" + "---|" * ncol]
        for r in rows[1:]:
            out.append("| " + " | ".join(r) + " |")
        out.append("")
        return "\n".join(out)

    # 从后往前替换最外层表格（前面的下标不会错位）
    for st, en, body in sorted(_extract_tabular(text), key=lambda x: x[0], reverse=True):
        text = text[:st] + stash(body) + text[en:]
    return text


def strip_answers(text: str) -> str:
    r"""\paren[A] → （　　）；\fillin[答案] → ＿＿＿＿"""
    text = re.sub(r"\\paren\s*\[[^\]]*\]", "（　　）", text)
    text = re.sub(r"\\fillin\s*\[[^\]]*\]", "＿＿＿＿", text)
    # \\fillin{{}} / \\fillin{{答案}} —— 花括号变体要一起吃掉，
    # 否则留下孤立 {{}}（实测 708 道题受影响）
    text = re.sub(r"\\fillin\s*\{[^}}]*\}", "＿＿＿＿", text)
    text = re.sub(r"\\fillin\b", "＿＿＿＿", text)
    # 兜底：紧跟在空位后面的孤立 {} （数据里自带的多余花括号）
    text = re.sub(r"＿＿＿＿\s*\{\}", "＿＿＿＿", text)
    return text


def show_answers(text: str) -> str:
    r"""把答案宏还原成可见文字（教师版）。

    \paren[A] → （ A ）    \fillin[答案] → 答案
    """
    text = re.sub(r"\\paren\s*\[([^\]]*)\]", lambda m: f"（ {m.group(1)} ）", text)
    text = re.sub(r"\\fillin\s*\[([^\]]*)\]", r"\1", text)
    # 空花括号：没答案就显示空位；有答案就显示答案
    text = re.sub(r"\\fillin\s*\{\}", "＿＿＿＿", text)
    text = re.sub(r"\\fillin\s*\{([^}}]*)\}", r"\1", text)
    return text


def extract_figures(text: str) -> tuple[str, list[str]]:
    r"""抽出 \includegraphics，返回（清理后的文本, 图片名列表）。"""
    imgs = re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", text)
    text = re.sub(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{[^}]+\}", "", text)
    return text, imgs


# ══════════════════════════════════════════════════════════════
#  宏转换：LaTeX 专有宏 → KaTeX 等价写法
#
#  题库用的是 LaTeX + newtxmath，有些宏 KaTeX 不认识，
#  不转换就会渲染成**红色源码**（实测：\symbfit 404 道题受影响）。
#
#  统计过的分布（17249 道）：
#    \symbfit / \symbf  404 道  ← 必须转
#    \R \up               11 道  ← 必须转
#    其余（\leqslant \geqslant \it \mathrm \text \displaystyle）
#    KaTeX 原生支持，不用动。
# ══════════════════════════════════════════════════════════════

MACRO_FIXES = [
    # 顺序重要：先长后短，避免 \symbf 吃掉 \symbfit 的前缀
    # ⚠️ 用 lambda 而不是字符串替换 —— 替换串里有反斜杠，
    #    字符串形式要套多层转义，极易写错（我踩过）。
    (re.compile(r"\\symbfit\s*\{([^}]*)\}"),
     lambda m: r"\boldsymbol{" + m.group(1) + "}"),
    (re.compile(r"\\symbfit\s+([A-Za-z])"),
     lambda m: r"\boldsymbol{" + m.group(1) + "}"),
    (re.compile(r"\\symbfit"), lambda m: r"\boldsymbol"),

    (re.compile(r"\\symbf\s*\{([^}]*)\}"),
     lambda m: r"\mathbf{" + m.group(1) + "}"),
    (re.compile(r"\\symbf\s+([A-Za-z])"),
     lambda m: r"\mathbf{" + m.group(1) + "}"),
    (re.compile(r"\\symbf"), lambda m: r"\mathbf"),

    (re.compile(r"\\bm\s*\{([^}]*)\}"),
     lambda m: r"\boldsymbol{" + m.group(1) + "}"),
    (re.compile(r"\\bm\s+([A-Za-z])"),
     lambda m: r"\boldsymbol{" + m.group(1) + "}"),

    # 自定义简写
    (re.compile(r"\\R\b"), lambda m: r"\mathbb{R}"),
    (re.compile(r"\\N\b"), lambda m: r"\mathbb{N}"),
    (re.compile(r"\\Z\b"), lambda m: r"\mathbb{Z}"),
    (re.compile(r"\\Q\b"), lambda m: r"\mathbb{Q}"),
    (re.compile(r"\\C\b"), lambda m: r"\mathbb{C}"),
    # 已废弃的字体切换（KaTeX 会报 unknown command）
    (re.compile(r"\\up\b"), lambda m: ""),
]


def fix_macros(text: str) -> str:
    r"""把 KaTeX 不认识的 LaTeX 宏换成等价写法。"""
    for pat, fn in MACRO_FIXES:
        text = pat.sub(fn, text)
    return text


def fix_macros(text: str) -> str:
    r"""把 KaTeX 不认识的 LaTeX 宏换成等价写法。"""
    for pat, rep in MACRO_FIXES:
        text = re.sub(pat, rep, text)
    return text


def convert_math(text: str) -> str:
    r"""R2/R3/R4: 让 LaTeX 对 Vue 模板安全。

    R3  \left\{ → \left\lbrace{}   （必须先处理）
    R2  \{ → \lbrace{}             （必须用 {} 分隔）
    R4  数学模式内 < > → \lt \gt    （< 后换行会被 Vue 当标签解析）
    """
    text = re.sub(r"\\left\s*\\\{", r"\\left\\lbrace{}", text)
    text = re.sub(r"\\right\s*\\\}", r"\\right\\rbrace{}", text)
    text = text.replace(r"\{", r"\lbrace{}").replace(r"\}", r"\rbrace{}")
    parts = re.split(r"(\$[^$]*\$)", text)
    for i in range(1, len(parts), 2):
        parts[i] = parts[i].replace("<", r"\lt ").replace(">", r"\gt ")
    return "".join(parts)


def source_label(q) -> str:
    r"""高考题的出处标签，如「2024新高考I卷 第1题」。

    为什么只给高考题加（用户要求）：讲义里注明「这是 2026 新课标 I 卷
    第 7 题」会显得正式、也方便学生回查原卷。模拟题/练习册的出处
    五花八门，加上反而杂乱。

    数据来自题库元数据：
        meta.year    2024            （年份）
        meta.region  新高考I卷        （卷别）
        key 里的 #N  第几题
    """
    if getattr(q, "kind", "") != "高考":
        return ""
    meta = getattr(q, "meta", None) or {}
    year = str(meta.get("year") or "").strip()
    region = str(meta.get("region") or "").strip()
    # 卷别兜底：老数据可能没有 region，从 key 里取（高考真题汇编/2024/新高考I卷#1）
    if not region and "/" in q.key:
        parts = q.key.split("/")
        if len(parts) >= 3:
            region = parts[-1].split("#")[0].strip()
    no = q.key.rsplit("#", 1)[1].strip() if "#" in q.key else ""
    head = f"{year}{region}"
    if not head and not no:
        return ""
    return f"{head} 第{no}题" if no else head


def _run_slidev_export(md: Path, pdf: Path, env: dict) -> tuple[bool, str]:
    r"""跑一次 `slidev export`，**带超时与进程组强杀**。

    返回 `(是否超时, 日志尾巴)`。

    为什么用 Popen 而不是 subprocess.run：
    `npx` 会再 fork 出 node/chromium，超时后只杀 npx 会留下孤儿进程继续占 CPU。
    用 `start_new_session=True` 让子进程自成进程组，超时就 `killpg` **整组**杀掉。
    """
    cmd = ["npx", "slidev", "export", str(md), "--format", "pdf",
           "--output", str(pdf), "--wait-until", "load", "--wait", "3000"]
    # 关键：必须 --wait-until load --wait 3000。
    # 默认 networkidle 会超时；wait=0 会在公式渲染完成前截图（产出空 PDF）。
    # 也不要传 slidev 自己的 --timeout，它会干扰内部等待。
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(SLIDEV_PROJ), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
    except FileNotFoundError:
        return True, "找不到 npx（检查 NODE_BIN / PATH）"

    try:
        out, _ = proc.communicate(timeout=EXPORT_TIMEOUT_SEC)
        return False, (out or "")[-600:]
    except subprocess.TimeoutExpired:
        log.error("Slidev 导出超时（>%ss），强杀进程组 %s",
                  EXPORT_TIMEOUT_SEC, proc.pid)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        try:
            proc.communicate(timeout=10)
        except Exception:
            log.warning("等待被杀的导出进程退出超时", exc_info=True)
        return True, f"导出超时（>{EXPORT_TIMEOUT_SEC}s），已终止子进程"


def _copy_trimmed(src: Path, dst: Path) -> None:
    r"""复制图片，并把**近白背景转成透明**。

    题库的图多是白底（实测某张 98.2% 是白），贴在米色讲义上
    会显出一个白方块，很突兀。转透明后与米色底融合。
    """
    try:
        from PIL import Image
        import numpy as np
        im = Image.open(src).convert("RGBA")
        a = np.array(im)
        r, g, b, al = a[:, :, 0], a[:, :, 1], a[:, :, 2], a[:, :, 3]
        near_white = (r > 242) & (g > 242) & (b > 242)
        a[:, :, 3] = np.where(near_white, 0, al)
        Image.fromarray(a).save(dst)
    except Exception:
        # 失败就原样复制，不阻断 —— 但要知道自己失败了
        log.debug("白底转透明失败，按原图复制：%s", src.name, exc_info=True)
        shutil.copy2(src, dst)


def copy_figures(text: str, width_pct: int = 55) -> tuple[str, str]:
    r"""把题干里的 \includegraphics 换成真实图片引用。

    题库图片在 AmTiKu/图片/，需复制到 Slidev 的 public/img/ 才能被引用。

    返回 (清理后的文本, img 标签)。

    ⚠️ 之前是**直接删掉** includegraphics —— 结果「如图，四棱锥…」这种题
    图没了就没法看。2650 道题受影响，必须真插入。
    """
    imgs = re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", text)
    text = re.sub(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{[^}]+\}", "", text)

    tags = []
    for name in imgs:
        src = AMTIKU / "图片" / name
        if not src.exists():
            continue
        try:
            PUBLIC_IMG.mkdir(parents=True, exist_ok=True)
            dst = PUBLIC_IMG / name
            if not dst.exists():
                _copy_trimmed(src, dst)
        except Exception:
            log.warning("配图复制失败，跳过：%s", name, exc_info=True)
            continue
        # 图居中 + **限宽限高**：
        # 只给 width 的话，竖长图（如 610×620）会算出 800px 高，
        # 在 16:9 页面里放不下 → 被裁掉（实测踩过）。
        tags.append(
            f'<img src="/img/{name}" '
            f'style="max-width:{width_pct}%;max-height:210px;'
            f'width:auto;height:auto;display:block;margin:6px auto" />')
    return text.strip(), "\n\n".join(tags)



    text, _ = extract_figures(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def transform(q, with_answers: bool = False, with_figures: bool = True) -> str:
    """一道题的题干 → 讲义 markdown（含选项与配图）。"""
    raw = q.stem
    if with_figures:
        raw, fig_tags = copy_figures(raw)
    else:
        # 不要图：直接去掉 includegraphics
        raw = re.sub(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{[^}]+\}", "", raw)
        fig_tags = ""
    # 清理多余空白
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    raw = fix_macros(raw)                      # ← 先修宏，再处理答案
    raw = show_answers(raw) if with_answers else strip_answers(raw)
    stem = tighten_math(
        convert_math(normalize_delims(convert_tabular(convert_enumerate(raw)))))

    # 单换行 → markdown 硬换行（行尾两空格）。
    # 真实试卷里（1）①②（2）各占一行；markdown 默认把单个换行
    # 当成空格，整道解答题会挤成一大段（用户要求与真实排版一致）。
    # 连续两个换行仍算段落分隔，不受影响。
    stem = re.sub(r"(?<!\n)\n(?!\n)", "  \n", stem)

    out = [f"{stem}\n"]
    if fig_tags:
        # 用标记包起来，后端据此分段包裹（避免破坏选项行的 flex 处理）
        out.append(f"\n<!--FIGS-->{fig_tags}<!--/FIGS-->\n")
    if q.options:
        opts = "　　".join(
            f"({o.label}) {tighten_math(convert_math(normalize_delims(fix_macros(o.text))))}"
            for o in q.options)
        out.append(f"\n{opts}\n")
    return "".join(out)


# ══════════════════════════════════════════════════════════════
#  讲义组装
# ══════════════════════════════════════════════════════════════

FRONTMATTER = """---
theme: default
title: {title}
info: 由 AmTiKu 生成
class: style-plain
aspectRatio: {ratio}
drawings:
  persist: true
transition: none
mdc: true
fonts:
  sans: PingFang SC
  serif: Songti SC
---

<div class="p-chapter">
<span class="p-hl">{title}</span>
</div>

<div class="p-space"></div>

<div class="p-body">

共 {n} 道题{extra}

</div>

<div class="p-space-lg"></div>
"""

PAGE = """---
layout: default
class: style-plain
---

<div class="p-ex">

{body}

</div>

{foot}
"""


def build_markdown(questions, *, title: str, ratio: str = "16/9",
                   density: str = "normal", with_answers: bool = False,
                   page_numbers: bool = False,
                   show_source: bool = False) -> str:
    """题目列表 → Slidev 讲义 markdown。"""
    extra = ""
    if questions and questions[0].meta.get("source_label"):
        extra = f"，选自 {questions[0].meta['source_label']}"

    parts = [FRONTMATTER.format(title=title, n=len(questions),
                                ratio=ratio, extra=extra)]
    spacer = DENSITIES.get(density, "p-space")

    for i, q in enumerate(questions, 1):
        lines = []
        # 题源标签（如「2024年新高考I卷」）默认不显示——讲义要页面干净
        if show_source:
            tag = q.meta.get("source_label", "")
            if tag:
                lines.append(f'<div class="p-point">{tag}</div>\n\n')
                if spacer:
                    lines.append(f'<div class="{spacer}"></div>\n\n')
        lines.append(f"{i}. {transform(q, with_answers)}\n")
        # div 后必须空一行，否则行内公式不渲染
        parts.append(PAGE.format(
            body="".join(lines),
            foot=f'<div class="p-foot">{i}</div>\n' if page_numbers else "",
        ))
    return "".join(parts)


# ══════════════════════════════════════════════════════════════
#  导出
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
#  讲义块模型
#
#  讲义 = 有序的内容块列表。块可以来自题库，也可以是老师自己写的。
#  这是与"组卷"的本质区别：组卷只有题目，讲义需要讲解、标题、公式。
# ══════════════════════════════════════════════════════════════

# 支持的块类型
BLOCK_TYPES = {
    "chapter": "章标题",      # L1：大模块
    "section": "节标题",      # L2：中模块
    "point":   "知识点",      # L3：最小单元（带红点）
    "text":    "讲解文字",    # 老师自己写的话
    "formula": "公式",        # 独立公式
    "question": "题目",       # 从题库引用（只存 key）
}

HANDOUTS = AMTIKU / "讲义" / "讲义存档.json"


def _load_all() -> list[dict]:
    if not HANDOUTS.exists():
        return []
    import json
    try:
        return json.loads(HANDOUTS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception:
        log.warning("讲义存档读取失败，按空处理：%s", HANDOUTS, exc_info=True)
        return []


def _save_all(items: list[dict]) -> None:
    import json
    HANDOUTS.parent.mkdir(parents=True, exist_ok=True)
    tmp = HANDOUTS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(HANDOUTS)


def list_handouts() -> list[dict]:
    """讲义列表（不含 blocks，避免列表接口过重）。"""
    return [{k: v for k, v in h.items() if k != "blocks"}
            for h in _load_all()]


def get_handout(name: str) -> dict | None:
    import json
    for h in _load_all():
        if h.get("name") == name:
            return json.loads(json.dumps(h))
    return None


def _count_questions(items: list) -> int:
    """统计题目数。兼容块模式（扁平）与画布模式（按页嵌套）。"""
    n = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        if "blocks" in it and isinstance(it["blocks"], list):
            n += _count_questions(it["blocks"])      # 画布：页 → 块
        elif it.get("type") == "question":
            n += 1
    return n


def save_handout(name: str, *, title: str = "", blocks: list[dict] | None = None,
                 ratio: str = "16:9", density: str = "normal",
                 with_answers: bool = False,
                 extra: dict | None = None) -> dict:
    """新建或覆盖一份讲义。同名覆盖。

    `extra` 放附加设置（如 title_font / body_font），原样存进存档。
    """
    import datetime as _dt
    items = _load_all()
    rec = {
        "name": name,
        "title": title or name,
        "blocks": blocks or [],
        "ratio": ratio,
        "density": density,
        "with_answers": with_answers,
        # 题目数：兼容两种结构
        #   块模式   blocks = [{type:"question",...}, ...]
        #   画布模式 blocks = pages = [{"blocks":[{...}]}, ...]
        "n": _count_questions(blocks or []),
        "at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if extra:
        rec.update({k: v for k, v in extra.items() if v})
    for i, x in enumerate(items):
        if x.get("name") == name:
            rec["at"] = x.get("at") or rec["at"]
            rec["updated"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            items[i] = rec
            break
    else:
        items.append(rec)
    _save_all(items)
    return rec


def remove_handout(name: str) -> bool:
    items = _load_all()
    keep = [x for x in items if x.get("name") != name]
    if len(keep) == len(items):
        return False
    _save_all(keep)
    return True


# ══════════════════════════════════════════════════════════════
#  块 → markdown
# ══════════════════════════════════════════════════════════════

def render_block(b: dict, *, with_answers: bool = False) -> str:
    """一个内容块 → 讲义 markdown 片段。"""
    t = b.get("type", "text")
    text = (b.get("text") or "").strip()

    if t == "chapter":
        return f'<div class="p-chapter">\n<span class="p-hl">{text}</span>\n</div>\n\n'
    if t == "section":
        return f'<div class="p-section">\n<span class="p-hl">{text}</span>\n</div>\n\n'
    if t == "point":
        return f'<div class="p-point">{text}</div>\n\n'
    if t == "formula":
        return f"{text}\n\n"
    if t == "text":
        # 老师写的讲解：支持行内公式，按普通段落渲染
        return f'<div class="p-body">\n\n{text}\n\n</div>\n\n'
    if t == "question":
        return ""     # 由 build_from_blocks 处理
    return ""


def build_from_blocks(blocks: list[dict], *, title: str, ratio: str = "16/9",
                      density: str = "normal", with_answers: bool = False,
                      page_numbers: bool = False,
                      show_source: bool = False) -> str:
    """块列表 → 完整讲义 markdown。

    分页规则（简单、可预期）：
      · chapter / section 各自**独占一页**
      · point / text / formula 累积到一页，直到遇到下一个标题
      · question **独占一页**（讲课时一题一页）
    这样老师加什么、加在哪，都能预期出几页。
    """
    sys.path.insert(0, str(AMTIKU))
    from amti import store

    parts = [FRONTMATTER.format(
        title=title, n=sum(1 for b in blocks if b.get("type") == "question"),
        ratio=ratio, extra="")]
    spacer = DENSITIES.get(density, "p-space")

    buf: list[str] = []          # 累积的内容
    page_no = 0

    def flush():
        nonlocal buf, page_no
        if not buf:
            return
        page_no += 1
        parts.append(PAGE.format(
            body="".join(buf),
            foot=f'<div class="p-foot">{page_no}</div>\n' if page_numbers else "",
        ))
        buf = []

    for b in blocks:
        t = b.get("type", "text")

        if t in ("chapter", "section"):
            flush()
            # 标题独占一页：加留白
            buf.append(render_block(b))
            buf.append(f'<div class="p-space-lg"></div>\n\n')
            flush()
            continue

        if t == "question":
            flush()
            key = b.get("key", "")
            q = store.find(key)
            if not q:
                continue
            page_no += 1
            body = []
            if show_source:
                tag = q.meta.get("source_label", "")
                if tag:
                    body.append(f'<div class="p-point">{tag}</div>\n\n')
                    if spacer:
                        body.append(f'<div class="{spacer}"></div>\n\n')
            body.append(f"{page_no}. {transform(q, with_answers)}\n")
            parts.append(PAGE.format(
                body="".join(body),
                foot=f'<div class="p-foot">{page_no}</div>\n' if page_numbers else "",
            ))
            continue

        # point / text / formula 累积
        if t == "point" and buf:
            buf.append(f'<div class="{spacer}"></div>\n\n' if spacer else "")
        buf.append(render_block(b, with_answers=with_answers))

    flush()
    return "".join(parts)


def export(keys: list[str], *, title: str = "", out: str = "",
           ratio: str = "16:9", density: str = "normal",
           with_answers: bool = False, page_numbers: bool = False,
           show_source: bool = False,
           do_compile: bool = True, retries: int = 3) -> dict:
    """从题库选题，导出 Slidev 讲义。

    返回结构与 `amti/export.py` 对齐（tex_abs / pdf_abs / dir_abs）。
    """
    import datetime as _dt

    if ratio not in RATIOS:
        return {"ok": False, "error": f"未知比例 {ratio!r}", "missing": []}

    # 延迟导入：避免在非 AmTiKu 环境（如独立测试）导入失败
    sys.path.insert(0, str(AMTIKU))
    from amti import store

    qs, missing = [], []
    for k in keys:
        q = store.find(k)
        (qs.append(q) if q else missing.append(k))
    if not qs:
        return {"ok": False, "error": "没有有效的题目", "missing": missing}

    if not out.strip():
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
        out = f"{title.strip() or '讲义'}_{stamp}"
    name = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", out).strip("_") or "讲义"

    # 确保 Slidev 工程可用
    if not (SLIDEV_PROJ / "node_modules" / "@slidev").exists():
        return {"ok": False, "error": f"Slidev 工程不可用：{SLIDEV_PROJ}", "missing": []}

    work = SLIDEV_PROJ / "_handout_build"
    work.mkdir(exist_ok=True)
    md = work / f"{name}.md"
    md.write_text(
        build_markdown(qs, title=title or name, ratio=RATIOS[ratio],
                       density=density, with_answers=with_answers,
                       page_numbers=page_numbers, show_source=show_source),
        encoding="utf-8")

    res = {"ok": True, "name": name, "questions": len(qs), "missing": missing,
           "tex_abs": str(md), "pdf_abs": None, "dir_abs": str(OUT_DIR),
           "saved_hint": f"{name} 讲义", "log": "", "ratio": ratio}

    if not do_compile:
        return res

    pdf = md.with_suffix(".pdf")
    env = dict(os.environ)
    if NODE_BIN.exists():
        env["PATH"] = f"{NODE_BIN}:{env.get('PATH', '')}"

    last = ""
    for attempt in range(1, retries + 1):
        if pdf.exists():
            pdf.unlink()
        # 关键：必须 --wait-until load --wait 3000
        # 默认 networkidle 会超时；wait=0 会在公式渲染完成前截图（产出空 PDF）。
        # 也不要传 --timeout，它会干扰内部等待。
        timed_out, last = _run_slidev_export(md, pdf, env)
        if timed_out:
            res["ok"] = False
            res["error"] = last
            res["log"] = last
            return res

        if pdf.exists() and pdf.stat().st_size > 10_000:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            final = OUT_DIR / f"{name}.pdf"
            shutil.copy2(pdf, final)
            res["pdf_abs"] = str(final)
            res["saved_hint"] = f"{name}.pdf 已保存到 试卷/"
            return res

        if attempt < retries:
            import time
            time.sleep(3)

    log.error("Slidev 导出失败（重试 %s 次后）：%s", retries, last[:200])
    res["ok"] = False
    res["error"] = "Slidev 导出失败"
    res["log"] = last
    return res


if __name__ == "__main__":  # 自测
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", default="1.1.3")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--ratio", default="16:9")
    ap.add_argument("--title", default="测试讲义")
    a = ap.parse_args()

    sys.path.insert(0, str(AMTIKU))
    from amti import store
    qs = [q for q in store.load_cached()
          if any(p.startswith(a.points) for p in q.points)][:a.limit]
    r = export([q.key for q in qs], title=a.title, ratio=a.ratio)
    print(r.get("pdf_abs") or r.get("error"))

def export_blocks(blocks: list[dict], *, title: str = "", out: str = "",
                  ratio: str = "16:9", density: str = "normal",
                  with_answers: bool = False, page_numbers: bool = False,
                  show_source: bool = False,
                  do_compile: bool = True, retries: int = 3) -> dict:
    """从内容块导出讲义（支持自己写的讲解 + 题库选题）。"""
    import datetime as _dt

    if ratio not in RATIOS:
        return {"ok": False, "error": f"未知比例 {ratio!r}", "missing": []}
    if not blocks:
        return {"ok": False, "error": "讲义是空的", "missing": []}

    if not out.strip():
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
        out = f"{title.strip() or '讲义'}_{stamp}"
    name = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", out).strip("_") or "讲义"

    if not (SLIDEV_PROJ / "node_modules" / "@slidev").exists():
        return {"ok": False, "error": f"Slidev 工程不可用：{SLIDEV_PROJ}", "missing": []}

    work = SLIDEV_PROJ
    md = work / f"_blocks_{name}.md"
    md.write_text(build_from_blocks(blocks, title=title or name,
                                    ratio=RATIOS[ratio], density=density,
                                    with_answers=with_answers,
                                    page_numbers=page_numbers,
                                    show_source=show_source),
                  encoding="utf-8")

    nq = sum(1 for b in blocks if b.get("type") == "question")
    res = {"ok": True, "name": name, "questions": nq, "missing": [],
           "tex_abs": str(md), "pdf_abs": None, "dir_abs": str(OUT_DIR),
           "saved_hint": f"{name} 讲义", "log": "", "ratio": ratio}
    if not do_compile:
        return res

    pdf = md.with_suffix(".pdf")
    env = dict(os.environ)
    if NODE_BIN.exists():
        env["PATH"] = f"{NODE_BIN}:{env.get('PATH', '')}"

    last = ""
    for attempt in range(1, retries + 1):
        if pdf.exists():
            pdf.unlink()
        timed_out, last = _run_slidev_export(md, pdf, env)
        if timed_out:
            res["ok"] = False
            res["error"] = last
            res["log"] = last
            return res
        if pdf.exists() and pdf.stat().st_size > 10_000:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            final = OUT_DIR / f"{name}.pdf"
            shutil.copy2(pdf, final)
            res["pdf_abs"] = str(final)
            res["saved_hint"] = f"{name}.pdf 已保存到 试卷/"
            return res
        if attempt < retries:
            import time
            time.sleep(3)

    log.error("Slidev 导出失败（重试 %s 次后）：%s", retries, last[:200])
    res["ok"] = False
    res["error"] = "Slidev 导出失败"
    res["log"] = last
    return res

# ══════════════════════════════════════════════════════════════
#  画布模式：绝对定位导出
#
#  与「块模式」的区别：
#    块模式  → 文档流，内容自上而下排，自动分页
#    画布模式 → 绝对定位，块放在 (x, y)，尺寸 (w, h)
#
#  为什么可行：Slidev 页面是**固定比例画布**（16:9 / A4 / 4:3），
#  position:absolute 的百分比坐标与 PDF 页面一一对应。
#  （实测验证：绝对定位容器内的 KaTeX 公式正常渲染）
#
#  坐标全部用**百分比**（0-100），换比例时按比例重算，不会错位。
# ══════════════════════════════════════════════════════════════

CANVAS_FRONTMATTER = """---
theme: default
title: {title}
info: 由 AmTiKu 生成
class: style-plain
aspectRatio: {ratio}
drawings:
  persist: true
transition: none
mdc: true
fonts:
  sans: PingFang SC
  serif: Songti SC
---
"""

# 首页：紧跟 frontmatter（讲稿版模板的做法，已验证）
FIRST_PAGE = """{body}
"""

# 后续页：用 --- 分隔
CANVAS_PAGE = """---
layout: default
class: style-plain
---

{body}
"""


def _pct(v, default: float = 0.0) -> float:
    """把坐标值夹到 0-100。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(100.0, f))


# 默认字号与行距（用户指定：16px / 2.0）
# ⚠️ 改这里时必须同步改前端 App.tsx 的 DEFAULT_FS / DEFAULT_LH
DEFAULT_FS = 16.0
DEFAULT_LH = 2.0


def _font_size(b: dict, kind: str) -> float:
    """字号（px）。

    优先用块自带的 fontSize；否则给**固定基准值**。

    ⚠️ 刻意**不按块宽缩放** —— 拉宽文本框时字号不该跟着变
    （PPT 也是这个行为）。之前按宽度算，92% 宽的章标题会到 60px，
    撑满整个屏幕，用户反馈「调不了字号」。
    """
    if b.get("fontSize"):
        try:
            return float(b["fontSize"])
        except (TypeError, ValueError):
            pass
    # 统一默认 16px（用户指定）。与前端 DEFAULT_FS / DEFAULT_LH 保持一致。
    return DEFAULT_FS


def render_canvas_block(b: dict, *, with_answers: bool = False,
                        show_source: bool = True) -> str:
    """一个块 → 绝对定位的 HTML，**内部使用讲义的模板类**。

    模板类（来自 `.dsh` 里那份讲稿版讲义，一级标题的做法）：
      p-hand  一级标题  手写体 + 黄色荧光笔
      p-sec   二级标题  稍小 + 荧光笔
      p-tag   三级      红点 + 文字
      p-t / p-ti  正文 / 缩进正文
      p-ex    练习
      p-space / p-space-lg  留白

    位置用百分比，与 Slidev 固定比例画布一一对应。
    注意：`<div>` 与内容之间必须空行，否则内部公式不渲染（实测踩过）。
    """
    kind = b.get("type", "text")
    x, y = _pct(b.get("x", 0)), _pct(b.get("y", 0))
    w, h = _pct(b.get("w", 40), 40), _pct(b.get("h", 0))
    # 防止 left+width 越界（前端已钳，这里是兜底：旧数据或手改 JSON）
    w = min(w, 100.0 - x)
    h = min(h, 100.0 - y)
    z = int(b.get("z", 0) or 0)

    # 外层：绝对定位
    outer = ["position:absolute", f"left:{x}%", f"top:{y}%",
             f"width:{w}%", f"z-index:{z}"]
    if h > 0:
        outer.append(f"height:{h}%")

    # 字号：优取块自带，否则按块宽自动缩放（与前端 autoFontSize 一致）
    outer.append(f"font-size:{_font_size(b, kind)}px")

    # 行距：优取块自带，否则 DEFAULT_LH（2.0）
    try:
        # 注意用 is None 判断，不能用 or —— 行距 1.0 是合法值但 falsy
        raw_lh = b.get("lineHeight")
        lh = DEFAULT_LH if raw_lh is None else float(raw_lh)
    except (TypeError, ValueError):
        lh = DEFAULT_LH
    outer.append(f"line-height:{max(1.0, min(3.0, lh))}")

    if b.get("align"):
        outer.append(f"text-align:{b['align']}")

    # 自动适配缩放：编辑器量出内容超过一页时算出的系数（fit<1）。
    # Chromium 的 zoom 会按整宽重排再等比缩小 —— 大表格+图的题
    # 也能收进一页，而不是溢出到页外（用户实测帆船题占满全部页面）。
    try:
        fit = float(b.get("fit") or 1)
    except (TypeError, ValueError):
        fit = 1.0
    if 0 < fit < 1:
        outer.append(f"zoom:{fit:.3f}")

    # 内层：模板类
    text = b.get("text", "") or ""

    if kind == "question":
        sys.path.insert(0, str(AMTIKU))
        from amti import store
        q = store.find(b.get("key", ""))
        if not q:
            inner = f'<div class="p-ex">\n\n<span style="opacity:.5">（题目未找到）</span>\n\n</div>'
        else:
            body = transform(q, with_answers)
            # 高考题标出处（用户要求）：标签在前，题目在后。
            # 块可单独覆盖（b["showSource"]），讲义级开关是 show_source。
            # 标签放在 `.p-ex` **外面** —— 它是出处，不属于题目正文的排版。
            lab = ""
            if b.get("showSource", show_source):
                lab = source_label(q)
                # 加括号（用户要求）：「2024上海卷（春） 第2题」→「（…）」
                lab = f"（{lab}）" if lab else "" 

            # 拆出图片段（transform 用 <!--FIGS--> 包起来了）
            fig_html = ""
            fm = re.search(r"<!--FIGS-->(.*?)<!--/FIGS-->", body, re.S)
            if fm:
                fig_html = fm.group(1).strip()
                body = body.replace(fm.group(0), "").strip()

            # 题干与选项拆开：选项行要单独用 flex 包裹（不换行）
            lines = body.split("\n")
            stem_lines, opt_lines = [], []
            for ln in lines:
                (opt_lines if ln.lstrip().startswith("(A)") else stem_lines).append(ln)
            stem_txt = "\n".join(stem_lines).strip()
            opt_txt = "\n".join(opt_lines).strip()

            segs = []
            # ① 题干（高考题出处**并进同一行**，用户要求：括号 + 与题目同排）
            #
            # 用**纯文本**而不是 <span class="p-src"> 有两个原因：
            #   1. 编辑器预览的 MarkdownBody 不解析 HTML，用 span 会导致
            #      **预览里有标签、导出后没有**（本项目最忌讳的不一致）；
            #   2. 纯文本在任何渲染路径下都稳，不会被 markdown 当 HTML 块。
            if stem_txt:
                segs.append(f'<div class="p-ex" style="line-height:{lh}">'
                            f'\n\n{lab}{stem_txt}\n\n</div>')
            elif lab:
                # 极端情况：只有选项没有题干 —— 别把出处弄丢
                segs.append(f'<div class="p-ex" style="line-height:{lh}">'
                            f'\n\n{lab}\n\n</div>')
            # ② 配图（单独一段，前后空行，否则图片不显示）
            if fig_html:
                segs.append(f'<div style="text-align:center">'
                            f'\n\n{fig_html}\n\n</div>')
            # ③ 选项（flex 不换行）
            if opt_txt:
                segs.append(f'<div class="p-ex" style="line-height:{lh}">'
                            f'\n\n<div style="display:flex;flex-wrap:nowrap;'
                            f'gap:0 1.2em">\n\n{opt_txt}\n\n</div>\n\n</div>')

            inner = "\n\n".join(segs)

    elif kind == "chapter":
        # 一级标题：模板做法
        inner = (f'<div class="p-hand" style="line-height:{lh}">\n\n'
                 f'<span class="p-hl">{text}</span>\n\n</div>')

    elif kind == "section":
        inner = (f'<div class="p-sec" style="line-height:{lh}">\n\n'
                 f'<span class="p-hl">{text}</span>\n\n</div>')

    elif kind == "point":
        inner = f'<div class="p-tag" style="line-height:{lh}">\n\n{text}\n\n</div>'

    elif kind == "formula":
        inner = f'<div class="p-t" style="line-height:{lh}">\n\n{text}\n\n</div>'

    elif kind == "indent":
        inner = f'<div class="p-ti">\n\n{text}\n\n</div>'

    elif kind == "table":
        # 表格：对齐「一数」的对比表格（表头黄底、单元格可放公式）
        inner = _render_table(b, _font_size(b, kind))

    elif kind == "emoji":
        # 表情标记：一数用 😡🤯🤮 标难度/易错。字号放大 4 倍才醒目。
        e = (text or "😡").strip()
        inner = (f'<div style="font-size:{_font_size(b, kind) * 4:.0f}px;'
                 f'line-height:1.1;text-align:center">{e}</div>')

    elif kind == "blank":
        inner = f'<div class="p-space"></div>'

    else:  # text
        inner = f'<div class="p-t">\n\n{text}\n\n</div>'

    sty = ";".join(outer)
    return f'<div style="{sty}">\n\n{inner}\n\n</div>\n'


def _render_table(b: dict, fs: float) -> str:
    r"""表格块 → HTML table。

    数据结构：
      headers: ["类型", "角度范围"]          # 可空
      rows:    [["线线角", "$\\alpha$"], ...]
      headerBg: 表头底色，默认黄（与一数一致）

    ⚠️ **每个单元格必须多行 + 空行包裹** ——
    单行 HTML 里的 $公式$ 不会被 markdown 解析（老坑，实测踩过）。
    """
    headers = b.get("headers") or []
    rows = b.get("rows") or []
    hbg = b.get("headerBg") or "transparent"   # 默认不加底色

    def cell(v, tag: str, extra: str = "") -> str:
        t = str(v or "")
        t = convert_math(normalize_delims(fix_macros(t)))
        # 空行包裹 → markdown 才会解析单元格里的公式
        # 竖线只保留在首列（学术三线表风格）；横线由调用方通过 extra 指定
        return (f'<{tag} style="padding:4px 8px;{extra}">\n\n{t}\n\n</{tag}>')

    parts = ['<table style="border-collapse:collapse;width:100%;'
             f'font-size:{fs}px;line-height:1.6;'
             'border-top:1.5px solid #333;border-bottom:1.5px solid #333">', '']
    if headers:
        parts.append("<tr>")
        for h in headers:
            parts.append(cell(h, "th", f"background:{hbg};font-weight:700;"
                                        "text-align:center;"
                                        "border-bottom:1.5px solid #333"))
        parts.append("</tr>")
        parts.append("")
    for row in rows:
        parts.append("<tr>")
        for v in row:
            parts.append(cell(v, "td", "vertical-align:middle"))
        parts.append("</tr>")
        parts.append("")
    parts.append("</table>")
    return "\n".join(parts)


def build_canvas_pages(pages: list[dict], *, title: str, ratio: str = "16/9",
                       with_answers: bool = False,
                       title_font: str = "", body_font: str = "",
                       show_source: bool = True) -> str:
    """画布页列表 → 完整讲义 markdown。

    `pages` 结构：[{ "blocks": [ {type,x,y,w,h,...}, ... ] }, ...]
    """
    parts = [CANVAS_FRONTMATTER.format(title=title, ratio=ratio)]

    # 字体选择：注入 CSS 变量覆盖 styles/index.css 的默认值
    # （老师可在编辑器里选标题/正文字体，导出必须跟着变）
    if title_font or body_font:
        css = ["<style>", ".style-plain {"]
        if title_font:
            css.append(f"  --font-hand: {title_font};")
        if body_font:
            css.append(f"  --font-song: {body_font};")
        css.append("}")
        css.append("</style>")
        parts.append("\n".join(css) + "\n")
    for i, pg in enumerate(pages):
        blocks = pg.get("blocks", []) if isinstance(pg, dict) else []
        # 按 z 排序，保证图层顺序
        ordered = sorted(blocks, key=lambda b: int(b.get("z", 0) or 0))
        body = "".join(render_canvas_block(b, with_answers=with_answers,
                                           show_source=show_source)
                       for b in ordered)
        tpl = FIRST_PAGE if i == 0 else CANVAS_PAGE
        parts.append(tpl.format(body=body or "\n"))
    return "".join(parts)


def export_canvas(pages: list[dict], *, title: str = "", out: str = "",
                  ratio: str = "16:9", with_answers: bool = False,
                  do_compile: bool = True, retries: int = 3,
                  title_font: str = "", body_font: str = "",
                  show_source: bool = True) -> dict:
    """从画布页导出讲义（绝对定位）。"""
    import datetime as _dt

    if ratio not in RATIOS:
        return {"ok": False, "error": f"未知比例 {ratio!r}", "missing": []}
    if not pages:
        return {"ok": False, "error": "讲义是空的", "missing": []}

    if not out.strip():
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
        out = f"{title.strip() or '讲义'}_{stamp}"
    name = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", out).strip("_") or "讲义"

    if not (SLIDEV_PROJ / "node_modules" / "@slidev").exists():
        return {"ok": False, "error": f"Slidev 工程不可用：{SLIDEV_PROJ}", "missing": []}

    # ⚠️ 必须生成到工程根目录：`styles/index.css` 在根目录，
    # 放到子目录会导致自定义样式（模板类）不生效 —— 实测踩过。
    work = SLIDEV_PROJ
    md = work / f"_canvas_{name}.md"
    md.write_text(build_canvas_pages(pages, title=title or name,
                                     ratio=RATIOS[ratio],
                                     with_answers=with_answers,
                                     title_font=title_font,
                                     body_font=body_font,
                                     show_source=show_source),
                  encoding="utf-8")

    nq = sum(1 for pg in pages for b in (pg.get("blocks") or [])
             if b.get("type") == "question")
    res = {"ok": True, "name": name, "questions": nq, "missing": [],
           "tex_abs": str(md), "pdf_abs": None, "dir_abs": str(OUT_DIR),
           "saved_hint": f"{name} 讲义", "log": "", "ratio": ratio,
           "pages": len(pages)}
    if not do_compile:
        return res

    pdf = md.with_suffix(".pdf")
    env = dict(os.environ)
    if NODE_BIN.exists():
        env["PATH"] = f"{NODE_BIN}:{env.get('PATH', '')}"

    last = ""
    for attempt in range(1, retries + 1):
        if pdf.exists():
            pdf.unlink()
        timed_out, last = _run_slidev_export(md, pdf, env)
        if timed_out:
            res["ok"] = False
            res["error"] = last
            res["log"] = last
            return res
        if pdf.exists() and pdf.stat().st_size > 10_000:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            final = OUT_DIR / f"{name}.pdf"
            shutil.copy2(pdf, final)
            res["pdf_abs"] = str(final)
            res["saved_hint"] = f"{name}.pdf 已保存到 试卷/"
            return res
        if attempt < retries:
            import time
            time.sleep(3)

    log.error("Slidev 导出失败（重试 %s 次后）：%s", retries, last[:200])
    res["ok"] = False
    res["error"] = "Slidev 导出失败"
    res["log"] = last
    return res
