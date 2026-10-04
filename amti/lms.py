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


def ensure(model: str = "", *, key: str = "", wait: float = 120.0) -> tuple[bool, str]:
    r"""保证模型可用。**已经就绪就立刻返回，什么都不做。**

    返回 `(能不能用, 说明)`。调用方都在"用户点了按钮、正在等"的路径上，
    所以失败信息必须说清**卡在哪一步**——含糊的"失败"等于让人干等。
    """
    t0 = time.time()
    started = False

    if not up():
        if not shutil.which(SERVER_START[0]):
            return False, ("没装 LM Studio 的命令行工具 `%s`。"
                           "装好后重试；或改用 llama.cpp（见本文件顶部）"
                           % SERVER_START[0])
        try:
            subprocess.run(SERVER_START, capture_output=True, timeout=60)
        except Exception as e:
            return False, "启动服务失败：%s: %s" % (type(e).__name__, e)
        started = True
        deadline = time.time() + wait
        while time.time() < deadline:
            if up():
                break
            time.sleep(1.0)
        else:
            return False, "服务起了 %.0f 秒还没就绪（:1234 不通）" % wait

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
    # 无参数 = 显示现状（给 启动.sh status 用），**不启动**
    print(status())
    raise SystemExit(0)
