#!/bin/bash
# 赵礼显讲义转录跑批：**分块跑，每块之间重启服务**。
#
# 三个坑，都在这里堵上（每个都是实测踩出来的）：
#
# 1. **App Nap**（最要命）：`UserIsActive = 0` 时 macOS 给后台进程上
#    App Nap / 后台 QoS，llama-server 会在生成中途**整段冻住**——
#    实测 `tg_3s` 从 12 t/s 掉到 0.01 t/s，冻 11–17 分钟又自己活过来。
#    **纯文本请求也这样**，所以跟图片、跟模型、跟内存都无关。
#    解法是 `caffeinate -dimsu`，其中 **`-u` 才是关键那个**。
# 2. **服务跑久了退化**：`-c 65536 -np 4` 这一档跑一阵之后 prompt eval
#    从 50 秒/页涨到 **966 秒/页**。改用 `-c 32768 -np 4`（每槽 8192）
#    并把 max_tokens 压到 4500；再按块重启做双保险。
# 3. **孤儿请求**：客户端被杀，服务端仍会把已入队的请求生成完。
#    所以（a）录题脚本用有界队列而不是 `ThreadPoolExecutor.map`，
#    （b）这里用 `pkill -9` 并用 `pgrep` 确认真的死透了才起新的。
#
# 用法：  bash 脚本/赵礼显讲义跑批.sh            # 从已缓存的地方续跑
#         bash 脚本/赵礼显讲义跑批.sh --状态
set -u
cd "$(dirname "$0")/.."

PY=.venv/bin/python
BACKEND="$HOME/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-2.46.0"
GGUF="$HOME/.lmstudio/models/lmstudio-community/Qwen3.8-27B-GGUF"
CTX=32768
SLOTS=4
CHUNK=40                       # 每块页数
LOG=/tmp/zlx/logs

if [ "${1:-}" = "--状态" ]; then
  echo "已转录 $(ls 数据/录题/赵礼显/scan/ 2>/dev/null | wc -l | tr -d ' ') / 340 页"
  exit 0
fi

mkdir -p "$LOG"

stop_server() {
  pkill -9 -f llama-server 2>/dev/null
  for _ in $(seq 1 30); do pgrep -f llama-server >/dev/null || break; sleep 1; done
  sleep 2
}

start_server() {
  stop_server
  echo "[$(date '+%H:%M:%S')] 起服务 -c $CTX -np $SLOTS"
  ( cd "$BACKEND" && DYLD_LIBRARY_PATH="$BACKEND" nohup caffeinate -dimsu \
      "$BACKEND/llama-server" \
      -m "$GGUF/Qwen3.8-27B-Q6_K.gguf" --mmproj "$GGUF/mmproj-Qwen3.8-27B-BF16.gguf" \
      --host 127.0.0.1 --port 1234 -c $CTX -np $SLOTS -ngl 99 --no-webui \
      >> "$LOG/server.log" 2>&1 & )
  for _ in $(seq 1 90); do
    sleep 2
    # 光 listen 还不算就绪：模型加载完之前会返回 503
    curl -s --max-time 3 http://127.0.0.1:1234/v1/models >/dev/null 2>&1 \
      && sleep 6 && return 0
  done
  echo "服务起不来，看 $LOG/server.log"; return 1
}

: > "$LOG/server.log"
lo=1
while [ $lo -le 340 ]; do
  hi=$((lo + CHUNK - 1)); [ $hi -gt 340 ] && hi=340
  # 这一块已经全缓存了就跳过，省一次服务重启
  missing=$(for i in $(seq $lo $hi); do
              f=$(printf "数据/录题/赵礼显/scan/p%03d.txt" $i)
              [ -s "$f" ] || echo x
            done | wc -l | tr -d ' ')
  if [ "$missing" -eq 0 ]; then
    echo "[$(date '+%H:%M:%S')] p${lo}-${hi} 已缓存，跳过"
    lo=$((hi + 1)); continue
  fi
  start_server || exit 1
  # ⚠️ `$hi（` 这种"变量紧跟全角括号"会被 bash 当成变量名的一部分
  # （报 `hi?: unbound variable`）——相邻非 ASCII 一律用 `${}` 包起来。
  echo "[$(date '+%H:%M:%S')] 跑 p${lo}-${hi}（缺 ${missing} 页）"
  "$PY" -u 脚本/赵礼显讲义录题.py scan --only "$lo-$hi" --workers $SLOTS \
      2>&1 | tee -a "$LOG/scan.log"
  lo=$((hi + 1))
done
stop_server
echo "[$(date '+%H:%M:%S')] 全部跑完：$(ls 数据/录题/赵礼显/scan/ | wc -l | tr -d ' ') 页"
