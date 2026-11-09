"""AmTiKu · Web 后端

只做三件事：把题目读出来、把统计算出来、把卷子导出来。
**不缓存、不写库**——分卷文件是唯一真相，每次请求现读。

接口按 UI 的需要设计，不是按数据库的表结构：

    GET  /api/questions      列表（带筛选）—— 工作台左中栏
    GET  /api/questions/{key} 单题详情
    POST /api/questions/{key}/source  改源码（默认只检查不写盘）
    GET  /api/stats          统计
    GET  /api/facets         筛选项（题型/来源/考点，带计数）
    POST /api/generate/replace 单题换题候选
    POST /api/export         导出套卷（LaTeX/elegantbook）
    GET  /api/figure         题图
"""
from __future__ import annotations

import atexit
import os
import sys
import threading
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from amti.paths import ROOT, UI_DIST

# 本文件在 amti/web/ 下，比 amti/store.py 深一级 → 项目根要退三层
PKG = ROOT
sys.path.insert(0, str(PKG))

from amti.logutil import get_logger                       # noqa: E402
from amti import lite_cache                                # noqa: E402
from amti import store                                    # noqa: E402
from amti.web.core import (_SEQ, _brief_cached_lite, _lite_hash, _seq_of,  # noqa: E402
                           _usage, _usage_bump)
from amti.web.runtime import (EXIT_IDLE_SEC, INFLIGHT as _INFLIGHT,  # noqa: E402
                              LAST_PING as _LAST_PING, PING_SEEN as _PING_SEEN)
from amti.web.routers.papers import router as papers_router  # noqa: E402
from amti.web.routers.trash import router as trash_router    # noqa: E402
from amti.web.routers.review import router as review_router  # noqa: E402
from amti.web.routers.meta import router as meta_router      # noqa: E402
from amti.web.routers.stats import router as stats_router    # noqa: E402
from amti.web.routers.topics import router as topics_router  # noqa: E402
from amti.web.routers.questions import router as questions_router  # noqa: E402
from amti.web.routers.insights import router as insights_router  # noqa: E402
from amti.web.routers.generate import router as generate_router  # noqa: E402
from amti.web.routers.exporting import router as exporting_router  # noqa: E402
from amti.web.routers.ai import (router as ai_router,        # noqa: E402
                                 _AI_JOBS, _AI_CANCELS)

log = get_logger(__name__)

# ── 导出串行化 ────────────────────────────────────────────
# 后端审查报告 Important #6：导出是 30s~分钟级的长任务，且都调用同一套
# LaTeX 渲染、往同一个临时目录写。并发跑会互相踩（一个在清理
# 临时文件，另一个正在读）。用非阻塞锁：忙就回 429，而不是排队堆线程。
app = FastAPI(title="AmTiKu · K12 数学题库")


#: 超过这个时长的请求记一条 warning，方便定位“列表为什么突然 3 秒”。
#: 可用 `AMTIKU_SLOW_MS` 调整；不设则 3000ms。配错就退回默认，别让服务起不来。
try:
    SLOW_REQUEST_MS = float(os.environ.get("AMTIKU_SLOW_MS", "3000"))
except ValueError:
    SLOW_REQUEST_MS = 3000.0

app.include_router(papers_router)
app.include_router(trash_router)
app.include_router(review_router)
app.include_router(meta_router)
app.include_router(stats_router)
app.include_router(topics_router)
app.include_router(questions_router)
app.include_router(insights_router)
app.include_router(generate_router)
app.include_router(exporting_router)
app.include_router(ai_router)


@app.middleware("http")
async def _count_inflight(request, call_next):
    """进出各加减一次，给看门狗判断"现在有没有活没干完"。

    数**所有**请求而不是只数导出：除了导出，录入、统计、讲义生成
    也都是几秒到几十秒的长活，中途被 `os._exit` 砍掉一样会留半成品。
    """
    _INFLIGHT[0] += 1
    try:
        return await call_next(request)
    finally:
        _INFLIGHT[0] -= 1


@app.middleware("http")
async def _same_origin_only(request, call_next):
    r"""只接受本机来源的请求。

    后端审查报告 Important #4：只 bind 127.0.0.1 是**对的一半** ——
    浏览器允许**任意网页**向 http://127.0.0.1:8899 发 POST（同源策略
    只挡"读取响应"，不挡"发送"）。而删题/改源码现在**不需要口令**，
    任意网页都能触发 `/api/trash/delete`——Origin 白名单因此更重要。
    校验 Origin 同时挡住 CSRF 与 DNS-rebinding。

    curl / 同源页面不带或带本机 Origin，都放行。
    """
    origin = request.headers.get("origin")
    if origin and not origin.startswith(
            ("http://127.0.0.1", "http://localhost", "http://[::1]")):
        log.warning("拒绝跨站请求：Origin=%s path=%s", origin, request.url.path)
        return JSONResponse({"detail": "拒绝跨站请求（只允许本机页面调用）"},
                            status_code=403)
    return await call_next(request)


@app.middleware("http")
async def _log_slow(request, call_next):
    """慢请求留痕：只记 > SLOW_REQUEST_MS 的路径，不刷正常访问日志。"""
    t0 = time.perf_counter()
    try:
        return await call_next(request)
    finally:
        ms = (time.perf_counter() - t0) * 1000
        if ms >= SLOW_REQUEST_MS:
            log.warning("慢请求 %.0fms %s %s", ms, request.method, request.url.path)


# ── 心跳 / 看门狗 ────────────────────────────────────────────────────
#
# 心跳状态、倒计时常量在 `amti.web.runtime`；alive/gone 端点在
# `amti.web.routers.meta`。这里只留看门狗线程和收尾逻辑。

