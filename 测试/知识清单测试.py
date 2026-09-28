"""知识清单（讲义讲解内容源）的回归测试。**不需要起服务。**

三块：

  ① **内容源本身** —— 书方言展得开、节点切得对、图宽是对的、考点映射没悬空
  ② **接口边界** —— `/api/klist/*`
  ③ **前后端一致**（最重要）—— 讲解块在画布上由前端 `render.tsx` 画、
     导出 PDF 由后端 `slidev_handout.ir_blocks` 画，**逐节点比对结构**。
     预览与导出不一致是这个项目反复踩的坑（表格/公式/图片/出处标签都栽过），
     所以这里不是抽查一条，是把生成物里 252 个节点全比一遍。

用法：

    python3 测试/知识清单测试.py        # 不需要 pytest
    pytest 测试/知识清单测试.py -q      # 有 pytest 时按用例粒度报告
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import klist                                     # noqa: E402
from amti import slidev_handout as sh                       # noqa: E402
from amti.web.server import app                             # noqa: E402
from fastapi.testclient import TestClient                   # noqa: E402

client = TestClient(app)


# ── ① 内容源 ──────────────────────────────────────────────────

def test_book_dialect_expands_own_macros():
    """书自己的宏（`\\lra` `\\abs` `\\thead` `appenum`…）必须展开成标准写法。

    不展开的话 `latex_blocks` 不认，会整片漏成 raw 宏显示在界面上 ——
    而「书方言 → 应用方言」只写在 `klist.dialect()` 这一处。
    """
    assert r"\longrightarrow" in klist.dialect(r"$a\lra b$")
    assert r"\left| x \right|" in klist.dialect(r"$\abs{x}$")
    assert "thead" not in klist.dialect(r"\thead{易错点}")
    assert "\\begin{itemize}" in klist.dialect(
        "\\begin{appenum}\\item 甲\\end{appenum}")


def test_store_has_nodes_with_unique_ids():
    nodes = klist.nodes()
    assert len(nodes) > 100, "生成物里节点太少：%d" % len(nodes)
    ids = [n["id"] for n in nodes]
    assert len(set(ids)) == len(ids), "节点 id 撞了"


def test_map_covers_every_point_without_dangling():
    """考点 ↔ 讲解节点的映射：全coverage、无悬空、无未知考点。"""
    rep = klist.map_report()
    assert rep["map_file"], "缺 讲义/知识清单映射.json"
    assert rep["dangling_nodes"] == [], "映射指向了不存在的节点"
    assert rep["unknown_points"] == [], "映射里有知识点库里没有的考点"
    assert rep["points_missing"] == [], "这些考点还没配讲解：%s" % rep["points_missing"][:5]


def test_no_unexpanded_macro_left():
    """生成物里不该剩下书方言宏（剩下就会在界面上显示成源码）。"""
    left = klist.load().get("stats", {}).get("unknown_macros", 0)
    assert left == 0, "还剩 %d 处未展开的宏" % left


def test_fig_width_is_absolute_not_percent():
    r"""图宽必须是**绝对单位**，不能是百分比。

    回归用例：`latex_blocks` 把宽度折成「占 15cm 版心的百分之几」，
    而百分比在**表格格子里**是按格子算的 —— 书的「示意图」列那 0.9cm 小图
    被算成格子的 7%，导出 PDF 里缩成一个点（210 张书图里 129 张在格子里）。
    所以 `parse_nodes` 把它们换回绝对厘米，这条守着别再换回去。
    """
    bad = []

    def walk_in(ins):
        for x in ins or []:
            if x.get("t") == "fig" and str(x.get("width", "")).endswith("%"):
                bad.append(x.get("width"))

    def walk(bs):
        for b in bs:
            t = b.get("t")
            if t == "fig" and str(b.get("width", "")).endswith("%"):
                bad.append(b.get("width"))
            elif t == "p":
                walk_in(b.get("in"))
            elif t == "list":
                for it in b["items"]:
                    walk(it)
            elif t == "box":
                walk(b["blocks"])
            elif t == "table":
                for row in b["rows"]:
                    for c in row:
                        if "blocks" in c:
                            walk(c["blocks"])
                        walk_in(c.get("in"))

    for n in klist.nodes():
        walk(n["blocks"])
    assert not bad, "还有 %d 张图用百分比宽度（表格格子里会缩到看不见）" % len(bad)


def test_every_figure_has_its_png():
    """IR 里引用的每一张图都得在 `图片/` 里真存在（否则预览/导出都是空的）。"""
    missing = set()

    def walk_in(ins):
        for x in ins or []:
            if x.get("t") == "fig":
                _need(x.get("id"), missing)

    def walk(bs):
        for b in bs:
            t = b.get("t")
            if t == "fig":
                _need(b.get("id"), missing)
            elif t == "p":
                walk_in(b.get("in"))
            elif t == "list":
                for it in b["items"]:
                    walk(it)
            elif t == "box":
                walk(b["blocks"])
            elif t == "table":
                for row in b["rows"]:
                    for c in row:
                        if "blocks" in c:
                            walk(c["blocks"])
                        walk_in(c.get("in"))

    for n in klist.nodes():
        walk(n["blocks"])
    assert not missing, "这些图在 图片/ 里找不到：%s" % sorted(missing)[:5]


def _need(fid, missing: set) -> None:
    name = Path(str(fid or "")).name
    if not name or not (ROOT / "图片" / name).is_file():
        missing.add(name)


def test_figures_are_not_pending():
    """生成物里不该有「引用了但没渲染」的图（那种会退化成 raw 块）。"""
    pend = klist.load().get("stats", {}).get("figs_pending", 0)
    assert pend == 0, "还有 %d 张图没渲染" % pend


def test_search_finds_body_text_and_survives_empty():
    """搜索按**正文原话**命中；空搜索不返回、不报错。"""
    hits = klist.search("子集")
    assert hits, "搜「子集」应该有结果"
    assert any("子集" in (h["title"] + h["hit"]) for h in hits)
    assert klist.search("") == [] and klist.search("   ") == []
    assert klist.search("这句话书里绝对没有") == []


# ── ② 接口边界 ────────────────────────────────────────────────

def test_api_tree_node_and_search():
    t = client.get("/api/klist/tree")
    assert t.status_code == 200
    tree = t.json()["tree"]
    assert tree and tree[0]["kids"] is not None

    # 目录里挑一个真节点，再取它的正文
    nid = tree[0]["id"]
    n = client.get("/api/klist/node/" + nid)
    assert n.status_code == 200, nid
    assert n.json()["id"] == nid
    assert isinstance(n.json()["blocks"], list)

    s = client.get("/api/klist/search", params={"q": "子集", "limit": 3})
    assert s.status_code == 200
    assert 0 < len(s.json()["items"]) <= 3


def test_api_node_404_and_search_limit_clamped():
    assert client.get("/api/klist/node/根本没有这个节点").status_code == 404
    # limit 越界要被 FastAPI 挡掉（和 /api/questions 一个规矩）
    assert client.get("/api/klist/search?q=x&limit=99999").status_code == 422
    assert client.get("/api/klist/search?q=x&limit=0").status_code == 422


def test_api_by_point_follows_the_curated_map():
    """按考点取讲解：返回的节点必须是映射里核定的那几个，且都真存在。"""
    pid = next(iter(klist.load_map()))
    r = client.get("/api/klist/by-point/" + pid)
    assert r.status_code == 200
    got = [n["id"] for n in r.json()["nodes"]]
    assert got == [i for i in klist.load_map()[pid] if klist.get_node(i)], \
        "按考点返回的节点与人工核定的映射不一致"
    assert client.get("/api/klist/by-point/不存在的考点").json()["nodes"] == []


def test_api_stats_reports_map_health():
    d = client.get("/api/klist/stats").json()
    assert d["ok"] is True
    assert d["stats"]["nodes"] > 100
    assert d["map"]["points_missing"] == []
    assert d["stale"] is False, "生成物过期了，跑 python3 -m amti.klist build"


# ── ③ 前后端一致：讲解块的 IR 两边画出来必须是同一个结构 ────────

# 数学段（`$$…$$` 优先，再 `$…$`）。判「源码泄漏」前要先摘掉它。
# ⚠️ 单 `$` 那一支**必须允许换行**：书里大量把 `$\begin{cases}…` 写成跨行
#    （`[^$\n]` 会漏掉它们，于是 16 个节点的 `\begin{cases}` 被误报成泄漏）。
_MATH_RE = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$]+?\$")


def _py_counts(blocks) -> dict:
    """后端（`ir_blocks`）画出来的结构计数。

    **只数表格与图** —— 正文段落两边刻意不同形：后端把列表渲染成
    markdown 原生列表（项里的公式才解析得了），前端渲染成 `<ol><li><div class=q-p>`。
    段落数因此天然不等，拿它当判据只会得到假警报。
    表格与图**必须**一致：它们是嵌套的（表格里套表格、格子里放图），
    也正是历史上"预览有、PDF 没有"的那一类。
    """
    html = sh.ir_blocks(blocks)
    return {"table": html.count("<table"), "img": html.count("<img")}


_NODE_PROBE = r"""
// 把前端的 render.tsx 用 esbuild 转出来，在 node 里真渲染一遍（react-dom/server），
// 数出「表格 / 图 / 段落」的个数 —— 与后端 ir_blocks 的结构逐节点比对。
//
// ⚠️ 两个坑：
//   ① 产物必须落在 **web/ 里**（不是 /tmp）：`--packages=external` 之后
//      `import 'react'` 是按**产物所在目录**解包的，放 /tmp 就找不到。
//   ② react 必须两边**同一份实例**：bundle 里内联一份 react、react-dom 又从
//      node_modules 拿一份的话，SSR 会报 "more than one copy of React"，
//      hooks 的 dispatcher 是 null（第一版就是这么挂的）。
import { execSync } from 'node:child_process'
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'

