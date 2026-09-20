#!/usr/bin/env python3
r"""录题心跳锁：让「每小时多次触发」的自动解析不会两轮同时写队列文件。

为什么需要：自动任务改成连续跑之后，一次触发可能还没做完上一场，下一次已经进来。
两个会话都在读改写 `数据/录题/Qoder录题队列.json` 和 `Qoder录题进度.jsonl`，
后写的会把先写的状态覆盖掉——表现为「某场做完又变回 todo」。

用法：
  python3 脚本/录题锁.py acquire      # 开工前抢锁；有人在跑就退出码 3（本轮直接放弃）
  python3 脚本/录题锁.py touch        # 每读完一组页图、每写完一个成品就敲一下
  python3 脚本/录题锁.py release      # 收工放锁
  python3 脚本/录题锁.py status       # 看当前锁状态

锁是 `数据/录题/.录题心跳` 的修改时间，TTL 默认 15 分钟。
崩溃没 release 也不要紧：心跳停更 15 分钟后锁自动失效，不会把整条流水线卡死。
"""
import os, sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HB = ROOT / "数据/录题/.录题心跳"
TTL = int(os.environ.get("LU_TI_TTL", 15 * 60))


def age():
    if not HB.exists():
        return None
    return time.time() - HB.stat().st_mtime


def write(msg):
    HB.parent.mkdir(parents=True, exist_ok=True)
    HB.write_text(json.dumps({"pid": os.getpid(), "说明": msg,
                              "时间": time.strftime("%Y-%m-%d %H:%M:%S")},
                             ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv):
    act = argv[0] if argv else "status"
    a = age()
    if act == "acquire":
        if a is not None and a < TTL:
            print("已有录题会话在跑（心跳 %d 秒前），本轮放弃" % a)
            sys.exit(3)
        write("acquire")
        print("锁已获取，心跳文件 %s" % HB.relative_to(ROOT))
        return
    if act == "touch":
        if a is not None and a > TTL:
            print("⚠️ 心跳已过期 %d 分钟，可能锁被别的会话接管过——确认没有并发再继续" % (a // 60))
            sys.exit(4)
        write("touch")
        print("心跳已刷新")
        return
    if act == "release":
        if HB.exists():
            HB.unlink()
        print("锁已释放")
        return
    if a is None:
        print("空闲（无心跳文件）")
    elif a < TTL:
        print("运行中，心跳 %d 秒前：%s" % (a, HB.read_text(encoding="utf-8").strip()))
    else:
        print("锁已过期（心跳 %d 分钟前），可被接管" % (a // 60))


if __name__ == "__main__":
    main(sys.argv[1:])
