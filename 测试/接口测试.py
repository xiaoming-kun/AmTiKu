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
    """列表瘦身：题干 + 答案块留下，长解析仍留给详情。

    答案块很小，却是卡片「显示答案」的必需数据；不带它就会退化成
    每题一次 /answer 请求（公式题尤其慢）。解析块仍然不带。
    """
    it = client.get("/api/questions?limit=1").json()["items"][0]
    assert it.get("lite") is True
    assert "stem" in it["blocks"] and it["blocks"]["stem"], "题干块不能为空"
    assert "answer" in it["blocks"], "答案块要随列表带下来"
    assert "solution" not in it["blocks"], "解析块仍留给详情"


def test_answer_blocks_endpoint_for_list_preview():
    """列表「显示答案」只取答案块；公式答案不能被前端当源码显示。"""
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    r = client.get(f"/api/questions/{_enc(key)}/answer")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["key"] == key
    assert isinstance(d["blocks"], list) and d["blocks"], d
    # 详情路由不能被更具体的 /answer 抢掉
    assert client.get(f"/api/questions/{_enc(key)}").status_code == 200
    # 列表 lite 也带答案块：卡片「显示」不需要再逐题发请求
    items = client.get("/api/questions?limit=10").json()["items"]
    assert any((x.get("blocks") or {}).get("answer") for x in items), "列表缺少答案块"


def test_detail_has_full_blocks():
    """详情按 key 拿全量：答案/解析的块 IR 在这里必须齐全。"""
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    d = client.get(f"/api/questions/{_enc(key)}").json()
    assert d["key"] == key
    assert set(d["blocks"]) >= {"stem", "answer", "solution", "options"}
    assert "tex" in d, "详情要带卷面源码（导出与核对脚本直接用它，不经过前端）"
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
    # 出处（卷别）也要有计数——否则「出处」筛选项没有数据源
    assert d["sources"] and all(x["value"] and "n" in x for x in d["sources"])


def test_map_shape():
    r"""知识地图：三学段齐全、按教材顺序、高中节点从考点库取名字。

    客户提的第一条是「没有小学初中的知识点」——这个接口就是那条的交付物，
    所以节点数、学段、教材顺序都要能被回归测住。
    """
    d = client.get("/api/map").json()
    stages = {s["key"]: s for s in d["stages"]}
    assert set(stages) == {"primary", "junior", "senior"}, stages.keys()
    assert stages["primary"]["n"] >= 250
    assert stages["junior"]["n"] >= 150
    assert stages["senior"]["n"] == 152            # 与 知识点.json 的考点数一致
    # 教材顺序：小学按 1→6 年级、上→下 册排
    books = stages["primary"]["books"]
    assert [b["grade"] for b in books] == sorted(b["grade"] for b in books)
    # 高中节点必须补出名称/星级（只存 id 会露馅成空标题）
    first = stages["senior"]["books"][0]["chapters"][0]["points"][0]
    assert first["id"] and first["title"] and "stars" in first
    # 小学知识点必须带一句话说明，否则界面只剩一串光秃秃的名词
    p = stages["primary"]["books"][0]["chapters"][0]["points"][0]
    assert p["id"].startswith("x") and p["note"]
    # 前后关系：客户第二条反馈就是「图谱要有前置后置」，这里守两件事——
    # ① 边不能引用不存在的点（否则界面画出断头线）；② 每条边都要有语义。
    ids = {pt["id"] for s in d["stages"] for b in s["books"]
           for c in b["chapters"] for pt in c["points"]}
    edges = d["edges"]
    assert len(edges) >= 800, len(edges)
    assert all(e["from"] in ids and e["to"] in ids for e in edges)
    assert all(e["from"] != e["to"] for e in edges)
    assert {e["strength"] for e in edges} <= {"hard", "soft"}
    assert {e["kind"] for e in edges} <= {"prereq", "order"}
    assert d["stats"]["edges"] == len(edges)
    assert d["stats"]["covered"] >= 550


def test_map_questions():
    """小学/初中的诊断题：能按知识点取到，题干和答案都不空。"""
    d = client.get("/api/map").json()
    pt = next(p for s in d["stages"] for b in s["books"] for c in b["chapters"]
              for p in c["points"] if p.get("q"))
    r = client.get("/api/map/questions/" + pt["id"])
    assert r.status_code == 200, r.text
    qs = r.json()["qs"]
    assert qs and all(q.get("prompt") and q.get("answer") for q in qs)
    assert client.get("/api/map/questions/没有这个点").status_code == 404


