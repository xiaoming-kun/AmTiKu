/** 卷子面板：挑好的题 + 「齐不齐」的体检 + 导出按钮。
 *
 *  从 App.tsx 抽出来的。体检必须在**导出前**就看得见——用户原话是
 *  「导出的才发现没解析」。
 */
import { useState } from 'react'
import { ChevronDown, ChevronUp, RefreshCw, SlidersHorizontal, X } from 'lucide-react'
import type { Q } from '@/lib/types'
import { SECTION_LABEL, scoreOf } from '@/lib/paper'
import { DIFF_STARS } from '@/lib/display'
import { Flags } from '@/app/ui'
import SwapDialog from '@/app/SwapDialog'

export default function PaperPanel({ paper, onOpen, onRemove, onMove, onSwap, onBack }: {
  paper: Q[]; onOpen: (q: Q) => void; onRemove: (k: string) => void
  onMove: (k: string, d: -1 | 1) => void
  onSwap: (oldKey: string, q: Q) => void
  onBack: () => void
}) {
  const [swapFor, setSwapFor] = useState<Q | null>(null)
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {paper.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center text-ink-faint">
          <SlidersHorizontal size={22} className="text-border-strong" />
          <span className="text-[13px]">卷子还是空的</span>
          <span className="text-[11.5px] leading-relaxed">
            在题目列表的卡片上点 <b className="text-brand-ink">加入组卷</b>，
            或按住 <kbd className="rounded border border-border bg-muted px-1">↑</kbd>
            <kbd className="ml-0.5 rounded border border-border bg-muted px-1">↓</kbd> 选好再按
            <kbd className="mx-0.5 rounded border border-border bg-muted px-1">Enter</kbd>
          </span>
          {/* 正常走不到这儿（空卷子会被 gotoPaper / 那个 effect 拦在列表上），
              留个出口以防万一 */}
          <button onClick={onBack}
            className="press mt-1 rounded-lg bg-brand px-3.5 py-2 text-[12.5px] font-medium
                       text-white shadow-[var(--shadow-brand)] hover:brightness-105">
            返回题目列表
          </button>
        </div>
      ) : (<>
        {/* 题量/分数/有解析那一行**搬到卷子条上了**（题目栏顶部那条）——
            两处都写一遍是重复，而且两处数字还可能不一致。 */}
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {/* 限宽：题目栏可能很宽，行拉满时标题和右侧的难度星会离成两截。
              840px 是「一眼能扫完一行」的宽度。 */}
          <div className="mx-auto w-full max-w-[840px] space-y-3">
          {SECTION_LABEL.map(([t, label]) => {
            const group = paper.filter((x) => x.type === t)
            if (!group.length) return null
            return (
              <div key={t}>
                <div className="mb-1.5 flex items-baseline gap-2 text-[11.5px] text-ink-faint">
                  <span className="font-semibold text-ink-soft">{label}</span>
                  <span className="tnum">{group.length} 题 · {scoreOf(t, group.length)} 分</span>
                </div>
                <ol className="space-y-1.5">
                  {group.map((it, i) => (
                    <li key={it.key} onClick={() => onOpen(it)} title="点击看详情"
                      className="press group flex cursor-pointer items-center gap-2 rounded-lg border
                                 border-border bg-surface px-2.5 py-1.5 transition-colors
                                 hover:border-brand-line hover:bg-brand-soft/30">
                      <span className="tnum w-4 shrink-0 text-right text-[11.5px] text-ink-faint">{i + 1}</span>
                      <span className="min-w-0 flex-1 truncate text-[12.5px]">
                        {it.point_titles?.[0] || it.key}
                      </span>
                      {it.difficulty && (
                        <span title={it.difficulty}
                          className="shrink-0 text-[10.5px] tracking-tight text-warn">
                          {'★'.repeat(DIFF_STARS[it.difficulty] || 0)}
                        </span>
                      )}
                      <Flags flags={it.flags} type={it.type} />
                      {/* 单题换题：整卷重抽会丢掉已经调好的顺序，这里只换这一道。 */}
                      <button onClick={(e) => { e.stopPropagation(); setSwapFor(it) }}
                        title="换一道同类型/同难度的题"
                        className="icon-btn h-5 w-5 shrink-0 opacity-60 group-hover:opacity-100">
                        <RefreshCw size={12} />
                      </button>
                      {/* 顺序：卷子是按题型分节的，所以只能**在节内**上下挪。
                          到顶/到底时按钮置灰，不做无声无息的无操作。 */}
                      <span className="flex shrink-0 items-center gap-0.5">
                        <button onClick={(e) => { e.stopPropagation(); onMove(it.key, -1) }}
                          disabled={i === 0} title="在这一节里上移"
                          className="icon-btn h-5 w-5 disabled:opacity-25 disabled:hover:bg-transparent">
                          <ChevronUp size={13} />
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); onMove(it.key, 1) }}
                          disabled={i === group.length - 1} title="在这一节里下移"
                          className="icon-btn h-5 w-5 disabled:opacity-25 disabled:hover:bg-transparent">
                          <ChevronDown size={13} />
                        </button>
                      </span>
                      <button onClick={(e) => { e.stopPropagation(); onRemove(it.key) }}
                        className="icon-btn h-5 w-5 shrink-0 opacity-0 group-hover:opacity-100"
                        title="从卷子移除">
                        <X size={13} />
                      </button>
                    </li>
                  ))}
                </ol>
              </div>
            )
          })}
          </div>
        </div>
      </>)}

      {swapFor && (
        <SwapDialog current={swapFor} exclude={paper.map((x) => x.key)}
          onClose={() => setSwapFor(null)}
          onPick={(q) => { onSwap(swapFor.key, q); setSwapFor(null) }} />
      )}
    </div>
  )
}
