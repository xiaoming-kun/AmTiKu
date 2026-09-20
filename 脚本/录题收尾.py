#!/usr/bin/env python3
r"""录题收尾：一场录完后回写进度 + 队列状态（规范 §3 / §12）。

用法：python3 脚本/录题收尾.py <序号> <入库题数> <待复核数> "备注" [状态]
状态默认 done；撞车/非数学时用 "跳过-已在库" / "跳过-非数学"。
进度锚点用卷名，不用行号。
"""
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "数据/录题"


def main(no, added, pending, note, status="done", minutes=0):
    QP = SRC / "Qoder录题队列.json"
    q = json.loads(QP.read_text(encoding="utf-8"))
    it = next((i for i in q["队列"] if i["序号"] == int(no)), None)
    if not it:
        sys.exit("队列里没有序号 %s" % no)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    it["状态"] = status
    it["完成时间"] = stamp
    it["入库题数"] = int(added)
    QP.write_text(json.dumps(q, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (SRC / "Qoder录题进度.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"卷名": it["卷名"], "状态": status, "入库题数": int(added),
                             "待复核": int(pending), "无答案卷": not it["答案"],
                             "用时分钟": int(minutes), "时间": stamp, "备注": note},
                            ensure_ascii=False) + "\n")
    # 库内模拟卷清单要跟着长，下一场的撞车预检才准
    from amti import store
    sims = [x for x in store.load_all() if x.meta.get("book") == "模拟题"]
    out = {}
    for x in sims:
        lab = x.meta.get("source_label")
        if not lab:
            continue
        d = out.setdefault(lab, {"题数": 0, "卷面标题": []})
        d["题数"] += 1
        pt = (x.meta.get("paper_title") or "").strip()
        if pt and pt not in d["卷面标题"]:
            d["卷面标题"].append(pt)
    for v in out.values():
        v["卷面标题"].sort()
    (SRC / "库内模拟卷清单.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    todo = [i["序号"] for i in q["队列"] if i["状态"] == "todo"]
    print("%s → %s（入库 %s，待复核 %s）" % (it["卷名"], status, added, pending))
    print("剩余 todo %d 场，接下来: %s" % (len(todo), todo[:8]))


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], a[3], a[4] if len(a) > 4 else "done",
         a[5] if len(a) > 5 else 0)
