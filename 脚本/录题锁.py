#!/usr/bin/env python3
r"""录题并发控制：认领（谁做哪场）+ 记账锁（改共享状态文件那一小段）。

为什么拆成两把：
  一场解析要读 19~21 页图、几十分钟，但真正会打架的只有**改 `队列.json` / `进度.jsonl`**
  那一小段。所以让多个会话并行读图写各自的成品（成品文件名带序号，天然不冲突），
  只在记账那几秒互斥。这样能把吞吐从 ~5 场/小时提到 N 倍。

用法：
  python3 脚本/录题锁.py claim <序号>     # 认领一场；已被别人认领则退出码 5
  python3 脚本/录题锁.py drop  <序号>     # 放弃认领（做不完/出错时释放）
  python3 脚本/录题锁.py claimed          # 列出已认领
  python3 脚本/录题锁.py book             # 抢记账锁；已被占则退出码 3，等会儿再试
  python3 脚本/录题锁.py unbook           # 放记账锁
  python3 脚本/录题锁.py status           # 看两把锁的当前状态
  python3 脚本/录题锁.py sweep [分钟]     # 收掉僵尸认领（默认 90 分钟没动、或已做完却没 drop 的）

**每轮开工先 sweep 一次**，否则崩掉的会话会把场次永久占死。

记账锁 TTL 默认 3 分钟（只包几次文件写 + 一次 commit，崩了也会自动放开）。
认领标记**不带 TTL**：一场做完由本人 drop，避免 20 分钟后第二个人重复做同一场。
"""
import json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "数据/录题"
HB = SRC / ".录题心跳"
CLAIMS = SRC / "_认领"
TTL = int(os.environ.get("LU_TI_TTL", 3 * 60))


def age(p):
    return None if not p.exists() else time.time() - p.stat().st_mtime


def claim_file(no):
    return CLAIMS / str(no)


def main(argv):
    act = argv[0] if argv else "status"
    CLAIMS.mkdir(parents=True, exist_ok=True)
    if act == "claim":
        no = argv[1]
        f = claim_file(no)
        try:
            with open(f, "x", encoding="utf-8") as fh:      # O_EXCL：原子，不会两人同时拿到
                fh.write(json.dumps({"pid": os.getpid(),
                                     "时间": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
        except FileExistsError:
            print(" #%s 已被认领（%s），换下一场" % (no, f.read_text(encoding="utf-8").strip()))
            sys.exit(5)
        print("#%s 已认领" % no)
        return
    if act == "drop":
        f = claim_file(argv[1])
        if f.exists():
            f.unlink()
        print("#%s 认领已释放" % argv[1])
        return
    if act == "claimed":
        ns = sorted(int(p.name) for p in CLAIMS.glob("*") if p.name.isdigit())
        print("已认领 %d 场：%s" % (len(ns), ns))
        return
    if act == "book":
        a = age(HB)
        if a is not None and a < TTL:
            print("记账锁被占（%d 秒前），稍后再试" % a)
            sys.exit(3)
        HB.parent.mkdir(parents=True, exist_ok=True)
        HB.write_text(json.dumps({"pid": os.getpid(), "说明": "book",
                                  "时间": time.strftime("%Y-%m-%d %H:%M:%S")},
                                 ensure_ascii=False) + "\n", encoding="utf-8")
        print("记账锁已获取")
        return
    if act == "unbook":
        if HB.exists():
            HB.unlink()
        print("记账锁已释放")
        return
    if act == "sweep":
        # 收尸。认领不带 TTL 是故意的（防慢场被抢），但会话崩了/被截断就没人 drop，
        # 结果比停摆更糟：那两场被永久占位，任何 worker 都再也拿不到，等于从队列里消失。
        # 实测 2026-09-21 攒了 3 个僵尸认领，其中 #147 挂了 12.5 小时。
        ttl = int(argv[1]) * 60 if len(argv) > 1 else 90 * 60
        done = {}
        try:
            q = json.loads((SRC / "Qoder录题队列.json").read_text(encoding="utf-8"))["队列"]
            done = {i["序号"]: i["状态"] for i in q}
        except Exception:
            pass
        dropped = []
        for p in list(CLAIMS.glob("*")):
            if not p.name.isdigit():
                continue
            no = int(p.name)
            a = age(p)
            if done.get(no) in ("已解析-待入库", "done"):
                why = "已做完但没 drop（状态 %s）" % done[no]
            elif a is not None and a > ttl:
                why = "认领挂了 %d 分钟没动" % (a // 60)
            else:
                continue
            p.unlink()
            dropped.append("#%s %s" % (no, why))
        for d_ in dropped:
            print("收掉僵尸认领：%s" % d_)
        if not dropped:
            print("没有僵尸认领")
        return
    a = age(HB)
    ns = sorted(int(p.name) for p in CLAIMS.glob("*") if p.name.isdigit())
    print("记账锁：%s" % ("空闲" if a is None else
                          ("被占，%d 秒前" % a if a < TTL else "已过期 %d 分钟" % (a // 60))))
    print("认领中：%d 场 %s" % (len(ns), ns[:20]))


if __name__ == "__main__":
    main(sys.argv[1:])

