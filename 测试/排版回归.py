"""排版金样回归：**排版改了，卷子还能不能看**。

`accept` 层③ 只查"文本层有没有泄漏、图片能不能取"，查不出排版变丑/变坏。
这个脚本拿一批**排版最刁钻**的题真编 PDF，钉住几个几何指标：

  · 有没有题被拆到两页（跨页修复循环应当把它清零）
  · 有没有 Overfull（一行/一张表冲出纸面）
  · 讲义"一题一页"是不是真的每题一页
  · 页数别离谱地涨（图缩小/重排把题挤散会体现成页数变多）

指标不追死数字，只卡"明显坏了"的阈值——参数微调不该动它，
但"四图选项又缩成 20pt""一题裂成两页"这类回归会红。

用法：

    python3 测试/排版回归.py          # 没有 pytest 也能跑
    pytest 测试/排版回归.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import export, layout, pdfcheck, store   # noqa: E402

# 排版最难的几种题：四图选项、超长题干、带图解答题、填空
SAMPLES = [
    "高考真题汇编/2010/广东卷（理）#6",          # 四张 TikZ 正视图选项
    "高考真题汇编/2026/上海卷（春）#15",          # 四张图选项 + 长题干
    "高考真题汇编/2024/全国甲卷（文）#8",         # 四张图选项（另一种比例）
    "高考真题汇编/2009/新课标卷（文）#19",        # 一万字的解答题
    "高考真题汇编/2019/全国III卷（文）#17",       # 六千字的解答题
    "高考真题汇编/2011/浙江卷（文）#13",          # 长填空
]


def _pick(keys: list[str]) -> list:
    out, missing = [], []
    for k in keys:
        q = store.find(k)
        (out if q else missing).append(q or k)
    if missing:
        print("  ⚠ 这些题不在库里（跳过）：%s" % "、".join(map(str, missing[:3])))
    return out


def _clean(r: dict) -> None:
    """删掉这次回归产生的预览文件（不进用户资料夹，也不堆在 数据/预览）。"""
    for key in ("tex_abs", "pdf_abs"):
        p = r.get(key)
        if not p:
            continue
        for ext in (".tex", ".aux", ".log", ".pdf", ".out"):
            try:
                Path(str(p)).with_suffix(ext).unlink(missing_ok=True)
            except OSError:
                pass


def _report(tag: str, r: dict) -> int:
    """打印一条导出结果，返回失败项数（0 = 好）。"""
    if not r.get("ok"):
        print("  ✗ %s 编译失败：%s" % (tag, (r.get("log") or "")[:200]))
        return 1
    lay = r.get("layout") or {}
    # 0.1cm 以下（< layout.OVERFULL_PT）的溢出纸上看不出来，不算排版问题
    over = [o for o in (r.get("overfull") or []) if o["pt"] >= layout.OVERFULL_PT]
    pages = r.get("pages")
    print("  · %s：%s 页，重排 %s 遍，溢出 %d 处%s"
          % (tag, pages, lay.get("passes"), len(over),
             "，降级" if lay.get("tight") else ""))
    bad = 0
    if lay.get("passes", 0) > 3:
        print("  ✗ 重排超过 3 遍（循环没收敛）")
        bad += 1
    if over:
        worst = over[0]
        print("  ✗ %d 处 Overfull，最宽 %.1fpt（%s）"
              % (len(over), worst["pt"], worst.get("key") or "?"))
        bad += 1
    return bad


def test_paper_layout():
    qs = _pick(SAMPLES)
    assert qs, "样例题都不在库里"
    r = export.export([q.key for q in qs], title="排版回归·卷面", out="排版回归_卷面",
                      mode="test", preview=True)
    bad = _report("卷面", r)
    lay = r.get("layout") or {}
    _clean_after = r          # 断言失败也要清（放在 finally 里太绕，统一在函数末尾清）
    still = lay.get("still_split") or []
    # 超过一页的题允许存在，但必须被如实报出来（不然就是"静默裂题"）
    if still and not any("超过一页" in w for w in (r.get("warnings") or [])):
        print("  ✗ 有题跨页却没报出来：%s" % still[:2])
        bad += 1
    spans = pdfcheck.question_spans(Path(r["tex_abs"]))
    split = [i for i, (a, b) in spans.items() if a != b]
    # 比一页还高的题（题库里个别"一整段粘成一道题"的脏数据）**允许跨页**，
    # 但必须在 `still_split` 里如实报出来——不允许"静默裂题"。
    from amti import paper
    order = paper.question_order(qs)
    ok_split = {i for i, q in enumerate(order, 1) if q.key in set(still)}
    unexpected = [i for i in split if i not in ok_split]
    if unexpected:
        print("  ✗ 还有 %d 道题被静默拆页：%s" % (len(unexpected), unexpected[:5]))
        bad += 1
    if split and still:
        print("  · 超一页的题（已报告）：%d 道" % len(still))
    pages = r.get("pages") or 0
    if pages > 2 + 2 * len(qs):
        print("  ✗ 页数异常（%d 页 / %d 题）" % (pages, len(qs)))
        bad += 1
    _clean(r)
    assert bad == 0, "卷面排版回归失败 %d 项" % bad


def test_handout_one_question_one_page():
    qs = _pick(SAMPLES[:2])
    assert qs, "样例题都不在库里"
    r = export.export([q.key for q in qs], title="排版回归·讲义", out="排版回归_讲义",
                      mode="handout", preview=True)
    bad = _report("讲义", r)
    if r.get("pages") != len(qs):
        print("  ✗ 一题一页没做到：%d 题 %s 页" % (len(qs), r.get("pages")))
        bad += 1
    _clean(r)
    assert bad == 0, "讲义排版回归失败 %d 项" % bad


def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    bad = 0
    print("排版回归（%d 项）" % len(tests))
    for name, fn in tests:
        try:
            fn()
            print("  ✓ %s" % name)
        except AssertionError as e:
            bad += 1
            print("  ✗ %s: %s" % (name, e))
        except Exception as e:                       # noqa: BLE001
            bad += 1
            print("  💥 %s: %s: %s" % (name, type(e).__name__, e))
    print("排版回归 %s" % ("通过" if not bad else "失败 %d 项" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