const WEB = %r
const out = path.join(WEB, '_klist_probe_bundle.mjs')
const nodes = JSON.parse(process.argv[2])
try {
  execSync(
    `npx esbuild "src/lib/render.tsx" --bundle --format=esm --platform=node `
    + `--packages=external --alias:@=./src --outfile="${out}" --log-level=error`,
    { cwd: WEB, stdio: 'pipe' })

  const mod = await import('file://' + out + '?t=' + Date.now())
  const { renderToStaticMarkup } =
    createRequire(path.join(WEB, 'package.json'))('react-dom/server')

  const count = (s, re) => (s.match(re) || []).length
  console.log(JSON.stringify(nodes.map((n) => {
    const html = renderToStaticMarkup(mod.renderBlocks(n.blocks))
    return { table: count(html, /<table/g), img: count(html, /<img/g),
             len: html.length }
  })))
} finally {
  fs.rmSync(out, { force: true })          // 不留临时产物在源码目录里
}
"""


def _node_counts(nodes: list) -> list[dict]:
    """前端（`renderBlocks`）画出来的结构计数。"""
    probe = Path("/tmp/amti-klist-probe.mjs")
    probe.write_text(_NODE_PROBE % str(ROOT / "web"), encoding="utf-8")
    r = subprocess.run(
        ["node", str(probe), json.dumps([{"blocks": n["blocks"]} for n in nodes],
                                        ensure_ascii=False)],
        cwd=str(ROOT / "web"), capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise AssertionError("前端渲染探针跑不起来：\n" + (r.stderr or "")[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_frontend_backend_block_parity():
    """252 个节点，逐个比「表格 / 图」的个数。

    这条是本文件的核心：讲解块在画布上由前端画、导出 PDF 由后端画，
    两边对同一份 IR 的结构必须一致。查的就是「前端把表格/图吃了」——
    界面看着有、PDF 里没有，或者反过来（本项目栽过好几次）。
    另外前端画出来不能是空的：整类块被漏掉时签名就是"渲染成空字符串"。
    """
    nodes = klist.nodes()
    assert nodes, "没有生成物，先跑 python3 -m amti.klist build"
    fe = _node_counts(nodes)
    bad = []
    for n, f in zip(nodes, fe):
        b = _py_counts(n["blocks"])
        if b["table"] != f["table"] or b["img"] != f["img"]:
            bad.append((n["id"], b, {k: f[k] for k in ("table", "img")}))
        elif n["chars"] > 50 and f["len"] < 20:
            bad.append((n["id"], "有正文（%d 字）" % n["chars"], "前端画出来是空的"))
    assert not bad, ("前后端画出来的结构不一致（后端/前端）：\n"
                     + "\n".join("  %s  %s  %s" % x for x in bad[:5]))


def test_ir_blocks_renders_every_block_type():
    """生成物里出现的每一种块都要能画出来 —— 不能有整类内容被静默丢掉。"""
    found: dict = {}

    def look(bs):
        for b in bs:
            found.setdefault(b.get("t"), b)
            if b.get("t") == "list":
                for it in b["items"]:
                    look(it)
            elif b.get("t") == "box":
                look(b["blocks"])
            elif b.get("t") == "table":
                for row in b["rows"]:
                    for c in row:
                        if "blocks" in c:
                            look(c["blocks"])

    for n in klist.nodes():
        look(n["blocks"])
    assert found, "生成物里一个块都没有？"

    want = {"p": 'class="p-t"', "math": "$$", "list": None, "table": "<table",
            "fig": "<img", "box": None}
    for t, must in want.items():
        if t not in found:
            continue
        out = sh.ir_blocks([found[t]])
        assert out.strip(), "块类型 %s 画出来是空的" % t
        if must:
            assert must in out, "块类型 %s 画出来缺 %s" % (t, must)


def test_ir_blocks_never_leaks_latex_source():
    r"""导出的 markdown 里不能漏 LaTeX 源码。

    本项目最忌讳的一种失败：构建成功、PDF 里却印着 `\begin{tabular}`。
    （真正的判据在 `amti.py accept` 层③ 的产物文本层，这里先在最前面拦一道。）

    ⚠️ 判据要**先把数学段摘掉**：`$$\left\{\begin{aligned}…` 里的
    `\begin{aligned}` 是**合法数学环境**（书里大量用它排方程组），
    它出现在导出里是对的。要抓的是数学段**之外**的源码泄漏
    —— 第一版没摘，64 个节点全是误报。
    """
    bad = []
    for n in klist.nodes():
        out = sh.ir_blocks(n["blocks"])
        prose = _MATH_RE.sub(" ", out)
        for pat in (r"\begin{", r"\end{", r"\includegraphics", r"\thead",
                    r"\lra", r"\numline", r"\srcgap"):
            if pat in prose:
                bad.append((n["id"], pat))
        # 图宽不能再退回百分比（格子里会缩没）。
        # ⚠️ 只看 **img 标签里**的 width，别把表格的 `width:100%` 也算进来
        #    （整篇扫的话 136 个节点全被误报）。
        for tag in re.findall(r"<img[^>]*>", out):
            if re.search(r'(?:^|[;"\s])width:\s*[\d.]+%', tag):
                bad.append((n["id"], "图宽是百分比"))
                break
    assert not bad, "有 %d 处源码/坏宽度漏进导出：%s" % (len(bad), bad[:5])


def test_ir_fig_copies_png_into_slidev():
    """讲解里的图要**复制进 Slidev 的 public/img** 才能在 PDF 里显示。

    只写 `<img src="/img/x.png">` 而没复制的话，导出的 PDF 是个空框
    （题库题目的配图走的是同一个约定，见 `copy_figures`）。
    """
    n = next((n for n in klist.nodes() if n["n_fig"]), None)
    assert n, "生成物里一张图都没有？"
    out = sh.ir_blocks(n["blocks"])
    assert "<img" in out, "这个节点的图没画出来：%s" % n["id"]
    pub = ROOT / "slidev" / "public" / "img"
    names = re.findall(r'<img src="/img/([^"]+)"', out)
    assert names, out[:200]
    for name in names:
        assert (pub / name).is_file(), "图没复制进 Slidev：%s" % name


# ── ④ 导出的 markdown 要过得了 **Slidev 自己的解析器** ────────────

_MDPROBE = r"""
// 用 Slidev 自己的 markdown 解析器（markdown-exit）过一遍生成的讲义 md。
// 秒级、不用开浏览器 —— 查的正是"构建成功但 PDF 坏了"那一类：
//   · 该当 HTML 块的 <table> 被转义进 <pre><code>（前面缺空行/缩进不对）
//   · 解析器直接抛错 → 整份讲义导不出来
// 真事故：`_ir_list` 里列表项的续行没缩进，后面跟着的缩进 <table> 把
// Slidev 解析器顶爆（"导出失败"但错误信息看不出是哪来的）。
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'

