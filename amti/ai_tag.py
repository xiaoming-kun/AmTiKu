"""DeepSeek 补考点：从旧 AI 录题模块迁出的共享函数。

只做一件事：题目文本 → 1–3 个考点 id + 难度；不写库。
"""
from __future__ import annotations

import json

from . import deepseek, knowledge

_DIFFS = ("简单题", "中档题", "难题")


def _points() -> list[dict]:
    try:
        return [
            {"id": p["id"], "title": str(p.get("title") or "").split("（")[0].strip()}
            for p in knowledge.all_points()
        ]
    except Exception:                        # noqa: BLE001
        return []


def _point_ids() -> set[str]:
    return {p["id"] for p in _points()}


def tag_points_deepseek(item: dict, images: list[bytes], *, on_usage=None
                        ) -> tuple[list[str], str]:
    """从题干/选项/题图补 1–3 个考点；只用 DeepSeek。"""
    pts = _points()
    if not pts:
        return [], ""
    plist = "\n".join("%s %s" % (p["id"], p["title"]) for p in pts)
    opts = item.get("options")
    opt_lines = []
    for o in (opts if isinstance(opts, list) else []):
        if isinstance(o, dict):
            t = str(o.get("text") or "").strip()
            if t:
                opt_lines.append("%s. %s" % (o.get("label") or "", t))
    prompt = (
        "你是 K12 数学教研员。只根据下面的题干和选项，从考点清单里选 1–3 个最贴切的考点，"
        "并给难度。只返回 JSON：{\"points\":[\"编号\"],\"difficulty\":\"简单题|中档题|难题\"}。"
        "编号必须来自清单；认不出就给空数组。\n\n考点清单：\n%s\n\n题干：%s\n%s"
        % (plist, str(item.get("stem") or "").strip()[:3000],
           ("选项：\n" + "\n".join(opt_lines[:20]) + "\n") if opt_lines else "")
    )
    raw = deepseek.chat(prompt, images[:2], timeout=180, max_tokens=300,
                        json_mode=True, on_usage=on_usage)
    d = deepseek.json_obj(raw)
    ids = d.get("points") or []
    if isinstance(ids, str):
        ids = [ids]
    allowed = _point_ids()
    out: list[str] = []
    for x in (ids if isinstance(ids, list) else []):
        pid = str(x).strip()
        if pid in allowed and pid not in out:
            out.append(pid)
    diff = str(d.get("difficulty") or "").strip()
    if diff not in _DIFFS:
        diff = ""
    return out[:3], diff


def tag_batch(items: list[dict], *, batch_size: int = 8, on_usage=None) -> list[dict]:
    """批量补考点：一次给 5–8 道，降低重复 prefill；返回与 items 等长的结果。"""
    pts = _points()
    if not pts or not items:
        return [{"points": [], "difficulty": ""} for _ in items]
    plist = "\n".join("%s %s" % (p["id"], p["title"]) for p in pts)
    out: list[dict] = [{"points": [], "difficulty": ""} for _ in items]
    for start in range(0, len(items), max(1, batch_size)):
        batch = items[start:start + max(1, batch_size)]
        payload = []
        for j, it in enumerate(batch):
            opts = []
            for o in (it.get("options") or []):
                if isinstance(o, dict) and str(o.get("text") or "").strip():
                    opts.append("%s. %s" % (o.get("label") or "", o.get("text")))
            payload.append({"i": j, "type": str(it.get("type") or ""),
                            "stem": str(it.get("stem") or "")[:2500],
                            "options": opts[:20]})
        prompt = (
            "你是 K12 数学教研员。给下面每道题从考点清单选 1–3 个最贴切的考点，并给难度。"
            "只返回 JSON：{\"items\":[{\"i\":0,\"points\":[\"编号\"],"
            "\"difficulty\":\"简单题|中档题|难题\"}]}。编号必须来自清单。\n\n"
            "考点清单：\n%s\n\n题目：\n%s"
            % (plist, json.dumps(payload, ensure_ascii=False))
        )
        raw = deepseek.chat(prompt, timeout=300, max_tokens=2000,
                            json_mode=True, on_usage=on_usage)
        d = deepseek.json_obj(raw)
        got = d.get("items") if isinstance(d.get("items"), list) else []
        allowed = _point_ids()
        for x in got:
            if not isinstance(x, dict):
                continue
            try:
                j = int(x.get("i"))
            except (TypeError, ValueError):
                continue
            if not (0 <= j < len(batch)):
                continue
            ids = x.get("points") or []
            if isinstance(ids, str):
                ids = [ids]
            ids = [str(p).strip() for p in ids if str(p).strip()]
            ids = [p for p in ids if p in allowed][:3]
            diff = str(x.get("difficulty") or "").strip()
            out[start + j] = {"points": ids,
                              "difficulty": diff if diff in _DIFFS else ""}
    return out
