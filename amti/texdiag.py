r"""把 xelatex 的报错翻译成「哪道题、什么原因、怎么修」。

## 为什么要有这个模块

现在的失败路径是这样的（`amti/export.py`）：导出 PDF → xelatex 失败 →
`first_errors(log)` 挑出几行 `!` 开头的原文 → 甩给用户。用户看到的是：

    ! Undefined control sequence.
    l.4213 \cancel{x}

他知道 **第 4213 行**有问题，可卷子是程序拼出来的，**没人知道 4213 行是哪道题**。
三万个 .tex 里翻不到，只能把卷子拆小、一道道试。

这个模块做两件事，各对应上面的一半：

① **报错行 → 题目 key。** 靠 `paper.py` 在每题前面写的一行注释
   `% AMTIKU-Q: <key>`（`qid_marks=True` 时才有）。有了它，
   「4213 行」就变成「`模拟题/某校高三联考#17` 这道题」。
   这一招是跟 MathBank 学的（它的 `latex_diagnostics.py:66-73` 从
   `% MathBank-Question-ID: <id>` 一路向上找最近的标记），
   一行注释的成本，换掉"二分定位"那一串编译。

② **日志 → 结构化诊断。** 把 TeX 的黑话翻成中文 + 给修法。
   这张表不是凭空写的，条目都来自本项目**已经踩过**的坑
   （见 `amti/normalize.py` 里 1002/1014/1109 行附近那些规则的注释）：
   落单的 `$$`、可选参数里的空行、不配平的方括号、缺包……

## 边界

**只读文本，不碰题目数据。** 这里绝不改任何题目——改数据要走
`normalize.py` / `fixups.py`。诊断只负责"说清楚"。
"""
from __future__ import annotations

import re
from pathlib import Path

#: 每题前面那行注释的前缀。`paper.py` 写、这里读，**改一处就得改两处**。
QID_PREFIX = "% AMTIKU-Q: "

#: 从日志里认行号。`-file-line-error` 给的 `./t.tex:123:` 优先——
#: 它比 `l.123` 可靠：`l.NNN` 是"出错处前的上下文"行号，而且
#: 附近的宏包消息也会带 `l.` 行，容易把诊断带偏。
_FILE_LINE = re.compile(r"^(?:\./)?([^\s:]+\.(?:tex|sty|cls)):(\d+):\s*(.*)$", re.M)
_CONTEXT_LINE = re.compile(r"^l\.(\d+)\s*(.*)$", re.M)

#: 从 `! Undefined control sequence` 后面那段上下文里抠出是哪个宏。
_UNDEFINED_CMD = re.compile(r"\\([A-Za-z@]+)")


def parse_markers(tex: str) -> list[tuple[int, str]]:
    r"""把 `.tex` 里的 `% AMTIKU-Q:` 标记扫成 `[(行号, key), …]`（行号 1 起）。

    返回的顺序就是题在卷面上的顺序，所以"找 4213 行属于哪道题"
    只要取最后一个 `行号 <= 4213` 的标记。

    题目 key 里可能有空格吗？——不会。但**可能带一堆全角字符**（卷名多是中文），
    所以这里按"前缀之后整行剩余"取，不再二次切分 —— 免得哪天 key 里出现分隔符
    就把 key 截断了。
    """
    out: list[tuple[int, str]] = []
    for i, line in enumerate(tex.split("\n"), 1):
        s = line.strip()
        if s.startswith(QID_PREFIX):
            out.append((i, s[len(QID_PREFIX):].strip()))
    return out


def locate(log: str, tex: str) -> dict:
    r"""从编译日志里找出**哪道题**出的错。

    返回 `{"key", "line", "raw"}`；找不出来时 `key` 为空串——
    调用方要能把"定位不到"和"定位到空 key"分开。
    """
    markers = parse_markers(tex)
    if not markers:
        return {"key": "", "line": 0, "raw": ""}

    line_no, raw = 0, ""
    m = _FILE_LINE.search(log)
    if m and m.group(1).endswith(".tex"):
        line_no, raw = int(m.group(2)), m.group(0).strip()
    if not line_no:
        m2 = _CONTEXT_LINE.search(log)
        if m2:
            line_no, raw = int(m2.group(1)), m2.group(0).strip()
    if not line_no:
        return {"key": "", "line": 0, "raw": raw}

    key = ""
    for mk_line, mk_key in markers:      # 顺序扫，取最后一个不晚于报错行的
        if mk_line <= line_no:
            key = mk_key
        else:
            break
    return {"key": key, "line": line_no, "raw": raw}


