"""AmTiKu · 知识地图

`知识点.json` 仍然是**高中考点**的唯一真相（题目标签只认它的 152 个 id）。
本模块补的是它缺的那一层：**学段、年级、教材册章和小学初中的知识点**。

    GET /api/map   → 小学 / 初中 / 高中 三学段，按人教版教材顺序排好

分工：

    知识点.json   高中考点的名称、星级、难度、五要素（题目标签指向这里）
    知识地图.json 教材位置：学段 → 年级 → 册 → 章 → 知识点
                  · 高中节点**只存 id**，名称现取，绝不复制一份（否则迟早分叉）
                  · 小学、初中节点在这里定义（题库里还没有它们的题）

所以「知识地图」不是第二个题库：它回答「这个知识点在教材哪儿、前后学什么」，
而不是「这道题考哪个考点」。

边（`edges`）三种：

    hard   先修：不会它，这课学不动
    soft   有帮助：学过更顺，但不是必需
    order  教材顺序：只用来把没有显式先修的基础课接起来

方向一律 `from`（先）→ `to`（后）。硬边必须无环（`audit()` 会查）。
高中 315 条来自已归档的「知识链路」起草稿（带理由）；小学、初中与跨学段边
由 `归档/cn-math-taxonomy` 的先修图投影得到（同册同章对齐，跨学段端点人工对齐）。
"""
from __future__ import annotations

from .paths import ROOT
import json
import re
from pathlib import Path

from . import knowledge
from . import store

MAP_PATH = ROOT / "知识地图.json"
# 小学/初中的诊断题（高中用题库里的真题，不在这里）
QS_PATH = ROOT / "小初诊断题.json"

# 学段 key → 显示名 / 年级显示名
STAGE_NAME = {"primary": "小学", "junior": "初中", "senior": "高中"}
GRADE_NAME = {1: "一年级", 2: "二年级", 3: "三年级", 4: "四年级",
              5: "五年级", 6: "六年级", 7: "七年级", 8: "八年级",
              9: "九年级", 10: "高一", 11: "高二", 12: "高三"}
# 小学/初中 id 的前缀；高中沿用 知识点.json 的数字 id
PREFIX = {"primary": "x", "junior": "c", "senior": ""}

# 缓存键取「文件 mtime+size」——改了地图自动失效（照 knowledge.py 的做法）。
_RAW: dict = {"key": None, "v": None}
_TREE: dict = {"key": None, "v": None}
_QS: dict = {"key": None, "v": None}


def _sig() -> tuple:
    try:
        st = MAP_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def load() -> dict:
    """原始地图（不做任何补全）。文件缺失时返回空壳，不抛异常。"""
    key = _sig()
    if _RAW["key"] == key and _RAW["v"] is not None:
        return _RAW["v"]
    if not MAP_PATH.exists():
        v = {"version": 0, "stages": [], "stats": {}}
    else:
        v = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    _RAW["key"], _RAW["v"] = key, v
    return v



_STAGE: dict = {"key": None, "v": {}}


def stage_index() -> dict[str, str]:
    """考点 id → 学段 key。

    只依赖 `知识地图.json` + `知识点.json`，**不依赖题目计数**——
    `tree()` 为了算每个点的题数会读全库，单题改完标签后调它会重新解析
    3 万道题（实测 2 秒+）。学段归属不需要题数，所以单独一份缓存。
    """
    key = (_sig(), knowledge.signature())
    if _STAGE["key"] == key:
        return _STAGE["v"]
    out: dict[str, str] = {}
    for st in load().get("stages", []):
        skey = st.get("key", "")
        for b in st.get("books", []):
            for c in b.get("chapters", []):
                for pt in c.get("points", []):
                    pid = pt.get("id")
                    if pid:
                        out[pid] = skey
    _STAGE["key"], _STAGE["v"] = key, out
    return out


