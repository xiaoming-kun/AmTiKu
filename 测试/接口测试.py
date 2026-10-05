"""接口层回归测试。

为什么加（后端审查报告 Important #5）：

    原来只有 `amti.py verify`（校验**数据**）和一个删题自检脚本，
    **接口层没有回归保护** —— 而本轮审查发现的问题恰好都在接口边界上：
    `limit` 越界、导出超时、跨站 Origin、列表瘦身后详情取全量。

用法（两种都行）：

    python3 测试/接口测试.py          # 不需要 pytest
    pytest 测试/接口测试.py -q        # 有 pytest 时按用例粒度报告

说明：用 `fastapi.testclient.TestClient`，**不用起服务**、不动真实数据
（只读端点 + 一个会被拒绝的越界请求）。
"""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient          # noqa: E402

from amti.web.server import app                    # noqa: E402

client = TestClient(app)


# ── 列表与分页边界 ────────────────────────────────────────────

def test_list_ok():
    """⚠️ 这里断言的是**下界**，不是等于 17249。

    库是会长的——录一份卷子就多十几道（`amti.record` 一次入库 18 道）。
    写死数字的话，**每录一次题这个测试就红一次**，而红的原因不是接口坏了。
    真正该盯的是「存量有没有被改」，那是 `test_stats_and_baseline` 的活。
    """
    r = client.get("/api/questions?limit=5")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] >= 17249, d["total"]
    assert len(d["items"]) == 5


def test_limit_over_max_rejected():
    """limit 必须有上界（审查报告 Important #1）。

    没有上界时 limit=999999 会让服务端构造 17k 条 _brief，
    每条都要把 LaTeX 解析成块 IR —— 足以卡住服务几十秒。
    """
    assert client.get("/api/questions?limit=5000").status_code == 422
    assert client.get("/api/questions?limit=1000").status_code == 200


def test_limit_under_min_rejected():
    assert client.get("/api/questions?limit=0").status_code == 422
    assert client.get("/api/questions?offset=-1").status_code == 422


def test_list_is_lite_but_stem_present():
    """列表瘦身（审查报告 💡#3）：只带题干块 IR，答案/解析留给详情。"""
    it = client.get("/api/questions?limit=1").json()["items"][0]
    assert it.get("lite") is True
    assert "stem" in it["blocks"] and it["blocks"]["stem"], "题干块不能为空"
    assert "answer" not in it["blocks"] and "solution" not in it["blocks"]


def test_detail_has_full_blocks():
    """详情按 key 拿全量：答案/解析的块 IR 在这里必须齐全。"""
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    d = client.get(f"/api/questions/{_enc(key)}").json()
    assert d["key"] == key
    assert set(d["blocks"]) >= {"stem", "answer", "solution", "options"}
    assert "tex" in d, "详情要带卷面源码（前端 LaTeX 标签页用）"
    assert "used" in d, "详情要带使用频次"


# ── 安全：跨站请求 ────────────────────────────────────────────

