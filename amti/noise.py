r"""版面噪声收集器：把清洗器**删掉的东西**留档。

黑名单永远追不完识别引擎的写法（`<details>`、图注字母串、表格残留…）。
与其每次见到一种再补一条正则，不如把每份卷子里被删掉的片段自动攒起来：
几十份卷子之后，写法会收敛成有限几种，那时候再一次性写规则。

落盘：`数据/录题/噪声样本.jsonl`，一行一条，**按内容去重**。
看统计：

    python3 -m amti.noise
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "数据" / "录题" / "噪声样本.jsonl"

#: 收集哪些东西。**只收"被删掉的片段"，不存整题**——避免把题库内容带进日志。
PATTERNS = [
    ("html_details", re.compile(r"<details\b[\s\S]*?</details>", re.I)),
    ("html_tag", re.compile(r"</?[a-zA-Z][^>]{0,120}>")),
    ("fig_labels", re.compile(r"(?m)(?:^[A-Za-z][0-9]?\s*$\n){3,}")),
]

_seen: set[str] | None = None


def _load_seen() -> set[str]:
    global _seen
    if _seen is not None:
        return _seen
    _seen = set()
    if STORE.is_file():
        for line in STORE.read_text(encoding="utf-8").splitlines():
            try:
                _seen.add(json.loads(line).get("hash", ""))
            except Exception:                                 # noqa: BLE001
                pass
    return _seen


def scan(text: str) -> list[tuple[str, str]]:
    r"""一段正文 → `[(类型, 片段)]`。不改文本，只负责看。"""
    t = text or ""
    out: list[tuple[str, str]] = []
    # 先整块取 <details>…</details>，再把它从文本里挖掉——
    # 否则里面的每个 `<summary>`、`</details>` 都会各记一条，样本全是碎片。
    for m in PATTERNS[0][1].finditer(t):
        frag = m.group(0).strip()
        if frag:
            out.append(("html_details", frag[:400]))
    t = PATTERNS[0][1].sub(" ", t)

    for tag, pat in PATTERNS[1:]:
        for m in pat.finditer(t):
            frag = m.group(0).strip()
            if not frag:
                continue
            if tag == "html_tag" and len(frag) <= 4:      # `<br>` 这种没信息量
                continue
            out.append((tag, frag[:400]))
    return out


def record(label: str, no, field: str, text: str) -> int:
    r"""把这段正文里的噪声片段记下来，返回新增条数（去重后）。"""
    seen = _load_seen()
    rows = []
    for tag, frag in scan(text):
        h = hashlib.sha1((tag + "|" + frag).encode("utf-8")).hexdigest()[:16]
        if h in seen:
            continue
        seen.add(h)
        rows.append({"hash": h, "kind": tag, "label": label,
                     "no": no, "field": field, "snippet": frag})
    if not rows:
        return 0
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def summary() -> dict:
    r"""按类型/片段统计，给人看哪种写法最常见。"""
    if not STORE.is_file():
        return {"total": 0, "kinds": {}, "top": []}
    rows = [json.loads(l) for l in STORE.read_text(encoding="utf-8").splitlines() if l.strip()]
    kinds = Counter(r["kind"] for r in rows)
    sig = Counter(r["snippet"].split("\n")[0][:60] for r in rows)
    return {"total": len(rows), "kinds": dict(kinds), "top": sig.most_common(10)}


if __name__ == "__main__":
    s = summary()
    print("样本总数:", s["total"])
    print("按类型:", s["kinds"])
    print("最常见的 10 种：")
    for frag, n in s["top"]:
        print(f"  {n:>3}  {frag}")
