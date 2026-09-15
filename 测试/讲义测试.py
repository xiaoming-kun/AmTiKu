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