def test_topics():
    r"""考点专题：列表、详情（讲义 + 精选题）、讲义 PDF 三件套。"""
    d = client.get("/api/topics").json()
    assert d["topics"], "一个专题都没有"
    t = d["topics"][0]
    body = client.get("/api/topics/" + t["id"]).json()
    assert body["topic"]["id"] == t["id"]
    qs = body["questions"]
    assert qs and qs[0]["blocks"]["stem"], "精选题没带题干块"
    assert qs[0]["blocks"].get("answer"), "精选题没带答案块"
    pdf = client.get("/api/topics/" + t["id"] + "/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert client.get("/api/topics/没有这个专题").status_code == 404


def test_open_lectures():
    """章节讲义：按知识图谱册/章返回，不再按来源分系列。"""
    d = client.get("/api/open-lectures?stage=primary").json()
    assert d["total"] == 10, d
    assert d["unmapped"] == 0, d
    first_book = d["books"][0]
    assert first_book["name"] == "二年级下册"
    chapter = first_book["chapters"][0]
    assert chapter["chapter"] == "第三单元 万以内数的认识"
    lid = chapter["lecture"]["id"]
    detail = client.get(f"/api/open-lectures/{lid}").json()
    assert detail["map"]["chapter"] == "第三单元 万以内数的认识"
    assert "位值制" in detail["article_title"]

    import re
    m = re.search(r'src="(/api/open-lectures/[^"]+/asset/[^"]+)"', detail["html"])
    if m:
        asset = client.get(m.group(1))
        assert asset.status_code == 200, asset.text
        assert asset.headers["content-type"].startswith("image/"), asset.headers

    j = client.get("/api/open-lectures?stage=junior").json()
    assert j["total"] == 34, j
    assert j["unmapped"] == 0 and j["missing_chapters"] == 0, j
    pairs = {(b["name"], c["chapter"]) for b in j["books"] for c in b["chapters"]}
    assert ("七年级上册", "第一章 有理数") in pairs
    assert ("七年级上册", "第二章 有理数的运算") in pairs
    assert ("八年级上册", "第十四章 全等三角形") in pairs
    assert ("九年级下册", "第三十四章 随机事件的概率") in pairs
    concise = [c for b in j["books"] for c in b["chapters"]]
    assert len(concise) == 34
    assert all(c["lecture"]["chars"] < 900 for c in concise)

    assert client.get("/api/open-lectures/没有这份").status_code == 404


def test_topic_export():
    """专题导出：讲义 + 练习编成一份 PDF（教师版/学生版）。"""
    import shutil
    if not shutil.which("xelatex"):
        return                      # 没装 LaTeX 的环境跳过：导出本来就依赖它
    t = client.get("/api/topics").json()["topics"][0]
    r = client.get(f"/api/topics/{t['id']}/export?answers=0")
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


def test_search_covers_source_and_points():
    r"""搜索框写着「题目/答案/考点/出处」——这四类都得**真能搜**。

    用户报的：输「2026精选模拟题」显示 0 道，而那本书有 2348 道。
    后端原来只比 `stem`/`answer`；`source=` 参数一直是对的，但搜索没接上。
    """
    f = client.get("/api/facets").json()
    src = max(f["sources"], key=lambda x: x["n"])
    # 关键词搜索：至少覆盖该出处的全部题（命中的只会更多，比如题干里也写了卷名）
    d = client.get("/api/questions", params={"q": src["value"], "limit": 1}).json()
    assert d["total"] >= src["n"], (src["value"], d["total"], src["n"])
    # 同一口径的 source= 筛选：与 facet 计数**精确一致**
    s = client.get("/api/questions", params={"source": src["value"], "limit": 1}).json()
    assert s["total"] == src["n"], (src["value"], s["total"], src["n"])
    # 搜考点名：至少能搜到该考点的题（可能更多，比如题干里出现同一个词）
    pt = next(x for x in f["points"] if x["n"] > 0 and x["title"])
    p = client.get("/api/questions", params={"q": pt["title"], "limit": 1}).json()
    assert p["total"] >= 1, (pt["title"], p["total"])


def test_stats_and_baseline():
    """基线要与现状一致，且**存量内容一个都不能变**。

    原先是 `b["当前"] == 17249`（写死的数字）——录题之后必然红。
    改成盯真正的不变量：**存量题的内容指纹不变**。

    ⚠️ 删除**不设 0**：重复题、坏题、合并题会正常进回收站，`accept` 层④
    也只把「内容变化 ≠ 0」当硬失败。把「删除 == 0」写进接口测试，
    等于每做一次正常清理就红一次；红久了就没人看了，反而盖住真正的回归。
    删除数仍然显示在体检页/顶栏，供人核对。
    """
    assert client.get("/api/stats").status_code == 200
    b = client.get("/api/baseline").json()
    assert b["当前"] >= 17249, b
    assert b["内容变化"] == 0, b


def test_usage_sorted_list():
    """默认排序按使用频次：used 字段必须在，且降序。"""
    items = client.get("/api/questions?sort=used&limit=10").json()["items"]
    used = [it.get("used", 0) for it in items]
    assert used == sorted(used, reverse=True), used


def test_year_sort_both_directions_unknown_last():
    r"""按年份排序：`year` 新→旧，`year2` 旧→新；没年份的题两档都排最后。

    没有年份的题 `meta.year` 是空 → 归 0。如果直接按 0 排，它们在
    「旧→新」里会跑到所有真题前面，整页都是无年份的题。
    """
    def years(sort: str, n: int = 200) -> list[int]:
        items = client.get(f"/api/questions?sort={sort}&limit={n}").json()["items"]
        return [int((it.get("meta") or {}).get("year") or 0) for it in items]

    desc = years("year")
    known = [y for y in desc if y]
    assert known == sorted(known, reverse=True), known[:20]
    first_zero = next((i for i, y in enumerate(desc) if y == 0), len(desc))
    assert all(y == 0 for y in desc[first_zero:]), "无年份的题没有排在末尾"

    asc = years("year2")
    known = [y for y in asc if y]
    assert known == sorted(known), known[:20]
    first_zero = next((i for i, y in enumerate(asc) if y == 0), len(asc))
    assert all(y == 0 for y in asc[first_zero:]), "无年份的题没有排在末尾"


def test_generate_and_ingest_endpoints_still_work():
    r"""组卷/录入是主流程，接口不能被新端点挤掉（这次真被挤掉过一次）。"""
    g = client.post("/api/generate", json={"mode": "test", "q": "糖水不等式"})
    assert g.status_code == 200, g.text
    assert "keys" in g.json() and "items" in g.json()

    pv = client.post("/api/ingest/preview", json={"text": ""})
    assert pv.status_code == 200, pv.text
    assert "errors" in pv.json() and "items" in pv.json()

    assert client.get("/api/vlm/status").status_code == 200


def test_ingest_multi_question_surface():
    r"""多题录入：标题预填 + 逐题覆盖 + 逐题诊断。

    守的是 2026-11 这轮手工录入工作台：粘一整份卷子，脚本切题，
    出处从 `\title{}` 认，卡片按 `block` 回填考点/难度/题号。
    """
    text = r"""\title{2025年长沙市高三调研}

\begin{question}
已知 $\mathrm{i}$ 是虚数单位，则复数 $\mathrm{i}^3$ 的值是 \paren[D]
\begin{choices}
\item \(1\)
\item \(-1\)
\item \(\mathrm{i}\)
\item \(-\mathrm{i}\)
\end{choices}
\begin{solution}
由虚数单位的定义得 $\mathrm{i}^3=-\mathrm{i}$。故选 D。
\end{solution}
\end{question}

\begin{problem}
甲同学每天预约成功的概率均为 \(0.7\)。
\begin{enumerate}
\item 求第三天才成功的概率；
\item 求所用天数 $X$ 的期望。
\end{enumerate}
\begin{solution}
(1) $0.3^2\times0.7=0.063$；(2) $E(X)=1.39$。
\end{solution}
\end{problem}
"""
    hint = client.post("/api/ingest/source", json={"text": text})
    assert hint.status_code == 200, hint.text
    assert hint.json()["title"] == "2025年长沙市高三调研", hint.text
    assert hint.json()["year"] == 2025, hint.text

    pv = client.post("/api/ingest/preview", json={
        "text": text, "book": "接口测试", "label": "2025年长沙市高三调研",
        "items": [
            {"block": 0, "pick": True, "source_no": "7",
             "points": ["8.5.1"], "difficulty": "简单题",
             "qtype": "single_choice", "point_source": "llm"},
            {"block": 1, "pick": False, "source_no": "8",
             "points": [], "difficulty": "中档题",
             "qtype": "detailed_answer"},
        ],
    })
    assert pv.status_code == 200, pv.text
    d = pv.json()
    assert d["count"] == 2, d["count"]
    assert d["source_hint"]["year"] == 2025, d["source_hint"]
    a, b = d["items"]
    assert a["block"] == 0 and b["block"] == 1, (a["block"], b["block"])
    assert a["source_no"] == "7" and b["source_no"] == "8", (a["source_no"], b["source_no"])
    assert a["points"] == ["8.5.1"], a["points"]
    assert a["manual_difficulty"] == "简单题" and a["difficulty"] == "简单题", a
    assert b["manual_difficulty"] == "中档题", b
    assert a["blocking"] == [] and b["blocking"] == [], (a["blocking"], b["blocking"])
    # 干跑要带渲染块，卡片才能直接画题干/选项/解析
    assert a["blocks"]["stem"] and a["blocks"]["options"], a.keys()

    # 标注接口的边界：空请求不报 500；一次最多 60 道（防把整本书塞进来）
    assert client.post("/api/ingest/tag", json={"items": []}).json()["ok"] is False
    r = client.post("/api/ingest/tag",
                    json={"items": [{"stem": "题"}] * 61})
    assert r.status_code == 413, r.status_code


def test_ingest_duplicate_is_skipped_not_upgraded():
    r"""手工录入规则：库里已有同题 → 整题跳过，不新增也不更新。

    构造：拿一道库里**没有考点**的题，用它的源码再 preview 一次，
    并故意给 `items` 带上考点——如果走旧的升级逻辑，`update_fields`
    会是 `["points"]`；手工录入的 API 必须把它压成空（预览不显示升级），
    `commit` 也固定 `update_existing=False`。
    """
    from amti import render_tex, store

    q = next((x for x in store.load_cached()
              if x.has_solution and x.answer.strip() and not x.figures
              and not x.points), None)
    if q is None:
        print("    （库里没有『无考点可升级』的题，跳过）")
        return
    tex = render_tex.question_to_tex(q)
    r = client.post("/api/ingest/preview", json={
        "text": tex, "book": "接口测试", "label": "去重不更新",
        "items": [{"block": 0, "pick": True, "points": ["1.1.1"],
                   "difficulty": "难题", "point_source": "llm",
                   "source_no": q.meta.get("source_no") or ""}],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["count"] == 1, d
    it = d["items"][0]
    assert it["same_key"] is True, it
    assert it["update_fields"] == [], it["update_fields"]
    assert d["dup"]["upgrade"] == 0, d["dup"]
    assert d["dup"]["new"] == 0, d["dup"]


def test_ingest_near_duplicate_over_95_is_skipped():
    r"""手工录入规则：整题相似 >95% 也不入库、不更新。

    拿一道库里的题，把开头「已知」改成「若」（非语义关键词、非数学内容），
    整题相似度会 >95%。它既不是 key 相同，也不是指纹完全相同，
    但手工录入 API 必须把它标成 `near_dup`、计入 `dup.skip`，
    并且 `update_fields` 为空（不升级）。
    """
    from amti import render_tex, store

    q = next((x for x in store.load_cached()
              if "已知" in (x.stem or "") and x.has_solution
              and x.answer.strip() and not x.figures), None)
    if q is None:
        print("    （库里没有合适的『已知』题，跳过）")
        return
    tex = render_tex.question_to_tex(q).replace("已知", "若", 1)
    r = client.post("/api/ingest/preview", json={
        "text": tex, "book": "接口测试", "label": "相似95",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["count"] == 1, d
    it = d["items"][0]
    assert it["same_key"] is False, it
    assert it["near_dup"] is True, it
    assert it["near_score"] > 0.95, it["near_score"]
    assert it["update_fields"] == [], it["update_fields"]
    assert d["dup"]["new"] == 0, d["dup"]
    assert d["dup"]["near"] == 1 and d["dup"]["skip"] == 1, d["dup"]


def test_ingest_global_source_survives_empty_item_overrides():
    """界面单卷时每张卡都带 label:''/year:''——不能因此丢掉左栏全局出处。"""
    text = r"""\begin{question}
已知 $1+1=2$，则 $2+2$ 等于 \paren[B]
\begin{choices}\item $3$\item $4$\item $5$\item $6$\end{choices}
\begin{solution}
$2+2=4$。故选 B。
\end{solution}
\end{question}
"""
    r = client.post("/api/ingest/preview", json={
        "text": text, "book": "接口测试",
        "label": "江苏南京中华中学10月质量检测",
        "region": "江苏", "year": 2026,
        "items": [{"block": 0, "label": "", "year": ""}],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    it = d["items"][0]
    assert it["label"] == "江苏南京中华中学10月质量检测", it
    assert it["year"] == 2026, it
    assert "江苏南京中华中学10月质量检测" in it["key"], it


def test_ingest_backfill_preview_marks_only_empty_fields():
    """补旧题模式（干跑）：只给已有题标「可补空字段」，不新增、不改正文。"""
    from amti import knowledge as kb
    from amti import render_tex, store

    q = next((x for x in store.load_cached()
              if not x.points and x.has_solution and x.answer.strip()
              and not x.figures), None)
    if q is None:
        print("    （库里没有空考点的合适题，跳过）")
        return
    pid = kb.all_points()[0]["id"]
    tex = render_tex.question_to_tex(q)
    r = client.post("/api/ingest/preview", json={
        "text": tex, "book": q.meta.get("book") or "接口测试",
        "label": "补旧题", "backfill": True,
        "items": [{"block": 0, "points": [pid], "difficulty": "简单题"}],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["backfill"] is True, d.get("backfill")
    assert d["count"] == 1, d
    it = d["items"][0]
    assert it["same_key"] is True, it
    assert "points" in it["update_fields"], it["update_fields"]
    assert d["dup"]["update"] == 1 and d["dup"]["new"] == 0, d["dup"]


def test_ingest_multi_title_preview_assigns_block_sources():
    """多卷材料：每个题块归到前面最近的 \title，界面据此预填单题出处。"""
    text = r"""\title{2024年甲卷}
\begin{question}
已知 $111110001+1=111110002$，则 $111110002-1$ 等于 \paren[A]
\begin{choices}\item $111110001$\item $111110002$\item $111110003$\item $111110004$\end{choices}
\begin{solution}
$111110002-1=111110001$。故选 A。
\end{solution}
\end{question}
\title{2025年乙卷}
\begin{question}
已知 $222220001+1=222220002$，则 $222220002-1$ 等于 \paren[A]
\begin{choices}\item $222220001$\item $222220002$\item $222220003$\item $222220004$\end{choices}
\begin{solution}
$222220002-1=222220001$。故选 A。
\end{solution}
\end{question}
"""
    r = client.post("/api/ingest/preview", json={
        "text": text, "book": "接口测试", "label": "精选模拟题", "year": 2026,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["count"] == 2, d
    assert len(d.get("source_titles") or []) == 2, d.get("source_titles")
    assert d["items"][0]["block_title"] == "2024年甲卷", d["items"][0]
    assert d["items"][1]["block_title"] == "2025年乙卷", d["items"][1]
    assert d["items"][0]["block_year"] == 2024, d["items"][0]


def test_ingest_preview_image_only_from_source_dir():
    """干跑带图题：卡片能取来源目录里的原图；不能越权读 /etc。"""
    import base64
    import tempfile

    d = Path(tempfile.mkdtemp())
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    (d / "fig.png").write_bytes(png)
    text = r"""\begin{question}
如图，求角。
\includegraphics[width=2cm]{fig.png}
\begin{solution}
略。
\end{solution}
\end{question}
"""
    r = client.post("/api/ingest/preview", json={
        "text": text, "book": "图测试", "label": "L", "year": 2026,
        "src_dir": str(d),
    })
    assert r.status_code == 200, r.text
    it = r.json()["items"][0]
    previews = it.get("figure_previews") or {}
    assert previews, it
    rel = next(iter(previews.values()))
    r = client.get("/api/ingest/preview-image",
                   params={"path": rel, "src_dir": str(d)})
    assert r.status_code == 200 and r.content == png, (r.status_code, r.text[:80])
    r = client.get("/api/ingest/preview-image",
                   params={"path": "/etc/passwd", "src_dir": str(d)})
    assert r.status_code == 404, r.text


def test_ingest_near_threshold_is_configurable():
    """95% 阈值可配：同一近似题，99% 不跳、95% 跳。"""
    from amti import render_tex, store

    q = next((x for x in store.load_cached()
              if "已知" in (x.stem or "") and x.has_solution
              and x.answer.strip() and not x.figures), None)
    if q is None:
        print("    （库里没有合适的「已知」题，跳过）")
        return
    tex = render_tex.question_to_tex(q).replace("已知", "若", 1)
    base = {"text": tex, "book": "接口测试", "label": "阈值"}
    d95 = client.post("/api/ingest/preview", json={**base, "near_threshold": 0.95}).json()
    d99 = client.post("/api/ingest/preview", json={**base, "near_threshold": 0.99}).json()
    assert d95["items"][0]["near_dup"] is True, d95["items"][0]
    assert d99["items"][0]["near_dup"] is False, d99["items"][0]


def test_llm_status_and_empty_unload():
    """模型状态可读；空模型名的卸载请求必须 400，不能真卸。"""
    r = client.get("/api/llm/status")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "tag_model" in d and "loaded" in d, d
    r = client.post("/api/llm/unload", json={"model": ""})
    assert r.status_code == 400, r.text


def test_search_covers_tags_and_source():
    r"""搜索框写着「搜索题目、答案、考点、出处」——**四类都得真能搜**。

    回归的坑：后端原来只比 `stem` 与 `answer` 两个字段，于是搜「余弦定理」
    只出 4 道（题干里恰好印着这四个字的），而库里打了这个考点标签的有 900 多道
    ——用户看到的是"标签搜索搜不出来"，实际是检索没查标签与出处。
    """
    def tot(**p):
        r = client.get("/api/questions", params={**p, "limit": 1})
        assert r.status_code == 200, r.text
        return r.json()["total"]

    by_point = tot(point="6.4.2")
    assert by_point > 0, "考点筛选本身就该有结果，否则这条用例测不出东西"
    assert tot(q="6.4.2") == by_point, "搜考点编号应当等于按该考点筛选（同一口径）"
    assert tot(q="余弦定理") >= by_point, "搜考点**名称**不该比按 id 筛的少"
    assert tot(q="2026精选模拟题") > 0, "出处（书名/卷名）没进检索"
    assert tot(q="已知集合") > 0, "题干正文的检索不许被改坏"


def test_stats_detail_health_fields():
    """题库体检：每个考点要带难度分布，来源/无标签来源要算出来。"""
    d = client.get("/api/stats/detail").json()
    assert d["points_covered"] <= d["points_total"]
    assert d["all_points"], "体检页没有考点数据"
    p = d["all_points"][0]
    assert set(p["by_diff"]) == {"简单题", "中档题", "难题"}, p.get("by_diff")
    assert d["by_source"], "来源统计为空"
    assert d["by_point_source"], "考点来源统计为空"


def test_point_source_filter_matches_health_stats():
    r"""体检页「无标签来源」点进去，列表数必须**正好**是卡片上的数。

    用户问的：「这个无标签来源怎么看」——卡片/队列现在可点，
    `point_source=无` 与 `/api/stats/detail` 的 `or "无"` 必须是同一口径。
    """
    d = client.get("/api/stats/detail").json()
    want = next((x["n"] for x in d["by_point_source"] if x["value"] == "无"), None)
    assert want is not None, d["by_point_source"]
    r = client.get("/api/questions", params={"point_source": "无", "limit": 1}).json()
    assert r["total"] == want, (r["total"], want)
    # 具体来源（如 llm）同样能筛，且互不重叠
    one = next(x for x in d["by_point_source"] if x["value"] != "无")
    r2 = client.get("/api/questions", params={"point_source": one["value"], "limit": 1}).json()
    assert r2["total"] == one["n"], (one, r2["total"])


def test_replace_candidates():
    """单题换题：同题型、排除卷内已用、带匹配理由；坏 key 要 404。"""
    cur = client.get("/api/questions?type=single_choice&limit=1").json()["items"][0]
    r = client.post("/api/generate/replace", json={
        "key": cur["key"], "type": cur["type"], "exclude": [cur["key"]], "limit": 5,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["items"], "没有返回候选"
    assert len(d["items"]) <= 5
    for it in d["items"]:
        assert it["key"] != cur["key"]
        assert it["type"] == cur["type"]
        assert set(it["match"]) == {"topic", "section", "difficulty"}

    bad = client.post("/api/generate/replace", json={"key": "no/such/key"})
    assert bad.status_code == 404


def test_trash_delete_needs_no_password_but_rejects_bad_reason():
    """删题**不再要口令**；原因必须是给定选项，拒绝时不动数据。"""
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    # 不带 password，给一个不在选项里的原因：必须走到「原因」校验，而不是「口令」
    r = client.post("/api/trash/delete",
                    json={"keys": [key], "reason": "接口测试乱填的原因"})
    assert r.status_code == 400, r.status_code
    assert "原因" in r.json()["detail"], r.json()
    # 确认没被删掉
    assert client.get(f"/api/questions/{_enc(key)}").status_code == 200


def test_trash_purge_still_requires_password():
    """清空回收站/永久删除不可恢复，仍然要口令（删题已不需要）。"""
    r = client.post("/api/trash/purge", json={"keys": [], "password": "错的"})
    assert r.status_code in (400, 403), r.status_code


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


# ── 改源码（详情页「改源码」）──────────────────────────────────
#
# 源码是题库的真相，所以接口的规矩是：
#   ① **不设口令**（用户明确说没必要）；只接受正文，元数据不进来；
#   ② 干跑 / 保存走**同一套**解析 + 规范化 + 规范审查；
#   ③ 一个字没改时**不写盘**（否则整库重写的 mtime 会把别的进程白白打回）。
# 下面只做**不落盘**的用例；真写盘的手工联调过（改一道再原样还原）。

def test_source_get_check_and_noop_save():
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    enc = _enc(key)
    cur = client.get(f"/api/questions/{enc}").json()
    before = cur["hash"]

    # **不设口令**：空 body 就直接给源码；返回的必须就是写进 .tex 的正文
    r = client.post(f"/api/questions/{enc}/source", json={})
    assert r.status_code == 200, r.text
    d = r.json()
    tex = d["tex"]
    assert d["hash"] == before
    assert tex.lstrip().startswith(("\\begin{question}", "\\begin{problem}")), tex[:40]

    # 干跑：同一个源码通过，且带渲染预览（前端「检查」直接画它）
    r = client.post(f"/api/questions/{enc}/source",
                    json={"tex": tex, "expect_hash": before})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and d["saved"] is False
    assert d["tex"] and d["blocks"]["stem"], "检查结果要能直接预览"

    # 坏源码：结构问题要逐条报出来，而且**一个字节都不写**
    r = client.post(f"/api/questions/{enc}/source",
                    json={"tex": "\\begin{question}\\end{question}",
                          "expect_hash": before})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is False and d["problems"], d
    assert client.get(f"/api/questions/{enc}").json()["hash"] == before

    # 保存但一个字没改：不写盘，明确回 unchanged
    r = client.post(f"/api/questions/{enc}/source",
                    json={"tex": tex, "expect_hash": before, "dry_run": False})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and d["saved"] is False and d.get("unchanged") is True, d
    assert client.get(f"/api/questions/{enc}").json()["hash"] == before


def test_source_edit_serializes_metadata_and_body_in_sync():
    r"""改源码 → 写进 `.tex` 的**元数据行和正文必须同步**。

    这是「源头是不是一份真相」的回归：源码编辑最后落盘的是
    `store.render_question(q)`——`%% @q`（key/type/options/answer/solution/
    hash/meta/points）和 `\begin{question}…` 由**同一个 Question** 生成。
    这里在内存里走一遍同一套序列化（不写盘），确认写出去再读回来没变。
    """
    import json
    from amti import store
    from amti.web.routers.questions import _source_candidate

    key = client.get("/api/questions?has=解析&limit=1").json()["items"][0]["key"]
    tex = client.get(f"/api/questions/{_enc(key)}").json()["tex"]
    marker = "（源码编辑回归测试）"
    edited = tex.replace("\\end{solution}", marker + "\n\\end{solution}", 1)
    assert edited != tex, "样本没有 solution 环境，测试已失效"

    q = store.find(key)
    cand, _before, _fixed, after, problems = _source_candidate(q, edited)
    assert not problems and not after, (problems, after)
    assert marker in cand.solution
    assert cand.points == q.points, "考点标签不能被源码编辑弄丢"
    assert cand.meta.get("difficulty") == q.meta.get("difficulty")

    block = store.render_question(cand)
    back = store.question_from_block(block)
    assert back is not None
    assert back.content_hash() == cand.content_hash(), "写出去再读回来内容变了"
    meta = json.loads(store.META_RE.search(block).group(1))
    assert meta["hash"] == cand.content_hash(), "元数据里的指纹没跟着正文更新"
    assert meta["solution"] == cand.solution, "元数据里的解析和正文不一致"
    assert meta["points"] == cand.points, "元数据里的考点没同步"
    assert meta["key"] == q.key, "源码编辑不能换 key"


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
    # 清掉刚生成的 .tex 和它记进「存档」的一条，别在用户的资料夹/存档里留垃圾
    import pathlib as _pl
    from amti import papers
    _pl.Path(r["tex_abs"]).unlink(missing_ok=True)
    papers.remove(r.get("name") or "")


def test_export_classified_into_kind_folders():
    r"""导出**按卷型分类落盘**：试卷 / 测试卷 / 讲义（用户要求）。

    `数据/导出位置.txt` 指向哪儿，就在哪儿下面建这三个子目录；
    `saved_hint` 要报**真实的分类目录**（`阿明的辅导讲义/试卷/`），
    不能还写「已保存到 阿明的辅导讲义/」——那会让人去错文件夹翻。

    分类名是**唯一来源**（`amti.paths.OUT_KINDS`），这里顺带钉住它，
    免得以后哪一处又自己写一个「试卷」字符串。
    """
    from amti import export, store, papers, paths

    keys = [q.key for _f, q in store.iter_questions()][:1]
    assert keys, "库里没有题，测不了导出"
    want = {"gaokao": "试卷", "test": "测试卷", "handout": "讲义"}
    assert set(want.values()) == set(paths.OUT_KINDS), "分类名与 paths 不一致"
    for mode, fold in want.items():
        name = f"分类自检_{mode}"
        r = export.export(keys, title="__分类自检", out=name,
                          mode=mode, do_compile=False)
        assert r.get("ok"), f"{mode} 导出失败：{r.get('error') or r}"
        assert r.get("kind") == fold, f"{mode} 分类错了：{r.get('kind')}"
        tex = Path(r["tex_abs"])
        try:
            assert tex.parent.name == fold, f"{mode} 落到了 {tex.parent}"
            assert paths.out_kind_label(fold) in r["saved_hint"], r["saved_hint"]
            assert r["dir_abs"] == str(paths.out_kind_dir(fold)), r["dir_abs"]
        finally:
            tex.unlink(missing_ok=True)
            papers.remove(r.get("name") or name)     # 别往存档里留测试卷

    # 分类会被拼进路径：`../` 这类值必须拒掉，不能只靠 name 那层清洗
    r = export.export(keys, title="x", kind="../逃逸", do_compile=False)
    assert r.get("ok") is False and r.get("error"), "非法分类必须被拒"


def test_settings_reports_kind_folders():
    """`/api/settings` 要把**分类子目录**告诉界面，前端不能再写死「试卷/」。"""
    d = client.get("/api/settings").json()
    assert d.get("out_name"), d
    assert d.get("kinds", {}).get("gaokao") == "试卷", d
    assert d.get("kinds", {}).get("test") == "测试卷", d
    assert d.get("kinds", {}).get("handout") == "讲义", d
    # 「考点覆盖卷」在界面上是独立卷型，但归 试卷（渲染用 test 卷型）
    assert d.get("kinds", {}).get("coverage") == "试卷", d


def test_export_preview_does_not_archive_or_count():
    r"""「编译预览」只编译：产物进 `数据/预览/`，**不存档、不计使用频次**。

    以前两个按钮走同一个 `run()`：点一次预览，用户资料夹里多一份 PDF，
    题目的「用过 N 次」还 +1（默认按 used 排序都跟着变）。
    """
    from amti import papers, paths, store
    from amti.web import server as srv

    keys = [q.key for _f, q in store.iter_questions()][:1]
    assert keys, "库里没有题，测不了导出"
    name = "预览自检"
    usage_before = dict(srv._usage())
    archived_before = {x.get("name") for x in papers.all_items()}
    r = client.post("/api/export", json={
        "keys": keys, "title": "__预览自检", "out": name,
        "mode": "gaokao", "preview": True, "compile": False,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    try:
        assert d.get("ok") and d.get("preview") is True, d
        assert Path(d["tex_abs"]).parent == paths.PREVIEW_DIR, d["tex_abs"]
        assert "预览" in d.get("saved_hint", ""), d.get("saved_hint")
        assert {x.get("name") for x in papers.all_items()} == archived_before, \
            "预览不该进存档"
        assert srv._usage() == usage_before, "预览不该改使用频次"
    finally:
        Path(d["tex_abs"]).unlink(missing_ok=True)


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


def test_blank_for_compact_sentinel():
    r"""解答题留白：0 = 按难度 3/5/8，正数 = 一律，**负数 = 不留白**（紧凑版）。"""
    from amti.paper import blank_for

    assert blank_for("简单题", 0) == 3.0
    assert blank_for("中档题", 0) == 5.0
    assert blank_for("难题", 0) == 8.0
    assert blank_for("难题", 4) == 4.0
    assert blank_for("难题", -1) == 0.0, "紧凑版（-1）必须真的不留白"


def test_rename_migrates_ledger_and_meta_refs():
    r"""改出处换 key 时：订正台账要迁，别的题 meta 里的 key 引用也要迁。

    - `数据/订正台账.json` 的 `patches[].key` / `retired[]` 不迁 → `fixups.run`
      一条对不上就整批不执行；
    - `dup_of` / `also_in` / `merged_keys` 不迁 → 查重提示/孪生题对账指向空。
    """
    from amti.web.routers import questions as srv

    assert "数据/订正台账.json" in srv._KEY_REF_FILES, "改名落点漏了订正台账"

    class X:
        def __init__(self, meta):
            self.meta = meta

    a = X({"dup_of": "a#1"})
    b = X({"also_in": ["x", "a#1"], "merged_keys": ["a#1", "y"]})
    c = X({"dup_of": "other#2"})
    n = srv._migrate_meta_refs([a, b, c], "a#1", "b#2")
    assert n == 3, n
    assert a.meta["dup_of"] == "b#2"
    assert b.meta["also_in"] == ["x", "b#2"]
    assert b.meta["merged_keys"] == ["b#2", "y"]
    assert c.meta["dup_of"] == "other#2", "别的题不能被误改"


def test_migrate_key_refs_rewrites_ledger_json_safely():
    r"""`_migrate_key_refs` 要能迁「订正台账」这种带数组/对象的 JSON，
    并且**改完仍是合法 JSON**（改坏了宁可不写）。"""
    import json
    import tempfile
    from amti.web.routers import questions as srv

    d = Path(tempfile.mkdtemp())
    f = d / "台账.json"
    f.write_text(json.dumps({"patches": [{"key": "a#1", "why": "x"}],
                             "retired": ["a#1", "other#2"]}, ensure_ascii=False),
                 encoding="utf-8")
    old = srv._KEY_REF_FILES
    srv._KEY_REF_FILES = (str(f),)
    try:
        moved = srv._migrate_key_refs("a#1", "b#2")
    finally:
        srv._KEY_REF_FILES = old
    assert moved == [str(f)], moved
    data = json.loads(f.read_text(encoding="utf-8"))
    assert data["patches"][0]["key"] == "b#2"
    assert data["retired"] == ["b#2", "other#2"]


def test_retry_on_concurrent_retries_then_succeeds():
    r"""装饰器要真的能接住 `store.ConcurrentWrite` —— 端点里先转成 409 的话它永远接不到。"""
    from amti.store import ConcurrentWrite
    from amti.web.retry import retry_on_concurrent

    calls = {"n": 0}

    @retry_on_concurrent
    def f():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConcurrentWrite("模拟并发写")
        return "ok"

    assert f() == "ok" and calls["n"] == 3, calls


def test_export_prints_source_and_drops_difficulty():
    r"""卷面上**印出处、不印难度**（用户要求：所有导出都跟讲义一样）。

    三种卷型一视同仁：题干第一行并上「（2024新高考I卷）」，**不印原卷
    的「第 1 题」**（用户明确说没必要）；难度星（`$\star$`）与卷首的
    「难度分布」都不许再出现在产物里。`show_source=False` 时整套出处消失。

    ⚠️ 为什么三种卷型一起断言：这两样都是**渲染期**的东西，而渲染分两条路
    （`_q_tex` 走 gaokao/test、`_render_handout` 走 handout）。只盯一条路的话，
    另一条会悄悄退回"印难度、不印出处"——本项目最忌讳的正是这种不一致
    （预览与导出、两个卷型，各印各的）。
    """
    from amti import paper, store
    from amti.paper import source_label

    q = next((x for _f, x in store.iter_questions()
              if x.type == "single_choice" and source_label(x)), None)
    assert q is not None, "库里没有带出处的高考单选题，测不了"

    lab = source_label(q)
    import re
    assert not re.search(r"第\s*\d+\s*题", lab), f"出处还带原卷题号：{lab}"
    # 模拟题的 `meta.source_label` 里有 611 道把原卷题号粘在卷名后面
    # （「浙江七彩阳光联盟返校考第 6 题」）——出口也必须剪掉。
    dirty = next((x for _f, x in store.iter_questions()
                  if re.search(r"第\s*\d+\s*题",
                               str((x.meta or {}).get("source_label") or ""))), None)
    if dirty is not None:
        assert not re.search(r"第\s*\d+\s*题", source_label(dirty)), \
            f"模拟题出处还带原卷题号：{dirty.key} -> {source_label(dirty)}"
    for mode in ("gaokao", "test", "handout"):
        tex = paper.render_paper([q], mode=mode, title="__接口测试_出处")
        tag = "（%s）" % lab
        assert tag in tex, f"{mode} 卷面没印出处：{lab}"
        assert r"\star" not in tex, f"{mode} 卷面还在印难度星"
        assert "难度分布" not in tex, f"{mode} 卷首还在印难度分布"
        # **出处与题干同一行**（用户要求：括号 + 与题目同排，不另起一行）
        line = next(ln for ln in tex.split("\n") if tag in ln)
        assert line.split(tag, 1)[1].strip(), f"{mode} 的出处单独占了一行"
    # 出处可以整套关掉（界面上的「印出处」开关）
    off = paper.render_paper([q], mode="test", title="__接口测试_出处", show_source=False)
    assert ("（%s）" % lab) not in off, "show_source=False 时卷面还在印出处"


def test_choices_columns_left_to_exam_zh():
    r"""选项列数**不许在 Python 里估**——不写 `columns` 交给 exam-zh 量。

    原来 `paper.choices_columns()` 按源码长度猜宽度（每个 `$…$` 一律折 5 个
    半角宽），数学选项全被判成"短"：`$\{x\mid x<-1\}\cup\{x\mid x>2\}$` 排出来
    近 5cm，源码里只是个 `$…$` → 判成 4 列 → C/D 在自己的格子里折行，
    卷面上就是「A B C D 挤一行、尾巴掉到下一行」（用户报的截图那张）。

    真实宽度只有 TeX 量得准，而 `choices` 环境不给 `columns` 时本来就是自动的
    （`exam-zh-choices.sty` 里 `\__examzh_choices_calc_columns:`：把每个选项排成
    hbox 取自然宽度再算列数，4→2→1 折半）。所以：

    * 默认产物里**一个 `[columns = N]` 都不许有**（有＝又有人在估宽度了）；
    * 显式传 `columns=N` 时才钉死（考点本那种"整份文档一个列数"的场合）。
    """
    from amti import paper, store

    q = next((x for _f, x in store.iter_questions() if x.options), None)
    assert q is not None, "库里没有带选项的题，测不了列数"

    auto = paper.question_tex(q, show_answers=False)
    assert "[columns" not in auto, (
        "默认没有让 exam-zh 自己选列数：卷面上又会出现折行的选项\n"
        + next(ln for ln in auto.split("\n") if "choices" in ln))

    pinned = paper.question_tex(q, show_answers=False, columns=2)
    assert "[columns = 2]" in pinned, "显式要求钉死列数时没生效"


def test_placeholder_solution_counts_as_missing():
    r"""「解析无」是**占位符**，不是解析。

    录入规矩（`amti/record.py`）：没有解析就写「解析无」。可消费端原来一律
    用 `bool(q.solution.strip())` 判断，于是 1202 道占位题被当成"解析齐全"：
    求解器的待解队列、`missing=解析` 筛选、录入升级全都漏掉它们。

    口径只能有一处，就是 `Question.has_solution`。
    """
    from amti.schema import Question

    q = Question(key="t/ph", type="fill_in_blank", stem=r"$1+1=$\fillin{}。",
                 answer="2", solution="解析无")
    assert not q.has_solution, "占位符被当成真解析了"
    assert "解析" in q.missing(), "缺解析没被报出来"

    q.solution = "由 $1+1=2$ 得。"
    assert q.has_solution and "解析" not in q.missing(), "真解析被误判成缺失"


def test_placeholder_solution_enters_solver_queues():
    r"""占位题必须进得了「补解析」队列，否则永远补不上。"""
    from amti import exchange, solve

    for q in solve.fill_todo("sol")[:50]:
        assert not q.has_solution, f"{q.key} 已经有解析，不该在补解析队列里"
    for q in exchange.pending(stage="solution")[:50]:
        assert not q.has_solution, f"{q.key} 已经有解析，不该在待解队列里"


def test_api_placeholder_solution_is_missing():
    r"""接口的 `flags["解析"]` 与筛选必须同一口径。

    ⚠️ 断言的是**与库内同口径的相等**，不是写死一个题数：
    缺解析的题会随着补解析变少（2026-10 一次落账就从 1208 降到 293），
    写死 1000 只会让「补完解析」这个正常动作把测试打红。
    """
    from amti import store
    want = sum(1 for q in store.load_all() if not q.has_solution)
    d = client.get("/api/questions?missing=解析&limit=1").json()
    assert d["total"] == want, "筛选数与库内口径不一致：%d vs %d" % (d["total"], want)
    # `want == 0` 是**合法状态**：全库解析补齐后就该是 0，别把"补齐了"当成测试坏了。
    if want:
        item = d["items"][0]
        assert item["flags"]["解析"] is False, "缺解析的题被标成有解析"

    real = client.get("/api/questions?has=解析&limit=1").json()["items"][0]
    assert real["flags"]["解析"] is True, "有解析的题被标成缺失"


def test_ingest_upgrades_placeholder_solution():
    r"""库里写「解析无」，新录入带真解析 → 该升级（不能当"已有解析"跳过）。"""
    from amti import ingest
    from amti.schema import Question

    old = Question(key="t/up", type="fill_in_blank", stem=r"$1+1=$\fillin{}。",
                   answer="2", solution="解析无")
    new = Question(key="t/up", type="fill_in_blank", stem=old.stem,
                   answer="2", solution="因为 $1+1=2$。")
    plan = ingest.merge_plan(old, new)
    assert plan.get("solution") == new.solution, f"占位解析没被升级：{plan}"


def test_store_roundtrip_preserves_every_field():
    r"""存储序列化**必须**字节级往返：写出去再读回来，内容指纹不变。

    这条是血的教训：曾经为了让导出别印「解析无」，把占位符从
    `render_tex.question_to_tex` 里跳过不写——而那正是**存储序列化器**。
    结果 1205 道题在一次整库重写后 `solution` 变成空串，key 集合完全正常，
    `rewrite_all` 的回读校验也没拦住（它当时只核 key）。

    现在 `rewrite_all` 会逐题核内容指纹；这里再补一条最小往返用例。
    """
    from amti import store
    from amti.schema import Question

    for sol in ("解析无", "无", "由 $1+1=2$ 得。"):
        q = Question(key="t/rt", type="fill_in_blank",
                     stem=r"$1+1=$\fillin{}。", answer="2", solution=sol)
        back = store.question_from_block(store.render_question(q))
        assert back is not None, "写出去再读回来失败了"
        assert back.content_hash() == q.content_hash(), (
            f"往返后内容变了：solution {sol!r} → {back.solution!r}")


def test_export_skips_placeholder_solution_but_storage_keeps_it():
    r"""「解析无」导出时不印，但**存储必须原样写**。

    这两件事原来搅在一起：为了让导出别印占位符，改了存储序列化器，
    一次整库重写清空了 1205 道题的 `solution`。现在分工明确：
      · `paper.question_tex`（导出）→ `skip_no_solution=True`
      · `store.render_question`（存储）→ 默认 False，一个字段不许少
    """
    from amti import paper, store
    from amti.schema import Question

    # 用内存里造的一道题，不依赖库里恰好还剩占位题——
    # 2026-10 全库解析补齐后占位题已是 0 道，靠"从库里找"会让测试在正常状态下红。
    q = Question(key="t/placeholder", type="fill_in_blank",
                 stem=r"$1+1=$\fillin{}。", answer="2", solution="解析无")
    out = paper.question_tex(q, show_answers=True)
    assert "解析无" not in out, "导出还在印占位符"
    assert "解析无" in store.render_question(q), "存储序列化把占位符弄丢了"


# ── 完整度筛选里「图」的两层意思 ───────────────────────────────

def test_has_figure_filter_returns_real_figures():
    r"""`has=有图` 出来的必须**真的有图**；`图` 是完整度，别混用。

    坑（用户报的）：`flags.图` 的意思是「图不缺」——有图，**或者这题本来
    不需要图**，全库 98% 都是 true。前端「只看有·图」原来拿它去筛，出来
    两万八，列表里全是纯代数题。现在「看有」走 `有图`（后端单独算），
    「看缺」仍走 `图`（说了如图却没有图）。
    """
    d = client.get("/api/questions", params={"has": "有图", "limit": 50}).json()
    assert d["total"] > 0, "库里应当有带图的题"
    assert all(it["flags"]["有图"] for it in d["items"]), "`有图` 筛出了没有图的题"

    plain = client.get("/api/questions", params={"has": "解析", "limit": 50}).json()
    assert any(it["flags"]["图"] and not it["flags"]["有图"] for it in plain["items"]), \
        "`图` 与 `有图` 应当能分开：不需要图的题 图=True 而 有图=False"

    miss = client.get("/api/questions", params={"missing": "图", "limit": 50}).json()
    assert all(not it["flags"]["图"] for it in miss["items"]), "`缺图` 筛出了图不缺的题"


# ── 改出处（PATCH source）────────────────────────────────────────

def _derivable_key(q: dict) -> bool:
    """这道题的 key 是不是由 `书/卷名#号` 拼出来的（后端改名只看这一种）。"""
    meta = q.get("meta") or {}
    key = q.get("key") or ""
    tail = key.rsplit("#", 1)[-1] if "#" in key else ""
    return bool(tail) and key == "%s/%s#%s" % (meta.get("book") or "",
                                               meta.get("source_label") or "", tail)


def test_patch_source_meta_only_when_key_not_derivable():
    r"""key 不是出处拼出来的题（`书/年份/卷名#号`）——改出处**只改标签**。

    这是真踩过的坑：`高考真题汇编/2024/新高考I卷#1` 的出处是
    `2024年新高考I卷`，按 meta 重拼 key 会把它改成 `书/2024年新高考I卷#1`，
    等于**悄悄换了身份**：基线里旧 key 变成"被删了"，组过的卷子也断引用。
    """
    items = client.get("/api/questions?limit=40").json()["items"]
    pick = next((it for it in items if not _derivable_key(it)), None)
    if pick is None:
        print("    （前 40 道都同构，跳过反例）")
        return
    full = client.get(f"/api/questions/{_enc(pick['key'])}").json()
    meta = full.get("meta") or {}
    book, label, year = meta.get("book") or "", meta.get("source_label") or "", meta.get("year") or ""
    ledger = ROOT / "数据" / "改出处.jsonl"
    old_ledger = ledger.read_text(encoding="utf-8") if ledger.is_file() else None
    audit_dir = ROOT / "变更记录"
    before_logs = set(audit_dir.glob("*界面改出处*")) if audit_dir.exists() else set()
    try:
        r = client.patch(f"/api/questions/{_enc(pick['key'])}",
                         json={"source": {"book": book, "label": label + "（测试）", "year": year}})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["key"] == pick["key"], "key 不该跟着出处改：%s" % d["key"]
        assert not d.get("renamed_from"), d.get("renamed_from")
        assert (d["meta"].get("source_label") or "").endswith("（测试）"), d["meta"]
        assert d["hash"] == full["hash"], "改出处不该动内容指纹"
    finally:
        back = client.patch(f"/api/questions/{_enc(pick['key'])}",
                            json={"source": {"book": book, "label": label, "year": year}})
        assert back.status_code == 200, back.text
        assert back.json()["meta"].get("source_label") == label
        for f in set(audit_dir.glob("*界面改出处*")) - before_logs:
            f.unlink(missing_ok=True)
        if old_ledger is None:
            ledger.unlink(missing_ok=True)
        else:
            ledger.write_text(old_ledger, encoding="utf-8")


def test_patch_source_rename_roundtrip():
    r"""key 就是 `书/卷名#号` 的题：改出处 → key 跟着改 → 改回来，一字不差。

    守的是「改了出处，先前组进卷子/讲义的引用会不会断」这条链：
      · 内容指纹**不能变**（出处是标签，不是正文）；
      · 旧 key 立刻取不到、新 key 取得到。
    **真改 key，所以 finally 里必须还原**（和改难度那条一个道理）。
    """
    items = client.get("/api/questions?limit=40").json()["items"]
    pick = next((it for it in items if _derivable_key(it)), None)
    if pick is None:
        print("    （前 40 道都不同构，跳过改名用例）")
        return
    key = pick["key"]
    full = client.get(f"/api/questions/{_enc(key)}").json()
    meta = full.get("meta") or {}
    book, label, year = meta.get("book") or "", meta.get("source_label") or "", meta.get("year") or ""
    before_hash = full["hash"]
    tail = key.rsplit("#", 1)[-1]
    tmp_label = label + "（测试改名）"

    ledger = ROOT / "数据" / "改出处.jsonl"
    old_ledger = ledger.read_text(encoding="utf-8") if ledger.is_file() else None
    audit_dir = ROOT / "变更记录"
    before_logs = set(audit_dir.glob("*界面改出处*")) if audit_dir.exists() else set()
    cur_key = key
    try:
        r = client.patch(f"/api/questions/{_enc(cur_key)}",
                         json={"source": {"book": book, "label": tmp_label, "year": year}})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["key"] == f"{book}/{tmp_label}#{tail}", d["key"]
        assert d.get("renamed_from") == cur_key, d.get("renamed_from")
        assert d["hash"] == before_hash, "改出处不该动内容指纹"
        assert client.get(f"/api/questions/{_enc(cur_key)}").status_code == 404, "旧 key 该失效"
        cur_key = d["key"]
        assert client.get(f"/api/questions/{_enc(cur_key)}").status_code == 200
    finally:
        if cur_key != key:
            back = client.patch(f"/api/questions/{_enc(cur_key)}",
                                json={"source": {"book": book, "label": label, "year": year}})
            assert back.status_code == 200, back.text
            assert back.json()["key"] == key, back.json()["key"]
        for f in set(audit_dir.glob("*界面改出处*")) - before_logs:
            f.unlink(missing_ok=True)
        if old_ledger is None:
            ledger.unlink(missing_ok=True)
        else:
            ledger.write_text(old_ledger, encoding="utf-8")


def test_patch_source_rename_keeps_usage_count():
    r"""改出处换 key 时，**使用频次**跟着迁到新 key（不能归零）。

    用户可观察的后果：改完出处，这道题「被组过 N 次」归零；默认按使用频次
    排序，它会掉到后面，看起来像「我常用的题不见了」。
    后端只迁了存档（`_KEY_REF_FILES`），漏了 `数据/使用频次.json`——
    而且内存缓存 `_usage_cache` 也要一起换 key，否则下次导出写盘会覆盖回去。
    """
    from amti import store
    from amti.web import server as srv

    usage = srv._usage()
    pick = None
    for q in store.load_cached():
        tail = q.key.rsplit("#", 1)[-1] if "#" in q.key else ""
        meta = q.meta or {}
        if not tail or not usage.get(q.key):
            continue
        if q.key == "%s/%s#%s" % (meta.get("book") or "",
                                  meta.get("source_label") or "", tail):
            pick = q
            break
    if pick is None:
        print("    （没有「改得出 key 且用过」的题，跳过使用频次迁移用例）")
        return

    key = pick.key
    meta = pick.meta or {}
    book = meta.get("book") or ""
    label = meta.get("source_label") or ""
    year = meta.get("year") or ""
    tail = key.rsplit("#", 1)[-1]
    n = usage[key]
    tmp_label = label + "（测试改名）"
    ledger = ROOT / "数据" / "改出处.jsonl"
    old_ledger = ledger.read_text(encoding="utf-8") if ledger.is_file() else None
    audit_dir = ROOT / "变更记录"
    before_logs = set(audit_dir.glob("*界面改出处*")) if audit_dir.exists() else set()
    cur_key = key
    try:
        r = client.patch(f"/api/questions/{_enc(cur_key)}",
                         json={"source": {"book": book, "label": tmp_label, "year": year}})
        assert r.status_code == 200, r.text
        cur_key = r.json()["key"]
        assert srv._usage().get(cur_key) == n, (
            f"改名后使用频次没迁过去：{srv._usage().get(cur_key)!r}（应为 {n}）")
        assert key not in srv._usage(), "旧 key 的计数该被迁走，不能留一份"
    finally:
        if cur_key != key:
            back = client.patch(f"/api/questions/{_enc(cur_key)}",
                                json={"source": {"book": book, "label": label, "year": year}})
            assert back.status_code == 200, back.text
        assert srv._usage().get(key) == n, "改回来之后使用频次没还原"
        for f in set(audit_dir.glob("*界面改出处*")) - before_logs:
            f.unlink(missing_ok=True)
        if old_ledger is None:
            ledger.unlink(missing_ok=True)
        else:
            ledger.write_text(old_ledger, encoding="utf-8")


# ── 改题号（和出处一起改）──────────────────────────────────────

def _pick_src_question(derivable: bool) -> dict | None:
    """挑一道来源齐全、且 source_no 与 key 尾一致的题（改完能原样还原）。

    **走内存里的全库**（`store.load_cached`），不翻列表页——同构题集中在
    `模拟题` 这本书里，按使用频次排序的前几十页根本轮不到它们，
    只翻前 40 条的话这条用例会永远「跳过」，等于没测。
    """
    from amti import store
    for q in store.load_cached():
        meta = q.meta or {}
        if not meta.get("book") or not meta.get("source_label"):
            continue
        tail = q.key.rsplit("#", 1)[-1] if "#" in q.key else ""
        if not tail:
            continue
        ok = q.key == "%s/%s#%s" % (meta.get("book"), meta.get("source_label"), tail)
        if ok != derivable:
            continue
        if str(meta.get("source_no") or "") not in ("", tail):
            continue
        return {"key": q.key, "meta": meta}
    return None


def test_patch_source_number_rename_roundtrip():
    r"""改出处时**题号也能改**（key 里 `#` 后面那截）——换尾、source_no 跟着走。

    用户报的：「修改出处的时候，第几题也需要能够修改」。
    出处填错往往连题号一起错；只改书名/卷名的话，key 和卷面出处永远错着。

    **真改 key，所以 finally 里必须原样改回**（和改出处那条一个道理）。
    """
    pick = _pick_src_question(derivable=True)
    if pick is None:
        print("    （没有合适的同构题，跳过改题号用例）")
        return
    key = pick["key"]
    full = client.get(f"/api/questions/{_enc(key)}").json()
    meta = full.get("meta") or {}
    book, label, year = meta.get("book") or "", meta.get("source_label") or "", meta.get("year") or ""
    head, old_tail = key.rsplit("#", 1)
    # 同一卷里挑一个没被占的号，撞了往后顺延
    new_tail = str(int(old_tail) + 1)
    for _ in range(50):
        if client.get(f"/api/questions/{_enc(f'{head}#{new_tail}')}").status_code == 404:
            break
        new_tail = str(int(new_tail) + 1)

    ledger = ROOT / "数据" / "改出处.jsonl"
    old_ledger = ledger.read_text(encoding="utf-8") if ledger.is_file() else None
    audit_dir = ROOT / "变更记录"
    before_logs = set(audit_dir.glob("*界面改出处*")) if audit_dir.exists() else set()
    cur_key = key
    try:
        r = client.patch(f"/api/questions/{_enc(cur_key)}",
                         json={"source": {"book": book, "label": label,
                                          "year": year, "no": new_tail}})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["key"] == f"{head}#{new_tail}", d["key"]
        assert d.get("renamed_from") == cur_key, d.get("renamed_from")
        assert str(d["meta"].get("source_no") or "") == new_tail, d["meta"]
        assert d["hash"] == full["hash"], "改题号不该动内容指纹"
        assert client.get(f"/api/questions/{_enc(cur_key)}").status_code == 404, "旧 key 该失效"
        cur_key = d["key"]
        assert client.get(f"/api/questions/{_enc(cur_key)}").status_code == 200
    finally:
        if cur_key != key:
            back = client.patch(f"/api/questions/{_enc(cur_key)}",
                                json={"source": {"book": book, "label": label,
                                                 "year": year, "no": old_tail}})
            assert back.status_code == 200, back.text
            assert back.json()["key"] == key, back.json()["key"]
        for f in set(audit_dir.glob("*界面改出处*")) - before_logs:
            f.unlink(missing_ok=True)
        if old_ledger is None:
            ledger.unlink(missing_ok=True)
        else:
            ledger.write_text(old_ledger, encoding="utf-8")


def test_patch_source_number_keeps_historical_head():
    r"""key 不同构（`书/年份/卷名#号`）时改题号：**只换 `#` 后面那截**，目录不动。

    这条守的是别把「改题号」实现成「按出处重拼 key」：那会顺手把
    `高考真题汇编/2024/新高考I卷#1` 改成 `书/2024年新高考I卷#2`，等于换身份。
    """
    pick = _pick_src_question(derivable=False)
    if pick is None:
        print("    （没有合适的不同构题，跳过改题号用例）")
        return
    key = pick["key"]
    full = client.get(f"/api/questions/{_enc(key)}").json()
    meta = full.get("meta") or {}
    book, label, year = meta.get("book") or "", meta.get("source_label") or "", meta.get("year") or ""
    head, old_tail = key.rsplit("#", 1)
    new_tail = str(int(old_tail) + 1)
    for _ in range(50):
        if client.get(f"/api/questions/{_enc(f'{head}#{new_tail}')}").status_code == 404:
            break
        new_tail = str(int(new_tail) + 1)

    ledger = ROOT / "数据" / "改出处.jsonl"
    old_ledger = ledger.read_text(encoding="utf-8") if ledger.is_file() else None
    audit_dir = ROOT / "变更记录"
    before_logs = set(audit_dir.glob("*界面改出处*")) if audit_dir.exists() else set()
    cur_key = key
    try:
        r = client.patch(f"/api/questions/{_enc(cur_key)}",
                         json={"source": {"book": book, "label": label,
                                          "year": year, "no": new_tail}})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["key"] == f"{head}#{new_tail}", d["key"]
        assert d.get("renamed_from") == cur_key, d.get("renamed_from")
        cur_key = d["key"]
    finally:
        if cur_key != key:
            back = client.patch(f"/api/questions/{_enc(cur_key)}",
                                json={"source": {"book": book, "label": label,
                                                 "year": year, "no": old_tail}})
            assert back.status_code == 200, back.text
            assert back.json()["key"] == key, back.json()["key"]
        for f in set(audit_dir.glob("*界面改出处*")) - before_logs:
            f.unlink(missing_ok=True)
        if old_ledger is None:
            ledger.unlink(missing_ok=True)
        else:
            ledger.write_text(old_ledger, encoding="utf-8")


def test_patch_source_number_must_be_positive_int():
    r"""题号只收正整数：`abc` / `0` / `-3` / 空串都 400，且**什么都没写进去**。"""
    pick = _pick_src_question(derivable=True)
    if pick is None:
        print("    （没有合适的题，跳过题号校验用例）")
        return
    key = pick["key"]
    meta = (client.get(f"/api/questions/{_enc(key)}").json().get("meta") or {})
    src = {"book": meta.get("book") or "", "label": meta.get("source_label") or "",
           "year": meta.get("year") or ""}
    for bad in ("abc", "0", "-3", "", "  "):
        r = client.patch(f"/api/questions/{_enc(key)}",
                         json={"source": {**src, "no": bad}})
        assert r.status_code == 400, f"题号 {bad!r} 该被拒：{r.status_code} {r.text}"
    assert client.get(f"/api/questions/{_enc(key)}").json()["key"] == key, "被拒时不许改名"


def test_search_ranked_by_stem():
    """搜索默认按相关度：题干里问「函数」的，要排在只有考点名带「函数」的前面。"""
    d = client.get("/api/questions", params={"q": "函数", "limit": 5}).json()
    assert d["total"] > 0
    top = d["items"][0]
    assert "函数" in top["stem"] or any("函数" in t for t in top.get("point_titles") or []), top["key"]
    # 多词按 AND：不能因为整串带空格就 0 结果
    m = client.get("/api/questions", params={"q": "函数 单调", "limit": 6}).json()
    assert m["total"] > 0, m
    assert all("函数" in x["stem"] or any("函数" in t for t in x.get("point_titles") or [])
               for x in m["items"]), [x["key"] for x in m["items"]]


def test_answer_source_filter():
    """回填后每道题都有 answer_source；筛选计数与 facets 对得上。"""
    f = client.get("/api/facets").json()
    src = {x["value"]: x["n"] for x in f["answer_sources"]}
    assert src.get("legacy", 0) > 0 and src.get("human", 0) > 0
    d = client.get("/api/questions", params={"answer_source": "human", "limit": 1}).json()
    assert d["total"] == src["human"], (d["total"], src["human"])


def test_batch_patch_stars_roundtrip():
    """批量改标签：一次请求改一道，再还原；只写受影响的卷。"""
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    meta = client.get(f"/api/questions/{_enc(key)}").json().get("meta") or {}
    orig = int(meta.get("stars") or 0)
    orig_rv = bool(meta.get("reviewed_at"))
    audit = ROOT / "变更记录"
    before = set(audit.glob("*批量改标签*")) if audit.exists() else set()
    try:
        r = client.post("/api/questions/batch", json={"keys": [key], "stars": 1})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["changed"] == 1 and j["partial"] is True, j
        # 没改出处 → 不应有改名映射；字段本身必须存在（前端靠它迁移卷子引用）
        assert j.get("renames") == [], j
        assert client.get(f"/api/questions/{_enc(key)}").json()["meta"].get("stars") == 1
        # 批量复核：标记 → 取消，和单题接口共用 same reviewed_at
        r = client.post("/api/questions/batch", json={"keys": [key], "reviewed": True})
        assert r.status_code == 200 and \
            client.get(f"/api/questions/{_enc(key)}").json()["meta"].get("reviewed_at")
    finally:
        client.post("/api/questions/batch", json={"keys": [key], "stars": orig,
                                                   "reviewed": orig_rv})
        for f in set(audit.glob("*批量改标签*")) - before:
            f.unlink(missing_ok=True)


def test_batch_patch_rejects_bad_input():
    key = client.get("/api/questions?limit=1").json()["items"][0]["key"]
    r = client.post("/api/questions/batch", json={"keys": [key], "points": ["9.9.9"]})
    assert r.status_code == 400, r.text
    # 考点操作模式只认 replace/add/remove；传错直接 400（这一步不写盘）
    r = client.post("/api/questions/batch",
                    json={"keys": [key], "points": [], "point_mode": "swap"})
    assert r.status_code == 400, r.text
    # 正文不能从批量接口进（Pydantic extra=forbid）
    r = client.post("/api/questions/batch", json={"keys": [key], "stem": "改题干"})
    assert r.status_code == 422, r.text


def test_detailed_answer_field_and_leading_marks():
    """解答题答案栏只能是「见解析」；题干自带作答位的表格题除外。"""
    import re
    from amti import store
    from amti.latex_ir import fillin_answers, paren_answers
    qs = store.load_all()
    bad = []
    for q in qs:
        if q.type != "detailed_answer" or q.answer.strip() in ("", "见解析"):
            continue
        if fillin_answers(q.stem) or paren_answers(q.stem):
            continue          # 作答位在题干里，答案由 \fillin 读出来
        bad.append((q.key, q.answer[:30]))
    assert not bad, bad
    lead = re.compile(r"^\s*【(?:答案|解析|详解|解答)】")
    marks = [q.key for q in qs if lead.search(q.solution or "")]
    assert not marks, marks


def test_reviewed_filter_and_toggle():
    """复核标记：未复核 → 标记 → 已复核，筛选计数跟着变；再还原。"""
    f0 = client.get("/api/facets").json()
    c0 = {x["value"]: x["n"] for x in f0["reviewed_states"]}
    pick = client.get("/api/questions", params={"reviewed": "no", "limit": 1}).json()
    assert pick["items"], "应该还有未复核的题"
    key = pick["items"][0]["key"]
    audit = ROOT / "变更记录"
    before = set(audit.glob("*界面改标签*")) if audit.exists() else set()
    try:
        r = client.patch(f"/api/questions/{_enc(key)}", json={"reviewed": True})
        assert r.status_code == 200, r.text
        assert client.get(f"/api/questions/{_enc(key)}").json()["meta"].get("reviewed_at")
        f1 = client.get("/api/facets").json()
        c1 = {x["value"]: x["n"] for x in f1["reviewed_states"]}
        assert c1.get("yes", 0) == c0.get("yes", 0) + 1, (c0, c1)
        y = client.get("/api/questions", params={"reviewed": "yes", "limit": 1}).json()
        assert y["total"] == c1["yes"], (y["total"], c1)
    finally:
        client.patch(f"/api/questions/{_enc(key)}", json={"reviewed": False})
        for f in set(audit.glob("*界面改标签*")) - before:
            f.unlink(missing_ok=True)


def test_review_stats_and_queue():
    """审阅工作台：统计与队列口径一致，队列只出待审/失效。"""
    s = client.get("/api/review/stats").json()
    assert s["total"] >= 17249, s["total"]
    assert s["reviewed"] == s["approved"] + s["needs_fix"] + s["flagged"]
    assert s["pending"] == s["total"] - s["reviewed"], (s["pending"], s["total"], s["reviewed"])
    q = client.get("/api/review/queue", params={"limit": 3}).json()
    assert q["total"] == s["pending"], (q["total"], s["pending"])
    assert q["items"], "队列不应该为空"
    for it in q["items"]:
        assert it["review"]["status"] in ("pending", "stale"), it["review"]
        assert 0 <= it["review"]["risk"] <= 100
        assert isinstance(it["review"]["reasons"], list)
        assert it["blocks"]["stem"], "审阅要看题干块"


def test_review_sample_is_stratified_and_deterministic():
    a = client.post("/api/review/sample", json={"n": 8, "seed": 123}).json()
    b = client.post("/api/review/sample", json={"n": 8, "seed": 123}).json()
    assert a["batch_id"] and a["population"] >= 1
    assert len(a["items"]) <= 8 and len(a["items"]) == len(b["items"])
    assert [x["key"] for x in a["items"]] == [x["key"] for x in b["items"]]
    assert len({x["key"] for x in a["items"]}) == len(a["items"])
    assert a["strata"] and sum(x["sample"] for x in a["strata"]) == len(a["items"])


def test_review_decision_roundtrip_and_stale():
    """通过 → 写复核指纹；收回 → 回到待审；正文变化 → 派生 stale。"""
    from amti.review import effective_status
    from amti.schema import Question

    sample = client.post("/api/review/sample", json={"n": 6, "seed": 7}).json()
    item = next((x for x in sample["items"]
                 if x["review"]["status"] == "pending"), None)
    if item is None:
        print("    （样本里没有纯待审题，跳过写库用例）")
    else:
        key = item["key"]
        try:
            r = client.post("/api/review/decision", json={
                "items": [{"key": key, "status": "approved", "note": "接口测试"}],
                "reviewer": "测试", "batch_id": sample["batch_id"]})
            assert r.status_code == 200, r.text
            d = client.get("/api/questions/" + _enc(key)).json()
            assert d["review"]["status"] == "approved", d["review"]
            assert d["review"]["reviewed_hash"], d["review"]
            assert d["review"]["reviewed_by"] == "测试"
            assert d["review"]["batch"] == sample["batch_id"]
            y = client.get("/api/questions", params={"reviewed": "yes", "limit": 1}).json()
            assert y["total"] >= 1
            client.post("/api/review/decision", json={
                "items": [{"key": key, "status": "pending"}]})
            d = client.get("/api/questions/" + _enc(key)).json()
            assert d["review"]["status"] == "pending", d["review"]
        finally:
            client.post("/api/review/decision", json={
                "items": [{"key": key, "status": "pending"}]})

    q = Question(key="review/t1", type="single_choice",
                 stem="已知 $x=1$，则 $x+1=$\\paren[B]",
                 options=[], answer="B", solution="因为 $1+1=2$，故选 B。",
                 meta={"answer_source": "human", "solution_source": "human",
                       "point_source": "human"})
    from amti.review import apply_decision
    apply_decision(q, "approved", reviewer="测试")
    assert effective_status(q) == "approved"
    q.answer = "C"
    assert effective_status(q) == "stale", "改答案后旧复核必须失效"
    q2 = Question(key="review/t2", type="single_choice", stem="x",
                  options=[], answer="A", solution="略",
                  meta={"reviewed_at": "2026-01-01 10:00",
                        "edited_at": "2026-01-01 10:00"})
    assert effective_status(q2) == "stale", "旧的编辑自动戳不能算复核"


def test_review_decision_rejects_bad_status():
    sample = client.post("/api/review/sample", json={"n": 1, "seed": 1}).json()
    key = sample["items"][0]["key"]
    r = client.post("/api/review/decision", json={
        "items": [{"key": key, "status": "stale"}]})
    assert r.status_code == 400, r.text
    r = client.post("/api/review/decision", json={
        "items": [{"key": "没有这道题", "status": "approved"}]})
    assert r.status_code == 404, r.text


def test_search_fts_status():
    """FTS5 索引：一次搜索后应已建好、条数与题库一致。"""
    client.get("/api/questions", params={"q": "函数", "limit": 1})
    st = client.get("/api/search/status").json()
    assert st["exists"] and st["current"], st
    total = client.get("/api/questions", params={"limit": 1}).json()["total"]
    assert st["n"] == total, (st, total)


def test_pdf_layout_markers_and_score_seal():
    from amti import paper, store
    det = next(q for q in store.load_all() if q.type == "detailed_answer")
    tex = paper.render_paper([det], mode="test", title="体检",
                             qid_marks=True, score_box=True, seal_line=True)
    assert "% AMTIKU-DETAIL: 1" in tex
    assert "\\label{amtiq1}" in tex and "\\label{amtiqend1}" in tex
    assert "总分" in tex and "密封线内不要答题" in tex
    assert tex.count("\\needspace{12\\baselineskip}") >= 1


def test_pdf_brand_header_footer():
    r"""卷子和讲义都要有 AmTiKu 页眉页脚（**版式，不是水印**）。

    这条只钉 LaTeX 源码这一层：PDF 里到底排没排出来，由
    `accept` 的端到端/人工看图兜底（xelatex 才是真相）。
    """
    from amti import paper, store
    q = next(iter(store.load_all()))
    tex = paper.render_paper([q], mode="test", title="品牌页眉")
    assert r"\fancyhead[L]" in tex and r"\fancyhead[R]" in tex
    assert "AmTiKu" in tex and "K12 数学题库" in tex
    assert r"\fancyfoot[C]" in tex and r"\pageref{LastPage}" in tex
    # 讲义走的是另一个文档类（elegantnote），版式也必须同一份
    h = paper.render_paper([q], mode="handout", title="品牌讲义")
    assert r"\fancyhead[L]" in h and "AmTiKu" in h
    assert "K12 数学讲义" in h


def test_generate_target_minutes_note():
    d = client.post("/api/generate",
                    json={"mode": "gaokao", "seed": 3,
                          "target_minutes": 1}).json()
    notes = d["report"].get("notes") or []
    assert any("比目标 1 分钟多" in x for x in notes), notes


def test_list_and_generate_filters_agree():
    r"""列表与组卷必须用**同一个** `QuestionFilter`。

    工程化重构的回归保护：以前 `/api/questions` 和 `/api/generate` 各写
    一遍 15 个筛选维度，列表新增「地区/完整度/星级/质检」后组卷没跟上，
    用户筛到 300 道、组卷却从没筛的池子里挑。现在两边共用
    `amti/web/query.py`，这里用几个有代表性的组合钉住“池子大小一致”。
    """
    combos = [
        {"point": "1.1.1"},
        {"paper_state": "partial"},
        {"quality": "lowres"},
        {"region_scope": "multi"},
        # `小问` 不在元数据读模型的 flags 列里；必须回退 Python 过滤，
        # 否则列表会忽略这个条件、和组卷的池子对不上。
        {"point": "1.1.1", "has": "小问"},
    ]
    for f in combos:
        listed = client.get("/api/questions", params={**f, "limit": 1}).json()["total"]
        r = client.post("/api/generate",
                        json={**f, "mode": "test", "max_items": 5000})
        assert r.status_code == 200, (f, r.text)
        keys = r.json().get("keys") or []
        assert len(keys) == listed, (f, listed, len(keys))


def test_generate_region_filter_actually_applies():
    """`region` 以前只解析、没进循环——地区选择器实际不起作用。

    组卷的 `region` 是精确匹配 `meta.region`；只要选了，入卷的题必须都在
    这个地区。用 facets 里的第一个地区做样本，最多取 200 道。
    """
    f = client.get("/api/facets").json()
    regions = f.get("regions") or []
    if not regions:
        print("    （facets 没有地区，跳过）")
        return
    region = regions[0].get("value")
    if not region:
        return
    r = client.post("/api/generate",
                    json={"mode": "test", "region": region, "max_items": 200})
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    assert items, region
    assert all((x.get("meta") or {}).get("region") == region for x in items)


def test_papers_and_trash_routers_registered():
    """路由从 server.py 拆到 routers/ 后，路径和响应形状不能变。"""
    for path in ("/api/papers", "/api/trash", "/api/trash/reasons"):
        r = client.get(path)
        assert r.status_code == 200, (path, r.text)
        assert "items" in r.json(), (path, r.json())


def test_meta_and_stats_routers_registered():
    """meta/stats 从 server.py 拆出后，路径与顶层字段不能变。"""
    assert client.get("/api/stats").json()["total"] > 0
    assert "items" in client.get("/api/changes").json()
    assert "基线" in client.get("/api/baseline").json()
    assert client.get("/api/settings").json()["out_dir"]
    assert "current" in client.get("/api/search/status").json()


def test_generate_has_constraints_and_minutes():
    d = client.post("/api/generate", json={"mode": "gaokao", "seed": 42}).json()
    assert len(d["keys"]) == 19, len(d["keys"])
    assert d["minutes"] > 0, d.get("minutes")
    assert all(s["minutes"] > 0 for s in d["slots"] if s["key"]), d["slots"][:2]
    # 入卷的题必须都有解析（硬约束）
    assert all(x["flags"].get("解析") for x in d["items"]), [x["key"] for x in d["items"]]


def test_detailed_layout_continuous():
    from amti import paper, store
    dets = [q for q in store.load_all() if q.type == "detailed_answer"][:2]
    tex = paper.render_paper(dets, mode="test", title="连续排", problem_blank_cm=5)
    # 已删除“一页一题”选项：解答题连续排，按 problem_blank_cm 固定留白
    assert "\\vspace*{\\fill}" not in tex
    # **可伸缩**：`plus 1fill` 让页底剩余纸面归入作答区（不再"留白之外另有一块白"），
    # `minus 0.8cm` 让差一两厘米的两道大题能挤进同一页。
    assert "\\vspace*{5.00cm plus 1fill minus 0.8cm}" in tex
    assert "\\filbreak" in tex


def test_pdf_layout_bracket_and_figure():
    r"""卷面观感的三条硬约束（用户报的"排版很难看"）：

    1. 选择题的（　）**不许右对齐**——exam-zh 默认 `paren/type=hfill` 会把
       放不下的括号甩到下一行最右侧，孤零零一个（　）。抽查里约一半选择题这样。
    2. **独立成行的配图要居中**：库里 97% 的图是单独一行、左对齐贴页边。
    3. 配图要有**高度上限**，一张图不能占掉半页。
    """
    from amti import paper, store
    qs = store.load_all()
    choice = next(q for q in qs if q.type == "single_choice")
    tex = paper.render_paper([choice], mode="gaokao", title="括号")
    assert "paren/type=none" in tex, "答题括号必须紧跟题干，不能右对齐"
    # 括号前面还要 `\unskip\nobreak`：xeCJK 在 `）` 与 `（` 之间插的胶是断点，
    # 只靠 `paren/type=none` 仍会 1/60 的概率让括号单独起一行。
    assert "\\unskip\\nobreak\\hskip 0.2em\\paren[" in tex, "括号不能自己起一行"
    assert "paren/type=hfill" not in tex.replace(" ", "")

    fig = next(q for q in qs
               if "\\includegraphics" in q.stem
               and any(line.strip().startswith("\\includegraphics")
                       for line in q.stem.splitlines()))
    ftex = paper.render_paper([fig], mode="gaokao", title="配图")
    assert "\\begin{center}\n\\includegraphics" in ftex, "独立成行的配图要居中"
    assert "height=0.32\\textheight" in ftex, "配图要有高度上限"


def test_pdf_image_options_not_split():
    r"""**四个图选项的题不许被拆到两页**（2010 广东卷（理）第 6 题实测）。

    措施两条，缺一不可：
    1. 图选项 ≥3 个时，把 `width=0.4\linewidth` 压到 0.30（整块从 12.4cm 收到 8cm）；
    2. 这类题按半页预留（`\needspace{0.5\textheight}`），节标题跟首题一起留
       （`0.58\textheight`），否则会留下孤零零一行「一、选择题」。
    """
    from amti import paper, store
    qs = store.load_all()
    # 2010 广东卷（理）第 6 题：四个 TikZ 选项图、每个 0.4\linewidth——实测被拆页的那道
    q = store.find("高考真题汇编/2010/广东卷（理）#6")
    if q is None:      # 数据万一改了名：退化成"随便找一道图选项题"，不让这条假红
        q = next(x for x in qs if paper._image_option_question(x))
    if paper._image_option_question(q) and sum(
            1 for o in q.options
            if "includegraphics" in (o.text or "") or "tikzpicture" in (o.text or "")) >= 3:
        tex = paper.render_paper([q], mode="gaokao", title="图选项")
        assert "\\needspace{0.5\\textheight}" in tex
        assert "width=0.30\\linewidth" in tex, "三个图选项以上要收到 0.30 行宽"
        assert "width=0.4\\linewidth" not in tex.split("\\begin{choices}", 1)[1]

    # 表格单元格里的图不包 center（LR 模式会报 Not allowed in LR mode）
    from amti.paper import center_figures
    s = "\\begin{tabular}{cc}\n\\includegraphics{a.png}\n\\end{tabular}"
    assert "center" not in center_figures(s), "表格单元格里不许包 center"
    # 并排的几张图（同一行）要一起居中
    s2 = "\\includegraphics{a.png}\\quad\\includegraphics{b.png}"
    assert center_figures(s2).startswith("\\begin{center}")


# ── AI 录题（DeepSeek）接口边界 ────────────────────────────────
#
# **一条都不写配置、不发网络请求**：这些用例跑在用户真实的环境里，
# 写进一个假 key 或改掉 base_url 就是把人家的软件改坏了。
# 所以只测"只读端点 + 会被拒绝的请求"。

def test_ai_status_never_leaks_key():
    """状态端点只回"配没配 + 末四位"。明文 key 一旦出现在响应里，
    任何一个本地脚本都能读走——这是这个功能的红线。"""
    r = client.get("/api/ai/status")
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d.get("configured"), bool)
    assert "api_key" not in d, d
    assert "key_hint" in d


def test_ai_run_rejects_empty_and_bad_base64():
    assert client.post("/api/ai/run", json={"name": "x.pdf", "data": ""}).status_code == 400
    assert client.post("/api/ai/run",
                       json={"name": "x.pdf", "data": "这不是base64"}).status_code == 400


def test_ai_job_unknown():
    assert client.get("/api/ai/job/不存在的任务").status_code == 404
    assert client.post("/api/ai/job/不存在的任务/cancel").status_code == 404


def test_ai_cancel_sets_flag_and_state():
    """取消端点只置位 + 改状态，不碰网络；用一个假任务验证。"""
    import threading
    import time
    from amti.web import server as _srv
    jid = "ai-test-cancel"
    ev = threading.Event()
    _srv._AI_JOBS[jid] = {"state": "running", "done": 1, "total": 2,
                          "msg": "正在读", "at": time.time(),
                          "result": None, "error": ""}
    _srv._AI_CANCELS[jid] = ev
    try:
        r = client.post("/api/ai/job/%s/cancel" % jid)
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "cancelling"
        assert ev.is_set()
        assert client.get("/api/ai/job/%s" % jid).json()["state"] == "cancelling"
    finally:
        _srv._AI_JOBS.pop(jid, None)
        _srv._AI_CANCELS.pop(jid, None)


def test_ai_cancel_end_to_end_keeps_partial():
    """真开一个任务（run 被替换成假实现，不发网络），取消后应落到 cancelled。"""
    import base64
    import threading
    import time
    from amti import aiingest as _ai
    from amti.web import server as _srv
    if not client.get("/api/ai/status").json().get("configured"):
        return                                  # 没配 key 时 /run 本来就 400

    started = threading.Event()

    def fake_run(data, **kw):
        started.set()
        stop = kw.get("should_stop") or (lambda: False)
        for _ in range(500):
            if stop():
                return {"ok": True, "latex": "", "title": "", "cancelled": True,
                        "crop_dir": "",
                        "stats": {"pages": 1, "ok": 0, "cancelled": True},
                        "pending": [], "problems": [], "warnings": ["任务已取消"]}
            time.sleep(0.01)
        return {"ok": True, "latex": "", "title": "", "cancelled": False,
                "crop_dir": "", "stats": {"pages": 1, "ok": 0},
                "pending": [], "problems": [], "warnings": []}

    old = _ai.run
    _ai.run = fake_run
    job = ""
    try:
        data = base64.b64encode(b"%PDF-1.4 fake").decode()
        r = client.post("/api/ai/run", json={"name": "x.pdf", "data": data})
        assert r.status_code == 200, r.text
        job = r.json()["job"]
        assert started.wait(2.0), "后台任务没起来"
        assert client.post("/api/ai/job/%s/cancel" % job).status_code == 200
        j = {}
        for _ in range(200):
            j = client.get("/api/ai/job/%s" % job).json()
            if j.get("state") in ("cancelled", "done", "error"):
                break
            time.sleep(0.01)
        assert j.get("state") == "cancelled", j
        assert (j.get("result") or {}).get("cancelled") is True, j
    finally:
        _ai.run = old
        if job:
            _srv._AI_JOBS.pop(job, None)
            _srv._AI_CANCELS.pop(job, None)


def test_ai_config_rejects_bad_url_without_writing():
    """非法地址要当场拒绝，**且不能留下半份配置**。"""
    before = client.get("/api/ai/status").json()
    r = client.post("/api/ai/config", json={"base_url": "ftp://example.com"})
    assert r.status_code == 400, r.text
    after = client.get("/api/ai/status").json()
    assert after["base_url"] == before["base_url"]
    assert after["configured"] == before["configured"]


def test_query_syntax_fields():
    """搜索语法：年份/类型/难度字段生效；-词 能减少结果。"""
    r = client.get("/api/questions", params={"q": "年份:2024", "limit": 5})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] > 0
    assert all(str(it["meta"].get("year")) == "2024" for it in d["items"])

    r = client.get("/api/questions", params={"q": "类型:多选", "limit": 5})
    assert r.status_code == 200
    d = r.json()
    assert d["total"] > 0
    assert all(it["type"] == "multi_choice" for it in d["items"])

    r = client.get("/api/questions", params={"q": "难度:中档", "limit": 5})
    assert r.status_code == 200
    d = r.json()
    assert d["total"] > 0
    assert all(it["difficulty"] == "中档题" for it in d["items"])

    base = client.get("/api/questions", params={"q": "三角形", "limit": 1}).json()
    neg = client.get("/api/questions", params={"q": "三角形 -外接圆", "limit": 1}).json()
    assert neg["total"] < base["total"], (base["total"], neg["total"])


def test_similar_questions_ready():
    """相似题：不返回自身，按相似度降序；内容库没建好时跳过。"""
    from amti import content_store
    if not content_store.current():
        return
    d = client.get("/api/questions?limit=20").json()
    key = d["items"][0]["key"]
    r = client.get("/api/questions/%s/similar" % _enc(key), params={"limit": 5})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["key"] == key
    assert got["ready"] is True
    items = got["items"]
    assert isinstance(items, list)
    for it in items:
        assert it["key"] != key
        assert 0 <= it.get("similarity", 0) <= 1
    scores = [it.get("similarity", 0) for it in items]
    assert scores == sorted(scores, reverse=True), scores


def test_duplicates_endpoint():
    """重复题：只返回同组、不含自身；没有组也不能报错。"""
    d = client.get("/api/questions?limit=10").json()
    key = d["items"][0]["key"]
    r = client.get("/api/questions/%s/duplicates" % _enc(key))
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["key"] == key
    assert isinstance(got["items"], list)
    for it in got["items"]:
        assert it["key"] != key


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