def _qs_sig() -> tuple:
    try:
        st = QS_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def _questions() -> dict:
    """知识点 id → 诊断题列表。文件缺失时返回空表，界面显示「暂无」。"""
    key = _qs_sig()
    if _QS["key"] == key and _QS["v"] is not None:
        return _QS["v"]
    if not QS_PATH.exists():
        v = {}
    else:
        v = json.loads(QS_PATH.read_text(encoding="utf-8")).get("points", {})
    _QS["key"], _QS["v"] = key, v
    return v


def questions_of(point_id: str) -> list[dict]:
    return _questions().get(point_id, [])


def _title_of(point_id: str) -> str:
    """高中考点名在 知识点.json；小学/初中的名字在 知识地图.json。"""
    for st in load().get("stages", []):
        for b in st.get("books", []):
            for c in b.get("chapters", []):
                for p in c.get("points", []):
                    if p.get("id") == point_id:
                        return p.get("title") or point_id
    return knowledge.title_of(point_id) or point_id


def questions(point_id: str) -> dict:
    """单个知识点的诊断题（接口用）。知识点不存在时返回空，由调用方判 404。"""
    if point_id not in _point_ids():
        return {}
    return {"id": point_id, "title": _title_of(point_id),
            "qs": questions_of(point_id)}


def _point_ids() -> set[str]:
    return {p["id"] for s in load().get("stages", []) for b in s.get("books", [])
            for c in b.get("chapters", []) for p in c.get("points", [])}


def _book_label(book: dict) -> str:
    """「一年级上册」「必修第一册」——数据里已经写好，缺了才拼。"""
    return book.get("name") or f"{GRADE_NAME.get(book.get('grade'), '')}{book.get('semester', '')}"


def tree() -> dict:
    """给界面用的完整树：高中节点补上名称/星级/难度/五要素。"""
    # 联合签名：地图自己 + 知识点库。只按地图 mtime 缓存的话，
    # 改了 知识点.json 里的考点名，这里会一直返回旧标题。
    # 题目数也要进签名：录了新题、这个点上的「N 题」角标就会变。
    key = (_sig(), knowledge.signature(), _qs_sig(), store.volume_signature())
    if _TREE["key"] == key and _TREE["v"] is not None:
        return _TREE["v"]
    raw = load()
    qcount: dict[str, int] = {}
    for q in store.load_cached():
        for pid in q.points:
            qcount[pid] = qcount.get(pid, 0) + 1
    stages = []
    for st in raw.get("stages", []):
        skey = st.get("key", "")
        books = []
        for b in st.get("books", []):
            chapters = []
            for c in b.get("chapters", []):
                pts = []
                for p in c.get("points", []):
                    pid = p.get("id", "")
                    if skey == "senior":
                        k = knowledge.get(pid)
                        pts.append({
                            "id": pid,
                            "title": knowledge.title_of(pid) or pid,
                            "note": k.get("topic", ""),
                            "stars": k.get("stars", 0),
                            "difficulty": k.get("difficulty", ""),
                            "fields": k.get("fields") or {},
                        })
                    else:
                        pts.append({"id": pid, "title": p.get("title", ""),
                                    "note": p.get("note", ""), "stars": 0,
                                    "difficulty": "", "fields": {}})
                for pt in pts:
                    pt["q"] = len(questions_of(pt["id"]))       # 诊断题（小初）
                    pt["nq"] = qcount.get(pt["id"], 0)           # 题库里的题（高中）
                chapters.append({"title": c.get("title", ""),
                                 "points": pts, "n": len(pts)})
            books.append({"name": _book_label(b), "grade": b.get("grade", 0),
                          "semester": b.get("semester", ""),
                          "note": b.get("note", ""),
                          "chapters": chapters,
                          "n": sum(c["n"] for c in chapters)})
        stages.append({"key": skey, "name": st.get("name") or STAGE_NAME.get(skey, skey),
                       "books": books,
                       "n": sum(b["n"] for b in books)})
    # 边：只保留两端都存在的（换了地图文件也不会画出断头线）
    ids = {p["id"] for s in stages for b in s["books"]
           for c in b["chapters"] for p in c["points"]}
    edges = [e for e in raw.get("edges", [])
             if e.get("from") in ids and e.get("to") in ids and e.get("from") != e.get("to")]
    out = {
        "version": raw.get("version", 0),
        "updated": raw.get("updated", ""),
        "edition": raw.get("edition", ""),
        "stages": stages,
        "edges": edges,
        "total": sum(s["n"] for s in stages),
        "stats": _stats(stages, edges),
    }
    _TREE["key"], _TREE["v"] = key, out
    return out


