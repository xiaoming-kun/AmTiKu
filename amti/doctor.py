r"""服务体检：一条命令看清三个进程的状态，能拉起的顺手拉起。

这条链上有三个独立进程，任何一个卡住，界面上都只显示"出错"：

    LM Studio  :1234      结构化/打标/看图重读
    PaddleOCR-VL :8111    PDF/图片识别（MLX，逐页）
    AmTiKu     :8899      题库主服务

`python3 -m amti.doctor` 会逐个探活；缺的拉起、卡的杀掉重来，最后打一张表。
`python3 -m amti.doctor --check` 只看不动。
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.6) -> bool:
    with socket.socket() as sk:
        sk.settimeout(timeout)
        return sk.connect_ex((host, port)) == 0


def _http(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:                                         # noqa: BLE001
        return False


def _run(cmd: list[str], timeout: float = 120) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:                                    # noqa: BLE001
        return -1, "%s: %s" % (type(e).__name__, e)


# ── 四项检查 ────────────────────────────────────────────────

def check_lmstudio(fix: bool) -> tuple[bool, str]:
    if _port_open(1234):
        return True, "在线"
    if not fix:
        return False, "未运行"
    from . import lms
    ok, why = lms.ensure()
    return ok, why[:80]


def check_ocr(fix: bool) -> tuple[bool, str]:
    """识别引擎：PaddleOCR-VL（:8111）。"""
    from . import paddle
    if paddle.up():
        return True, "PaddleOCR-VL 在线"
    if not fix:
        return False, "未运行"
    ok, why = paddle.ensure()
    return ok, why[:80]


def check_app(fix: bool) -> tuple[bool, str]:
    if _http("http://127.0.0.1:8899/api/facets"):
        return True, "在线"
    if not fix:
        return False, "未运行"
    subprocess.Popen([sys.executable, "-m", "amti.web.server", "--port", "8899"],
                     cwd=str(ROOT), stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(20):
        if _port_open(8899):
            return True, "已拉起"
        time.sleep(1)
    return False, "起不来（看 /tmp/amti_web.log）"


CHECKS = [
    ("LM Studio :1234", check_lmstudio),
    ("识别引擎", check_ocr),
    ("题库 :8899", check_app),
]


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    fix = "--check" not in argv
    bad = 0
    for name, fn in CHECKS:
        ok, msg = fn(fix)
        print(("✓ " if ok else "✗ ") + name.ljust(18) + " " + msg)
        bad += 0 if ok else 1
    print()
    print("全部就绪" if not bad else "有 %d 项没起来" % bad)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
