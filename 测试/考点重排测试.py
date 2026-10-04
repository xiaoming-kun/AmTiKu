"""按考点重排的讲义（amti/pointbook.py）单元测试。

覆盖三件最容易悄悄坏掉的事：

1. **难度三级信号的优先级**——题自带 > 同卷位置 > 考点星级。优先级反了，
   人工订过的难度会被位置推定盖掉；「同卷位置」如果给小分组（教辅的章节）
   也算，就会把「第 3 题」当成「简单题」。
2. **选题账要能对上**——每档不超配额、缺口=配额-实取、一题不在两个考点重复，
   以及最硬的一条：**生成物里印出来的题数 == 选题数**（少印/多印都算失败）。
3. **渲染期的三道修不许越界**——`\fillin[…=[4,5]$]` 的 `]`、正文里的 `_____`、
   染红时的 `}`，都只在**出题**时改；写回题库的路径（`store.render_question`）
   必须一个字都不动（历史上「渲染期改动当数据」污染过 236 道）。

用法：

    python3 测试/考点重排测试.py        # 不需要 pytest
    pytest 测试/考点重排测试.py -q
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import klist, knowledge, paper, pointbook, store      # noqa: E402


# ── 一、难度信号 ──────────────────────────────────────────────

def test_own_difficulty_wins():
    """题自带 `meta.difficulty` 必须压过位置与星级。"""
    q = next(q for q in store.load_cached()
             if (q.meta.get("difficulty") or "").strip()
             and q.difficulty != knowledge.difficulty_of(q.points[0]))
    sels = pointbook.select_all()
    assert _signal_of(sels, q)[1] == pointbook.SRC_OWN, f"{q.key} 依据判错了"


def test_position_only_for_real_papers():
    """少于 MIN_PAPER 道的那一组（多半是教辅章节）不许按位置定难度。"""
    from collections import Counter
    sizes = Counter()
    for q in store.load_cached():
        m = pointbook._KEY_NO.match(q.key or "")
        if m:
            sizes[m.group("paper")] += 1
    pos = pointbook.position_map(store.load_cached())
    small = {q.key for q in store.load_cached()
             if (m := pointbook._KEY_NO.match(q.key or ""))
             and sizes[m.group("paper")] < pointbook.MIN_PAPER}
    keyed = {k.split("|")[0] for k in pos}
    assert not (keyed & small), "小分组里的题被按位置推了难度"


def test_position_signal_uses_paper_layout_rule():
    """位置信号必须出自 `paper.position_difficulty`（与组卷同一把尺）。"""
    pos = pointbook.position_map(store.load_cached())
    assert pos and set(pos.values()) <= {"简单题", "中档题", "难题"}


_POS: dict[str, str] | None = None


def _posmap() -> dict[str, str]:
    global _POS
    if _POS is None:
        _POS = pointbook.position_map(store.load_cached())
    return _POS


def _signal_of(sels, q):
    """在这份选题结果里找这道题，返回 (难度档, 依据)。"""
    for k, qs in sels[q.points[0]].taken.items():
        for one in qs:
            if one.key != q.key:
                continue
            if (one.meta.get("difficulty") or "").strip():
                return k, pointbook.SRC_OWN
            if pointbook._idof(one) in _posmap():
                return k, pointbook.SRC_POS
            return k, pointbook.SRC_POINT
    return None, None


# ── 二、选题账 ────────────────────────────────────────────────

def test_quota_and_shortfall():
    sels = pointbook.select_all()
    for pid, s in sels.items():
        for k in pointbook.ORDER:
            assert len(s.taken[k]) <= pointbook.QUOTA[k], f"{pid} {k} 超配额"
            assert s.short[k] == max(0, pointbook.QUOTA[k] - len(s.taken[k])), pid
            assert s.stock[k] >= len(s.taken[k]), pid


def test_no_duplicate_within_bucket():
    sels = pointbook.select_all()
    for pid, s in sels.items():
        for k, qs in s.taken.items():
            hs = {q.content_hash() for q in qs}
            assert len(hs) == len(qs), f"{pid} {k} 有重复题"


def test_one_question_one_point():
    """一题只归主考点：不许同一道题出现在两个考点里（用户选的口径）。"""
    sels = pointbook.select_all()
    seen: dict[str, str] = {}
    for pid, s in sels.items():
        for qs in s.taken.values():
            for q in qs:
                h = q.content_hash()
                assert h not in seen, f"{q.key} 同时出现在 {seen.get(h)} 与 {pid}"
                seen[h] = pid


def test_selection_is_deterministic():
    """同输入同输出：排序得定死（高考优先→年份→key），复跑要逐位相同。"""
    a = pointbook.select_all()
    b = pointbook.select_all()
    for pid in a:
        assert [q.key for q in a[pid].taken["中档题"]] == \
               [q.key for q in b[pid].taken["中档题"]], pid


# ── 三、讲解侧 ────────────────────────────────────────────────

def test_role_split():
    assert pointbook.role_of("01-必修1-集合与函数/1.1.1-集合的含义与表示") == "知识讲解"
    assert pointbook.role_of("11-题型与解法/集合与常用逻辑用语") == "常考题型与解法"
    assert pointbook.role_of("13-易错点与限时训练/集合-逻辑与函数") == "易错警示"
    assert pointbook.role_of("15-知识关联与主线/主线一-函数-贯穿最深的一条") == "知识主线"


def test_commentary_drops_empty_headings():
    """只有标题、内容在孩子身上的节点不许进讲义（会排成一串空标题）。"""
    for pid in ("1.1.3", "5.2.1", "10.1.1"):
        for role, items in pointbook.commentary(pid):
            for title, tex in items:
                assert len(re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", tex)) >= 12, \
                    f"{pid}/{role}/{title} 是个空节点"


def test_book_ang_replaced_without_breaking_angle():
    """书里的 `\\ang x` 换成 `\\angle x`，但已有的 `\\angle` 不许被啃掉。"""
    hit = [n for n in klist.sources().values()
           if re.search(r"\\ang(?![a-zA-Z])", n["body"])]
    assert hit, "书里已经没有 \\ang 了？这条测试该跟着删"
    for n in hit:
        body = klist.dialect(n["body"])
        # 图换 PNG 之后 `\angle` 会随图一起消失，比较必须在**同一口径**下做
        plain = klist._AXIS_RE.sub(" ", klist._TIKZ_RE.sub(" ", body))
        before = len(re.findall(r"\\angle(?![a-zA-Z])", plain))
        tex, _d, _p = pointbook.node_latex(n["id"])
        assert not re.search(r"\\ang(?![a-zA-Z])", tex), n["id"]
        assert len(re.findall(r"\\angle(?![a-zA-Z])", tex)) >= before, \
            f"{n['id']} 的 \\angle 被换没了"


def test_figures_point_at_existing_pngs():
    """讲义里每个 `\\includegraphics` 都得真有其图（断引用就是空页）。"""
    from amti.export import IMG_DIR
    for pid in ("1.1.3", "3.4.1", "10.1.2"):
        sels = pointbook.select_all()
        body = pointbook.point_body(pid, sels[pid])
        names = re.findall(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}", body)
        assert names, f"{pid} 没有图，取数可能断了"
        for nm in names:
            assert (IMG_DIR / nm).is_file(), f"{pid} 引用了不存在的图 {nm}"


# ── 四、u2tex ────────────────────────────────────────────────

def test_u2tex_math_run_and_spacing():
    out = pointbook.u2tex("交集 A∩B（公共元素）与补集 ∁ᵤA。")
    assert r"$A\cap B$" in out, out
    assert r"\capB" not in out, "命令名没断开，TeX 会读成未定义的 \\capB"


def test_u2tex_keeps_existing_math_untouched():
    src = r"最小二乘 $\hat{y}=\hat{b}-\hat{a}$，公差 d≥0。"
    out = pointbook.u2tex(src)
    assert r"$\hat{y}=\hat{b}-\hat{a}$" in out, out
    assert r"$d\geq 0$" in out, out


def test_u2tex_circled_stays_in_text():
    out = pointbook.u2tex("①正确；②错误")
    assert r"\textcircled{1}" in out and "$\\textcircled" not in out, out


def test_u2tex_escapes_plain_angle():
    out = pointbook.u2tex("则 1<x<2 成立")
    assert r"\textless{}" in out, out


def test_u2tex_keeps_angle_in_math_as_is():
    r"""数学式里的 `<` 原样留着：换成 `\lt` 反而炸——exam-zh 没有 `\lt`/`\gt`。"""
    out = pointbook.u2tex("解集为 $a<x<b$ 或 x>y 时")
    assert r"$a<x<b$" in out, out
    assert r"\lt" not in out and r"\gt" not in out, out
    assert r"\textgreater{}" in out, out


def test_u2tex_scripts_group():
    out = pointbook.u2tex("aₙ₊₁=aₙ+d")
    assert r"$a_{n+1}=a_{n}+d$" == out, out


def test_u2tex_ascii_caret_forms():
    r"""`a^{n-k}`（自带括号）与 `a^(n-k)`（纯文本括号）都得成上标，不能吐 `\^`。"""
    assert pointbook.u2tex("(a+b)ⁿ=Σ_{k=0}^{n} C(n,k) a^(n−k)") == \
        r"$(a+b)^{n}=\Sigma _{k=0}^{n} C(n,k) a^{n−k}$"
    assert r"\^" not in pointbook.u2tex("a^(n-k) 与 T_{k+1}"), "落成了 \\^（会加帽）"


def test_guard_leading_bracket_keeps_the_bracket():
    """题干以 `[甲]` 开头：补 `{}` 堵住环境，但 `[` 本身一个字都不能丢。"""
    q = next(x for x in store.load_cached()
             if x.stem.lstrip().startswith("[") and x.type == "detailed_answer")
    tex = paper.question_tex(q, show_answers=True)
    head = tex.split("\n")
    assert head[0] == r"\begin{problem}{}", head[0]
    assert head[1].startswith("["), f"题干开头的 [ 丢了：{head[1][:20]}"


def test_unmapped_symbols_are_known():
    """全库五要素里不许冒出映射表之外的符号（冒出来就是表该长了）。"""
    left: set[str] = set()
    for p in knowledge.all_points():
        import json
        left |= pointbook.unmapped(json.dumps(knowledge.fields_of(p["id"]),
                                              ensure_ascii=False))
    assert not left, f"未映射：{sorted(left)}"


# ── 五、渲染期三道修，且不外溢到写库 ──────────────────────────

def test_fix_blank_brackets():
    tex = r"\fillin[$\bar{A}=\{x\mid 4\leqslant x\leqslant 5\}=[4,5]$]。"
    fixed = paper.fix_blank_brackets(tex)
    assert fixed.startswith(r"\fillin[{") and fixed.endswith(r"}]。"), fixed
    assert fixed.count("$") == 2, "数学模式没配平"
    # 包一层花括号之后，作答位里那个区间右端点不再被当成终止符
    assert fixed.index("[{") < fixed.index("=[4,5]") < fixed.rindex("}]")


def test_fix_blank_brackets_escaping_math_inside_blank():
    r"""作答位落在 `$…$` 里、答案又没带 `$` → 得补上（exam-zh 按正文排参数）。"""
    tex = r"$\left(\fillin[\frac{1}{c} - \frac{1}{b}]\right) x=0$"
    fixed = paper.fix_blank_brackets(tex)
    assert r"\fillin[$\frac{1}{c} - \frac{1}{b}$]" in fixed, fixed


def test_fix_blank_brackets_left_right_delimiter():
    r"""`\right]` 那种答案：包花括号能救，换成 `\rbrack` 会炸（`\right` 只认定界符）。"""
    tex = r"\fillin[$\left(e, \frac{e^2}{2}\right]$]。"
    fixed = paper.fix_blank_brackets(tex)
    assert r"\right\rbrack" not in fixed, fixed
    assert fixed.count("$") == 2, fixed


def test_fix_text_specials_keeps_math_subscripts():
    tex = "概率为_____。又 $x_i$ 与 $a_1$。"
    fixed = paper.fix_text_specials(tex)
    assert r"\underline{\hspace{5em}}" in fixed, fixed
    assert r"$x_i$" in fixed and r"$a_1$" in fixed, "数学式里的下标被动了"


def test_fix_text_specials_escapes_raw_hash():
    """解析里混进的元话（`#10`）得转义，否则 «macro parameter character #» 停编译。"""
    fixed = paper.fix_text_specials("（原册第 1 页里 #10 只印了答案）")
    assert r"\#10" in fixed, fixed
    assert paper.fix_text_specials(r"已有 \# 的不重复转义") == r"已有 \# 的不重复转义"


