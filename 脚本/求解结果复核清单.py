r"""把外部大模型的求解结果整理成人工复核清单（Markdown）。

用法：

    python3 脚本/求解结果复核清单.py            # 生成 数据/题库审阅/求解复核清单_日期.md
    python3 脚本/求解结果复核清单.py --only mismatch,error    # 只要这几类

配套规则见 `docs/求解要求_外部模型.md` 第 8 节（验收口径）：
`mismatch` 必须人工复核后才决定改不改题库；`unsure` / `needs_figure` / `error`
不计入完成数，单独列出来。本脚本**只读不改**，不碰题库也不改结果文件。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "数据" / "题库审阅" / "求解批次"
OUT_DIR = ROOT / "数据" / "题库审阅" / "求解结果"
REPORT_DIR = ROOT / "数据" / "题库审阅"

_TAG = re.compile(r"<(状态|核对|答案|解析|备注)>\s*(.*?)(?:</\1>|\Z)", re.S)


def tags(body: str) -> dict:
    return {m.group(1): m.group(2).strip() for m in _TAG.finditer(body)}


def cell(s: str, limit: int = 160) -> str:
    r"""压成一行、去掉竖线，别把表格撑坏。"""
    s = re.sub(r"\s+", " ", s or "").replace("|", "／")
    return s if len(s) <= limit else s[:limit] + "…"


def collect() -> tuple[list[dict], dict]:
    rows, stat = [], {"题数": 0}
    for bf in sorted(BATCH_DIR.glob("批次_*.jsonl")):
        n = int(bf.stem.split("_")[1])
        rf = OUT_DIR / ("结果_%03d.txt" % n)
        recs = [json.loads(l) for l in bf.read_text(encoding="utf-8").splitlines() if l.strip()]
        blocks = {}
        if rf.exists():
            for key, body in jc_split(rf.read_text(encoding="utf-8")):
                blocks.setdefault(key, body)
        for r in recs:
            stat["题数"] += 1
            body = blocks.get(r["key"])
            if body is None:
                rows.append({**r, "批": n, "状态": "未做", "核对": "", "答案": "", "备注": ""})
                continue
            t = tags(body)
            rows.append({**r, "批": n,
                         "状态": t.get("状态", ""), "核对": t.get("核对", ""),
                         "求解答案": t.get("答案", ""), "解析": t.get("解析", ""),
                         "备注": t.get("备注", "")})
            stat[t.get("状态", "?")] = stat.get(t.get("状态", "?"), 0) + 1
            stat["核对_" + t.get("核对", "?")] = stat.get("核对_" + t.get("核对", "?"), 0) + 1
    return rows, stat


def jc_split(text: str):
    r"""跟机检脚本同一套切块逻辑（不 import 脚本目录，避免路径麻烦，这里复制最小实现）。"""
    blocks, cur, buf = [], None, []
    for line in text.splitlines():
        if line.startswith("@@Q "):
            if cur is not None:
                blocks.append((cur, "\n".join(buf)))
            cur, buf = line[4:].strip(), []
            continue
        if line.strip() == "@@END":
            if cur is not None:
                blocks.append((cur, "\n".join(buf)))
            cur, buf = None, []
            continue
        if cur is not None:
            buf.append(line)
    if cur is not None:
        blocks.append((cur, "\n".join(buf)))
    return blocks


def letters(s: str) -> str:
    return "".join(sorted(set(re.findall(r"[A-D]", (s or "").upper()))))


def suspect_type(rows: list[dict]) -> list[dict]:
    r"""疑似题型标错：单选却解出多个字母 / 多选只解出一个字母 / 题库答案是「AB」这类多字母。"""
    out = []
    for r in rows:
        if r["状态"] not in ("ok", "unsure", "error"):
            continue
        found = re.findall(r"故选\s*([A-D、,，\s]+)", r.get("解析", "") or "")
        picked = letters(found[-1]) if found else ""
        bank = letters(r["answer"])
        if r["type"] == "single_choice" and len(picked) >= 2:
            out.append((r, "单选题解出 %s" % picked))
        elif r["type"] == "multi_choice" and r["状态"] == "ok" and len(picked) == 1:
            out.append((r, "多选题只解出 %s" % picked))
        elif r["type"] == "single_choice" and len(bank) >= 2:
            out.append((r, "单选题题库答案是 %s" % bank))
    return out


def build(rows: list[dict], stat: dict, want: set) -> str:
    today = _dt.date.today().strftime("%Y-%m-%d")
    L = ["# 求解结果 · 人工复核清单（%s）" % today, ""]
    L += ["> 来源：`数据/题库审阅/求解批次/` + `数据/题库审阅/求解结果/`，"
          "口径见 `docs/求解要求_外部模型.md` 第 8 节。",
          "> **本清单只登记，不改题库。** `mismatch` 要人工复核后才决定改不改；"
          "`unsure` / `needs_figure` / `error` 不计入完成数。", ""]
    L += ["## 总览", "",
          "| 指标 | 数量 |", "|---|---|",
          "| 应做（缺解析题总数） | %d |" % stat["题数"],
          "| `ok`（解析可用） | %d |" % stat.get("ok", 0),
          "| `unsure`（没把握） | %d |" % stat.get("unsure", 0),
          "| `needs_figure`（缺图） | %d |" % stat.get("needs_figure", 0),
          "| `error`（题面坏了） | %d |" % stat.get("error", 0),
          "| `未做` | %d |" % stat.get("未做", 0),
          "| 核对 `match` | %d |" % stat.get("核对_match", 0),
          "| 核对 `mismatch`（答案要复核） | %d ｜其中解析可用（`ok`）%d，其余见第二、四节 |"
          % (stat.get("核对_mismatch", 0),
             len([r for r in rows if r.get("核对") == "mismatch" and r["状态"] == "ok"])),
          "| 核对 `missing`（题库没可核对答案） | %d ｜其中 `ok`%d |"
          % (stat.get("核对_missing", 0),
             len([r for r in rows if r.get("核对") == "missing" and r["状态"] == "ok"])),
          ""]

    def table(title, items, cols):
        L.append("## %s" % title)
        L.append("")
        if not items:
            L.append("无。")
            L.append("")
            return
        head = [c[0] for c in cols]
        L.append("| " + " | ".join(head) + " |")
        L.append("|" + "---|" * len(head))
        for r in items:
            L.append("| " + " | ".join(c[1](r) for c in cols) + " |")
        L.append("")

    if "mismatch" in want:
        ms = [r for r in rows if r.get("核对") == "mismatch" and r["状态"] == "ok"]
        table("一、答案不一致（mismatch，%d 道）— 先复核再动题库" % len(ms), ms, [
            ("批次", lambda r: "%03d" % r["批"]),
            ("题号 key", lambda r: cell(r["key"], 90)),
            ("题型", lambda r: r["type_label"]),
            ("题库答案", lambda r: cell(r["answer"], 40)),
            ("求解答案", lambda r: cell(r.get("求解答案", ""), 40)),
            ("依据（备注）", lambda r: cell(r.get("备注", ""))),
        ])

    if "error" in want:
        es = [r for r in rows if r["状态"] == "error"]
        table("二、题面坏了（error，%d 道）— 要回原卷重录" % len(es), es, [
            ("批次", lambda r: "%03d" % r["批"]),
            ("题号 key", lambda r: cell(r["key"], 90)),
            ("题型", lambda r: r["type_label"]),
            ("坏在哪（备注）", lambda r: cell(r.get("备注", ""))),
        ])

    if "needs_figure" in want:
        ns = [r for r in rows if r["状态"] == "needs_figure"]
        table("三、需要配图（needs_figure，%d 道）— 图丢了，题干还写着「如图」" % len(ns), ns, [
            ("批次", lambda r: "%03d" % r["批"]),
            ("题号 key", lambda r: cell(r["key"], 90)),
            ("题库答案", lambda r: cell(r["answer"], 40)),
            ("备注", lambda r: cell(r.get("备注", ""))),
        ])

    if "unsure" in want:
        us = [r for r in rows if r["状态"] == "unsure"]
        table("四、没把握（unsure，%d 道）" % len(us), us, [
            ("批次", lambda r: "%03d" % r["批"]),
            ("题号 key", lambda r: cell(r["key"], 90)),
            ("卡在哪（备注）", lambda r: cell(r.get("备注", ""))),
        ])

    if "missing" in want:
        ms = [r for r in rows if r.get("核对") == "missing" and r["状态"] == "ok"]
        table("五、题库没有可核对答案、由求解补出的结论（missing，%d 道）" % len(ms), ms, [
            ("批次", lambda r: "%03d" % r["批"]),
            ("题号 key", lambda r: cell(r["key"], 90)),
            ("补出的结论", lambda r: cell(r.get("求解答案", ""), 120)),
        ])

    if "type" in want:
        st = suspect_type(rows)
        L.append("## 六、疑似题型标错（%d 道）" % len(st))
        L.append("")
        if st:
            L.append("| 批次 | 题号 key | 登记题型 | 情况 |")
            L.append("|---|---|---|---|")
            for r, why in st:
                L.append("| %03d | %s | %s | %s |" % (r["批"], cell(r["key"], 90),
                                                       r["type_label"], cell(why, 40)))
        else:
            L.append("无。")
        L.append("")

    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="求解结果人工复核清单")
    ap.add_argument("--only", default="mismatch,error,needs_figure,unsure,missing,type",
                    help="要输出哪几节，逗号分隔")
    ap.add_argument("--out", default="", help="输出文件；默认 数据/题库审阅/求解复核清单_日期.md")
    a = ap.parse_args()
    want = {x.strip() for x in a.only.split(",") if x.strip()}
    rows, stat = collect()
    out = Path(a.out) if a.out else REPORT_DIR / (
        "求解复核清单_%s.md" % _dt.date.today().strftime("%Y%m%d"))
    out.write_text(build(rows, stat, want), encoding="utf-8")
    print("共 %d 题 → %s" % (stat["题数"], out))
    print("  ok %d / unsure %d / needs_figure %d / error %d"
          % (stat.get("ok", 0), stat.get("unsure", 0),
             stat.get("needs_figure", 0), stat.get("error", 0)))
    print("  mismatch %d / missing %d" % (stat.get("核对_mismatch", 0),
                                          stat.get("核对_missing", 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