# ── 结构化诊断 ────────────────────────────────────────────────────────
#
# 每条规则：正则 → (一句话原因, 修法, 可能缺的包)。
# 顺序有意义：**越具体的放前面**。比如 `File 'cancel.sty' not found`
# 既匹配"缺包"也匹配"找不到文件"，得先命中缺包那条。
#
# 包名那列只用于提示；本项目不自动注入 `\usepackage`（见文件头"边界"）。
_RULES: list[tuple[re.Pattern, str, str, str]] = [
    (re.compile(r"File `([^']+\.sty)' not found"),
     "缺 LaTeX 宏包：%s",
     "装这个包（TeX Live/MacTeX 里 `tlmgr install <包名>`），"
     "或把用到它的题改写成不依赖该包的写法。",
     ""),

    (re.compile(r"Undefined control sequence"),
     "用了一个 TeX 不认识的宏",
     "看日志里紧跟着的那一行（形如 `l.NNN \\宏名`）是哪个宏。"
     "常见的三种：① 库里写了个模板没定义的宏（如 `\\overparen`，"
     "KaTeX 有、amsmath 没有）；② 少 `\\usepackage`；"
     "③ 宏名拼错。**判定方法**：把这个宏单独拎出来做一个最小文档编译一次。",
     ""),

    (re.compile(r"Missing \$ inserted"),
     "数学符号跑到了数学模式外面",
     "题干里有 `_`、`^`、`\\alpha` 一类的数学记号没包在 `$…$` 里。"
     "多半是某处 `$` 不配对，把它前面一整段都挤出了数学模式。",
     ""),

    (re.compile(r"Command \\end\{question\} invalid in math mode|"
                r"invalid in math mode"),
     "数学模式没有闭合（最常见的是落单的 `$$`）",
     "`$$` 会开一个行间公式并吞掉后面所有正文，直到 `\\end{question}`。"
     "规范要求行间公式写 `\\[ … \\]`。用 `amti.py conform` 找**落单的** `$$`"
     "（那是拦验收的检查项）。",
     ""),

    (re.compile(r"Paragraph ended before \\(\w+) was complete"),
     "某个命令的可选参数里有空行",
     "TeX 扫可选参数 `[…]` 时遇到空段就停。`\\fillin[…]`／`\\paren[…]` "
     "里不能有空行——把参数里的换行改成空格即可。",
     ""),

    (re.compile(r"Runaway argument|File ended while scanning"),
     "花括号/方括号不配平，TeX 一路扫到了文件末尾",
     "从报错处往回找一个没配对的 `{` 或 `[`。不配平的方括号会让 TeX "
     "扫到文件结尾才报警——**真正的错处通常离报错行很远**。",
     ""),

    (re.compile(r"Missing \} inserted|Extra \}"),
     "花括号不配对",
     "在报错行附近找多出来或少掉的 `{` / `}`。",
     ""),

    (re.compile(r"File `([^']+)' not found"),
     "找不到引用的文件：%s",
     "题干里 `\\includegraphics` 引的图不在 `图片/` 里，或路径写错了。"
     "跑 `amti.py verify` 会列出缺失的图片引用。",
     ""),

    (re.compile(r"Environment (\w+) undefined"),
     "用了未定义的环境：%s",
     "这个 `\\begin{%s}` 所在的宏包没加载，或者名字拼错了。",
     ""),

    (re.compile(r"Dimension too large"),
     "尺寸超出 TeX 上限",
     "几乎总是 TikZ 坐标算出来的数太大（比如分母趋零）。"
     "把那张图单独拎出来编译，缩一下坐标范围。",
     ""),

    (re.compile(r"TeX capacity exceeded"),
     "超出 TeX 的容量上限",
     "常见于递归宏展开或超深嵌套。看日志里 `TeX capacity exceeded, sorry "
     "[<哪种容量>]` 方括号里的类型再对症处理。",
     ""),

    (re.compile(r"LaTeX Warning: Reference|There were undefined references"),
     "交叉引用没对上",
     "多编译一遍就好（本项目编译两遍正是为此）。若两遍仍报，"
     "说明 `\\label`/`\\ref` 写错了。",
     ""),

    (re.compile(r"Overfull \\hbox"),
     "排版溢出（不是错误，是警告）",
     "内容超出版心宽度。**一般可以不管**；成片出现才需要查是不是"
     "某道题里有超长公式。",
     ""),
]

