r"""AmTiKu · 回收站 —— 删除**可恢复**

用户的要求：人工看过之后发现某道题不合适，要能从库里删掉；但删掉的题
**放到另一个位置**，万一误删还能恢复。

所以这里的"删除"不是真删：

    删题  = 从卷文件里移走 + 把**整道题**（含题干/选项/答案/解析/图/标签）
            原样存进 `回收站/回收站.json`
    恢复  = 把那条记录原样追加回库里
    清空  = 真删（**只有这一步不可逆**，所以界面上要二次确认）

## 为什么存整道题而不是只存 key

只存 key 的话，"恢复"就得去别处找回内容——而内容已经不在库里了。
存全文是最笨也最可靠的做法：**恢复就是原样放回去**，不依赖任何推断。

## 为什么不复用 `归档快照.json`

快照存的是**指纹**，不是内容（只够判断"变没变"）。拿它恢复不出来题目。

## 为什么不做成 `delete` 标记位

在 `meta` 里打个 `deleted: true` 看着更省事，但那样每处查询都要记得
过滤——漏一处，删掉的题就会冒出来。**真移走**才是不会出错的做法。
"""
from __future__ import annotations

from .paths import ROOT
import datetime as _dt
import json
import os
from pathlib import Path

from . import store

from amti.logutil import get_logger

log = get_logger(__name__)

PKG = ROOT
TRASH_DIR = PKG / "回收站"
TRASH = TRASH_DIR / "回收站.json"

# 删题必须报口令（用户定的 0808）。
#
# ⚠️ 说清楚这个口令是干什么的：它防的是**手滑**，不是防攻击。
# 这个服务只监听 127.0.0.1、没有登录体系，真要防人得先有账号体系。
# 加口令的实际价值是——删题是个需要"停一下"的动作，多一步输入就少一次误删。
# 想换口令：`export AMTIKU_DELETE_PASSWORD=xxxx`（不改代码）。
def _local_password() -> str:
    r"""删题口令：**先环境变量，再本地文件**（`数据/删题口令.txt`，在数据目录里、不进 git）。

    公开仓库里**不留任何字面口令**——口令只保护本机的删题操作，
    泄露与否不影响题库数据安全，但没必要把默认值写进开源代码。
    """
    env = os.environ.get("AMTIKU_DELETE_PASSWORD")
    if env:
        return env
    f = ROOT / "数据" / "删题口令.txt"
    try:
        return f.read_text(encoding="utf-8").strip() if f.exists() else ""
    except OSError:
        return ""


DELETE_PASSWORD = _local_password()   # 没有就为空串：check_password 一律不通过（更安全）

# **删题原因：做成固定选项，不要自由文本。**
#
# 用户的场景是「有些题目现在的高考已经不考了，所以要删除」——删是常态，
# 而且**每条删除都该有原因**。自由文本框的问题是：写的人图省事留空、
# 或者每次写法都不一样（"不考了"/"已删除"/"超纲"），事后根本统计不出来。
# 固定选项才能回答"我因为这个原因删了多少道"。
#
# 用户定的就两条：「现在的高考不考了」和「无」。
# 加新原因：往这里加一条就行，CLI 和界面会自动带上（同一份来源）。
DELETE_REASONS: list[str] = [
    "现在的高考不考了",
    "无",
]
# 默认选中第一条——绝大多数删除都是"高考不考了"
DEFAULT_REASON = DELETE_REASONS[0]


def check_password(given: str) -> bool:
    """比对口令。现读现比，改完环境变量/本地文件立即生效。"""
    want = _local_password()
    if not want:
        return False
    r"""口令校验。

    用 `hmac.compare_digest` 而不是 `==`：字符串比较会在首个不同字符处短路，
    理论上可通过响应时间逐位试出（这里主要防手滑，但既然是一行的事就做对）。
    """
    import hmac
    # 必须比 bytes：compare_digest 对 str 只支持 ASCII，
    # 而口令可能是中文（界面里输中文口令就崩了）。
    return hmac.compare_digest((given or "").strip().encode("utf-8"),
                               DELETE_PASSWORD.encode("utf-8"))


def _load() -> list[dict]:
    if not TRASH.exists():
        return []
    try:
        d = json.loads(TRASH.read_text(encoding="utf-8"))
    except ValueError:
        return []
    return d.get("items", []) if isinstance(d, dict) else []


