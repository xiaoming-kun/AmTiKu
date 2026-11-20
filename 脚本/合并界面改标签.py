"""把历史上「一次改标签一个文件」的台账合并成按日一份（评估报告建议 #8）。

到 2026-11-20，`变更记录/` 下已攒 2,849 份 `YYYYMMDD_HHMMSS_界面改标签.md`，
一天几十份，grep 和按天回看都很难。本脚本：

1. 解析每份旧文件的四行（时间 / 题目 / 改动 / 内容指纹）；
2. 按日期追加到 `变更记录/<YYYYMMDD>_界面改标签.md` 的表格里；
3. 把旧文件**移动**（不是删除）到 `变更记录/归档/界面改标签/`。

用法：
    python3 脚本/合并界面改标签.py            # 只统计
    python3 脚本/合并界面改标签.py --apply    # 真合并 + 移动
"""
from __future__ import annotations

import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amti.audit import CHANGE_DIR  # noqa: E402

ARCHIVE = CHANGE_DIR / "归档" / "界面改标签"
NAME_RE = re.compile(r"^(\d{8})_\d{6}_界面改标签\.md$")
HEAD = "# 界面改标签\n\n| 时间 | 题目 | 改动 | 内容指纹 |\n|---|---|---|---|\n"


def _parse(p: Path):
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError:
        return None
    t = re.search(r"- 时间：(.+)", txt)
    q = re.search(r"- 题目：`([^`]+)`", txt)
    c = re.search(r"- 改动：(.*)", txt)
    f = re.search(r"- 内容指纹：([0-9a-f]+) → ([0-9a-f]+)", txt)
    if not (t and q and c):
        return None
    return (t.group(1).strip(), q.group(1).strip(), c.group(1).strip(),
            f.group(1) if f else "", f.group(2) if f else "")


def main() -> int:
    apply_ = "--apply" in sys.argv[1:]
    files = sorted(p for p in CHANGE_DIR.glob("*_界面改标签.md") if NAME_RE.match(p.name))
    rows: dict[str, list[tuple]] = defaultdict(list)
    bad = 0
    for p in files:
        r = _parse(p)
        if r is None:
            bad += 1
            continue
        day = p.name[:8]
        rows[day].append((p, r))
    total = sum(len(v) for v in rows.values())
    print("旧台账文件：%d 份（解析失败 %d）" % (len(files), bad))
    print("可合并：%d 行，跨 %d 天" % (total, len(rows)))
    print("示例日：", ", ".join("%s(%d)" % (d, len(rows[d])) for d in sorted(rows)[:5]))

    if not apply_:
        print("写库：否（--apply 才合并）")
        return 0

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    moved = 0
    for day, items in sorted(rows.items()):
        items.sort(key=lambda x: x[1][0])
        f = CHANGE_DIR / ("%s_界面改标签.md" % day)
        text = f.read_text(encoding="utf-8") if f.exists() else ""
        if not text.startswith("# 界面改标签"):
            text = HEAD + text
        elif "| 时间 | 题目 | 改动 | 内容指纹 |" not in text:
            # 已有一份按日文件（新机制写的），表格头重复加会乱，不重复
            pass
        add = []
        for _p, (at, key, fields, h1, h2) in items:
            line = "| %s | `%s` | %s | %s → %s（没变） |" % (at, key, fields, h1, h2)
            if line not in text:
                add.append(line)
        if add:
            f.write_text(text + "\n".join(add) + "\n", encoding="utf-8")
        for p, _r in items:
            shutil.move(str(p), str(ARCHIVE / p.name))
            moved += 1
    print("已合并：%d 行；移动旧文件：%d 份 → %s" % (total, moved, ARCHIVE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
