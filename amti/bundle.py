#!/usr/bin/env python3
r"""合订本 → 按套拆开（**多套卷装进一个 PDF** 的唯一处理办法）。

## 为什么要拆，而不是"把文档切块喂模型"

上下文不够时，最直觉的做法是把正文按页数切成几块、逐个喂给 27B。这条路
**会静默出错**，所以不能走：

* `assemble()` 拿**题号**当主键（`ans_by_n[题号]`，一套卷就是 1–19）；
* `rec_to_question()` 的入库键是 `模拟题/<label>#<题号>`。

十一套卷合订在一起，就有十一个"第 1 题"。按 40 页一刀切，第 5 题的答案会
配上第 5 套卷的解析，而且**一个字都不会报错**——比"装不下"严重得多。

所以切分的单位只能是**一套卷**：目录怎么说，就怎么切。切完每套都是普通的
一份卷，后面 OCR → 结构化 → 配对 → 入库那条路一行都不用改。

## 目录从哪来

只认 **PDF 自带的文字层**（这类合订本是生成的，目录是嵌进去的文字），
不依赖 OCR：建任务的时候还没扫，等扫完再拆就晚了 40 分钟。

实测两种版式都要认：

    汇编：第一套试卷………………2        ← 名字和页码同一行
    答案：第一套答案……………………      ← 页码被排版拆成单独一列，
          第二套答案……………………         文末再给一串 "2 23 39 …"
          …
          1 2 23 39 60 83 …

没有目录、目录读不出、页数对不上 → **返回空列表**，调用方按单份卷走原路，
行为跟加这个模块之前一模一样。
"""
from __future__ import annotations

import re
from pathlib import Path

#: 目录一条：`第三套补充………………23`（"补充"是第三套的加卷，仍算试卷）
ENTRY = re.compile(r"第\s*([一二三四五六七八九十]+)\s*套\s*(试卷|答案|补充)?")
#: 页码（不把 `2.5` 这种小数和 `1.2.3` 这种考点号当页码）
NUM = re.compile(r"(?<![\d.])(\d{1,4})(?![\d.])")
_DIGIT = "零一二三四五六七八九"
#: 一套卷 1–60 页；超出就是目录错位了，宁可不拆
MAX_PAGES = 60


def cn_num(s: str) -> int:
    r"""`十一` → 11，`三` → 3（这套卷的目录只用到 1–20，不搞大数）。"""
    if s == "十":
        return 10
    if "十" in s:
        a, _, b = s.partition("十")
        return (int(_DIGIT.index(a)) if a else 1) * 10 + (
            int(_DIGIT.index(b)) if b else 0)
    return int(_DIGIT.index(s))


def parse_toc(text: str, pages: int) -> list[dict]:
    r"""目录文字 + 总页数 → `[{no,name,kind,start,end}]`；读不出就返回 `[]`。

    `kind`：`试卷` / `答案`（`补充` 归试卷）。
    """
    hits = list(ENTRY.finditer(text or ""))
    if len(hits) < 2:
        return []
    # 两页目录会重复列举同一套：同名的后一条不要
    uniq, seen = [], set()
    for m in hits:
        name = "第%s套" % m.group(1) + ("补充" if m.group(2) == "补充" else "")
        if name in seen:
            continue
        seen.add(name)
        uniq.append((name, m))
    if len(uniq) < 2:
        return []

    # ① 一行一条：名字后面紧跟页码
    starts = []
    for _name, m in uniq:
        n = NUM.search(text[m.end():m.end() + 40])
        if not n:
            starts = []
            break
        starts.append(int(n.group(1)))
    # ② 页码被排版拆到另外一列：取文末最后 N 个数字（前面可能有页脚"1"）
    if not starts:
        nums = [int(x) for x in NUM.findall(text)]
        if len(nums) < len(uniq):
            return []
        starts = nums[-len(uniq):]

    if not (len(starts) == len(uniq) and all(
            1 <= s <= pages for s in starts)
            and all(b > a for a, b in zip(starts, starts[1:]))):
        return []
    secs = []
    for i, (name, m) in enumerate(uniq):
        end = starts[i + 1] - 1 if i + 1 < len(starts) else pages
        if not (1 <= end - starts[i] + 1 <= MAX_PAGES):
            return []
        secs.append({"no": cn_num(m.group(1)), "name": name,
                     "kind": "答案" if m.group(2) == "答案" else "试卷",
                     "start": starts[i], "end": end})
    return secs


