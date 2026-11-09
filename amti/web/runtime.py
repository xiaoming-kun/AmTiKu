"""Web 层运行时状态。

心跳/退出倒计时和基线缓存原来散在 `server.py`，路由一拆就会变成
「router 反向 import server」。这里只放**可变的进程级状态和常量**，
不依赖 FastAPI，也不做业务读写；server 和 router 都从这里拿同一份对象。
"""
from __future__ import annotations

# 浏览器心跳：页面每几秒 ping，关页面 sendBeacon 缩短倒计时
LAST_PING: list[float] = [0.0]
PING_SEEN: list[bool] = [False]
INFLIGHT: list[int] = [0]

EXIT_IDLE_SEC = 95.0
GONE_GRACE_SEC = 30.0

# 基线状态缓存（/api/baseline）；存基线后由 /api/snapshot 清空
BASE: dict = {"key": None, "v": None}