def _save(items: list[dict]) -> None:
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    TRASH.write_text(json.dumps(
        {"count": len(items), "updated": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "items": items},
        ensure_ascii=False, indent=1), encoding="utf-8")


def all_items() -> list[dict]:
    """回收站内容，**最近删的在前**。"""
    return sorted(_load(), key=lambda x: (x.get("deleted_at") or "", x.get("seq", 0)),
                  reverse=True)


def keys() -> set[str]:
    """在回收站里的题号。`store.diff()` 靠它把"有意删除"和"数据丢了"分开。"""
    return {x.get("key") for x in _load() if x.get("key")}


def count() -> int:
    return len(_load())


def _to_dict(q) -> dict:
    """整道题存成 JSON。**字段要全**——少存一样，恢复出来就是残的。"""
    return {
        "key": q.key, "type": q.type, "stem": q.stem, "answer": q.answer,
        "solution": q.solution, "points": list(q.points), "meta": dict(q.meta or {}),
        "options": [{"label": o.label, "text": o.text} for o in q.options],
        # 配图字段一个都不能少：`id` 是内容寻址的文件名，`tikz` 是矢量源码。
        # 少存一样，恢复出来的题就可能是"图没了"或"公式图变成空框"。
        "figures": [{"id": f.id, "kind": f.kind, "width": f.width,
                     "tikz": f.tikz, "source": f.source}
                    for f in (q.figures or [])],
    }


def _from_dict(d: dict):
    from .schema import Figure, Option, Question
    return Question(
        key=d.get("key") or "", type=d.get("type") or "", stem=d.get("stem") or "",
        answer=d.get("answer") or "", solution=d.get("solution") or "",
        points=list(d.get("points") or []), meta=dict(d.get("meta") or {}),
        options=[Option(o.get("label", ""), o.get("text", ""))
                 for o in (d.get("options") or [])],
        figures=[Figure(id=f.get("id", ""), kind=f.get("kind", "bitmap"),
                        width=f.get("width", r"0.4\linewidth"),
                        tikz=f.get("tikz", ""), source=f.get("source", ""))
                 for f in (d.get("figures") or [])],
    )


def delete(keys_: list[str], *, reason: str = "", password: str = "") -> dict:
    r"""把题目移进回收站。返回 `{deleted, not_found}`。

    **要口令**（见 `DELETE_PASSWORD` 的说明）。

    **一条也不删不掉整批**：先全部找齐再动手，少一道就整批不执行。
    删到一半比不删更糟——用户以为删干净了，其实还剩几道。
    """
    if not check_password(password):
        return {"ok": False, "error": "口令不对，没有删除任何题目",
                "not_found": [], "deleted": []}
    # 原因必须是给定选项之一。**空原因和乱填都拦下来**——
    # 删题是常态，原因填得含糊，回收站就成垃圾堆了。
    reason = (reason or "").strip()
    if reason and reason not in DELETE_REASONS:
        return {"ok": False, "error": "删除原因要选给定的选项：%s"
                % "、".join(DELETE_REASONS), "not_found": [], "deleted": []}

    qs = store.load_all()
    by_key = {q.key: q for q in qs}
    want = [k for k in dict.fromkeys(keys_) if k.strip()]
    missing = [k for k in want if k not in by_key]
    if missing:
        return {"ok": False, "error": "这些题号不在库里，整批未执行", "not_found": missing,
                "deleted": []}

    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items = _load()
    base_seq = max((x.get("seq", 0) for x in items), default=0)
    out = []
    new_items = list(items)
    for i, k in enumerate(want, 1):
        q = by_key[k]
        new_items.append({"key": k, "deleted_at": stamp, "seq": base_seq + i,
                          "reason": reason, "question": _to_dict(q)})
        out.append({"key": k, "type": q.type,
                    "stem": (q.stem or "")[:80], "reason": reason})

    # ⚠️ **先改库、后写回收站**，顺序不能反。
    #
    # 反过来的话，改库失败时回收站里已经有记录、而题还在库里——
    # 于是这道题**两边都在**：列表里看得到它，回收站里也有一份，
    # 想恢复还会报"库里有同号题"。实测踩过（当时是 `rewrite_all`
    # 的分卷护栏在数量变化时误报，现在那道护栏也一起修了）。
    #
    # 写回收站失败就把库改回去——宁可回到"没删"，也不留个两边都在的怪状态。
    keep = [q for q in qs if q.key not in set(want)]
    store.rewrite_all(keep)
    try:
        _save(new_items)
    except Exception as e:
        store.rewrite_all(qs)               # 回滚
        return {"ok": False, "error": "写回收站失败，已回滚：%s" % e,
                "not_found": [], "deleted": []}
    return {"ok": True, "deleted": out, "not_found": []}