def book_kind(secs: list[dict]) -> str:
    r"""整本算试卷还是答案 —— **按多数**，不是看第一条。

    `第三套补充` 这种加卷没有「答案」两个字，按单条判会把整本答案册判成
    试卷（实测：11 条答案 + 1 条补充）。
    """
    if not secs:
        return ""
    ans = sum(1 for s in secs if s["kind"] == "答案")
    return "答案" if ans * 2 > len(secs) else "试卷"


def sections_of(pdf: Path) -> list[dict]:
    r"""PDF 的目录 → 套；没有文字层 / 不是合订本 → `[]`。

    **只认命中最多的那一页**，不能把前两页拼起来：答案册的目录后面紧跟
    一张「1 2 3 4 …」的答案速查表，拼进来会把页码抽成一堆个位数
    （实测：`NUM.findall` 抽出 80 多个数字，切出来的页范围全是错的）。
    """
    try:
        import fitz                                  # 重依赖，用到才导
    except Exception:                                # noqa: BLE001
        return []
    try:
        with fitz.open(pdf) as doc:
            pages = doc.page_count
            best, best_hits = "", 0
            for i in range(min(3, pages)):
                t = doc[i].get_text()
                h = len(ENTRY.findall(t))
                if h > best_hits:
                    best, best_hits = t, h
    except Exception:                                # noqa: BLE001
        return []
    if best_hits < 2:
        return []
    return parse_toc(best, pages)


def _safe(s: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fa5]+", "_", s).strip("_") or "卷"


def split_pdf(pdf: Path, secs: list[dict], out_dir: Path) -> list[Path]:
    r"""按页范围切出 N 个 PDF（保留原有页面内容，图片/公式都不重排）。"""
    import fitz
    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    with fitz.open(pdf) as src:
        for s in secs:
            one = fitz.open()
            one.insert_pdf(src, from_page=s["start"] - 1, to_page=s["end"] - 1)
            dst = out_dir / ("%s-%s.pdf" % (_safe(pdf.stem), _safe(s["name"])))
            one.save(dst)
            one.close()
            made.append(dst)
    return made


def make(pdf: Path, answers: Path | None = None) -> list[dict]:
    r"""合订本 → 切好的 `[{paper, answers, name}]`；不是合订本就 `[]`。

    会**照目录落盘**（`<上传目录>/拆卷/<卷名>/…-第X套.pdf`），调用方拿路径建任务。

    配对规则：**按套的序号一一对应**（第十一套试卷 ↔ 第十一套答案）。
    两份都拆且套数一致才配；只拆出一边就只建题目卷的任务。

    还会认一种常见的选反：`pdf` 全是"答案"、`answers` 全是"试卷"——
    这时自动对调，照错顺序传进来的也能用。
    """
    secs = sections_of(pdf)
    if len(secs) < 2:
        return []
    secs_a: list[dict] = []
    if answers is not None:
        secs_a = sections_of(answers)
        if len(secs_a) != len(secs):
            secs_a = []

    # 选反了：第一个是答案册、第二个才是试卷
    if not secs_a and answers is not None and book_kind(secs) == "答案":
        other = sections_of(answers)
        if other and len(other) >= 2 and book_kind(other) == "试卷":
            pdf, answers, secs = answers, pdf, other
            secs_a = sections_of(answers)
            if len(secs_a) != len(secs):
                secs_a = []
    elif secs_a and book_kind(secs) == "答案" and book_kind(secs_a) == "试卷":
        pdf, answers = answers, pdf
        secs, secs_a = secs_a, secs

    # 全是答案册：当试卷录进来只会得到一堆没有题干的"解答"
    if book_kind(secs) == "答案":
        raise ValueError("这份 PDF 的目录里全是「答案」（是答案册），"
                         "请把试卷放第一个、答案卷放第二个")

    out_dir = pdf.parent / "拆卷" / _safe(pdf.stem)
    papers = split_pdf(pdf, secs, out_dir)
    ans_files: list[Path] = []
    if secs_a:
        a_dir = pdf.parent / "拆卷" / _safe(answers.stem)
        ans_files = split_pdf(answers, secs_a, a_dir)
    return [{"paper": p, "answers": ans_files[i] if ans_files else None,
             "name": s["name"]}
            for i, (p, s) in enumerate(zip(papers, secs))]


