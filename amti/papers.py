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
import os
import threading
from pathlib import Path

PAPER_DIR = ROOT / "试卷"
ARCHIVE = PAPER_DIR / "存档.json"
# 存档是「读整份 → 改 → 写整份」。两个请求同时进来会互相覆盖（丢一份）
_LOCK = threading.RLock()


class ArchiveCorrupt(RuntimeError):
    r"""`试卷/存档.json` 读不出来（坏 JSON / 顶层不是数组）。

    单独一个异常，是为了让调用方**能区分**「真的没有存档」和「存档坏了」。
    ⚠️ **文件坏了绝不能返回空表**：写路径是 `_load → 改 → _save`，
    一次坏文件被当成空表，下一次任何保存都会用一条新记录覆盖整份存档，
    几百份试卷一次消失。宁可这次操作失败。
    """


def _load() -> list[dict]:
    if not ARCHIVE.exists():
        return []
    try:
        d = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ArchiveCorrupt(
            "试卷存档读不出来：%s（%s）。为避免把它当成空存档、"
            "然后被下一次保存覆盖，本次操作已中止。请先修好或从 备份/ 恢复。"
            % (ARCHIVE, e)) from e
    if not isinstance(d, list):
        raise ArchiveCorrupt("试卷存档结构不对（顶层不是数组）：%s" % ARCHIVE)
    return d


def _save(items: list[dict]) -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再原子替换——中途失败不会留半个存档。
    # 临时文件名带进程号：两个进程同时写不会抢同一个 tmp。
    tmp = ARCHIVE.with_name(ARCHIVE.name + ".%d.tmp" % os.getpid())
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ARCHIVE)


def add(name: str, keys: list[str], *, title: str = "", mode: str = "gaokao",
        params: dict | None = None, kind: str = "试卷", note: str = "") -> dict:
    r"""记一次导出。同名覆盖（重导同一套卷不该留两条）。"""
    with _LOCK:
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
    with _LOCK:
        return sorted(_load(), key=lambda x: (x.get("updated") or x.get("at") or "",
                                              x.get("seq", 0)), reverse=True)


def get(name: str) -> dict | None:
    with _LOCK:
        return next((x for x in _load() if x.get("name") == name), None)


def remove(name: str) -> bool:
    with _LOCK:
        items = _load()
        n = len(items)
        items = [x for x in items if x.get("name") != name]
        if len(items) == n:
            return False
        _save(items)
        return True


def rename(name: str, new: str) -> bool:
    with _LOCK:
        items = _load()
        for x in items:
            if x.get("name") == name:
                x["name"] = new
                _save(items)
                return True
        return False


# ── 题目的「被组卷」信号 ───────────────────────────────────────────────
#
# 卡片上要能一眼看出「这题组过几份卷、最近一份叫什么」。真相是存档
# （`keys` 列表），所以这里只是**派生索引**：按存档文件的 mtime+size
# 缓存，存档一变就整份重算（几百条记录，重算 <5ms）。
_USAGE: dict = {"sig": None, "map": {}}


def _archive_sig() -> tuple | None:
    try:
        st = ARCHIVE.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def usage_index() -> dict[str, dict]:
    r"""`key` → `{"n": 被几份存档用到, "last": 最近一份的卷名}`。

    **不写库、不改题**：删掉一份存档，下一次数就少一，派生数据永远跟得上。
    存档坏了（`ArchiveCorrupt`）就返回空表——列表页不该因为档案坏了整页打不开，
    真正的报错在试卷库那边给。
    """
    sig = _archive_sig()
    if _USAGE["sig"] == sig:
        return _USAGE["map"]
    out: dict[str, dict] = {}
    try:
        items = all_items()          # 已按时间倒序：第一次遇到的就是最近一份
    except ArchiveCorrupt:
        _USAGE.update({"sig": sig, "map": {}})
        return {}
    for rec in items:
        title = rec.get("title") or rec.get("name") or ""
        for k in dict.fromkeys(rec.get("keys") or ()):   # 同一份卷里重复的题只算一次
            d = out.get(k)
            if d is None:
                out[k] = {"n": 1, "last": title}
            else:
                d["n"] += 1
    _USAGE.update({"sig": sig, "map": out})
    return out


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

        # 存档文件坏了：**必须报错，不能当空表** ——
        # 当空表的话下一次保存会用一条新记录覆盖整份存档（几百份卷子没了）。
        ARCHIVE.write_text("{坏掉的 json", encoding="utf-8")
        try:
            all_items()
            check("存档损坏时必须报错", False, "返回了空表")
        except ArchiveCorrupt:
            check("存档损坏时必须报错", True)
        try:
            add("新卷", ["c#1"])
            check("坏存档时保存也必须拒绝", False, "竟然写进去了")
        except ArchiveCorrupt:
            check("坏存档时保存也必须拒绝", True)
        check("坏文件没被覆盖",
              ARCHIVE.read_text(encoding="utf-8") == "{坏掉的 json")
    finally:
        PAPER_DIR, ARCHIVE = old_dir, old_arc

    print("papers 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