def test_red_answer_wraps_whole_blank():
    tex = r"则 $\bar{A}=$\fillin[$A=[4,5]$]。"
    out = paper.red_answer_macros(paper.fix_blank_brackets(tex))
    # 染红的组必须**整个包住**作答位（老实现用 `[^\]]*` 匹配，正好在 `[4,5]`
    # 那个 `]` 上断掉，把 `}` 插进了数学式中间）。
    assert r"{\color{amtiAnsRed}\fillin[{$A=[4,5]$}]}" in out, out
    assert out.count("{") == out.count("}"), f"花括号不配平：{out}"


def test_red_answer_never_leaves_stray_brace():
    r"""染色后**不许在任何作答位中间插 `}`**——那是 «Argument of \fillin has an
    extra }» 的唯一成因，一插上整份卷子就出不来（用户报障原文）。

    三种槽里带 `]` 的形态都要过：`\sqrt[3]`、区间 `$[0,1]$`、`\left[…\right]`。
    xparse 扫可选参数时数方括号，`}` 一旦落进还没收尾的 `\fillin[…]` 里，
    引擎直接报「extra }」停编译（实测：这 3 道题单独出卷、开「答案印在题目上」
    时 100% 复现，修好后全库 158 道一次编过）。
    """
    cases = [
        r"则 $q$ 的最大值为\fillin[$\sqrt[3]{\frac{3}{2}}$]．",   # [3] 自带 ]
        r"值域为\fillin[$[0,1]$]。",                              # 区间 ]
        r"范围为\fillin[$\left[-1,3\right]$] 。",                 # \right] 定界符
        r"则 $\bar{A}=$\fillin[$A=[4,5]$]。",
    ]
    for stem in cases:
        out = paper.red_answer_macros(paper.fix_blank_brackets(stem))
        assert out.count("{") == out.count("}"), f"花括号不配平：{out}"
        assert out.count("[") == out.count("]"), f"方括号不配平：{out}"
        # 染色组必须**整块**罩住作答位：槽的收尾 `]` 后面紧接着的就是
        # 关组的那一个 `}`。老实现会把 `}` 插在槽中间（提前冒出来的 `]`）
        m = re.search(r"\{\\color\{%s\}\\(?:fillin|paren)\[" % paper.ANS_RED, out)
        assert m, out
        end = paper._blank_arg_end(out, m.end() - 1)
        assert end > 0 and out[end + 1] == "}", f"染色组没罩住作答位：{out}"
        assert out.count(r"\fillin[") == 1, out


