#!/bin/bash
# AmTiKu · 通宵录题
#
# 用户 2026-09-17 的要求：
#   * 一份一份录入（跑完一份立刻入库，不攒批）
#   * 可中断续跑
#   * **白天（8:00–18:00）不要 DeepSeek 参与**——本脚本只用本地模型
#     （PaddleOCR-VL 转录 + 本地 27B 打考点），**不花任何云端 token**
#
# 用法：  ./录题-通宵.sh              # 跑默认目录（桌面/27年试卷/模拟试卷）
#         ./录题-通宵.sh <目录>       # 跑指定目录
#         ./录题-通宵.sh --状态       # 看进度
#
# 停：    pkill -f "amti.record.*--all"

set -u
cd "$(dirname "$0")"
PY=".venv/bin/python"
SRC="${1:-$HOME/Desktop/27年试卷/模拟试卷}"
LOG=/tmp/ruku/tongxiao.log
mkdir -p /tmp/ruku

BACKEND="$HOME/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-2.38.0"
GGUF="$HOME/.lmstudio/models/PaddlePaddle/PaddleOCR-VL-1.6-GGUF"

say() { echo "[$(date '+%m-%d %H:%M')] $*"; }

# ── 状态 ──────────────────────────────────────────────
if [ "${1:-}" = "--状态" ] || [ "${1:-}" = "--status" ]; then
  $PY - <<'EOF'
import json
from pathlib import Path
p = Path("数据/录题/进度.json")
if not p.exists():
    print("还没开始"); raise SystemExit
d = json.loads(p.read_text(encoding="utf-8"))
ok = [v for v in d.values() if v.get("ok")]
bad = [v for v in d.values() if not v.get("ok")]
print("已完成 %d 场，新增 %d 题；失败 %d 场"
      % (len(ok), sum(v.get("新增", 0) for v in ok), len(bad)))
if bad:
    for k, v in list(d.items())[:0] or []:
        pass
    print("失败样例：", [(v.get("label"), v.get("err")) for v in bad[:3]])
EOF
  exit 0
fi

# ── 1. OCR 服务（PaddleOCR-VL，端口 1235）─────────────
if ! curl -s --max-time 4 http://127.0.0.1:1235/health >/dev/null 2>&1; then
  say "起 OCR 服务（1235）…"
  ( cd "$BACKEND" && DYLD_LIBRARY_PATH="$BACKEND" nohup "$BACKEND/llama-server" \
      -m "$GGUF/PaddleOCR-VL-1.6-GGUF.gguf" \
      --mmproj "$GGUF/PaddleOCR-VL-1.6-GGUF-mmproj.gguf" \
      --host 127.0.0.1 --port 1235 -c 32768 -np 8 -ngl 99 --no-webui \
      >> /tmp/ruku/ocr.log 2>&1 & )
  for i in $(seq 1 30); do
    sleep 2
    curl -s --max-time 3 http://127.0.0.1:1235/health >/dev/null 2>&1 && break
  done
fi
curl -s --max-time 4 http://127.0.0.1:1235/health >/dev/null 2>&1 \
  && say "OCR 服务 ✓" || { say "OCR 服务起不来，看 /tmp/ruku/ocr.log"; exit 1; }

# ── 2. 本地 27B（打考点 + 判图，端口 1234）────────────
# 注意：LM Studio 常见「模型加载着、但 HTTP 服务停了」，两者要分开看
if ! curl -s --max-time 4 http://127.0.0.1:1234/v1/models >/dev/null 2>&1; then
  say "起 LM Studio 服务…"
  lms server start >/dev/null 2>&1
  sleep 5
fi
if ! curl -s --max-time 4 http://127.0.0.1:1234/v1/models 2>/dev/null | grep -q qwen; then
  say "加载 qwen3.8-27b…"
  lms load qwen/qwen3.8-27b --context-length 32768 --parallel 4 \
      --gpu max --ttl 7200 --identifier qwen/qwen3.8-27b -y >/dev/null 2>&1
fi
curl -s --max-time 4 http://127.0.0.1:1234/v1/models 2>/dev/null | grep -q qwen \
  && say "本地 27B ✓" || { say "27B 起不来"; exit 1; }

# ── 3. 跑批 ───────────────────────────────────────────
say "开始录题：$SRC"
say "（只用本地模型，不花云端 token；Ctrl-C 或 pkill 随时可停，重跑自动续）"
$PY -u -m amti.record --all "$SRC" --book 模拟题 \
    --workers 8 --outdir 数据/录题/输出 2>&1 | tee -a "$LOG"
say "跑批结束"