_PKG_HINTS = {
    r"\cancel": "cancel", r"\xlongequal": "extarrows", r"\ce": "mhchem",
    r"\wideparen": "yhmath", r"\overparen": "amsmath", r"\sfrac": "xfrac",
    r"\ang": "siunitx", r"\SI": "siunitx", r"\bm": "bm",
    r"\adjustbox": "adjustbox", r"\diagbox": "diagbox",
}


def diagnose(log: str) -> dict:
    r"""日志 → 结构化中文诊断。

    返回 `{summary, cause, fix, package, command, raw}`；
    `raw` 永远是**原始那行**——翻译错了也不能把原文弄丢，
    否则用户连自己搜都没得搜。
    """
    raw = _first_error_line(log)
    text = raw or (log[-400:] if log else "")

    package = ""
    m = re.search(r"File `([^']+\.sty)' not found", log or "")
    if m:
        package = m.group(1).removesuffix(".sty")

    command = ""
    # ⚠️ 必须**在整份日志里**找宏名，不能只看 `raw` 那一行。
    # `_first_error_line()` 优先返回的是 `l.NNN \宏名` 那行上下文，
    # 里面**不含** "Undefined control sequence" 这句话 —— 拿 raw 去判就永远
    # 取不到宏名（我第一版就是这么写的，自检立刻报出来）。
    mu = re.search(r"Undefined control sequence[\s\S]{0,400}?\\([A-Za-z@]+)", log or "")
    if mu:
        command = "\\" + mu.group(1)
    if command in _PKG_HINTS:
        package = package or _PKG_HINTS[command]

    for pat, cause, fix, _ in _RULES:
        mm = pat.search(text) or pat.search(log or "")
        if not mm:
            continue
        # %s 补位：缺包名 / 环境名。给不出来的就退回原文，不留空占位符。
        fills = [g for g in mm.groups() if g]
        cause_s = _fill(cause, fills)
        fix_s = _fill(fix, fills)
        return {"summary": _SUMMARY.get(pat.pattern[:24], cause_s.split("：")[0]),
                "cause": cause_s, "fix": fix_s,
                "package": package, "command": command, "raw": raw}

    if not (log or "").strip():
        return {"summary": "编译失败，但 LaTeX 没有任何输出",
                "cause": "引擎可能压根没跑起来（没装 xelatex / 路径不对）",
                "fix": "确认 `xelatex --version` 能跑；`which xelatex` 有输出。",
                "package": "", "command": "", "raw": raw}

    return {"summary": "编译失败",
            "cause": "日志里没有命中已知的错误模式",
            "fix": "看原始日志。若反复出现，把那一行加进 `amti/texdiag.py` 的规则表。",
            "package": package, "command": command, "raw": raw}


_SUMMARY = {
    "File `([^']+\\.sty)' not": "缺宏包",
    "Undefined control sequen": "未定义的宏",
    "Missing \\$ inserted": "数学符号跑到数学模式外",
    "Command \\\\end\\{question": "数学模式没闭合（落单的 $$）",
    "Paragraph ended before ": "可选参数里有空行",
    "Runaway argument|File e": "括号不配平",
    "Missing \\} inserted|Ext": "花括号不配对",
    "File `([^']+)' not foun": "找不到引用的文件",
    "Environment (\\w+) undef": "环境未定义",
    "Dimension too large": "尺寸超上限",
    "TeX capacity exceeded": "超出 TeX 容量",
    "LaTeX Warning: Reference": "交叉引用没对上",
    "Overfull \\\\hbox": "排版溢出（警告）",
}


def _fill(template: str, fills: list[str]) -> str:
    """把模板里的 `%s` 依次填上；不够就原样留着（不填空占位）。"""
    out = template
    for f in fills:
        if "%s" not in out:
            break
        out = out.replace("%s", f, 1)
    return out


def _first_error_line(log: str) -> str:
    r"""挑出**第一条**真正的报错行。

    优先 `-file-line-error` 的 `文件:行号:` 格式：宏包自己也会打 `!`，
    先到的那条常常是"附近某个宏包的消息"，不是病因
    （MathBank 的注释里也记了这个坑）。
    """
    m = _FILE_LINE.search(log or "")
    if m:
        return m.group(0).strip()
    m2 = _CONTEXT_LINE.search(log or "")
    if m2:
        return m2.group(0).strip()
    for line in (log or "").split("\n"):
        if line.startswith("!"):
            return line.strip()
    return ""


