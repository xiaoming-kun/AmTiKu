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
    r = client.get("/api/questions?limit=5")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 17249, d["total"]
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
    assert client.get("/api/stats").status_code == 200
    b = client.get("/api/baseline").json()
    assert b["当前"] == 17249, b


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
    orig = client.get(f"/api/questions/{enc}").json().get("meta", {}).get("difficulty", "")
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