def test_cross_origin_rejected():
    """任意网页都能向 127.0.0.1 发 POST（同源策略不挡发送），
    所以用 Origin 白名单挡住（审查报告 Important #4）。"""
    r = client.get("/api/facets", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403


def test_local_and_no_origin_allowed():
    assert client.get("/api/facets",
                      headers={"Origin": "http://127.0.0.1:8899"}).status_code == 200
    assert client.get("/api/facets").status_code == 200      # curl / 脚本


# ── 只读端点健康 ──────────────────────────────────────────────

def test_facets_shape():
    d = client.get("/api/facets").json()
    assert len(d["points"]) >= 150
    assert d["points_covered"] >= 150
    assert any(p["value"].startswith("1.1") for p in d["points"])


def test_stats_and_baseline():
    """基线要与现状一致，且**存量内容一个都不能变**。

    原先是 `b["当前"] == 17249`（写死的数字）——录题之后必然红。
    改成盯真正的不变量：库只增不减（删题走回收站、可恢复），
    且「内容变化」必须是 0。
    """
    assert client.get("/api/stats").status_code == 200
    b = client.get("/api/baseline").json()
    assert b["当前"] >= 17249, b
    assert b["内容变化"] == 0, b
    assert b["删除"] == 0, b


def test_usage_sorted_list():
    """默认排序按使用频次：used 字段必须在，且降序。"""
    items = client.get("/api/questions?sort=used&limit=10").json()["items"]
    used = [it.get("used", 0) for it in items]
    assert used == sorted(used, reverse=True), used


def test_trash_requires_password():
    """删除必须带正确口令；错口令要被拒（且不动数据）。"""
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    r = client.post("/api/trash/delete",
                    json={"keys": [key], "reason": "接口测试", "password": "错的"})
    assert r.status_code in (400, 403, 422), r.status_code
    # 确认没被删掉
    assert client.get(f"/api/questions/{_enc(key)}").status_code == 200


def test_reveal_rejects_outside_path():
    """/api/reveal 只能打开项目内路径。"""
    assert client.get("/api/reveal?path=/etc/hosts").status_code == 403


# ── 改标签接口（PATCH）────────────────────────────────────────
#
# 这一组是**补写**的：改 `patch_question`（抽记档助手）时漏了 return，
# 接口变成返回 None → FastAPI 报 ResponseValidationError(500)，
# 而当时那 12 个用例没一个碰 PATCH，回归就这么溜过去了。
# 所以这里补上，而且**改完必须还原**（只动难度，可逆）。

def test_patch_rejects_body_fields():
    """题干/选项等正文一律拒绝（只允许 answer/difficulty/points/stars/type）。"""
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    r = client.patch(f"/api/questions/{_enc(key)}", json={"stem": "改题干试试"})
    assert r.status_code == 400, r.status_code
    assert "只允许改" in r.json()["detail"]


def test_patch_difficulty_roundtrip():
    """改难度 → 还原（空字符串＝恢复按主考点派生）。

    改完**必须**能拿到完整记录（`key`/`tex`/`blocks`）——
    返回 None 会让 FastAPI 直接 500，这正是回归现场。
    """
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    enc = _enc(key)
    cur = client.get(f"/api/questions/{enc}").json()
    orig = cur.get("meta", {}).get("difficulty", "")
    if orig:
        # 上一轮被强杀（Ctrl-C / kill）时 `finally` 的还原跑不到，会在这道题上
        # 留下一条**手动难度**。不报出来的话它会被当成正常数据留很久
        # （实测踩过：集合基础题被留成「难题」，还被 snapshot 进了基线）。
        print(f"    ⚠️ {key} 上有上轮残留的手动难度「{orig}」，本次跑完会还原成它")
        if orig == "难题":
            print("       （多半是残留，不是有意的）")
    # 这个接口会写一份「变更记档」，测试跑完要把**自己产生的**记档删掉，
    # 否则每跑一次测试就往仓库里丢两个文件。
    audit_dir = ROOT / "变更记录"
    before_logs = set(audit_dir.glob("*界面改标签*")) if audit_dir.exists() else set()
    try:
        r = client.patch(f"/api/questions/{enc}", json={"difficulty": "难题"})
        assert r.status_code == 200, r.status_code
        d = r.json()
        assert d["key"] == key and d["difficulty"] == "难题"
        assert "tex" in d and "blocks" in d, "PATCH 也要回完整记录"
    finally:
        # 无论断言成败都还原，别把测试的痕迹留在题库里
        back = client.patch(f"/api/questions/{enc}", json={"difficulty": orig or ""})
        assert back.status_code == 200, back.status_code
        # 清掉本次新产生的记档文件
        for f in set(audit_dir.glob("*界面改标签*")) - before_logs:
            f.unlink(missing_ok=True)


# ── 知识链路（`设计/知识链路.md`）──────────────────────────────
#
# 这一层的意义和别的接口不同：链路的**数据是人写的**，所以接口必须替人
# 守住那几条硬规矩——悬空引用、自环、硬性前置成环（成环＝死锁，
# 「可学」状态永远点不亮）。这些错在数据里看不出来，只有算一遍才知道。

def test_chain_graph_shape():
    r = client.get("/api/chain")
    assert r.status_code == 200
    d = r.json()
    assert len(d["nodes"]) >= 100, d["stats"]
    ids = {n["id"] for n in d["nodes"]}
    assert all(e["pre"] in ids and e["post"] in ids for e in d["edges"]), "边引用了不存在的考点"
    assert all(e["strength"] in ("hard", "soft") for e in d["edges"])
    assert all(e["reason"].strip() for e in d["edges"]), "有边没写理由"
    assert all(n["n"] >= 0 for n in d["nodes"]), "题量不能是负数"


def test_chain_audit_is_not_swallowed_by_pid():
    """`/api/chain/audit` 必须声明在 `/api/chain/{pid}` 之前。

    FastAPI 按声明顺序匹配：反过来的话 `audit` 会被当成一个考点 id，
    体检面板直接 404 —— 而 404 在界面上表现成「这个功能没做」。
    """
    assert client.get("/api/chain/audit").status_code == 200


def test_chain_hard_edges_are_acyclic():
    """硬性前置成环 = 那几个考点永远学不了。这条是数据层的红线。"""
    d = client.get("/api/chain").json()
    fwd: dict[str, list[str]] = {}
    indeg = {n["id"]: 0 for n in d["nodes"]}
    for e in d["edges"]:
        if e["strength"] != "hard":
            continue
        fwd.setdefault(e["pre"], []).append(e["post"])
        indeg[e["post"]] += 1
    queue = [k for k, v in indeg.items() if v == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for v in fwd.get(cur, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    assert seen == len(indeg), "hard 边有环，拓扑排序没能走完全部考点"


def test_chain_node_detail_and_404():
    d = client.get("/api/chain/1.1.2").json()
    assert d["id"] == "1.1.2"
    assert d["title"], "考点名要从知识点库现取"
    assert any(e["pre"] == "1.1.1" and e["strength"] == "hard" for e in d["pre"])
    assert d["fields"], "五段式字段要带上（侧栏详情直接显示）"
    assert all("title" in e for e in d["pre"] + d["post"]), "前置/后续要带名称，侧栏才不用再查"
    assert client.get("/api/chain/9.9.9").status_code == 404


# ── 导出链路 ──────────────────────────────────────────────────
#
# 为什么单独加这一节：验收四层里**没有一条**真正走过导出的 Python 入口。
# 层③「端到端渲染」走的是 `paper.render_paper`，而界面导出走的是
# `export.render_paper`（一层包装）→ `export.export`。
# 结果：给 `paper` 加了参数、忘了同步包装，**整个导出功能 500**，
# 而 `amti.py accept` 依然四层全绿。踩过一次，所以补上。

def test_export_passes_only_supported_kwargs():
    r"""`export.export` 传给 `render_paper` 的关键字，包装函数必须都收。

    **这才是那个 bug 的准确形状**：给 `paper.render_paper` 加了 `qid_marks`，
    `export.export` 也开始传它，却忘了给 `export.render_paper` 加这个参数
    → `TypeError` → **整个导出 500**，而 `amti.py accept` 四层全绿
    （层③ 走 `paper`，不经过这层包装）。

    所以直接去读 `export.export` 的源码，把它**实际传的**关键字抠出来，
    逐个对包装函数的签名 —— 以后再加参数也一样拦得住。
    """
    import ast
    import inspect
    import textwrap

    from amti import export

    tree = ast.parse(textwrap.dedent(inspect.getsource(export.export)))
    passed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "render_paper":
            passed |= {k.arg for k in node.keywords if k.arg}

    assert passed, "没在 export.export 里找到 render_paper 调用 —— 这条测试已失效，要改"
    accepted = set(inspect.signature(export.render_paper).parameters)
    bad = sorted(passed - accepted)
    assert not bad, (
        f"export.export 传了 export.render_paper 不认的参数：{bad}\n"
        f"（导出会直接 TypeError → 界面收到 HTTP 500）"
    )


def test_export_wrapper_signature_is_valid():
    r"""包装函数的参数必须都是 `paper.render_paper` 认识的（防拼错/防漂移）。

    `graphicspath` 与 `subject` 是**故意不暴露**的 —— 导出的图目录固定
    是项目的 `图片/`，学科固定是数学。所以它们在允许清单里。
    """
    import inspect

    from amti import export, paper

    inner = set(inspect.signature(paper.render_paper).parameters)
    outer = set(inspect.signature(export.render_paper).parameters)
    INTENTIONALLY_FIXED = {"graphicspath", "subject"}
    bad = sorted(outer - inner - INTENTIONALLY_FIXED)
    assert not bad, f"export.render_paper 有不被 paper 认识的参数：{bad}"


def test_export_runs_end_to_end_without_compile():
    """真调一次 `export.export`（不编译），确保参数确实透传得下去。

    `do_compile=False` 是为了快（编译一次要几秒），
    但**参数透传**这一步照样走到 —— 也就是刚才那个 500 的位置。
    """
    from amti import export, store

    keys = [q.key for _f, q in store.iter_questions()][:2]
    assert keys, "库里没有题，测不了导出"
    r = export.export(keys, title="__接口测试_导出", do_compile=False)
    assert r.get("ok"), f"export.export 失败：{r.get('error') or r}"
    assert r.get("tex_abs"), "没给出 .tex 落盘位置"
    # 清掉刚生成的 .tex，别在「讲义」目录里留垃圾
    import pathlib as _pl
    _pl.Path(r["tex_abs"]).unlink(missing_ok=True)


def test_export_unknown_mode_rejected():
    """未知卷型要**返回**错误，不能抛异常（UI 靠这个字段显示提示）。"""
    from amti import export, store

    keys = [q.key for _f, q in store.iter_questions()][:1]
    r = export.export(keys, title="x", mode="不存在", do_compile=False)
    assert r.get("ok") is False and r.get("error"), r


def test_export_qid_marks_only_when_compiling():
    """`qid_marks` 只在要编译时才写 —— 不编译的导出不该多出 N 行注释。"""
    from amti import export, store

    keys = [q.key for _f, q in store.iter_questions()][:2]
    from amti import paper
    off = paper.render_paper([store.find(k) for k in keys], mode="test",
                             title="t", qid_marks=False)
    on = paper.render_paper([store.find(k) for k in keys], mode="test",
                            title="t", qid_marks=True)
    assert "AMTIKU-Q" not in off, "不编译时不该有定位注释"
    assert on.count("AMTIKU-Q") == len(keys), "编译时每题都该有定位注释"


def test_export_prints_source_and_drops_difficulty():
    r"""卷面上**印出处、不印难度**（用户要求：所有导出都跟讲义一样）。

    三种卷型一视同仁：题干第一行并上「（2024新高考I卷 第1题）」，
    难度星（`$\star$`）与卷首的「难度分布」都不许再出现在产物里。

    ⚠️ 为什么三种卷型一起断言：这两样都是**渲染期**的东西，而渲染分两条路
    （`_q_tex` 走 gaokao/test、`_render_handout` 走 handout）。只盯一条路的话，
    另一条会悄悄退回"印难度、不印出处"——本项目最忌讳的正是这种不一致
    （预览与导出、两个卷型，各印各的）。
    """
    from amti import paper, store
    from amti.slidev_handout import source_label

    q = next((x for _f, x in store.iter_questions()
              if x.type == "single_choice" and source_label(x)), None)
    assert q is not None, "库里没有带出处的高考单选题，测不了"

    lab = source_label(q)
    for mode in ("gaokao", "test", "handout"):
        tex = paper.render_paper([q], mode=mode, title="__接口测试_出处")
        tag = "（%s）" % lab
        assert tag in tex, f"{mode} 卷面没印出处：{lab}"
        assert r"\star" not in tex, f"{mode} 卷面还在印难度星"
        assert "难度分布" not in tex, f"{mode} 卷首还在印难度分布"
        # **出处与题干同一行**（用户要求：括号 + 与题目同排，不另起一行）
        line = next(ln for ln in tex.split("\n") if tag in ln)
        assert line.split(tag, 1)[1].strip(), f"{mode} 的出处单独占了一行"


# ── 无 pytest 时的运行器 ──────────────────────────────────────

def _enc(key: str) -> str:
    """题号里含 `#`（如 `高考真题汇编/2024/新高考I卷#17`）与 `/`，
    直接拼进 URL 会被当成片段/路径分隔 → 必须整体编码。
    （前端用 `encodeURIComponent`，等价。）
    """
    return urllib.parse.quote(key, safe="")


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
