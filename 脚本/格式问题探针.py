r"""全库格式探针 —— 扫 `conform` 16 项管不到的形态。

每个探针只报「可疑」，不改数据。逐条由人（大模型）读过再定性。

    python3 脚本/格式问题探针.py          # 只看汇总
    python3 脚本/格式问题探针.py 页眉      # 看某一族的明细
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amti import store

# ── 文本层脏字符 ────────────────────────────────────────────
CRLF = re.compile(r"\r")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
NBSP = re.compile("[\u00a0\u2000-\u200a\u202f\u205f\u3000]")
ZW = re.compile("[\u200b-\u200f\u2060-\u206f\ufeff\u180e]")
REPL = re.compile("[\ufffd\u25a1]|<unk>")

# ── 卷面残留（规范 §3：不带分值、页眉页脚） ──────────────────
PAGE_HEAD = re.compile(
    r"第\s*\d+\s*页[　 ]*共\s*\d+\s*页"
    r"|第\s*\d+\s*页\s*[/／]\s*共\s*\d+\s*页"
    r"|共\s*\d+\s*页"
    r"|绝密.{0,3}启用前"
    r"|注意事项\s*[：:]?\s*\d"
    r"|考生.{0,4}(?:须知|答题)")
SCORE = re.compile(
    r"[（(【\[]\s*(?:本题)?(?:满分|分值)?\s*\d{1,3}\s*分\s*[）)】\]]"
    r"|每题\s*\d{1,3}\s*分|共\s*\d{1,2}\s*小题|满分\s*\d{2,3}\s*分")

# ── 公式写法 ────────────────────────────────────────────────
DOLLAR_DOLLAR = re.compile(r"\$\$[\s\S]+?\$\$")
FRACTHIN = re.compile(r"\\(?:d?frac|d?tfrac)\s(?![{\\])|\\(?:d?frac|d?tfrac)(?=[0-9a-zA-Z])")
SUP_SUB_BARE = re.compile(r"(?<!\\)\^(?![_{\s]\b)[^{\s]{1,2}(?![a-zA-Z0-9])")
ARRAY_ENV = re.compile(r"\\begin\{(align|align\*|eqnarray|gather|multline|flalign|math|displaymath|itemize|description)\}")
EQNO = re.compile(r"\\(?:eqno|leqno|over)\b")
TEX_CMD = re.compile(r"\\(?:textbf|textit|emph|texttt|underline|colorbox|color|href|includegraphics\w*)\b")

# ── 解析栏里的录入元话 / 结构残留 ───────────────────────────
ANSWER_TAG = re.compile(r"【\s*(?:答案|解析|分析|解答|考点|点评|专题|难度|题号|方法|点睛)\s*】"
                        r"|\b(?:Answer|Solution|Analysis)\s*[:：]")
MARKER_LINE = re.compile(r"\bTODO\b|\bTBD\b|\bXXX\b|待补|待定|暂无解析|见原卷|略。|答案略|解析略")
LINEMARK = re.compile(r"\\n(?![a-zA-Z])|\\t(?![a-zA-Z])")
DOUBLE_PUNCT = re.compile(r"([，。；、])\1+")
UNCLOSED_TEXT = re.compile(r"\\text\{[^{}]*$")

# ── 选择题特有的坏形 ────────────────────────────────────────
TRAILING_TRUNC = ("，", ",", "、", ";", "；", "和", "与", "及", "则", "若", "设", "到", "在",
                  "了", "是", "为", "的", "地", "得", "至", "由", "以", "使", "当", "个")


def brace_delta(s: str) -> int:
    d = 0
    for ch in s.replace("\\{", "").replace("\\}", ""):
        if ch == "{":
            d += 1
        elif ch == "}":
            d -= 1
    return d


def fields(q):
    yield "stem", q.stem
    yield "answer", q.answer
    yield "solution", q.solution
    for o in q.options:
        yield "opt" + o.label, o.text


FAMILIES = [
    ("页眉页脚", PAGE_HEAD),
    ("分值", SCORE),
    ("双美元", DOLLAR_DOLLAR),
    ("控制字符", CTRL),
    ("CRLF", CRLF),
    ("奇怪空白", NBSP),
    ("零宽字符", ZW),
    ("乱码占位", REPL),
    ("答案栏标记", ANSWER_TAG),
    ("待补或注释", MARKER_LINE),
    ("字面反斜杠n", LINEMARK),
    ("意外环境", ARRAY_ENV),
    ("eqno/over", EQNO),
    ("排版宏", TEX_CMD),
    ("重复标点", DOUBLE_PUNCT),
]


def main() -> int:
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    qs = store.load_all()
    detail: dict[str, list] = defaultdict(list)

    for q in qs:
        for fld, txt in fields(q):
            if not txt:
                continue
            for name, rx in FAMILIES:
                m = rx.search(txt)
                if m:
                    detail[name].append((q.key, fld, m.group(0)[:70].replace("\n", "\\n")))
            if brace_delta(txt) != 0:
                detail["花括号不配平"].append((q.key, fld, "delta=%+d" % brace_delta(txt)))
            if txt.count("$") % 2:
                detail["美元符落单"].append((q.key, fld, "$ x%d" % txt.count("$")))
            if FRACTHIN.search(txt):
                detail["frac无花括号"].append((q.key, fld, FRACTHIN.search(txt).group(0)))
            if txt.strip().endswith(TRAILING_TRUNC):
                detail["末尾像被截断"].append((q.key, fld, "…" + txt.strip()[-16:].replace("\n", "\\n")))

    print("全库 %d 道题，探针结果：\n" % len(qs))
    order = sorted(detail.items(), key=lambda kv: -len({k for k, _f, _s in kv[1]}))
    for name, rows in order:
        print("  %-14s %4d 道 / %4d 处" % (name, len({r[0] for r in rows}), len(rows)))

    if want == "报告":
        by_key = {q.key: q for q in qs}
        out = ["# 全库格式探针报告", ""]
        for name, rows in order:
            rx = dict(FAMILIES).get(name)
            out.append("## %s（%d 道 / %d 处）" % (name, len({r[0] for r in rows}), len(rows)))
            out.append("")
            for key, fld, _snip in rows[:70]:
                txt = dict(fields(by_key[key])).get(fld, "")
                m = rx.search(txt) if rx else None
                if m:
                    a, b = max(0, m.start() - 45), min(len(txt), m.end() + 45)
                    snip = txt[a:b].replace("\n", "⏎")
                else:
                    snip = txt[-60:].replace("\n", "⏎")
                out.append("- `%s` [%s] …%s…" % (key, fld, snip))
            out.append("")
        Path("数据/格式探针报告.md").write_text("\n".join(out), encoding="utf-8")
        print("\n已写 数据/格式探针报告.md")
        return 0

    if want and want != "报告":
        for name, rows in detail.items():
            if not name.startswith(want):
                continue
            print("\n### %s（%d 处）" % (name, len(rows)))
            for key, fld, snip in rows:
                print("  %-46s %-7s %s" % (key, fld, snip))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
