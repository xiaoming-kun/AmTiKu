/** 生成中的进度浮层：转圈 + 进度条 + 阶段清单 + 已用时间。
 *
 *  原来只有「组卷」（ExportPage）里有这个浮层，讲义编辑器的「生成 PDF」
 *  只有按钮变成「生成中…」，等 30~60 秒完全不知道卡在哪一步
 *  （用户要求：生成的时候加个动画）。
 *
 *  为什么按**时间**推断阶段：后端导出是一次阻塞请求（`POST /api/export/slidev-canvas`），
 *  没有进度上报。要做真进度得改成「任务 id + 轮询」，那是另一个量级的改动；
 *  这里的阶段时间是用实测耗时定的，够用且零风险。
 */

import { useEffect, useState } from 'react'

type Stage = [number, string]

/** 组卷（两遍 xelatex）。实测耗时定档。 */
export const LATEX_STAGES: Stage[] = [
  [0, '排版：把题目拼成 LaTeX 源文件'],
  [3, '第一遍编译：写辅助文件'],
  [12, '第二遍编译：交叉引用与目录'],
  [28, '收尾：生成 PDF'],
]

/** 讲义（Slidev：起 Chromium → 渲染 → 打印 PDF）。
 *
 *  第一次导出要冷启动浏览器内核，明显更慢；页数越多也越慢。 */
export const SLIDEV_STAGES: Stage[] = [
  [0, '整理画布内容：题目 / 公式 / 配图'],
  [2, '生成 Slidev 页面'],
  [5, '启动渲染器（Chromium）'],
  [12, '渲染公式与图片'],
  [30, '编译 PDF'],
  [55, '收尾：保存到 试卷/'],
]

export default function CompileOverlay({ since, label, stages = LATEX_STAGES, hint }:
  { since: number; label: string; stages?: Stage[]; hint?: string }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(t)
  }, [])
  const sec = Math.max(0, (now - since) / 1000)

  // 当前处在第几个阶段（取最后一个已达到的）
  let cur = 0
  for (let i = 0; i < stages.length; i++) if (sec >= stages[i][0]) cur = i

  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center
                    bg-surface/85 backdrop-blur-[2px] anim-fade-in">
      <div className="w-[400px] max-w-[88%] rounded-2xl border border-border bg-surface
                      px-6 py-5 shadow-xl anim-pop">
        <div className="mb-3 flex items-center gap-2.5">
          {/* 转圈：表示"在动"；下面的进度条表示"到哪了" */}
          <span className="inline-block h-4 w-4 shrink-0 rounded-full border-2
                           border-brand-soft border-t-brand"
            style={{ animation: 'spin .8s linear infinite' }} />
          <span className="text-[13px] font-medium text-ink">{label}</span>
          <span className="ml-auto font-mono text-[12px] tabular-nums text-ink-faint">
            {sec.toFixed(1)}s
          </span>
        </div>

        <div className="progress-track mb-3" />

        {/* 阶段清单：走过的打勾，当前的高亮 —— 长等待里这是最有用的信息 */}
        <ol className="space-y-1">
          {stages.map(([, text], i) => (
            <li key={text}
              className={`flex items-center gap-2 text-[11.5px] ${
                i < cur ? 'text-ink-faint'
                  : i === cur ? 'font-medium text-ink'
                    : 'text-ink-faint/60'}`}>
              <span className="w-3 shrink-0 text-center">
                {i < cur ? '✓' : i === cur ? '●' : '○'}
              </span>
              <span>{text}</span>
            </li>
          ))}
        </ol>

        <div className="mt-3 text-[10.5px] leading-relaxed text-ink-faint">
          {hint || '中途不用重复点，生成完会自动出结果'}
        </div>
      </div>
    </div>
  )
}
