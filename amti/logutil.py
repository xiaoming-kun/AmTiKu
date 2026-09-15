"""统一日志。

为什么需要（后端审查报告 Important #3）：

    全项目原本**0 处 logging**，而 `except Exception:` 有 12 处。
    抽样看那些捕获都写了注释说明意图（"记档失败不该挡住改标签"、
    "失败就原样复制，不阻断"）——作者是有意识的，但后果是
    **失败完全不可见**。本项目已经反复踩到"Slidev 失败是静默的：
    构建成功 ≠ 渲染正确"，每次都要人工看 PDF 文本层才发现。

用法：

    from amti.logutil import get_logger
    log = get_logger(__name__)
    ...
    except Exception:
        log.warning("记档失败（不影响本次修改）", exc_info=True)

级别用环境变量 `AMTIKU_LOG_LEVEL` 控制（默认 WARNING）；
`AMTIKU_LOG_LEVEL=DEBUG` 可以看清每一步在干什么。
"""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False
_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DEFAULT_DATEFMT = "%H:%M:%S"


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = os.environ.get("AMTIKU_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, _DEFAULT_DATEFMT))
    root = logging.getLogger("amti")
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """取一个挂在 `amti` 名下的 logger。"""
    _configure()
    short = name.split(".")[-1] if name.startswith("amti") else name
    return logging.getLogger(f"amti.{short}")