def _stats(stages: list[dict], edges: list[dict]) -> dict:
    covered = {e["from"] for e in edges} | {e["to"] for e in edges}
    return {
        "points": sum(s["n"] for s in stages),
        "covered": len(covered),
        "edges": len(edges),
        "hard": sum(1 for e in edges if e.get("strength") == "hard"),
        "soft": sum(1 for e in edges if e.get("strength") == "soft"),
        "prereq": sum(1 for e in edges if e.get("kind") != "order"),
        "order": sum(1 for e in edges if e.get("kind") == "order"),
    }


def stats() -> dict:
    t = tree()
    return {
        "total": t["total"],
        "edges": t["stats"],
        "stages": [{"key": s["key"], "name": s["name"], "n": s["n"],
                    "books": len(s["books"])} for s in t["stages"]],
        "grades": [{"stage": s["key"], "grade": b["grade"],
                    "name": GRADE_NAME.get(b["grade"], str(b["grade"])),
                    "book": b["name"], "n": b["n"]}
                   for s in t["stages"] for b in s["books"]],
    }


def audit() -> dict:
    """结构自检。返回 {ok, errors, warnings, counts}，不抛异常。"""
    errors: list[str] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}
    if not MAP_PATH.exists():
        return {"ok": False, "errors": ["知识地图.json 不存在"], "warnings": [], "counts": {}}
    raw = load()
    if not raw.get("stages"):
        errors.append("stages 为空")
    hs_ids = {p["id"] for p in knowledge.all_points()}
    seen: set[str] = set()
    hs_seen: set[str] = set()
    id_re = re.compile(r"^([xc])(\d{2})\.(\d+)\.(\d+)$")
    for st in raw.get("stages", []):
        skey = st.get("key", "")
        if skey not in STAGE_NAME:
            errors.append(f"未知学段 {skey}")
            continue
        stage_n = 0
        for b in st.get("books", []):
            label = _book_label(b)
            grade = b.get("grade")
            if not isinstance(grade, int) or grade not in GRADE_NAME:
                errors.append(f"{label}：grade 非法 {grade!r}")
            if b.get("semester") not in ("上", "下", ""):
                errors.append(f"{label}：semester 非法 {b.get('semester')!r}")
            if not b.get("chapters"):
                errors.append(f"{label}：没有章")
            for c in b.get("chapters", []):
                if not c.get("points"):
                    errors.append(f"{label} · {c.get('title')}：没有知识点")
                for p in c.get("points", []):
                    pid = p.get("id", "")
                    if pid in seen:
                        errors.append(f"知识点 id 重复：{pid}")
                    seen.add(pid)
                    if skey == "senior":
                        if pid not in hs_ids:
                            errors.append(f"{label} · {c.get('title')}：考点 {pid} 不在 知识点.json")
                        elif pid in hs_seen:
                            errors.append(f"高中考点重复映射：{pid}")
                        else:
                            hs_seen.add(pid)
                    else:
                        m = id_re.match(pid)
                        if not m or m.group(1) != PREFIX[skey]:
                            errors.append(f"{label} · {c.get('title')}：id 格式不对 {pid}")
                        if not (p.get("title") or "").strip():
                            errors.append(f"{label}：知识点缺 title（{pid}）")
                        if not (p.get("note") or "").strip():
                            warnings.append(f"{label}：{pid} 缺一句话说明")
                    stage_n += 1
        counts[skey] = stage_n
    missing = sorted(hs_ids - hs_seen)
    if missing:
        errors.append(f"高中考点漏映射 {len(missing)} 个：{missing[:8]}")

    # ── 边 ──
    edges = raw.get("edges", [])
    if not edges:
        warnings.append("没有任何先修边（知识地图只剩目录）")
    pairs: set[tuple] = set()
    hard: dict[str, list[str]] = {}
    covered: set[str] = set()
    for e in edges:
        a, b = e.get("from", ""), e.get("to", "")
        if not a or not b:
            errors.append(f"边缺端点：{e}")
            continue
        if a not in seen or b not in seen:
            errors.append(f"边引用不存在的知识点：{a} → {b}")
            continue
        if a == b:
            errors.append(f"自环边：{a}")
        key = (a, b, e.get("kind", "prereq"))
        if key in pairs:
            errors.append(f"重复边：{a} → {b}")
        pairs.add(key)
        covered |= {a, b}
        if e.get("strength") == "hard" and e.get("kind") != "order":
            hard.setdefault(a, []).append(b)
    # 硬边必须无环（软边允许有环，但这里一并按硬边查）
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(u: str) -> bool:
        color[u] = 1
        stack.append(u)
        for w in hard.get(u, []):
            if color.get(w) == 1:
                errors.append("硬边成环：" + " → ".join(stack[stack.index(w):] + [w]))
                return True
            if color.get(w, 0) == 0 and dfs(w):
                return True
        stack.pop()
        color[u] = 2
        return False

    for v in seen:
        if color.get(v, 0) == 0 and dfs(v):
            break
    lonely = sorted(seen - covered)
    if lonely:
        warnings.append(f"{len(lonely)} 个知识点没有任何前后关系（多为每册第一课）：{lonely[:5]}")
    counts["edges"] = len(edges)

    # ── 诊断题（只是附加数据：没有题不报错，写坏了要报） ──
    qs = _questions()
    qn = 0
    for pid, arr in qs.items():
        if pid not in seen:
            errors.append(f"诊断题挂在不存在的知识点上：{pid}")
            continue
        if not isinstance(arr, list):
            errors.append(f"诊断题格式不对（应为列表）：{pid}")
            continue
        for i, q in enumerate(arr, 1):
            if not str(q.get("prompt") or "").strip():
                errors.append(f"{pid} 第 {i} 题缺题干")
            if not str(q.get("answer") or "").strip():
                errors.append(f"{pid} 第 {i} 题缺答案")
            qn += 1
    counts["questions"] = qn
    empty = [pid for pid in seen if pid not in qs and pid[:1] in "xc"]
    if empty:
        # 小初有 433 个点，37 个综合与实践类没有题是正常的；只记数量，不刷屏
        warnings.append(f"{len(empty)} 个小学/初中知识点还没有诊断题")
    declared = (raw.get("stats") or {}).get("points") or {}
    for k, v in counts.items():
        if k in declared and declared[k] != v:
            warnings.append(f"stats.points.{k} 声明 {declared[k]}，实际 {v}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "counts": counts}


def point_index() -> dict[str, dict]:
    """id → {阶段, 年级, 册, 章, 标题}，给「按考点查教材位置」用。"""
    out: dict[str, dict] = {}
    for s in tree()["stages"]:
        for b in s["books"]:
            for c in b["chapters"]:
                for p in c["points"]:
                    out[p["id"]] = {
                        "stage": s["name"], "grade": GRADE_NAME.get(b["grade"], ""),
                        "book": b["name"], "chapter": c["title"],
                        "title": p["title"],
                    }
    return out


def _selftest() -> int:
    a = audit()
    print("知识地图：", json.dumps(stats(), ensure_ascii=False))
    for w in a["warnings"][:5]:
        print("  警告：", w)
    for e in a["errors"][:10]:
        print("  错误：", e)
    print("通过" if a["ok"] else "失败")
    return 0 if a["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
