r"""DeepSeek 整理已有题库：**只生成建议，不写库**。

用于「题目已经在库里，但缺考点 / 缺难度 / 缺答案 / 缺解析」的存量整理。
写库仍然走现有两个唯一入口：

* 考点/难度 → `PATCH /api/questions/{key}`；
* 答案/解析 → `POST /api/questions/{key}/solution`（带 `source=deepseek`）。

所以这里只读题、调模型、返回 proposal；任何一条写盘都要人再点一次。
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import aispec, deepseek, knowledge, store

TASKS = {"points", "difficulty", "answer", "solution"}


def _q_text(q) -> str:
    lines = [q.stem.strip()]
    for o in (q.options or []):
        lines.append("%s. %s" % (o.label, o.text))
    if q.answer.strip():
        lines.append("现有答案：%s" % q.answer.strip())
    if q.solution.strip():
        lines.append("现有解析：%s" % q.solution.strip()[:1200])
    return "\n".join(lines)


def _one(q, tasks: set[str], model: str, point_list: str, allowed: set[str],
         usage: dict, lock) -> dict:
    req = []
    if "points" in tasks or "difficulty" in tasks:
        req.append('points（1–2 个考点编号，必须来自清单）')
    if "difficulty" in tasks:
        req.append('difficulty（"简单题" / "中档题" / "难题"）')
    if "answer" in tasks:
        req.append('answer（只写最终答案；选择题写字母）')
    if "solution" in tasks:
        req.append('solution（可入库的中文解析，LaTeX，只写解析正文）')
    prompt = (
        "你是 K12 数学教研员。下面是一道**已经在题库里**的题，请只补全缺失字段；"
        "不要改题干/选项，不要编造出处。只返回一个 JSON 对象。\n"
        "需要补：\n- " + "\n- ".join(req) + "\n"
        "要求：\n"
        "1. 不确定的字段留空串或 []，不要乱猜；\n"
        "2. solution 用 LaTeX（行内 $...$），不要 Markdown 围栏，不重复题干；\n"
        "3. 如果 solution 需要用到答案，必须与现有答案一致；现有答案为空时才在 answer 里给答案；\n"
        "4. points 只能从下面清单里选，第一条是主考点。\n"
    )
    if point_list:
        prompt += "\n考点清单：\n" + point_list + "\n"
    prompt += "\n题目：\n" + _q_text(q)[:4000]
    raw = deepseek.chat(prompt, system=aispec.system_prompt(),
                        timeout=300, max_tokens=4096, json_mode=True,
                        on_usage=lambda u: _add_usage(usage, lock, u))
    d = deepseek.json_obj(raw)
    prop: dict = {}
    if "points" in tasks:
        pts = d.get("points") or []
        if isinstance(pts, str):
            pts = [pts]
        ids = []
        for x in pts if isinstance(pts, list) else []:
            pid = str(x).strip()
            if pid in allowed and knowledge.get(pid) and pid not in ids:
                ids.append(pid)
        prop["points"] = ids[:2]
        prop["point_titles"] = [knowledge.title_of(x) for x in ids[:2]]
    if "difficulty" in tasks:
        diff = str(d.get("difficulty") or "").strip()
        prop["difficulty"] = diff if diff in ("简单题", "中档题", "难题") else ""
    if "answer" in tasks:
        ans = str(d.get("answer") or "").strip()
        prop["answer"] = ans[:120]
    if "solution" in tasks:
        sol = str(d.get("solution") or "").strip()
        sol = re.sub(r"^```(?:latex|tex|markdown)?\s*", "", sol, flags=re.I)
        sol = re.sub(r"\s*```$", "", sol).strip()
        prop["solution"] = sol[:12000]
        try:
            from .latex_blocks import parse_blocks
            prop["solution_blocks"] = parse_blocks(sol)
        except Exception:                       # noqa: BLE001
            prop["solution_blocks"] = []
    if "answer" in tasks and prop.get("answer"):
        try:
            from .latex_blocks import parse_blocks
            prop["answer_blocks"] = parse_blocks(prop["answer"])
        except Exception:                       # noqa: BLE001
            prop["answer_blocks"] = []
    return {"key": q.key, "ok": True, "proposal": prop,
            "current": {"points": q.points, "difficulty": q.difficulty,
                        "answer": q.answer, "solution": q.solution},
            "error": ""}


def _add_usage(usage: dict, lock, u: dict) -> None:
    with lock:
        for k in usage:
            try:
                usage[k] += int((u or {}).get(k) or 0)
            except (TypeError, ValueError):
                pass



def tag_items(items: list[dict], stage: str = "senior") -> dict:
    """给「已有题卡」补考点/难度，只调 DeepSeek，不碰题库。

    用于 AI 录题完成后发现转录漏了 points 的兜底；和「整理题库」共用
    `ai_tag.tag_points_deepseek` 的考点白名单与 JSON 校验。
    """
    from . import knowledge

    cfg = deepseek.load()
    if not cfg["api_key"]:
        raise deepseek.AIError("还没填 DeepSeek API Key")
    if not items:
        return {"ok": True, "items": [], "model": cfg["model"], "failed": 0}

    from .ai_tag import tag_batch
    out: list[dict] = [{"ok": False, "points": [], "point_titles": [],
                        "difficulty": "", "error": "未处理"} for _ in items]
    try:
        got = tag_batch([{"stem": str(it.get("stem") or ""),
                          "options": it.get("options") or [],
                          "type": str(it.get("type") or "")} for it in items],
                        batch_size=8)
        for i, g in enumerate(got):
            pts = g.get("points") or []
            out[i] = {"ok": bool(pts), "points": pts,
                      "point_titles": [knowledge.title_of(p) for p in pts],
                      "difficulty": g.get("difficulty") or "", "error": ""}
    except Exception as e:                           # noqa: BLE001
        for i in range(len(out)):
            out[i]["error"] = str(e)[:160]
    failed = sum(1 for x in out if not x.get("ok"))
    return {"ok": True, "items": out, "model": cfg["model"], "failed": failed}

def curate(keys: list[str], tasks: list[str], stage: str = "k12") -> dict:
    ts = {str(x).strip() for x in tasks if str(x).strip()}
    bad = ts - TASKS
    if bad:
        raise ValueError("不支持的整理任务：%s" % "、".join(sorted(bad)))
    if not ts:
        raise ValueError("至少选一个整理任务")
    keys = [str(k).strip() for k in keys if str(k).strip()]
    if not keys:
        raise ValueError("没有选中题目")
    cfg = deepseek.load()
    if not cfg["api_key"]:
        raise deepseek.AIError("还没填 DeepSeek API Key")
    all_points = knowledge.all_points(stage or "k12")
    point_list = "\n".join("%s %s" % (p.get("id"), knowledge.title_of(p.get("id")))
                           for p in all_points if p.get("id")) \
        if ("points" in ts or "difficulty" in ts) else ""
    allowed = {str(p.get("id")) for p in all_points if p.get("id")}
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
             "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 0}
    import threading
    lock = threading.Lock()
    items: list[dict] = []
    errors: list[str] = []
    t0 = time.time()

    def work(key: str) -> dict:
        one = store.read_one(key)
        if one is None:
            return {"key": key, "ok": False, "error": "没有这道题"}
        q = one[0]
        return _one(q, ts, cfg["model"], point_list, allowed, usage, lock)

    with ThreadPoolExecutor(max_workers=min(3, len(keys))) as ex:
        futs = {ex.submit(work, k): k for k in keys}
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:                                   # noqa: BLE001
                r = {"key": futs[fut], "ok": False, "error": str(e)[:200]}
            if r.get("ok"):
                items.append(r)
            else:
                errors.append(str(r.get("error") or r.get("key") or "整理失败"))
                items.append(r)
    # 保持用户传入的顺序；失败的也放在结果里，界面逐题显示。
    order = {k: i for i, k in enumerate(keys)}
    items.sort(key=lambda x: order.get(x.get("key"), 999))
    return {
        "ok": True, "items": items, "errors": errors,
        "model": cfg["model"],
        "cost_cny": deepseek.cost_cny(cfg["model"], usage),
        "seconds": int(time.time() - t0), "usage": usage,
    }
