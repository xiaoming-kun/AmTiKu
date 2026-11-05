r"""把探针命中的**整段原文**导出来读，一族一个文件。

    python3 脚本/格式问题细看.py          # 全部族
    python3 脚本/格式问题细看.py 栏头串入  # 只导一族

输出 数据/格式细看/<族名>.md，每道一段：题干／选项／答案／解析全文。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amti import store

OUT = Path("数据/格式细看")

# ── 族定义：名字 → (扫哪些字段的正则) ──────────────────────
# 注意都写成 (字段白名单 or None=全部, 正则)
FAMS: list[tuple[str, tuple[str, ...] | None, re.Pattern]] = [
    # 大题栏头/说明行串进了选项或题干（「二、选择题：本题共3小题，每小题6分…」）
    ("栏头串入", ("stem", "optA", "optB", "optC", "optD"),
     re.compile(r"[一二三四五六]\s*、\s*(?:单|多)?项?选择题|[填空选择解答]题[：:].{0,12}(?:本题|每小题)"
                r"|本大题共\s*\d+\s*小题|每小题\s*\d+\s*分[，,]")),
    # 一整张答案对照表被塞进某一道题的解析里
    ("答案表泄漏", ("solution",),
     re.compile(r"题号\s*\d+\s*\d+|答案\s*[A-D]\s+[A-D]\s+[A-D]|\d{1,2}\s*【答案】.*\d{1,2}\s*【答案】")),
    # 广告、群号、水印、扫描 App、机构署名
    ("广告水印", None,
     re.compile(r"QQ\s*(?:教师|学生)?群|群[号[:：]]\s*\d{6,}|扫描\s*App|亿人都在用|学科网|zxxk"
                r"|公众号|资源来自|版权所有|青云解析|师曰|命题人|审题人|\b\d{4}[A-Z]\b")),
    # 页眉页脚：第 X 页（共 Y 页）
    ("页眉页脚", None,
     re.compile(r"第\s*\d+\s*页[,，. ]*(?:共|[/／])\s*\d+\s*页|共\s*\d+\s*页[）)]|第\s*\d+\s*页\s*[（(]"
                r"|\[\s*共\s*\d+\s*页\s*\]|【第\s*\d+\s*页】|参考答案.{0,12}第\s*\d+\s*页")),
    # 分值：（13分）／……13分／本小题满分
    ("分值", None,
     re.compile(r"[（(]\s*(?:本题)?(?:满分|分值)?\s*\d{1,3}\s*分\s*[）)]|本小题满分\s*\d+\s*分"
                r"|满分\s*\d{2,3}\s*分|…+\s*\d{1,3}\s*分|\d{1,3}\s*分\s*$")),
    # 解析开头的【答案】／【解析】／【解析一】等标记
    ("答案栏标记", ("solution",),
     re.compile(r"^\s*【\s*(?:答案|解析|分析|解答|解析一|解析二|方法|点睛|考点|点评)\s*】")),
    # 大模型自己的复核话术混进了正文
    ("元话入正文", None,
     re.compile(r"本轮|复核|在全库检索|命中\s*\d+\s*处|同型栏头|待复核|已登记|口径[:：]|"
                r"原卷[:：]|答案册[:：]|取页|成品\.json|队列|逐字比对")),
    # 占位/省略式解析（违反「解析必须完整」）
    ("省略式解析", ("solution",),
     re.compile(r"【解析略】|解析略|答案略|略。|（?过程略）?|见原卷|待补")),
    # 乱码方块
    ("乱码方块", None, re.compile("[□■]")),
    # 重复标点
    ("重复标点", None, re.compile(r"([，。；、])\1+")),
    # $$…$$
    ("双美元", None, re.compile(r"\$\$")),
    # align*/gather 等库里不该出现的环境
    ("意外环境", None, re.compile(r"\\begin\{(align|align\*|gather|multline|flalign|math|itemize)\}")),
    # \over 老式写法
    ("over写法", None, re.compile(r"\\over(?![a-zA-Z])")),
    # 行间式没被 \[ \] 包住（裸公式段）
    ("裸行间式", None, re.compile(r"^\s*\\\[", re.M)),
]


def fields(q):
    yield "stem", q.stem
    yield "answer", q.answer
    yield "solution", q.solution
    for o in q.options:
        yield "opt" + o.label, o.text


def dump(name, only_fields, rx, qs) -> int:
    hits = []
    for q in qs:
        for fld, txt in fields(q):
            if only_fields and fld not in only_fields:
                continue
            if txt and rx.search(txt):
                hits.append(q)
                break
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / ("%s.md" % name)
    lines = ["# %s（%d 道）" % (name, len(hits)), ""]
    for q in hits:
        lines.append("## `%s`" % q.key)
        lines.append("*type=%s · answer=%s*" % (q.type, q.answer))
        lines.append("")
        lines.append("题干：\n```\n%s\n```" % q.stem)
        if q.options:
            lines.append("选项：\n```\n%s\n```" %
                         "\n".join("%s. %s" % (o.label, o.text) for o in q.options))
        lines.append("解析：\n```\n%s\n```" % (q.solution or "（空）"))
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    print("%-10s %4d 道 → %s" % (name, len(hits), p))
    return len(hits)


def main() -> int:
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    qs = store.load_all()
    print("全库 %d 道\n" % len(qs))
    for name, only, rx in FAMS:
        if want and not name.startswith(want):
            continue
        dump(name, only, rx, qs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
