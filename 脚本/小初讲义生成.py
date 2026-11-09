"""用 DeepSeek 为小学/初中每一章生成 content JSON。

    python3 脚本/小初讲义生成.py --all --workers 4
    python3 脚本/小初讲义生成.py --ids x11.2 x11.3
    python3 脚本/小初讲义生成.py --all --force

只写 `数据/专题/小初/content/<id>.json`；不编译、不改 manifest。
写完全部后跑：
    python3 -m amti.lecture_tex validate
    python3 -m amti.lecture_tex check
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import deepseek  # noqa: E402
from amti import lecture_tex  # noqa: E402

SPEC = (ROOT / "设计" / "小初讲义生成规范.md").read_text(encoding="utf-8")
CONTENT = ROOT / "数据" / "专题" / "小初" / "content"
DOSSIER = ROOT / "数据" / "专题" / "小初" / "dossiers"

SYSTEM = (
    "你是资深 K12 数学教师，熟悉人教版小学/初中教材。"
    "你只输出一个合法的 JSON 对象，不输出 Markdown 代码围栏、不解释。"
    "数学必须正确；每个公式和例题都要自己验算。"
)

SCHEMA = """{
  "id": "章id",
  "title": "章标题",
  "subtitle": "册 · 单元/章",
  "difficulty": "基础/中档/稍难",
  "stars": 1,
  "intro": "100~200 字引子",
  "outline": ["4~9 条内容提要"],
  "sections": [{"title": "节标题", "body": "LaTeX 正文"}],
  "summary": ["4~9 条本节小结"],
  "pitfalls": [{"wrong": "易错点", "right": "正确做法"}],
  "source_note": "教材位置/来源与许可"
}"""


def _compact_dossier(d: dict) -> dict:
    out = {k: d.get(k) for k in ("id", "stage", "stage_name", "book", "chapter", "points")}
    out["diagnostics"] = (d.get("diagnostics") or [])[:8]
    ex = d.get("existing") or {}
    out["existing"] = {
        "title": ex.get("title"),
        "text": (ex.get("text") or "")[:2200],
        "source": ex.get("source") or {},
    } if ex else {}
    return out


def _trim_sample(c: dict) -> dict:
    out = {k: c.get(k) for k in ("title", "subtitle", "difficulty", "stars", "intro",
                                 "outline", "summary", "pitfalls", "source_note")}
    out["sections"] = []
    for s in (c.get("sections") or [])[:2]:
        body = str(s.get("body") or "")
        out["sections"].append({"title": s.get("title"), "body": body[:900]})
    return out


def _prompt(d: dict, sample: dict) -> str:
    return f"""请严格按下面的规范，为这一章写一份 content JSON。

【规范】
{SPEC}

【本章素材】
{json.dumps(_compact_dossier(d), ensure_ascii=False, indent=1)}

【结构样板（只参考语气和结构，不要照抄内容）】
{json.dumps(_trim_sample(sample), ensure_ascii=False, indent=1)}

【输出 JSON 的字段】
{SCHEMA}

硬性要求：
1. 覆盖本章全部知识点，3–5 页，正文 1800–4000 字，3–7 节。
2. 每节至少一个 definition/theorem/proposition/example 环境；至少一幅 TikZ 图或一张表；纯代数章也必须有一张 booktabs 表（概念对比/法则归纳/易错点），不能只有段落。
3. 不排任何习题；全文不要出现“练习/习题/作业/选择题/填空题/下列各题”。
4. 不写裸 ~；范围写“7 到 10”或 $7\\sim10$。
5. 不用 \\documentclass/\\usepackage/\\chapter/\\section/\\includegraphics/\\input。
6. 不编造页码、作者、定理名；source_note 只写册/章/单元与开源许可。
7. 小学低年级用具体物体和数一数；初中写清条件、符号法则；不要提前教后续章节。
8. 只输出 JSON 对象，不要任何解释。
"""


def _extract_json(s: str) -> dict:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("回复里没有 JSON 对象")
    return json.loads(s[i:j + 1])


def gen_one(cid: str, sample: dict, force: bool = False) -> tuple[str, bool, str]:
    out = CONTENT / f"{cid}.json"
    if out.is_file() and not force:
        try:
            c = json.loads(out.read_text(encoding="utf-8"))
            if not lecture_tex.validate_content(c, cid):
                return cid, True, "已存在且通过 validate，跳过"
        except Exception:
            pass
    d = json.loads((DOSSIER / f"{cid}.json").read_text(encoding="utf-8"))
    prompt = _prompt(d, sample)
    last = ""
    for attempt in range(1, 4):
        try:
            raw = deepseek.chat(prompt, system=SYSTEM, json_mode=True,
                                max_tokens=8192, timeout=300)
            c = _extract_json(raw)
            c["id"] = cid
            c.setdefault("title", d.get("chapter") or cid)
            c.setdefault("subtitle", f"{d.get('book')} · {d.get('chapter')}")
            c.setdefault("difficulty", "基础" if d.get("stage") == "primary" else "中档")
            c.setdefault("stars", 1 if d.get("stage") == "primary" else 2)
            c.setdefault("source_note", f"本讲义依据人教版{d.get('book')}{d.get('chapter')}编写。")
            issues = lecture_tex.validate_content(c, cid)
            if not issues:
                out.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
                return cid, True, "OK"
            last = "；".join(issues)
            prompt += "\n\n上一版没通过校验，问题：\n- " + "\n- ".join(issues) + "\n请修好后重新输出完整 JSON。"
        except Exception as e:
            last = str(e)
            time.sleep(2 * attempt)
    return cid, False, last[:500]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    ids = a.ids or (sorted(p.stem for p in CONTENT.glob("*.json"))
                    if not a.all else [p.stem for p in DOSSIER.glob("*.json")])
    if not ids:
        print("没有要生成的章；用 --all 或 --ids")
        return 1
    sample = json.loads((CONTENT / "x11.1.json").read_text(encoding="utf-8"))
    CONTENT.mkdir(parents=True, exist_ok=True)
    done, bad = 0, 0
    with ThreadPoolExecutor(max_workers=max(1, min(6, a.workers))) as pool:
        futs = {pool.submit(gen_one, cid, sample, a.force): cid for cid in ids}
        for fut in as_completed(futs):
            cid, ok, msg = fut.result()
            if ok:
                done += 1
                print("OK", cid, msg, flush=True)
            else:
                bad += 1
                print("ERR", cid, msg, flush=True)
    print(f"完成 {done}，失败 {bad}，共 {len(ids)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
