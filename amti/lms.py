r"""LM Studio 的**按需启动**。

平台启动时**一个字节都不碰模型**；只有真的要用（点「大模型录入」、
或跑求解器）才调 `ensure()` 把它拉起来。

## 为什么要单独一个模块

`amti/solve.py`（求解）和 `amti/vlm.py`（读图）都要"先确保模型在跑"。
写两份 → 两处都会漏、行为还不一样。所以只此一处。

## 想换 llama.cpp？

它比 LM Studio 稳（`--mmproj` 显式指定视觉投影，不吃 LM Studio 那套
自动配对），改这两个常量即可：

    SERVER_START = ["llama-server", "-m", "<模型>.gguf",
                    "--mmproj", "<视觉投影>.gguf", "--port", "1234"]
    MODEL_LOAD   = []          # 起进程时就带上模型了，不用单独加载

接口两边都是 OpenAI 兼容，`amti/vlm.py` 一个字都不用改。
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

#: LM Studio 的 OpenAI 兼容接口（**求解**走这里）。
API = "http://127.0.0.1:1234/v1"

#: llama.cpp 的接口（**读图**走这里）。用另一个端口，
#: 好让求解与读图各跑各的、互不打扰——27B 的求解模型不必为读图让位。
VISION_API = "http://127.0.0.1:1235/v1"
VISION_PORT = 1235

#: 怎么起服务 / 怎么加载模型。
#: `{key}` = **模型 key**（`lms ls` 里那一列，如 `dots.ocr`）——用它去加载；
#: `{id}`  = **identifier**（API 里 `"model"` 字段用的名字，如 `dots-ocr`）。
#: ⚠️ 这俩**不是一回事**，实测踩过：拿 identifier 去 `lms load` 会报
#: `Model not found`，而报错信息看着像"模型没下载"。
SERVER_START = ["lms", "server", "start"]
MODEL_LOAD = ["lms", "load", "{key}", "--identifier", "{id}", "-y"]

# ══ 读图：为什么用 llama.cpp 而不是 LM Studio ═══════════════════════════
#
# **实测结论（2026-10-03，逐条验过）**：
#
#   · LM Studio 0.4.24 **没把 mmproj 与模型配对**，把视觉投影当成独立模型，
#     于是调接口直接报 `does not support image inputs`。这是它内部的配对逻辑，
#     外面插不上手 —— 试过 `lms load` 各种写法都不行。
#   · llama.cpp 用 `--mmproj` **显式指定**，同一个模型文件就报
#     `modalities: {'vision': True}`，并且真的读出了图（`A.240 B.280`）。
#
# 所以读图这条路走 llama.cpp。它和 LM Studio 用的是同一份 .gguf，
# **不用重下模型**。
#
# ⚠️ 三个实测踩过的坑，改这里的路径前先看：
#   ① `dots.ocr` 的 mmproj 能加载、但**吐不出内容**（会把图像标记原样回显）。
#      所以读图默认用 paddleocr-vl，不是 dots.ocr。
#   ② paddleocr 目录里有**两个** mmproj，`mmproj.gguf` 是**坏的**
#      （`failed to seek for tensor v.post_ln.bias`），要用
#      `PaddleOCR-VL-1.6-GGUF-mmproj.gguf`。
#   ③ `prompt_tokens` **不能**用来判断"图有没有进去"——llama.cpp 的
#      OpenAI 接口不把图像 token 算进去。实测读对了图，它照样是 363。
#      （我一开始拿它当判据，白查了一轮。）
LLAMA_SERVER = Path.home() / ".amtiku" / "llama.cpp" / "llama-server"
VISION_MODEL = (Path.home() / ".lmstudio/models/PaddlePaddle"
                / "PaddleOCR-VL-1.6-GGUF/PaddleOCR-VL-1.6-GGUF.gguf")
VISION_MMPROJ = (Path.home() / ".lmstudio/models/PaddlePaddle"
                 / "PaddleOCR-VL-1.6-GGUF/PaddleOCR-VL-1.6-GGUF-mmproj.gguf")

#: 求解模型的 MLX 目录——**关思考的模板补丁打在它身上**。
#:
#: 为什么要在模型文件外面动手：LM Studio 的 MLX 引擎**不吃** `reasoning_effort`
#: （实测 `none` / `low` / 顶层 `enable_thinking` / `chat_template_kwargs`
#: 四种传法全部无效），而 Qwen3.8 默认 `xhigh` 思考，会把 `maxtok` 全烧在
#: 推理上，正文一个字不返回、HTTP 还是 200——实测整卷 532 秒、0 题块、
#: `finish=length`，一声不吭。模板那条只有 `enable_thinking is false`
#: 才插空思考块，所以只能改文件本身。
MLX_ROOT = Path.home() / ".lmstudio/models"
MLX_MODEL_DIR = (Path.home() / ".lmstudio/models/lmstudio-community"
                 / "Qwen3.8-27B-MLX-4bit")
NO_THINK_LINE = "{%- set enable_thinking = false %}"


def ensure_no_think() -> str:
    r"""给**所有 MLX 模型**补一行「默认关思考」。幂等；没模型就什么都不做。

    为什么要扫全目录：实测 9B 也一样默认思考，把 16000 的 maxtok 全烧在
    reasoning 上、正文一个字不返回（守卫当场拦下）。补丁只认 27B 那个路径
    的话，换个模型就又中招。判据是 `config.json` 里有 `quantization`
    （MLX 的标记），GGUF 目录不动。
    """
    import json as _json
    notes = []
    for tpl in sorted(MLX_ROOT.glob("*/*/chat_template.jinja")):
        cfg = tpl.parent / "config.json"
        if not cfg.is_file():
            continue
        try:
            if "quantization" not in _json.loads(cfg.read_text(encoding="utf-8")):
                continue
            text = tpl.read_text(encoding="utf-8")
        except (OSError, ValueError):
            continue
        if text.lstrip().startswith(NO_THINK_LINE):
            continue
        try:
            tpl.write_text(NO_THINK_LINE + "\n" + text, encoding="utf-8")
            notes.append(tpl.parent.name)
        except OSError:
            pass
    return ("给 %s 补上关思考的模板行" % "、".join(notes)) if notes else ""


def up(timeout: float = 2.0) -> bool:
    """:1234 的接口通不通。"""
    try:
        with urllib.request.urlopen(API + "/models", timeout=timeout):
            return True
    except Exception:
        return False


def loaded(timeout: float = 15.0) -> list[str]:
    r"""当前**已加载进内存**的模型 identifier。

    ⚠️ 不能用 `/v1/models` —— 它列的是**全部已下载**的模型（实测 6 个），
    跟"在不在内存里"是两回事。只有 `lms ps` 说得清。
    解析从 `IDENTIFIER` 表头之后开始：表头之前是"没有模型"的提示语，
    按列数猜会把提示语里的 `No` 当成模型名。
    """
    if not shutil.which("lms"):
        return []
    try:
        out = subprocess.run(["lms", "ps"], capture_output=True, text=True,
                             timeout=timeout).stdout
    except Exception:
        return []
    return _parse_ps(out)


def _run_quiet(cmd: list[str], timeout: float) -> None:
    """跑一条命令，失败/超时都不吭声——调用方只关心"起没起来"。"""
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:                                         # noqa: BLE001
        pass


def _wait_up(seconds: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < seconds:
        if up():
            return True
        time.sleep(1.0)
    return False


def _clear_stale_lock() -> None:
    r"""清掉 LM Studio 上次没退干净留下的 pid 锁。

    实测：进程被 kill 之后 `llmster-pid.lock` 还在，双击图标只是闪一下就退，
    看起来像"应用坏了"。
    """
    lock = Path.home() / ".lmstudio" / ".internal" / "llmster-pid.lock"
    if not lock.is_file():
        return
    try:
        pid = int("".join(c for c in lock.read_text() if c.isdigit()) or 0)
    except Exception:                                         # noqa: BLE001
        return
    if pid:
        try:
            os.kill(pid, 0)          # 还活着就别动
            return
        except OSError:
            pass
    try:
        lock.unlink()
    except Exception:                                         # noqa: BLE001
        pass


def _launch_app() -> str:
    r"""把 LM Studio **应用**拉起来。`lms` 只是它的命令行，应用没开时叫不动。

    两条路：`open -a` 正常、Finder 兜底（实测用 `open` 有时不弹窗，
    走 Finder 的 `open application file` 反而能起来）。
    """
    _run_quiet(["open", "-a", "LM Studio"], 20)
    time.sleep(4)
    if up():
        return "open -a 启动成功"
    try:
        subprocess.run(
            ["osascript", "-e",
             'tell application "Finder" to open application file "LM Studio" '
             'of folder "Applications" of startup disk'],
            capture_output=True, text=True, timeout=25)
        time.sleep(4)
    except Exception:                                         # noqa: BLE001
        pass
    return "Finder 兜底已尝试"


def ensure(model: str = "", *, key: str = "", wait: float = 120.0) -> tuple[bool, str]:
    r"""保证模型可用。**已经就绪就立刻返回，什么都不做。**

    返回 `(能不能用, 说明)`。调用方都在"用户点了按钮、正在等"的路径上，
    所以失败信息必须说清**卡在哪一步**——含糊的"失败"等于让人干等。
    """
    note = ensure_no_think()   # 模板被重下载冲掉时补回来（幂等）
    if note and model:
        # 刚补的模板，已加载的实例还用着旧的 → 卸掉，让它重载时读到新的
        _run_quiet(["lms", "unload", model], 60)
    t0 = time.time()
    started = False

    if not up():
        if not shutil.which(SERVER_START[0]):
            return False, ("没装 LM Studio 的命令行工具 `%s`。"
                           "装好后重试；或改用 llama.cpp（见本文件顶部）"
                           % SERVER_START[0])
        # ① 应用开着的话，`lms server start` 最快
        _run_quiet(SERVER_START, 60)
        ok = _wait_up(15)
        if not ok:
            # ② 应用根本没开：先把 App 拉起来（open → Finder 兜底），再起服务
            note = _launch_app()
            _clear_stale_lock()
            _run_quiet(SERVER_START, 60)
            ok = _wait_up(wait)
            if not ok:
                return False, ("LM Studio 应用起来了吗？:1234 等了 %.0f 秒仍不通（%s）"
                               % (wait, note))
        started = True

    if not model:
        return True, "接口就绪" + ("（刚启动，%.0f 秒）" % (time.time() - t0) if started else "")
    if model in loaded():
        return True, "模型 `%s` 已在内存" % model

    cmd = [a.format(key=key or model, id=model) for a in MODEL_LOAD]
    if not cmd:                       # llama.cpp：模型跟着进程起
        return True, "接口就绪（模型由启动命令自带）"
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=wait + 120)
    except Exception as e:
        return False, "加载模型 `%s` 失败：%s: %s" % (model, type(e).__name__, e)
    if model in loaded():
        return True, "已加载 `%s`（%.0f 秒）" % (model, time.time() - t0)
    return False, ("加载 `%s`（key=%s）失败（退出码 %s）：%s"
                   % (model, key or model, r.returncode,
                      ((r.stderr or "") + (r.stdout or ""))[-300:]))


#: 读图服务是不是**本进程起的**。
#: 只有自己起的才在退出时收掉 —— 你手动 `./启动.sh vision` 起的那个
#: 也许正被别的脚本用着，不该跟着 web 服务一起死。
#: 整卷结构化要的上下文。10 页数学卷约 1.5 万 token，再加 8k 输出，32k 起步。
SOLVE_CTX = int(os.environ.get("AMTIKU_SOLVE_CTX", "32768"))

#: 模型常驻时长（秒）。默认一周——省得隔夜重跑时第一发请求就 400。
TTL_SECONDS = int(os.environ.get("AMTIKU_LLM_TTL", str(7 * 24 * 3600)))

#: 已确认可用的 (模型, 上下文) → identifier。避免每次调用都问一遍 `lms ps`。
_CTX_CACHE: dict[tuple[str, int], str] = {}


def ps_json(timeout: float = 20.0) -> list[dict]:
    r"""`lms ps --json` 的结构化结果。拿不到就返回空列表（调用方当"没加载"）。"""
    if not shutil.which("lms"):
        return []
    try:
        out = subprocess.run(["lms", "ps", "--json"], capture_output=True,
                             text=True, timeout=timeout).stdout
        return json.loads(out) if out.strip() else []
    except Exception:                                         # noqa: BLE001
        return []


def unload(model: str, timeout: float = 120.0) -> tuple[bool, str]:
    r"""卸载一个已加载的模型。返回 `(成功, 说明)`。

    只给界面的「AI 模型状态」用：用户想立刻释放 9B/27B 内存时，
    不用切终端敲 `lms unload`。**不主动加载**任何东西。
    """
    if not (model or "").strip():
        return False, "没有指定模型"
    if not shutil.which("lms"):
        return False, "没装 LM Studio 命令行工具 `lms`"
    try:
        p = subprocess.run(["lms", "unload", model], capture_output=True,
                           text=True, timeout=timeout)
    except Exception as e:                                    # noqa: BLE001
        return False, "卸载失败：%s" % e
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    if p.returncode != 0:
        return False, out or ("lms unload 退出码 %d" % p.returncode)
    return True, out or "已卸载"


def ensure_ctx(model: str, *, need_tokens: int = 0,
               min_ctx: int = SOLVE_CTX, wait: float = 900.0,
               ttl: int | None = None) -> tuple[bool, str, str]:
    r"""确保 `model` 以**足够大的上下文**加载，返回 `(能不用, identifier, 说明)`。

    ## 为什么要这个

    整卷结构化是把**十几页文本一次性**塞给 27B。LM Studio 默认按 8192 起，
    于是第一次跑必然 `HTTP 400`——报错原文还只说 "Bad Request"，看不出是
    上下文不够。手工 `lms load -c 32768` 能解决，但**没人会记得每次都敲**，
    而且加载出来的 identifier 会变成 `qwen/qwen3.8-27b:2`，
    调用方拿旧名字还会 404。

    所以把这三件事收成一处：

      ① 上下文不够 → 自动卸载重载（按需要算，不低于 `min_ctx`）
      ② 重载后 identifier 变了 → 把新名字返回给调用方
      ③ 已经够了 → **什么都不做**，直接复用（不折腾正在跑的模型）

    `need_tokens` 给的是"这份文档大约多少 token"，会按 1.15 倍余量、
    向上取整到 4096 的倍数；再与 `min_ctx`、模型自身上限取合适值。
    """
    ok, why = ensure()
    if not ok:
        return False, "", why

    want = min_ctx
    if need_tokens > 0:
        want = max(want, int(math.ceil((need_tokens + 8192) * 1.15 / 4096)) * 4096)

    rows = ps_json()
    hits = [r for r in rows
            if r.get("modelKey") == model or model in (r.get("identifier") or "")]
    ceiling = max([r.get("maxContextLength") or 0 for r in hits] or [0])
    # **装不下就别发**：请求一旦超过上下文，服务端只会回一句 400 并把
    # 三十万 token 的输入原样丢掉——整卷白扫、白等。这里当场说清楚，
    # 顺带把「拆开再录」这个唯一可行的下一步写进错误里。
    if ceiling and need_tokens > ceiling:
        return False, "", (
            "输入太长：约 %d token，超过 `%s` 的上下文上限 %d。"
            "整本汇编/答案册不能一次结构化 —— 拆成单份试卷再录，"
            "或换上下文更大的模型。" % (need_tokens, model, ceiling))
    if ceiling and want > ceiling:
        want = ceiling

    key = (model, want)
    if key in _CTX_CACHE:
        return True, _CTX_CACHE[key], "复用已确认的 `%s`（%d）" % (_CTX_CACHE[key], want)

    good = [r for r in hits if (r.get("contextLength") or 0) >= want]
    if good:
        ident = good[0]["identifier"]
        _CTX_CACHE[key] = ident
        return True, ident, "复用 `%s`（上下文 %d ≥ %d）" % (
            ident, good[0].get("contextLength"), want)

    # 不够 → 把同款模型的实例都卸掉，按目标上下文重载
    for r in hits:
        try:
            subprocess.run(["lms", "unload", r["identifier"]],
                           capture_output=True, timeout=120)
        except Exception:                                     # noqa: BLE001
            pass
    try:
        # `--ttl` 给一周：LM Studio 默认 60 分钟不用就卸载，隔一晚上再跑
        # 第一发请求就会撞 400（模型正在 JIT 加载）。这里直接把它钉住。
        subprocess.run(["lms", "load", model, "-c", str(want), "--gpu", "max",
                        "--ttl", str(ttl or TTL_SECONDS), "-y"],
                       capture_output=True, text=True, timeout=wait)
    except Exception as e:                                    # noqa: BLE001
        return False, "", "加载 `%s`（-c %d）失败：%s: %s" % (model, want, type(e).__name__, e)

    rows = ps_json()
    hits = [r for r in rows if r.get("modelKey") == model]
    good = [r for r in hits if (r.get("contextLength") or 0) >= want]
    if not good:
        return False, "", ("`%s` 重载后仍没有 %d 上下文（现有：%s）。"
                           "多半是内存不够，换个更小的模型或降 `AMTIKU_SOLVE_CTX`。"
                           % (model, want, [r.get("contextLength") for r in hits]))
    ident = good[0]["identifier"]
    _CTX_CACHE[key] = ident
    return True, ident, "已按 %d 上下文重载 → `%s`" % (want, ident)


_VISION_SPAWNED = False


def stop_vision_if_ours() -> str:
    r"""退出时收掉自己起的读图服务；不是自己起的就不动。返回说明（空=没做事）。

    ⚠️ 为什么要这个：`ensure_vision()` 用 `start_new_session=True` 起进程，
    它**脱离**了父进程。实测漏掉一次收尾，它就变成孤儿跑了 **10 小时**、
    一直占着内存 —— 而用户以为"关掉应用就没了"。
    """
    global _VISION_SPAWNED
    if not _VISION_SPAWNED:
        return ""
    _VISION_SPAWNED = False
    return "读图服务：" + stop_vision()


def up_vision(timeout: float = 2.0) -> bool:
    """:1235（llama.cpp 读图服务）通不通。"""
    try:
        with urllib.request.urlopen(VISION_API + "/models", timeout=timeout):
            return True
    except Exception:
        return False


def ensure_vision(*, wait: float = 180.0) -> tuple[bool, str]:
    r"""保证**读图**服务可用。已就绪就立刻返回。

    和 `ensure()` 分开是因为它俩跑的不是同一个东西：
    求解用 LM Studio（:1234，27B），读图用 llama.cpp（:1235，paddleocr-vl）。
    合成一个的话，读图会把 27B 挤掉。

    起进程用的是 `subprocess.Popen`，**不等待**——llama-server 是常驻
    服务，不是一次性的命令。之后轮询端口等它就绪。
    """
    if up_vision():
        return True, "读图服务已在跑"
    if not LLAMA_SERVER.is_file():
        return False, ("没找到 llama.cpp：%s\n"
                       "装一个（约 30MB，不用重下模型）：\n"
                       "  curl -sL https://github.com/ggml-org/llama.cpp/releases/"
                       "download/b11378/llama-b11378-bin-macos-arm64.tar.gz | "
                       "tar xz -C ~/.amtiku && mv ~/.amtiku/llama-b11378 "
                       "~/.amtiku/llama.cpp" % LLAMA_SERVER)
    for f, what in ((VISION_MODEL, "模型"), (VISION_MMPROJ, "视觉投影")):
        if not f.is_file():
            return False, "找不到%s文件：%s" % (what, f)
    global _VISION_SPAWNED
    t0 = time.time()
    try:
        subprocess.Popen(
            [str(LLAMA_SERVER), "-m", str(VISION_MODEL), "--mmproj", str(VISION_MMPROJ),
             "--host", "127.0.0.1", "--port", str(VISION_PORT),
             "-c", "8192", "--no-warmup"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        _VISION_SPAWNED = True      # 记下来，退出时好收（见 stop_vision_if_ours）
    except Exception as e:
        return False, "启动 llama.cpp 失败：%s: %s" % (type(e).__name__, e)
    while time.time() - t0 < wait:
        if up_vision():
            return True, "读图服务已启动（%.0f 秒）" % (time.time() - t0)
        time.sleep(1.0)
    return False, ("llama.cpp 起了 %.0f 秒还没就绪（:%d 不通）。"
                   "多半是 mmproj 文件不对——注意 paddleocr 目录里"
                   " `mmproj.gguf` 是坏的，要用 `PaddleOCR-VL-1.6-GGUF-mmproj.gguf`"
                   % (wait, VISION_PORT))


def stop_vision() -> str:
    """停掉读图服务（`./启动.sh stop` 用）。**只停自己起的那个。**"""
    try:
        r = subprocess.run(["pkill", "-f", "llama-server.*--port %d" % VISION_PORT],
                           capture_output=True, timeout=10)
        return "已停" if r.returncode == 0 else "本来就没跑"
    except Exception as e:
        return "停止失败：%s" % e


def status() -> dict:
    """给界面看的现状。**不启动任何东西**——点了按钮才走 `ensure()`。"""
    return {"up": up(), "loaded": loaded(), "api": API}


def _selftest() -> int:
    r"""控制样本：`loaded()` 的解析必须**不把提示语当成模型名**。

    实测踩过：`lms ps` 没有模型时输出 "No models are currently loaded."，
    按"列数 ≥ 5 就是数据行"去猜会把 `No` 当成模型名 —— 于是
    `ensure()` 以为模型已加载，跳过加载，后面调接口才发现模型不在。
    """
    fails = 0

    def check(name, got, want):
        nonlocal fails
        ok = got == want
        print("  %s %s" % ("✓" if ok else "✗", name) if ok
              else "  ✗ %s  got=%r want=%r" % (name, got, want))
        if not ok:
            fails += 1

    print("lms 自检")
    check("空输出 → 没有模型", _parse_ps(""), [])
    check("只有提示语 → 没有模型",
          _parse_ps("No models are currently loaded.\n\nTo load a model, run:\n\n"
                    "    lms load <model path>\n"), [])
    check("有表头有数据 → 取 identifier",
          _parse_ps("\nIDENTIFIER    MODEL       STATUS    SIZE\n"
                    "dots-ocr      dots.ocr    IDLE      3.24 GB\n"), ["dots-ocr"])
    check("两个模型",
          _parse_ps("IDENTIFIER  MODEL\n"
                    "a           m1\nb           m2\n"), ["a", "b"])

    # 上下文护栏：装不下的文档**不能发出去**（发了就是 400 + 整卷白跑）。
    # 数字取自真实现场：260 页答案册估 32.5 万 token，模型上限 262144。
    global ps_json, ensure
    _old_ps, _old_ensure = ps_json, ensure
    ps_json = lambda *_a, **_k: [{"modelKey": "m", "identifier": "m",
                                  "contextLength": 32768,
                                  "maxContextLength": 262144}]
    ensure = lambda *_a, **_k: (True, "")
    _CTX_CACHE.clear()
    try:
        ok, _ident, why = ensure_ctx("m", need_tokens=324935)
        fits = ensure_ctx("m", need_tokens=12000)[0]
    finally:
        ps_json, ensure = _old_ps, _old_ensure
        _CTX_CACHE.clear()
    check("装不下（32.5 万 > 26.2 万）→ 不发请求", ok, False)
    check("错误里写清上限和下一步", "262144" in why and "拆成单份" in why, True)
    check("装得下 → 放行", fits, True)

    print("lms 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


def _parse_ps(out: str) -> list[str]:
    """把 `lms ps` 的输出解析成 identifier 列表（独立出来好测）。"""
    names: list[str] = []
    seen_header = False
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "IDENTIFIER":
            seen_header = True
            continue
        if seen_header:
            names.append(parts[0])
    return names


if __name__ == "__main__":
    import sys as _s
    if "--selftest" in _s.argv:
        raise SystemExit(_selftest())
    _args = [a for a in _s.argv[1:] if not a.startswith("-")]
    if _args:
        # `python3 -m amti.lms 32768` → 确保模型按该上下文加载（启动脚本可先调它）
        try:
            _ctx = int(_args[0])
        except ValueError:
            _ctx = SOLVE_CTX
        _ok, _ident, _msg = ensure_ctx(os.environ.get("AMTIKU_LLM", "qwen/qwen3.8-27b"),
                                       min_ctx=_ctx)
        print(("✓ " if _ok else "✗ ") + _msg)
        if _ok:
            print("identifier:", _ident)
        raise SystemExit(0 if _ok else 1)
    # 无参数 = 显示现状（给 启动.sh status 用），**不启动**
    print(status())
    raise SystemExit(0)
