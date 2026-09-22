#!/usr/bin/env python3
r"""Windows/macOS 免安装包的**接口冒烟**：把包当服务真跑起来，走一遍用户真会走的路。

为什么要有它：`--selftest` 只证明「库读得进、PDF 编得出」，而**用户实际走的是 HTTP**——
打开页面 → 筛选 → 看图 → 组卷导出 → A4 讲义 → 录入写库。这几条里：

* **写库**在 Windows 上要走 `msvcrt.locking` 那条分支（POSIX 上走 `flock`）。
  只在这台机器上真写一次，才知道那条分支行不行——它坏了就是**改坏题库**，
  比导出失败严重得多。
* **看图**要把 PIL + numpy 的透明化那条路真的跑一遍（打包最容易漏的就是它）。
* **导出**要走 `server.export()` 而不是 `paper` + `compile_tex`（早先
  `_paper` 未导入的 NameError 就只在这条路上炸）。

用法（由工作流先起好服务）：
    <包目录>/AmTiKu --port 8951        # 另开一个进程
    python packaging/win_smoke_api.py --port 8951

失败以非 0 退出，并把响应原文打出来——只留一个红叉是看不出哪儿不对的。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

FAILED: list[str] = []

# 录入用的一小段源材料：模仿 demo 里的填空题（同一种宏），只是**每次换数字**——
# 不换的话第二次跑就会被查重挡下（"入库后题数没涨"），看起来像写库坏了。
# 答案：$f(x)=x^2-2kx$ 在 $[0,2k]$ 上的最小值是 $f(k)=-k^2$。
_K = random.randint(50, 99)
INGEST = rf"""\begin{{question}}
自检题（第 {_K} 号）：已知函数 $f(x)=x^{{2}}-{2 * _K}x$，则 $f(x)$ 在 $[0,{2 * _K}]$ 上的最小值为\fillin[-{_K * _K}]
\begin{{solution}}
$f(x)=(x-{_K})^{{2}}-{_K * _K}$，其图象开口向上、对称轴为 $x={_K}$，而 ${_K}\in[0,{2 * _K}]$，故最小值为 $f({_K})=-{_K * _K}$。
\end{{solution}}
\end{{question}}
"""


def req(base: str, path: str, *, method: str = "GET", body=None, timeout: int = 240):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read(), dict(resp.headers)


def jget(base: str, path: str, **kw):
    st, raw, _ = req(base, path, **kw)
    assert st == 200, f"HTTP {st}"
    return json.loads(raw)


def check(label: str, fn) -> None:
    t0 = time.time()
    try:
        extra = fn() or ""
        print(f"  ✓ {label}  ({time.time() - t0:.1f}s){('  ' + extra) if extra else ''}",
              flush=True)
    except Exception as e:                       # noqa: BLE001
        FAILED.append(label)
        print(f"  ✗ {label}  ({time.time() - t0:.1f}s)  {type(e).__name__}: {e}",
              flush=True)


def wait_up(base: str, sec: int = 180) -> float:
    t0 = time.time()
    last = ""
    while time.time() - t0 < sec:
        try:
            st, raw, _ = req(base, "/", timeout=10)
            if st == 200 and raw:
                return time.time() - t0
        except Exception as e:                   # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(2)
    raise SystemExit(f"服务 {sec} 秒没起来（最后一次：{last}）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8951)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    base = f"http://{a.host}:{a.port}"

    print(f"等待服务起来：{base}")
    print(f"  ✓ 服务已就绪（{wait_up(base):.1f}s）")

    st: dict = {}

    def frontend():
        st["html"] = req(base, "/")[1].decode("utf-8", "replace")
        assert "AmTiKu" in st["html"] or "<div id=" in st["html"], "页面里没有应用外壳"

    def assets():
        m = re.search(r'(/assets/[^"\']+\.js)', st["html"])
        assert m, "页面里没有引用前端 JS（web/dist 没打进去？）"
        body = req(base, m.group(1))[1]
        assert len(body) > 50_000, f"前端 JS 只有 {len(body)} 字节"
        return f"{m.group(1)} {len(body) // 1024} KB"

    def questions():
        d = jget(base, "/api/questions?limit=100&lite=0")
        assert d["total"] > 0, "库里一道题都没有"
        st["items"] = d["items"]
        # 导出只取前几道：这里验的是"这条路通不通"，不是"能不能出 100 题的卷"
        st["keys"] = [it["key"] for it in d["items"][:4]]
        return f"共 {d['total']} 道"

    def facets():
        d = jget(base, "/api/facets")
        assert d, "筛选项是空的"
        return f"{len(d)} 组筛选项"

    def stats():
        d = jget(base, "/api/stats")
        assert d, "统计是空的"
        return ", ".join(f"{k}={v}" for k, v in list(d.items())[:4]
                         if isinstance(v, (int, str)))

    def _find_fig(items):
        for it in items:
            m = re.search(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", it.get("stem") or "")
            if m:
                return m.group(1)
        return None

    def figure_raw():
        # 先在前 100 道里找；找不到就专门筛"有图"的题（真实库里第一屏未必带图）
        name = _find_fig(st["items"])
        if not name:
            name = _find_fig(jget(base, "/api/questions?has=图&limit=20&lite=0")["items"])
        assert name, "找不到带图的题（图片或题干里的图丢了？）"
        st["fig"] = name
        _, body, hdr = req(base, f"/api/figure?path={name}&raw=1")
        assert body[:4] == b"\x89PNG", "取回来的不是 PNG"
        return f"{name} {len(body) // 1024} KB"

    def figure_transparent():
        # 这条路要用 PIL + numpy 现算（打包最容易漏的就是这两个）
        _, body, hdr = req(base, f"/api/figure?path={st['fig']}")
        assert body[:4] == b"\x89PNG", "透明化后的不是 PNG"
        assert len(body) > 1000, "透明化后的图太小"
        return f"{len(body) // 1024} KB（透明化）"

    def export_gaokao():
        d = jget(base, "/api/export", method="POST", body={
            "keys": st["keys"], "title": "接口冒烟_试卷", "out": "接口冒烟_试卷",
            "mode": "gaokao", "show_answers": True, "answers_at_end": True,
            "compile": True})
        assert d.get("ok"), f"导出失败：{d.get('error') or d.get('log')}"
        st["paper"] = d
        return f"{d['questions']} 题 → {d['pdf_abs']}"

    def export_handout():
        d = jget(base, "/api/export", method="POST", body={
            "keys": st["keys"], "title": "接口冒烟_讲义", "out": "接口冒烟_讲义",
            "mode": "handout", "compile": True})
        assert d.get("ok"), f"讲义导出失败：{d.get('error') or d.get('log')}"
        st["handout"] = d
        return f"{d['questions']} 题 → {d['pdf_abs']}"

    def pdf_download():
        for key, label in (("paper", "试卷"), ("handout", "讲义")):
            # 文件名是中文，必须 URL 编码（不编码 urllib 直接抛 UnicodeEncodeError）
            name = urllib.parse.quote(st[key]["name"] + ".pdf")
            stt, body, _ = req(base, f"/api/pdf?path={name}")
            assert stt == 200 and body[:4] == b"%PDF", f"{label} PDF 取回来不对"
        return "试卷 + 讲义都能下载，PDF 头正确"

    def ingest_preview():
        d = jget(base, "/api/ingest/preview", method="POST",
                 body={"text": INGEST, "book": "自检"})
        items = d.get("items") or []
        assert items, f"没解析出题：{json.dumps(d, ensure_ascii=False)[:400]}"
        probs = [p for it in items for p in (it.get("problems") or [])]
        assert not probs, f"预检有问题：{probs}"
        return f"{len(items)} 道，预检无问题"

    def ingest_commit():
        before = jget(base, "/api/questions?limit=1")["total"]
        d = jget(base, "/api/ingest/commit", method="POST",
                 body={"text": INGEST, "book": "自检"})
        assert d.get("ok"), f"入库失败：{json.dumps(d, ensure_ascii=False)[:500]}"
        after = jget(base, "/api/questions?limit=1")["total"]
        assert after == before + 1, f"入库后题数 {before} → {after}，不是 +1"
        # 这一步真正验证的是 Windows 上的写锁（msvcrt）能拿到、能释放、库没写坏
        return f"{before} → {after}（写锁这条分支在 Windows 上走通了）"

    check("打开首页（前端外壳在包里）", frontend)
    check("前端静态资源可访问", assets)
    check("列出题目 /api/questions", questions)
    check("筛选项 /api/facets", facets)
    check("统计 /api/stats", stats)
    check("看图（原图）/api/figure?raw=1", figure_raw)
    check("看图（透明化，走 PIL+numpy）", figure_transparent)
    check("组卷导出试卷 /api/export", export_gaokao)
    check("导出 A4 讲义 /api/export", export_handout)
    check("下载导出的 PDF /api/pdf", pdf_download)
    check("录入预检 /api/ingest/preview", ingest_preview)
    check("正式入库 /api/ingest/commit（写库锁）", ingest_commit)

    if FAILED:
        print(f"\n接口冒烟失败 {len(FAILED)} 项：" + "、".join(FAILED))
        return 1
    print("\n接口冒烟全部通过（页面 / 看图 / 试卷 / 讲义 / 写库）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