def explain(log: str, tex: str = "") -> str:
    r"""给用户看的一句话：**哪道题 + 什么原因 + 怎么修**。

    `tex` 传进来才会做题目定位；不传就只说原因。
    """
    d = diagnose(log)
    where = ""
    if tex:
        loc = locate(log, tex)
        if loc["key"]:
            where = "题目 `%s`（第 %d 行）：" % (loc["key"], loc["line"])
        elif loc["line"]:
            where = "第 %d 行附近：" % loc["line"]
    parts = ["%s%s" % (where, d["summary"])]
    if d["cause"] and d["cause"] != d["summary"]:
        parts.append("原因：%s" % d["cause"])
    if d["command"]:
        parts.append("涉及命令：`%s`" % d["command"])
    if d["package"]:
        parts.append("可能缺包：`%s`" % d["package"])
    if d["fix"]:
        parts.append("修法：%s" % d["fix"])
    if d["raw"]:
        parts.append("原始报错：%s" % d["raw"])
    return "\n".join(parts)


# ── 自检 ──────────────────────────────────────────────────────────────
#
# 规矩和 `conform.py` 一样：**先证明它管用**。
# 每条规则都要有一个"必须抓到的坏日志"，定位也要有"必须认对"的样本。

def _selftest() -> int:
    print("texdiag 自检")
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print("  %s %s%s" % ("✓" if cond else "✗", name,
                             "" if cond else "  ← " + str(extra)))
        if not cond:
            fails += 1

    # ① 标记扫描
    tex = "\n".join([
        r"\documentclass{exam-zh}",
        "% AMTIKU-Q: 高考真题汇编/2026/全国I卷#15",   # 普通 key
        r"\begin{question}",
        "题干 $x$",
        r"\end{question}",
        "% AMTIKU-Q: 模拟题/某省A9协作体2026届高三（上）返校联考#2",  # 全角+括号
        r"\begin{question}",
        r"坏宏 \cancel{x}",
        r"\end{question}",
    ])
    mk = parse_markers(tex)
    check("扫到 2 个标记", len(mk) == 2, mk)
    check("行号正确", mk[0][0] == 2 and mk[1][0] == 6, mk)

    # ② 定位：`-file-line-error` 格式，报错在第 8 行 → 属于第二道题
    log_fl = "./t.tex:8: Undefined control sequence.\nl.8 \\cancel"
    loc = locate(log_fl, tex)
    check("定位到第二道题", loc["key"].endswith("联考#2"), loc)
    check("报错行号 = 8", loc["line"] == 8, loc)

    # ③ 定位：只有 `l.NNN` 的旧格式也要认
    log_l = "! Undefined control sequence.\nl.8 \\cancel"
    check("旧格式也能定位", locate(log_l, tex)["key"].endswith("联考#2"),
          locate(log_l, tex))

    # ④ 定位：报错在第一个标记之前 → key 为空，但要给出行号
    loc0 = locate("./t.tex:1: Emergency stop.", tex)
    check("标记之前报错不硬套", loc0["key"] == "" and loc0["line"] == 1, loc0)

    # ⑤ 没有标记时不能崩
    check("无标记不崩", locate(log_fl, "")["key"] == "")

    # ⑥ 各条诊断规则
    cases = [
        ("! LaTeX Error: File `cancel.sty' not found.", "cancel"),
        ("! Undefined control sequence.\nl.8 \\wideparen{AB}", "yhmath"),
        ("! Missing $ inserted.", ""),
        ("! Command \\end{question} invalid in math mode.", ""),
        ("! Paragraph ended before \\fillin was complete.", ""),
        ("! Runaway argument?", ""),
        ("! Dimension too large.", ""),
        ("! File `nope.png' not found.", ""),
    ]
    for log, want_pkg in cases:
        d = diagnose(log)
        ok = d["summary"] != "编译失败" and d["raw"]
        if want_pkg:
            ok = ok and d["package"] == want_pkg
        check("诊断 %-42s" % log.strip().split("\n")[0][:42], ok, d)

    # ⑦ 空日志（引擎没跑起来）要有专门的话
    d = diagnose("")
    check("空日志有专门提示", "没有任何输出" in d["summary"], d)

    # ⑧ explain 串起来
    s = explain(log_fl, tex)
    check("explain 同时给题号与原因",
          "联考#2" in s and "修法" in s, s)

    # ⑨ 一条规则都不命中时不能假装知道
    d = diagnose("! 某种没见过的新错误")
    check("未知错误不瞎猜", d["summary"] == "编译失败" and d["raw"], d)

    print("texdiag 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys as _s
    if "--selftest" in _s.argv:
        raise SystemExit(_selftest())
    raise SystemExit(0)