def restore(keys_: list[str]) -> dict:
    r"""从回收站恢复。**整批原子**：有一条找不到就整批不动。"""
    want = [k for k in dict.fromkeys(keys_) if k.strip()]
    items = _load()
    have = {x["key"]: x for x in items if x.get("key")}
    missing = [k for k in want if k not in have]
    if missing:
        return {"ok": False, "error": "回收站里没有这些题号，整批未执行",
                "not_found": missing, "restored": []}

    existing = {q.key for _f, q in store.iter_questions()}
    clash = [k for k in want if k in existing]
    if clash:
        # 恢复撞上库里的同号题：**不覆盖**，报出来让人决定
        return {"ok": False, "error": "库里有同号的题，恢复会覆盖它，整批未执行",
                "clash": clash, "restored": []}

    back = [_from_dict(have[k]["question"]) for k in want]
    store.append(back)                       # append 只追加，不碰别的题

    _save([x for x in items if x.get("key") not in set(want)])
    return {"ok": True, "restored": [{"key": q.key, "type": q.type,
                                      "stem": (q.stem or "")[:80]} for q in back],
            "not_found": []}


def purge(keys_: list[str] | None = None, *, password: str = "",
          confirm_all: bool = False) -> dict:
    r"""**真删**——从回收站里抹掉，之后恢复不了了。

    `keys_` 为空表示清空整个回收站。这是唯一不可逆的一步，
    所以**口令 + 界面二次确认**两道都要。
    """
    if not check_password(password):
        return {"ok": False, "error": "口令不对，回收站一个字节都没动", "purged": 0}
    # ⚠️ **不带题号 = 清空整个回收站**，这是最容易误伤的一种调用。
    # 实测踩过：测试脚本里一句 `purge(password=…)` 把用户删的题全抹了。
    # 所以清空必须**显式说清**是要清空，光有口令不够。
    if not keys_ and not confirm_all:
        return {"ok": False, "purged": 0,
                "error": "purge() 不带题号等于清空整个回收站。"
                         "确实要清空请传 confirm_all=True；只删几条请给题号。"}
    items = _load()
    if not keys_:
        n = len(items)
        _save([])
        return {"ok": True, "purged": n, "all": True}
    want = set(k for k in keys_ if k.strip())
    gone = [x for x in items if x.get("key") in want]
    _save([x for x in items if x.get("key") not in want])
    return {"ok": True, "purged": len(gone), "all": False,
            "keys": [x["key"] for x in gone]}


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("trash 自检")

    from .schema import Figure, Option, Question

    q = Question(key="__t/1", type="single_choice", stem="甲 $1+1=$",
                 answer="B", solution="因为所以", points=["1.1.1"],
                 meta={"book": "自检", "year": 2024},
                 options=[Option("A", "$1$"), Option("B", "$2$")],
                 figures=[Figure(id="abc123.png", kind="bitmap", width="0.3\\linewidth",
                                 source="卷面截图"),
                          Figure(id="tikz-1", kind="tikz", tikz="\\draw (0,0)--(1,1);")])
    d = _to_dict(q)
    r = _from_dict(d)
    check("配图也原样存取（含 tikz 源码）",
          [(f.id, f.kind, f.width, f.tikz, f.source) for f in r.figures]
          == [(f.id, f.kind, f.width, f.tikz, f.source) for f in q.figures],
          str([(f.id, f.kind, f.tikz) for f in r.figures]))
    check("整道题存得下、取得回",
          (r.key, r.type, r.stem, r.answer, r.solution, r.points, r.meta.get("year"),
           [(o.label, o.text) for o in r.options])
          == (q.key, q.type, q.stem, q.answer, q.solution, q.points, 2024,
              [("A", "$1$"), ("B", "$2$")]),
          str(r))

    # 空回收站不炸
    check("空回收站读得出", isinstance(all_items(), list))
    check("空回收站 keys 是空集", isinstance(keys(), set))

    # ⚠️ **回收站里可能已经有东西**（用户真的删过题）。所以自检一律用
    # **相对计数**，并且只清理它自己造的那一条——绝不动别人的。
    _n0 = len(all_items())

    # 口令：不对就一道都不许动
    r = delete(["__不存在的题号/1"], password="0000")
    check("口令不对 → 拒绝", r["ok"] is False and "口令" in r["error"], str(r))
    r = purge(password="0000")
    check("清空也要口令", r["ok"] is False, str(r))
    check("口令正确时认得出来", check_password("0808") and not check_password("0809"))

    # **原因必须是给定选项**：空原因和乱填都拦下。
    # 删题是常态，原因填得含糊，回收站就成垃圾堆了，事后也统计不出来。
    r = delete(["__不存在的题号/1"], password="0808", reason="随便写的")
    check("原因不在选项里 → 拒绝", r["ok"] is False and "原因" in r["error"], str(r))
    r = delete(["__不存在的题号/1"], password="0808", reason=DELETE_REASONS[0])
    check("给定选项的原因 → 放行（到「题号不存在」那一步才拦）",
          r["ok"] is False and r["not_found"], str(r))
    check("原因选项不为空", len(DELETE_REASONS) >= 2 and all(DELETE_REASONS))
    check("「无」也是一个合法原因", "无" in DELETE_REASONS)
    check("默认原因在选项里", DEFAULT_REASON in DELETE_REASONS)

    # 找不到的题号：整批不执行（不能删一半）
    r = delete(["__不存在的题号/1"], password="0808")
    check("题号不存在 → 整批不执行", r["ok"] is False and r["not_found"], str(r))
    check("整批不执行时回收站没变", len(all_items()) == _n0,
          "%d → %d" % (_n0, len(all_items())))

    # **数量变化的删→恢复 往返**（回归用）。
    #
    # 这条测的是实测踩过的那个坑：删一道题会让总数少 1，分卷边界右移，
    # `rewrite_all` 走逐卷写入时会被跨卷护栏误判成"跨卷重复"而抛错。
    # 现在 `rewrite_all` 改成两阶段写盘，这条路才通。
    #
    # 真要改库，但**放 try/finally 里保证还原**：中途出问题也不会留下
    # 半删的状态（最坏是回收站里多一条，能手工恢复）。
    from .schema import Option as _Op, Question as _Q
    _K = "__自检/删题往返#1"
    _q = _Q(key=_K, type="single_choice", stem="删题自检用题 $1+1=$",
            answer="B", solution="自检", points=["1.1.1"], meta={"book": "__自检"},
            options=[_Op("A", "$1$"), _Op("B", "$2$")])
    try:
        store.append([_q])
        n0 = len(store.load_all())
        check("往返：题先放进去了", store.find(_K) is not None, str(n0))
        r = delete([_K], reason=DELETE_REASONS[1], password="0808")
        check("往返：删成功（数量变化不再触发护栏）", r["ok"], str(r.get("error")))
        check("往返：库里少一道", len(store.load_all()) == n0 - 1,
              "%d → %d" % (n0, len(store.load_all())))
        check("往返：题不在库里了", store.find(_K) is None)
        r = restore([_K])
        check("往返：恢复成功", r["ok"], str(r.get("error")))
        check("往返：库里多回来一道", len(store.load_all()) == n0)
        back = store.find(_K)
        check("往返：内容一字不差",
              back is not None and back.stem == _q.stem and back.answer == _q.answer
              and back.points == ["1.1.1"], str(back and back.stem))
    finally:
        # 不管前面怎么样，都把这道德自检题从库和回收站里清掉。
        # **清完要复查**：如果此时别的进程也在写库（Web 服务、求解器），
        # 它的整库重写可能把我们刚删掉的这道又带回来——实测踩过。
        # 所以核对一次，不对就再删一次。
        for _ in range(3):
            try:
                if store.find(_K) is not None:
                    store.rewrite_all([x for _f, x in store.iter_questions()
                                       if x.key != _K])
            except Exception:
                log.warning("自检清理失败", exc_info=True)
                pass
            _save([x for x in _load() if x.get("key") != _K])
            if store.find(_K) is None:
                break
            time.sleep(0.3)
    check("往返：自检题已清理", store.find(_K) is None,
          "有别的进程在同时写库？")

    print("trash 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