# ── 自检 ────────────────────────────────────────────────────────────
def _selftest() -> int:
    fails = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("bundle 自检")

    # 版式①：一行一条（汇编）
    toc1 = ("    目录\n 第一套试卷………………2\n  第二套试卷………………8 \n"
            " 第三套试卷………………15 \n 第三套补充………………23 \n"
            " 第四套试卷………………32 \n 第五套试卷………………39 \n"
            " 第六套试卷………………46 \n 第七套试卷………………54 \n"
            " 第八套试卷………………62 \n 第九套试卷………………70 \n"
            " 第十套试卷………………85\n 第十一套试卷………………92\n1\n")
    s1 = parse_toc(toc1, 99)
    check("一行一条：切出 12 套", len(s1) == 12, str(len(s1)))
    check("第一套 2–7 页", s1 and (s1[0]["start"], s1[0]["end"]) == (2, 7), str(s1[:1]))
    check("第三套补充单算一套", s1 and s1[3]["name"] == "第三套补充", str(s1[3:4]))
    check("第十一套到卷尾", s1 and (s1[-1]["start"], s1[-1]["end"]) == (92, 99),
          str(s1[-1:]))
    check("页范围首尾相接、不重不漏",
          all(s1[i]["end"] + 1 == s1[i + 1]["start"] for i in range(len(s1) - 1)))

    # 版式②：页码被拆到单独一列，前面还有个页脚"1"（答案册）
    toc2 = ("目录\n第一套答案…………………………\n第二套答案…………………………\n"
            "第三套答案…………………………\n第三套补充…………………………\n"
            "第四套答案…………………………\n第五套答案…………………………\n"
            "第六套答案…………………………\n第七套答案…………………………\n"
            "第八套答案…………………………\n第九套答案…………………………\n"
            "第十套答案…………………………\n第十一套答案……………………\n"
            "1\n2\n23\n39\n60\n83\n101\n120\n142\n169\n193\n223\n243\n")
    s2 = parse_toc(toc2, 260)
    check("页码独立成列：切出 12 套", len(s2) == 12, str(len(s2)))
    check("页脚那个 1 不算页码", s2 and s2[0]["start"] == 2, str(s2[:1]))
    check("最后一套到 260 页", s2 and s2[-1]["end"] == 260, str(s2[-1:]))
    check("答案册认得出来（含「第三套补充」也要算答案册）",
          book_kind(s2) == "答案", book_kind(s2))
    check("汇编认得出来是试卷", book_kind(s1) == "试卷", book_kind(s1))

    # 单份卷：没有目录，**什么都不做**
    check("没有目录 → 不拆", parse_toc("一、选择题：本题共 8 小题\n1. 已知…", 12) == [])
    # 目录错位：页数不够 / 不递增 → 不拆（宁可回到单份卷，也不切歪）
    check("页码越界 → 不拆", parse_toc(toc1, 40) == [])
    bad = "第一套试卷……9\n第二套试卷……3\n"
    check("页码倒序 → 不拆", parse_toc(bad, 99) == [])
    check("一套卷 80 页（不像目录）→ 不拆", parse_toc(bad, 99) == [])
    # 中文数字
    check("十 → 10", cn_num("十") == 10)
    check("十一 → 11", cn_num("十一") == 11)
    check("三 → 3", cn_num("三") == 3)

    print("bundle 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    for p in sys.argv[1:]:
        secs = sections_of(Path(p))
        print("%s：%d 页" % (p, __import__("fitz").open(p).page_count))
        for s in secs:
            print("  %-8s %-6s %3d–%-3d" % (s["name"], s["kind"],
                                            s["start"], s["end"]))
