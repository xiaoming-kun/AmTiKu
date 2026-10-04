#!/bin/bash
# 其他杂项转录跑批：**按 文件 × 页块 循环，每块之间重启服务**。
#
# 三个坑都在这里堵上（每个都是实测踩出来的，详见 数据/录题/赵礼显/README.md）：
#
# 1. **App Nap**（最要命）：`UserIsActive = 0` 时 macOS 给后台进程上后台 QoS，
#    `llama-server` 会在生成中途**整段冻住**（tg_3s 从 12 t/s 掉到 0.01 t/s，
#    冻 11–17 分钟又自己活过来）。**纯文本请求也这样**，跟图/模型/内存都无关。
#    解法是 `caffeinate -dimsu`，**`-u` 才是关键那个**。
# 2. **服务跑久了退化**：`-c 65536` 那档跑一阵后 prompt eval 从 50 秒/页
#    涨到 **966 秒/页**。用 `-c 32768 -np 4`（每槽 8192）+ max_tokens 4500，
#    再按块重启做双保险。
# 3. **孤儿请求**：客户端被杀，服务端仍会把已入队的请求生成完。所以
#    （a）录题脚本用**有界队列**而不是 ThreadPoolExecutor.map，
#    （b）这里 `pkill -9` 并用 `pgrep` 确认死透才起新的。
#
# ⚠️ **用 1235 端口，不动 LM Studio 的 1234**。
#    原因：LM Studio 的监听进程名是 `LM Studio`，`pkill -f llama-server` 打不到它，
#    于是"起了新服务却连回旧服务"——实测扫出来的全是 dots.ocr 的结果。
#    所以自己另起一个端口，靠 `AMTI_API_PORT` 和录题脚本对齐；
#    停服务时也只杀**带 `--port 1235` 的那一个**。
#
# 用法：  bash 脚本/其他杂项跑批.sh              # 从已缓存的地方续跑
#         bash 脚本/其他杂项跑批.sh --状态
#         CHUNK=40 bash 脚本/其他杂项跑批.sh     # 改每块页数
set -u
cd "$(dirname "$0")/.."

PY=.venv/bin/python
BACKEND="$HOME/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-2.46.0"
GGUF="$HOME/.lmstudio/models/lmstudio-community/Qwen3.8-27B-GGUF"
CTX=32768
SLOTS=4
CHUNK="${CHUNK:-60}"           # 每块页数（越大重启越少、退化风险越高）
PORT="${AMTI_API_PORT:-1235}"
export AMTI_API_PORT="$PORT"
LOG=/tmp/zlx/logs

if [ "${1:-}" = "--状态" ]; then
  "$PY" 脚本/其他杂项录题.py report
  exit 0
fi

mkdir -p "$LOG"

# ⚠️ 起跑前先清**残留的 scan 子进程**。
# 实测踩过：`pkill -f 跑批.sh` 只杀得掉 bash 本身，它 fork 出的
# `python … scan` **会变成孤儿继续跑** —— 于是新旧两批同时在跑、
# 抢同一个服务的 4 个槽（每页从 90 秒涨到 300 秒），
# 而且**两边往同一批 pNNN.txt 上写**，谁后写谁算，结果是竞态。
# 旧进程还带着旧版本的模块在内存里，改了代码它也不知道。
# ⚠️ 只认**真在跑脚本的那个解释器进程**，光按脚本名匹配会误伤：
# 任何"命令行里字面包含这串字"的 bash 包装（比如手工敲的
# `pgrep -f "…录题.py scan"`、或一条 nohup 包装命令）都会被 `-f` 匹配到，
# 于是守卫把自己挡住了、还报"有残留没清掉"。实测踩过。
_SCAN_RE='[Pp]ython.*其他杂项录题\.py scan'
pkill -f "$_SCAN_RE" 2>/dev/null
sleep 2
pkill -9 -f "$_SCAN_RE" 2>/dev/null
sleep 1
_left=$(pgrep -f "$_SCAN_RE" | wc -l | tr -d ' ')
[ "$_left" -gt 0 ] && { echo "还有 ${_left} 个残留 scan 进程没清掉，先手工处理"; exit 1; }

