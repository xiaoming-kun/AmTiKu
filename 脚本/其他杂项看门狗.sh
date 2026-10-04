#!/bin/bash
# 其他杂项转录 · **看门狗**：跑批挂了就把它拉起来，直到 1723 页全部扫完。
#
# 为什么需要：这一批要连跑 **13 小时以上、无人值守**。跑批脚本自己
# 已经能扛住"服务崩/单块失败"（每块重启服务、跳过已缓存的块），
# 但**它自己被杀掉就没人管了** —— 实测踩过一次：手滑 `pkill` 之后
# 整夜没跑，第二天才发现少了 10 小时。
#
# ⚠️ **不要改正在运行的跑批脚本。** bash 是**边读边执行**脚本文件的，
# 改一个运行中的 .sh 会让它从错误的偏移继续读、行为错乱。
# 所以监督逻辑单独放这里，跑批脚本一个字都不动。
#
# 用法：
#   nohup bash 脚本/其他杂项看门狗.sh > /tmp/zlx/logs/watchdog.log 2>&1 &
#   bash 脚本/其他杂项看门狗.sh --状态
set -u
cd "$(dirname "$0")/.."

SCAN=数据/录题/其他杂项/scan
LOG=/tmp/zlx/logs
PLAN="$LOG/plan.txt"
PY=.venv/bin/python
MAX_RESTART="${MAX_RESTART:-40}"      # 最多拉几次，防死循环

# 总页数：从跑批脚本生成的计划表算（没有就用 PDF 现算一遍）
total_pages() {
  if [ -f "$PLAN" ]; then
    awk -F'\t' '{s+=$2} END{print s+0}' "$PLAN"
  else
    "$PY" - <<'EOF'
import sys, importlib.util, fitz
sys.path.insert(0, '.'); sys.path.insert(0, '脚本')
spec = importlib.util.spec_from_file_location("m", "脚本/其他杂项录题.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(sum(fitz.open(m.pdf_of(f)).page_count for f in m.list_files() if m.pdf_of(f).exists()))
EOF
  fi
}

scanned_pages() { find "$SCAN" -name 'p*.txt' 2>/dev/null | wc -l | tr -d ' '; }

# 最新一页转录距今多少**秒**（一页都没有就返回一个很大的数）
newest_age_sec() {
  local f
  f=$(find "$SCAN" -name 'p*.txt' -type f -exec stat -f '%m' {} + 2>/dev/null \
      | sort -rn | head -1)
  [ -z "$f" ] && { echo 999999; return; }
  echo $(( $(date +%s) - f ))
}

TOTAL=$(total_pages)
if [ "${1:-}" = "--状态" ]; then
  echo "已扫 $(scanned_pages) / ${TOTAL} 页"
  pgrep -f "^bash 脚本/其他杂项跑批.sh$" >/dev/null \
    && echo "跑批：在跑" || echo "跑批：不在跑"
  pgrep -f "^bash 脚本/其他杂项看门狗.sh" >/dev/null \
    && echo "看门狗：在跑" || echo "看门狗：不在跑"
  exit 0
fi

mkdir -p "$LOG"
# **停滞判据**：多少分钟不出新页就判为卡住。
# 单页最坏实测约 300 秒（4 并发下），所以 15 分钟不出页一定是卡了，不是慢。
STALL_MIN="${STALL_MIN:-15}"
restarts=0
while true; do
  # ── 停滞检测：**进程活着但不出页** ────────────────────────────────
  # 这是本项目的头号坑（见 赵礼显 README 坑 1）：`UserIsActive=0` 时 macOS
  # 上后台 QoS，llama-server 会在生成中途**整段冻住**（tg_3s 从 12 t/s
  # 掉到 0.01 t/s，冻 11–17 分钟又自己活过来）。`caffeinate -dimsu` 是主防线，
  # 这里做第二道 —— 因为**"进程还在"和"还在干活"是两件事**，
  # 光看存活的看门狗对冻住的进程完全无感，能白等一整夜。
  if pgrep -f "^bash 脚本/其他杂项跑批.sh$" >/dev/null; then
    _age=$(newest_age_sec)
    if [ "$_age" -gt $(( STALL_MIN * 60 )) ]; then
      echo "[$(date '+%m-%d %H:%M:%S')] ⚠ 已 $((_age/60)) 分钟没出新页（>${STALL_MIN} 分），判为卡住 → 杀掉重来"
      pkill -f "^bash 脚本/其他杂项跑批.sh$" 2>/dev/null
      sleep 3
      pkill -9 -f "[Pp]ython.*其他杂项录题\.py scan" 2>/dev/null
      sleep 3
      # 下一轮循环发现"跑批不在了"，会把它拉起来
    fi
  fi
  if ! pgrep -f "^bash 脚本/其他杂项跑批.sh$" >/dev/null; then
    done_n=$(scanned_pages)
    if [ "$done_n" -ge "$TOTAL" ]; then
      # **扫完就自动收尾**：boxes → figs → build → verify → audit → KaTeX → PDF。
      # 为什么要自动：这一整套要跑 13 小时以上，人不可能守着；
      # 轮次/注意力都会先耗尽，而收尾漏一步（比如 figs 在 boxes 之前跑）
      # 就是白做一场、还看不出来。
      echo "[$(date '+%m-%d %H:%M:%S')] 全部扫完（${done_n}/${TOTAL}），开始收尾"
      bash 脚本/其他杂项收尾.sh 2>&1 | tee -a "$LOG/watchdog.log"
      echo "[$(date '+%m-%d %H:%M:%S')] 收尾结束，看门狗退出"
      break
    fi
    restarts=$((restarts + 1))
    if [ "$restarts" -gt "$MAX_RESTART" ]; then
      # ⚠️ **到上限也要收尾，不能直接退出。**
      # 第一版这里是"停手等人看"然后 break —— 后果很严重：只要有**一页**
      # 反复失败（某页模型 3 次都转不出来），计数就永远到不了 TOTAL，
      # 重启 40 次后放弃，**收尾永不触发** —— 明明扫了 1722/1723 页，
      # 却一个 .tex 都拿不到。宁可出"带缺口的产物 + 一张缺口清单"，
      # 也不要什么都没有。
      echo "[$(date '+%m-%d %H:%M:%S')] ⚠ 已重启 ${MAX_RESTART} 次仍未扫满（${done_n}/${TOTAL}）"
      echo "  缺的页（这批大概率是模型反复转不出来的，值得回原文件看）："
      while IFS=$'\t' read -r slug pages; do
        [ -z "$slug" ] && continue
        i=1
        while [ "$i" -le "$pages" ]; do
          f=$(printf "数据/录题/其他杂项/scan/%s/p%03d.txt" "$slug" "$i")
          [ -s "$f" ] || echo "    ${slug} p${i}"
          i=$((i + 1))
        done
      done < "$LOG/plan.txt" | head -40
      echo "[$(date '+%m-%d %H:%M:%S')] 带着缺口开始收尾（产物照出，缺口已在上面列出）"
      bash 脚本/其他杂项收尾.sh 2>&1 | tee -a "$LOG/watchdog.log"
      echo "[$(date '+%m-%d %H:%M:%S')] 收尾结束，看门狗退出"
      break
    fi
    echo "[$(date '+%m-%d %H:%M:%S')] 跑批不在了（已扫 ${done_n}/${TOTAL}），第 ${restarts} 次拉起"
    nohup bash 脚本/其他杂项跑批.sh >> "$LOG/batch.log" 2>&1 &
    sleep 20
  fi
  sleep 60
done