const SLIDEV = %r
const { MarkdownExit } = createRequire(path.join(SLIDEV, 'package.json'))('markdown-exit')
const md = new MarkdownExit({ html: true, linkify: false, breaks: false })
const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
console.log(JSON.stringify(cases.map((c) => {
  let html = '', err = ''
  try { html = md.render(c.md) } catch (e) { err = String((e && e.message) || e) }
  return {
    id: c.id,
    tables: (html.match(/<table/g) || []).length,
    imgs: (html.match(/<img/g) || []).length,
    escaped: /&lt;table|&lt;tr&gt;|&lt;td/.test(html),   // HTML 被转义 = 排版塌了
    err,
  }
})))
"""


def test_markdown_survives_slidev_parser():
    """252 个节点的讲义 markdown，逐个过 Slidev 的解析器。

    两条断言：
      ① 解析不报错、HTML 没被转义进 `<pre><code>`
      ② **`<table>`/`<img>` 经解析后一个不少** —— 这条最实用：
         "导出里少了表"这种事故在 PDF 里才发现，这里秒级就拦住了。
    """
    cases = [{"id": n["id"], "md": sh.ir_blocks(n["blocks"])}
             for n in klist.nodes()]
    assert cases, "没有生成物"
    probe = Path("/tmp/amti-klist-mdprobe.mjs")
    probe.write_text(_MDPROBE % str(ROOT / "slidev"), encoding="utf-8")
    src = Path("/tmp/amti-klist-md.json")
    src.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(["node", str(probe), str(src)],
                       cwd=str(ROOT / "slidev"), capture_output=True, text=True,
                       timeout=300)
    if r.returncode != 0:
        raise AssertionError("markdown 探针跑不起来：\n" + (r.stderr or "")[-2000:])
    got = json.loads(r.stdout.strip().splitlines()[-1])
    bad = []
    for c, g in zip(cases, got):
        if g["err"] or g["escaped"]:
            bad.append((c["id"], g["err"] or "HTML 被转义进代码块"))
        elif g["tables"] != c["md"].count("<table") or g["imgs"] != c["md"].count("<img"):
            bad.append((c["id"], "解析后表/图少了：%d→%d / %d→%d"
                        % (c["md"].count("<table"), g["tables"],
                           c["md"].count("<img"), g["imgs"])))
    assert not bad, "有 %d 个节点过不了 Slidev 的解析器：%s" % (len(bad), bad[:5])


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for fn in fns:
        try:
            fn()
            print("  ✅ %s" % fn.__name__)
        except Exception as e:
            bad += 1
            print("  💥 %s: %s" % (fn.__name__, e))
            traceback.print_exc()
    print("\n  %d/%d 通过" % (len(fns) - bad, len(fns)))
    sys.exit(1 if bad else 0)