def test_render_fixes_do_not_touch_stored_data(tmp_path=None):
    """写库路径必须原样：`store.render_question` 里不许出现这两道修的痕迹。"""
    q = store.find("高考真题汇编/2025/上海卷（秋）#1")
    assert q is not None, "样例题没了（选题口径变了，请换一个带右闭区间的填空）"
    stored = store.render_question(q)
    assert r"\rbrack" not in stored and r"\underline{\hspace" not in stored
    assert r"\fillin[$\bar{A}" in stored, "题干本身被改了？"
    printed = paper.question_tex(q, show_answers=True)
    assert r"\fillin[{" in printed, "出题路径没修"


# ── 六、生成物对账 ────────────────────────────────────────────

def test_build_writes_and_counts_match():
    """每个文件印出的题数 == 选题数；导言区只有一份。"""
    sels = pointbook.select_all()
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        summary = pointbook.build(out=out, verbose=False)
        files = sorted((out / "points").glob("*.tex"))
        assert len(files) == len(sels) == 152, len(files)
        for f in files:
            pid = f.name.split("-")[0]
            s = f.read_text(encoding="utf-8")
            n = s.count(r"\begin{question}") + s.count(r"\begin{problem}")
            assert n == s_given(sels[pid]), f"{pid} 印了 {n} 道，选了 {s_given(sels[pid])} 道"
        main = (out / "main.tex").read_text(encoding="utf-8")
        assert main.count(r"\documentclass") == 1, "导言区被抄了两份"
        assert r"{exam-zh}" in main
        assert main.count(r"\include{points/") == len(files)
        assert summary["questions"] == sum(s_given(s) for s in sels.values())


def test_point_body_has_no_unexpanded_book_dialect():
    """生成物里不许残留书自己的宏/环境（dialect 漏了就会编译报未定义）。"""
    sels = pointbook.select_all()
    body = pointbook.point_body("6.3.1", sels["6.3.1"])
    bad = re.findall(r"\\(?:numline|thead|makecell|shortstack|appenum|notebox|"
                     r"srcgap|srcmiss|dg|cu|para|vec|set|trip|ra|lra|Lra|Ra)\b", body)
    assert not bad, f"残留书方言：{sorted(set(bad))}"


def s_given(sel) -> int:
    return sum(len(v) for v in sel.taken.values())


def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
        except Exception as e:            # noqa: BLE001
            bad += 1
            print(f"  ❌ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n  {len(tests) - bad}/{len(tests)} 通过")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_run())