stop_server() {
  # 只杀**我们起的那个**（靠命令行里的端口认人），LM Studio 的 1234 一概不碰
  pkill -9 -f "llama-server.*--port $PORT" 2>/dev/null
  for _ in $(seq 1 30); do pgrep -f "llama-server.*--port $PORT" >/dev/null || break; sleep 1; done
  sleep 2
}

start_server() {
  stop_server
  echo "[$(date '+%H:%M:%S')] 起服务 :$PORT -c $CTX -np $SLOTS"
  ( cd "$BACKEND" && DYLD_LIBRARY_PATH="$BACKEND" nohup caffeinate -dimsu \
      "$BACKEND/llama-server" \
      -m "$GGUF/Qwen3.8-27B-Q6_K.gguf" --mmproj "$GGUF/mmproj-Qwen3.8-27B-BF16.gguf" \
      --host 127.0.0.1 --port $PORT -c $CTX -np $SLOTS -ngl 99 --no-webui \
      >> "$LOG/server.log" 2>&1 & )
  for _ in $(seq 1 90); do
    sleep 3
    # ⚠️ 光"有响应"不算就绪：模型加载完之前 llama-server 返回的是
    # `503 {"error":{"message":"Loading model"}}`，而 `curl >/dev/null`
    # 对 503 **也返回 0** —— 于是判据通过、整块请求打在没加载好的服务上，
    # 全块失败还要重跑。实测踩到过。必须确认响应里真有模型 id。
    curl -s --max-time 3 "http://127.0.0.1:$PORT/v1/models" 2>/dev/null \
      | grep -q '"id"' && { sleep 2; return 0; }
  done
  echo "服务起不来，看 $LOG/server.log"; return 1
}

# ── 逐文件跑：拿 `list` 的输出算每份文件多少页 ─────────────────────
# 用 Python 打印「短名 页数」两列，bash 逐行读——比在 bash 里算 PDF 页数可靠。
: > "$LOG/server.log"
"$PY" - <<'EOF' > "$LOG/plan.txt"
import sys
sys.path.insert(0, '.')
sys.path.insert(0, '脚本')
import importlib.util, fitz
from pathlib import Path
spec = importlib.util.spec_from_file_location("m", "脚本/其他杂项录题.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for f in m.list_files():
    p = m.pdf_of(f)
    if p.exists():
        print("%s\t%d" % (f["slug"], fitz.open(p).page_count))
EOF

total=0; done_files=0
while IFS=$'\t' read -r slug pages; do
  [ -z "$slug" ] && continue
  lo=1
  while [ "$lo" -le "$pages" ]; do
    hi=$((lo + CHUNK - 1)); [ "$hi" -gt "$pages" ] && hi=$pages
    # 这一块已经全缓存就跳过，省一次服务重启
    missing=$(for i in $(seq "$lo" "$hi"); do
                f=$(printf "数据/录题/其他杂项/scan/%s/p%03d.txt" "$slug" "$i")
                [ -s "$f" ] || echo x
              done | wc -l | tr -d ' ')
    if [ "$missing" -eq 0 ]; then
      lo=$((hi + 1)); continue
    fi
    start_server || exit 1
    # ⚠️ `$hi（` 这种"变量紧跟全角括号"会被 bash 当成变量名的一部分
    # （报 unbound variable）——相邻非 ASCII 一律用 ${} 包起来。
    echo "[$(date '+%H:%M:%S')] ${slug} p${lo}-${hi}（缺 ${missing} 页）"
    "$PY" -u 脚本/其他杂项录题.py scan --file "$slug" --only "$lo-$hi" \
        --workers $SLOTS 2>&1 | tee -a "$LOG/scan.log"
    lo=$((hi + 1))
  done
  done_files=$((done_files + 1))
done < "$LOG/plan.txt"

stop_server
echo "[$(date '+%H:%M:%S')] 跑批结束"
"$PY" 脚本/其他杂项录题.py report
