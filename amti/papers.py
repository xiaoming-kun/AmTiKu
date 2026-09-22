r"""AmTiKu · 试卷存档

导出的卷子要**记得住**：出了什么卷、用了哪些题、什么参数。
不然「我上次那套卷呢」就只能去 `试卷/` 里翻文件名。

存档是**追加式**的清单（`试卷/存档.json`），每条记：

    name    卷名（也是文件名前缀）
    keys    题目 key 列表，**有顺序**——卷子是按这个顺序排的
    mode    gaokao / test
    params  版式参数（间距、留白、显示答案…）
    at      什么时候导的

有了 keys 就能**原样重现**这套卷；有了 params 就能接着改。

顺带支持**合集**：同一份存档可以被标记成「合集」，
当成一个可复用的题组（比如「导数压轴精选」），
下次组卷时直接拿来用。
"""
from __future__ import annotations

from .paths import ROOT
import datetime as _dt
import json
from pathlib import Path

PAPER_DIR = ROOT / "试卷"
ARCHIVE = PAPER_DIR / "存档.json"


def _load() -> list[dict]:
    if not ARCHIVE.exists():
        return []
    try:
        d = json.loads(ARCHIVE.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再原子替换——中途失败不会留半个存档
    tmp = ARCHIVE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ARCHIVE)


def add(name: str, keys: list[str], *, title: str = "", mode: str = "gaokao",
        params: dict | None = None, kind: str = "试卷", note: str = "") -> dict:
    r"""记一次导出。同名覆盖（重导同一套卷不该留两条）。"""
    items = _load()
    rec = {
        "name": name,
        "title": title or name,
        "kind": kind,                  # 试卷 / 合集
        "mode": mode,
        "keys": list(keys),
        "n": len(keys),
        "params": params or {},
        "note": note,
        # **精确到秒**：只到分钟的话同一分钟内导两次会「同时刻」，
        # 排序就不稳，"最近导出的"可能不是真的最近那道（自检抓到过）
        "at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    # 递增序号：时间戳只到秒，同一秒内导两次会打平，光靠时间排不稳。
    rec["seq"] = max([x.get("seq", 0) for x in items] or [0]) + 1
    for i, x in enumerate(items):
        if x.get("name") == name:
            rec["seq"] = x.get("seq", rec["seq"])
            rec["at"] = x.get("at") or rec["at"]
            rec["updated"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            items[i] = rec
            break
    else:
        items.append(rec)
    _save(items)
    return rec


def all_items() -> list[dict]:
    """按时间倒序。"""
    # 主键时间、次键序号——同一秒内也不会乱
    return sorted(_load(), key=lambda x: (x.get("updated") or x.get("at") or "",
                                          x.get("seq", 0)), reverse=True)


def get(name: str) -> dict | None:
    return next((x for x in _load() if x.get("name") == name), None)


def remove(name: str) -> bool:
    items = _load()
    n = len(items)
    items = [x for x in items if x.get("name") != name]
    if len(items) == n:
        return False
    _save(items)
    return True


def rename(name: str, new: str) -> bool:
    items = _load()
    for x in items:
        if x.get("name") == name:
            x["name"] = new
            _save(items)
            return True
    return False


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    import tempfile
    global ARCHIVE, PAPER_DIR
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("papers 自检")
    old_dir, old_arc = PAPER_DIR, ARCHIVE
    d = Path(tempfile.mkdtemp())
    PAPER_DIR, ARCHIVE = d, d / "存档.json"
    try:
        check("空存档读出空表", all_items() == [])

        add("导数精选", ["a#1", "a#2", "a#3"], kind="合集", note="压轴题")
        add("2026模拟", ["b#1", "b#2"], mode="test",
            params={"bottom_sep": "2em"})
        check("存了两条", len(all_items()) == 2)
        check("顺序是倒序（新的在前）",
              all_items()[0]["name"] == "2026模拟")
        check("keys 保持顺序", get("导数精选")["keys"] == ["a#1", "a#2", "a#3"])
        check("参数记住了", get("2026模拟")["params"]["bottom_sep"] == "2em")

        add("导数精选", ["a#1", "a#9"], kind="合集")
        check("同名覆盖不留两条", len(all_items()) == 2)
        check("覆盖后 keys 变了", get("导数精选")["keys"] == ["a#1", "a#9"])

        check("改名", rename("导数精选", "导数精选II")
              and get("导数精选II") is not None)
        check("删掉", remove("2026模拟") and len(all_items()) == 1)
        check("删不存在的返回 False", remove("不存在") is False)

        # 存档文件坏了不能崩——只当空的
        ARCHIVE.write_text("{坏掉的 json", encoding="utf-8")
        check("存档损坏时不崩，当空表", all_items() == [])
    finally:
        PAPER_DIR, ARCHIVE = old_dir, old_arc

    print("papers 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
