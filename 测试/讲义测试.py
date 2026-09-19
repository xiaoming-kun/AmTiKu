"""讲义相关的单元测试（不需要起服务）。

覆盖「高考题标出处」这个需求（用户要求：讲义里先写
「2026新课标I卷 第7题」，然后才是题目本身）。

⚠️ 这里同时把**前后端两条实现**放在一起测 ——
   前端 `web/src/editor/shared.tsx::sourceLabel` 与后端
   `amti/slidev_handout.py::source_label` 必须产出**同一个字符串**。
   预览与导出不一致是这个项目反复踩的坑（表格/公式/图片都踩过）。

用法：

    python3 测试/讲义测试.py        # 不需要 pytest
    pytest 测试/讲义测试.py -q      # 有 pytest 时按用例粒度报告
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import slidev_handout as sh          # noqa: E402
from amti import store                          # noqa: E402


# ── 后端：出处标签 ────────────────────────────────────────────

def test_gaokao_label_format():
    """高考题要生成「2024新高考I卷 第1题」这种标签。"""
    q = next(q for q in store.load_cached()
             if q.kind == "高考" and "#" in q.key and q.meta.get("year"))
    lab = sh.source_label(q)
    assert lab, f"高考题应有出处标签：{q.key}"
    assert str(q.meta["year"]) in lab
    assert lab.endswith(f"第{q.key.rsplit('#', 1)[1]}题"), lab
    assert " 第" in lab, f"年份卷别与题号之间应有空格：{lab!r}"


def test_non_gaokao_has_no_label():
    """模拟题/练习册不加（用户要求只标高真题）。"""
    q = next(q for q in store.load_cached() if q.kind != "高考")
    assert sh.source_label(q) == "", f"{q.key} 不该有标签"


def test_render_puts_label_inline_with_stem():
    """出处**和题目同一行**，且加括号（用户要求）。

    实现细节：标签是**纯文本**并进题干第一段，不能是独立的
    `<div class="p-src">`（那样会换行），也不能是 `<span>`
    （编辑器 MarkdownBody 不解析 HTML → 预览与导出不一致）。
    """
    q = next(q for q in store.load_cached()
             if q.kind == "高考" and q.meta.get("year"))
    out = sh.render_canvas_block({"type": "question", "key": q.key,
                                  "x": 4, "y": 4, "w": 92})
    lab = sh.source_label(q)
    assert f"（{lab}）" in out, f"标签要带括号：{lab!r}"
    assert 'class="p-src"' not in out, "标签不该是独立块（会被换行）"
    assert "<span" not in out.split("p-ex", 1)[1][:200], "标签不该用 span"

    # 标签与题干正文必须落在**同一段**里
    para = out.split('class="p-ex"')[1].split("</div>")[0]
    assert f"（{lab}）" in para, "标签不在题干那一段里"
    assert re.search(rf"（{re.escape(lab)}）\s*\S", para), "标签后面应紧跟题干正文"


def test_switch_off_hides_label():
    """讲义级开关关掉就不标；块级 showSource 也要能单独覆盖。"""
    q = next(q for q in store.load_cached() if q.kind == "高考" and q.meta.get("year"))
    off = sh.render_canvas_block({"type": "question", "key": q.key,
                                  "x": 4, "y": 4, "w": 92}, show_source=False)
    assert sh.source_label(q) not in off, "关掉后不该出现出处"
    # 讲义级关、块级开 → 仍显示
    on = sh.render_canvas_block({"type": "question", "key": q.key, "showSource": True,
                                 "x": 4, "y": 4, "w": 92}, show_source=False)
    assert f"（{sh.source_label(q)}）" in on


def test_canvas_markdown_contains_label():
    """整份讲义的 markdown 里也要有（导出 PDF 靠它）。"""
    q = next(q for q in store.load_cached() if q.kind == "高考" and q.meta.get("year"))
    md = sh.build_canvas_pages(
        [{"blocks": [{"type": "question", "key": q.key, "x": 4, "y": 4, "w": 92}]}],
        title="出处标签测试", ratio="16/9")
    assert sh.source_label(q) in md


# ── 画布比例（iPad）──────────────────────────────────────────
#
# 用户反馈：16:9 的讲义导进 iPad「不伦不类」（上下留黑边）。
# 真机比例：iPad 12.9″/13″/10.2″ = 4:3；iPad 11″/10.9″/Air ≈ 1.439。
# 两边都必须有这个键：前端下拉（RATIO_BOX，算画布宽高）与后端（Slidev 的
# aspectRatio）——少一边就会出现"选得出来但导出报未知比例"。

def test_ipad_ratio_known_to_backend():
    assert "ipad11" in sh.RATIOS, "后端 RATIOS 少了 ipad11"
    assert sh.RATIOS["ipad11"] == "2360/1640"
    assert sh.RATIOS["4:3"] == "4/3"          # 12.9″ 那批 iPad 走这个
    assert "16:9" in sh.RATIOS                # 老比例必须保留（用户要求）


def test_unknown_ratio_rejected():
    r = sh.export_canvas([{"blocks": []}], title="x", out="x",
                         ratio="21:9", do_compile=False)
    assert not r["ok"] and "未知比例" in r["error"], r


def test_ipad_ratio_in_markdown():
    """导出的 markdown 里 aspectRatio 要真的是 iPad 的比。"""
    q = next(q for q in store.load_cached() if q.kind == "高考")
    md = sh.build_canvas_pages(
        [{"blocks": [{"type": "question", "key": q.key, "x": 4, "y": 4, "w": 92}]}],
        title="iPad 比例", ratio=sh.RATIOS["ipad11"])
    assert "aspectRatio: 2360/1640" in md, md[:200]


# ── 段落间距：预览与导出必须一致 ──────────────────────────────
#
# 用户反馈：讲义**导出**的东西里，题干与 (1)(2) 之间空得很大、很别扭。
# 根因：题目正文里的空行在 markdown 里是**分段**，预览侧 `.q-p` 给 0.4em，
# 导出侧却吃 Slidev 默认的 ~1em —— 同一条规则两边不一样。
# 这条测试把「两边都是 0.4em」钉住，防止再漂移。

def test_paragraph_spacing_same_both_sides():
    import pathlib as _p
    # 导出侧：讲义 markdown 里必须带上收紧段距的样式
    q = next(q for q in store.load_cached() if q.kind == "高考")
    md = sh.build_markdown([q], title="段距")
    css = sh.TIGHT_SPACING_CSS
    assert css in md, "导出的 markdown 少了收紧段距的 <style>"
    assert "margin: 0.4em 0" in css, css

    # 加个空行分段的解答题，确认它真的落进 .p-ex 的段距规则里
    qa = next((x for x in store.load_cached()
               if x.type == "detailed_answer" and "\n\n" in (x.stem or "")), None)
    if qa is not None:
        md2 = sh.build_markdown([qa], title="段距2")
        assert "<style>" in md2 and "0.4em" in md2, md2[:300]

    # 预览侧：web/src/index.css 里同一层级的段距也是 0.4em（`.q-p` 定义在那儿）
    root = _p.Path(__file__).resolve().parent.parent
    prev = (root / "web" / "src" / "index.css").read_text(encoding="utf-8")
    assert ".q-p" in prev and "0.4em" in prev, "预览侧 .q-p 的段距不是 0.4em"


# ── 选项里的图片（用户报过的 bug）────────────────────────────
#
# 现象：卷面上选项显示成 `(A)\includegraphics[width=0.15\paperwidth]{x.png}` 源码。
# 四个原因叠在一起，这条测试把它们全钉住：
#   ① transform() 只对题干做了 copy_figures，选项原样丢给 KaTeX；
#   ② 选项的图**包在 $…$ 里**，不脱定界符 KaTeX 就只显示命令；
#   ③ Slidev 的 CSS reset 让 `img` 是 block → 每个选项各占一行；
#   ④ 外面套 display:flex + markdown 空行 → 选项变成被压窄的 <p> flex item，
#      图小到 13px。

IMG_OPT_Q = "高考真题汇编/2013/江西卷（文）#10"


def _img_opt_question():
    q = store.find(IMG_OPT_Q)
    assert q, "测试用题不在库里：%s" % IMG_OPT_Q
    return q


def test_option_images_converted():
    r"""选项里的 \includegraphics 要变成 <img>，且不能留数学定界符包着。"""
    out = sh.render_canvas_block({"type": "question", "key": IMG_OPT_Q,
                                  "x": 4, "y": 6, "w": 92, "h": 0, "z": 0})
    assert "includegraphics" not in out, "选项还在漏 LaTeX 源码"
    assert out.count("<img") >= 4, "四个图象选项都要有图"
    # 不允许 `$<img …>$` 这种把图片又塞回数学模式的形式。
    # ⚠️ 不能用 `\$[^$]*<img`：公式后面正常跟一张图（`$l_2$ … <img>`）也会被误判。
    #    只认「$ 紧跟图片」或「图片紧跟 $」。
    assert not re.search(r"\$\s*<img", out), "图片开头被 $ 包住（数学模式）"
    assert not re.search(r"/>\s*\$", out), "图片结尾被 $ 包住（数学模式）"


def test_option_images_are_inline_block():
    """图片必须 display:inline-block。

    Slidev 的 reset 把 `img` 设成 block，不加这句**每个选项占一行**（实测）。
    """
    out = sh.render_canvas_block({"type": "question", "key": IMG_OPT_Q,
                                  "x": 4, "y": 6, "w": 92, "h": 0, "z": 0})
    imgs = re.findall(r"<img[^>]*>", out)
    opt_imgs = [t for t in imgs if "108px" in t]
    assert len(opt_imgs) >= 4, f"应有 4 张选项图：{len(opt_imgs)}"
    for t in opt_imgs:
        assert "display:inline-block" in t, f"选项图缺 inline-block：{t[:70]}"


def test_options_not_wrapped_in_flex():
    """选项不要再套 display:flex。

    flex + markdown 空行会把选项行包成 <p>（flex item），
    宽度被压到几十 px → 图 13px 且各占一行。
    """
    out = sh.render_canvas_block({"type": "question", "key": IMG_OPT_Q,
                                  "x": 4, "y": 6, "w": 92, "h": 0, "z": 0})
    tail = out[out.find("(A)"):] if "(A)" in out else ""
    assert "display:flex" not in tail, "选项又被 flex 包住了"


def test_text_options_keep_math():
    """普通文字/公式选项不受影响（图片处理不能吃掉数学）。"""
    q = next(q for q in store.load_cached()
             if q.kind == "高考" and q.options and "$" in q.options[0].text)
    out = sh.render_canvas_block({"type": "question", "key": q.key,
                                  "x": 4, "y": 6, "w": 92})
    assert "(A)" in out and "$" in out, "文字选项应保留公式"
    assert "includegraphics" not in out


# ── 前后端一致性（前端实现用 node 跑）────────────────────────

_JS = """
import { sourceLabel } from '%s/web/src/editor/shared.tsx'
""" % ROOT

_NODE_PROBE = r"""
// 用 esbuild 把 TS 里的 sourceLabel 转出来单独跑，避免依赖浏览器。
// ⚠️ 必须是**纯 ESM**：混用 require + 顶层 await 会让 node 报
//    ERR_AMBIGUOUS_MODULE_SYNTAX（第一次就是这么踩的）。
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'amti-src-'))
const out = path.join(dir, 'shared.mjs')
// 必须 --bundle + --alias:@=./src：
//   shared.tsx 里有 `@/lib/...` 别名导入，不解析别名 node 会 import 失败。
execSync(
  `npx esbuild "src/editor/shared.tsx" --bundle --format=esm --platform=node `
  + `--alias:@=./src --outfile="${out}" --log-level=error`,
  { cwd: '%s/web', stdio: 'pipe' })

