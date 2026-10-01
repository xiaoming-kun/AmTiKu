/** 生成中的进度浮层：转圈 + 进度条 + 阶段清单 + 已用时间。
 *
 *  导出是一次阻塞请求，等 30~60 秒完全不知道卡在哪一步，
 *  所以要在等待期间给个交代（用户要求：生成的时候加个动画）。
 *
 *  为什么按**时间**推断阶段：后端导出是一次阻塞请求（`POST /api/export`），
 *  没有进度上报。要做真进度得改成「任务 id + 轮询」，那是另一个量级的改动；
 *  这里的阶段时间是用实测耗时定的，够用且零风险。
 */

import { useEffect, useState } from 'react'
import { Check, Circle, CircleDot, Loader2 } from 'lucide-react'

type Stage = [number, string]

/** 组卷（两遍 xelatex）。实测耗时定档。 */
export const LATEX_STAGES: Stage[] = [
  [0, '排版：把题目拼成 LaTeX 源文件'],
  [3, '第一遍编译：写辅助文件'],
  [12, '第二遍编译：交叉引用与目录'],
  [28, '收尾：生成 PDF'],
]

/** 组卷（按考点覆盖率挑题）。挑题是纯 CPU 的贪心，
 *  46 道题要在两万道的池子里滚 46 轮，实测 4~5 秒——够慢到需要给个交代。 */
export const COVER_STAGES: Stage[] = [
  [0, '统计这批题能覆盖到的考点'],
  [1, '贪心挑题：每轮取"带来新考点最多"的那道'],
  [3, '按易 → 难排好'],
  [6, '收尾：算出卷面总分'],
]

export default function CompileOverlay({ since, label, stages = LATEX_STAGES, hint }:
  { since: number; label: string; stages?: Stage[]; hint?: string }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(t)
  }, [])
  // `since` 没给对（0 或负数）时**兜一下底**：直接减会算出"已用 57 年"
  // 这种荒唐数字（`Date.now()` 是 1970 年起的毫秒数，1.79e9 秒）。
  // 调用方忘了传 `since` 是它的错，但浮层不该把荒唐数字甩给用户看。
  const sec = since > 0 && since <= now ? (now - since) / 1000 : 0

  // 当前处在第几个阶段（取最后一个已达到的）
  let cur = 0
  for (let i = 0; i < stages.length; i++) if (sec >= stages[i][0]) cur = i

  return (
    <div className="anim-fade-in absolute inset-0 z-30 flex items-center justify-center
                    bg-surface/80 backdrop-blur-[2px]">
      <div className="pop-c w-[400px] max-w-[90%] rounded-[var(--radius-pop)] border border-border
                      bg-surface px-5 py-4 shadow-[var(--shadow-pop)]">
        <div className="flex items-center gap-2.5">
          {/* 转圈：表示"在动"；下面的进度条表示"到哪了" */}
          <Loader2 size={15} className="shrink-0 animate-spin text-brand" />
          <span className="text-[13px] font-semibold tracking-tight text-ink">{label}</span>
          {/* 秒表在跳，就说明进程还活着 */}
          <span className="tnum ml-auto font-mono text-[11.5px] text-ink-faint">
            {sec.toFixed(1)}s
          </span>
        </div>

        {/* 不定长进度条：不假装知道百分比 */}
        <div className="progress-track my-3.5" />

        {/* 阶段清单：走过的打勾，当前的高亮 —— 长等待里这是最有用的信息 */}
        <ol className="space-y-1.5">
          {stages.map(([, text], i) => (
            <li key={text}
              className={`flex items-center gap-2 text-[12px] ${
                i < cur ? 'text-ink-faint'
                  : i === cur ? 'font-medium text-ink'
                    : 'text-ink-faint/60'}`}>
              <span className="grid w-3.5 shrink-0 place-items-center">
                {i < cur ? <Check size={12} strokeWidth={3} className="text-has" />
                  : i === cur ? <CircleDot size={11} className="text-brand" />
                    : <Circle size={8} className="text-border-strong" />}
              </span>
              <span className="min-w-0 flex-1 truncate">{text}</span>
            </li>
          ))}
        </ol>

        <div className="mt-3.5 border-t border-border pt-2.5 text-[11px] leading-relaxed text-ink-faint">
          {hint || '中途不用重复点，生成完会自动出结果'}
        </div>
      </div>
    </div>
  )
}