def _cleanup_vision() -> None:
    r"""收掉**本进程起的**读图服务。可以重复调用（`lms` 那边会清标志）。

    只收自己起的：你手动 `./启动.sh vision` 起的那个也许正被别的脚本用着。
    """
    from amti import lms as _lms
    try:
        msg = _lms.stop_vision_if_ours()
        if msg:
            print("  " + msg)
    except Exception:
        pass


def _watchdog() -> None:
    """没 ping 了就退出。只在 `--exit-with-browser` 下起。

    **有请求在跑就不退**：导出要几十秒，退在这儿等于把活砍一半。
    等它跑完，下一轮（2 秒后）再看，那时没 ping 就正常退出。
    """
    while True:
        time.sleep(2.0)
        if not _PING_SEEN[0]:
            continue                       # 页面还没打开过，不算
        if _INFLIGHT[0] > 0:
            continue                       # 有请求在跑，等它干完
        if time.monotonic() - _LAST_PING[0] > EXIT_IDLE_SEC:
            print("页面已关闭，题库服务退出")
            # ⚠️ **必须在这里收，不能指望 `finally`/`atexit`** ——
            # `os._exit()` 会跳过它们（实测：读图服务因此变成孤儿跑了 10 小时）。
            _cleanup_vision()
            os._exit(0)


# ── 静态前端 ──────────────────────────────────────────────────────────

if UI_DIST.exists():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        # no-cache：前端重建后刷新即生效（旧项目的坑：
        # index.html 没缓存头 → 改了前端要 Cmd+Shift+R 才看得到）
        return FileResponse(UI_DIST / "index.html",
                            headers={"Cache-Control": "no-cache, must-revalidate"})
else:
    # 别静默跳过：以前这里什么都不说，免安装版就成了"接口都能用、首页 404"，
    # 排查时只能靠猜。源码运行时没构建前端也会走到这里。
    log.warning("找不到前端 %s —— 只提供 API，界面打不开"
                "（源码运行请先 cd web && npm run build）", UI_DIST)


def _sync_lite_cache() -> None:
    """把还没有落盘的 lite 记录补进 SQLite。派生缓存，失败不影响主流程。"""
    try:
        qs = store.load_cached()
        have = lite_cache.hashes()
        batch: list[tuple[str, str, dict]] = []
        valid: dict[str, str] = {}
        n = 0
        for q in qs:
            h = _lite_hash(q)
            valid[q.key] = h
            if have.get(q.key) == h:
                continue
            try:
                d = _brief_cached_lite(q)
            except Exception:
                continue
            batch.append((q.key, h, d)); n += 1
            if len(batch) >= 400:
                lite_cache.put_many(batch); batch.clear()
        if batch:
            lite_cache.put_many(batch)
        gone = lite_cache.prune(valid)
        if n or gone:
            print("  lite 缓存补齐 %d 条，清掉 %d 条过期" % (n, gone))
    except Exception as e:
        print("  lite 缓存同步失败（不影响使用）：%s" % e)


def main() -> int:
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser(description="AmTiKu Web 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--open", action="store_true",
                    help="启动后自动打开浏览器")
    ap.add_argument("--exit-with-browser", action="store_true",
                    help="浏览器页面一关就退出（配合 --open 用）")
    a = ap.parse_args()

    url = f"http://{a.host}:{a.port}"
    print(f"AmTiKu → {url}")

    # **预热**：把全库读进缓存、把知识点索引建好。
    # 不做的话，第一次打开页面要等 2 秒多（全库 17,554 道现读现解析）。
    # 这里花 1 秒，换用户第一次点开就是快的。
    def _warm():
        t0 = time.time()
        try:
            # **只做真正影响首屏的事**：把题库读进内存、建好录入序号。
            # FTS/读模型/ lite 缓存不再在这里同步构建：数据刚变过时，
            # 一次 FTS 重建 + 读模型重建会让首个请求等十几秒。
            # 列表/搜索会在后台按需增量/回退，首屏先出来。
            n = len(store.load_cached())
            _seq_of("")
            print("  已载入 %d 道（%.1fs）" % (n, time.time() - t0))
        except Exception as e:
            print("  预热失败（不影响使用）：%s" % e)
    threading.Thread(target=_warm, daemon=True).start()

    if a.exit_with_browser:
        # 看门狗只在这里起。命令行调用时页面从没打开过，
        # 起看门狗会**立刻**把服务杀掉。
        threading.Thread(target=_watchdog, daemon=True).start()
        print("  页面关闭后会自动退出")

    if a.open:
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    # 预热「录入序号」表：原本首个列表请求要全库走一遍才建好
    try:
        _seq_of("")
        log.info("录入序号表已预热：%s 道", len(_SEQ))
    except Exception:
        log.warning("预热录入序号表失败（不影响启动）", exc_info=True)

    log.info("AmTiKu 服务启动：http://%s:%s", a.host, a.port)
    # 服务退了就把**我们自己起的**读图服务一并收掉，否则它会变成孤儿进程
    # 一直占内存（实测残留过 10 小时）。`atexit` 覆盖正常退出；
    # `os._exit` 那条路（关浏览器的看门狗）由 `_cleanup_vision()` 单独负责。
    atexit.register(_cleanup_vision)
    # `atexit` 在**被信号打死**时不执行（实测 `kill -TERM` 进程直接没了，
    # 读图服务就成了孤儿）。所以 SIGTERM/SIGINT 也要自己接一下：
    # 先收尾，再交回默认行为退出。
    import signal

    def _on_signal(signum, _frame):
        _cleanup_vision()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for _sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(_sig, _on_signal)
        except (ValueError, OSError):
            pass                                  # 非主线程 / 平台不支持
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