const mod = await import('file://' + out)
const cases = JSON.parse(process.argv[2])
console.log(JSON.stringify(cases.map((q) => mod.sourceLabel(q))))
"""


def test_frontend_backend_label_parity():
    """前端 sourceLabel 与后端 source_label 必须逐题一致。

    不一致的后果很隐蔽：**编辑器预览有出处、导出 PDF 没有**（或反过来），
    而人只会看其中一个。
    """
    qs = [q for q in store.load_cached()
          if q.kind == "高考" and q.meta.get("year")][:5]
    qs += [q for q in store.load_cached() if q.kind != "高考"][:2]
    cases = [{"key": q.key, "kind": q.kind, "meta": q.meta} for q in qs]
    backend = [sh.source_label(q) for q in qs]

    probe = ROOT / "测试" / "_source_label_probe.mjs"
    probe.write_text(_NODE_PROBE % ROOT, encoding="utf-8")
    try:
        r = subprocess.run(["node", str(probe), json.dumps(cases, ensure_ascii=False)],
                           cwd=str(ROOT / "web"), capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, (r.stdout + r.stderr)[-500:]
        frontend = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        probe.unlink(missing_ok=True)

    for q, b, f in zip(qs, backend, frontend):
        assert b == f, f"前后端不一致：{q.key} 后端={b!r} 前端={f!r}"


# ── 无 pytest 时的运行器 ──────────────────────────────────────

def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ {name}")
        except AssertionError as e:
            bad += 1
            print(f"  ❌ {name}: {e}")
        except Exception as e:                       # noqa: BLE001
            bad += 1
            print(f"  💥 {name}: {type(e).__name__}: {e}")
    print(f"\n  {len(tests) - bad}/{len(tests)} 通过")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
