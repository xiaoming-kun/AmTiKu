"""乐观并发重试装饰器。

从 `server.py` 抽出来，给各个 router 共用；只依赖 store 的
`ConcurrentWrite`，不依赖 Web 层，避免 router ↔ server 循环导入。
"""
from __future__ import annotations

import functools
import time

from fastapi import HTTPException

from amti import store


def retry_on_concurrent(fn):
    r"""乐观并发被拒就**自动重跑一遍**这个接口。

    `store.rewrite_all(..., based_on=…)` / `write_one(...)` 在读之后、写回之前
    发现库被别人写过，会抛 `ConcurrentWrite` 拒绝覆盖。对用户来说那是
    "保存失败，请重试"——但没必要让人手动重试：这里重跑整个接口，等于重新
    读、重新改、重新写。

    重跑是安全的：写回之前没有外部副作用（改的都是内存里的 Question 对象，
    写被拒就等于没改过）。重跑若干次仍被拒，才回 409。
    """
    @functools.wraps(fn)
    def _wrapped(*a, **kw):
        for i in range(4):
            try:
                return fn(*a, **kw)
            except store.ConcurrentWrite:
                if i == 3:
                    break
                time.sleep(0.05 * (i + 1))
        raise HTTPException(
            409, "题库正被别的进程连续写入（多半是后台求解器），"
                 "为避免覆盖别人的改动，这次**没有保存**。请在几秒后再试一次。")
    return _wrapped
