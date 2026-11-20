/** 卷子面板：挑好的题 + 「齐不齐」的体检 + 导出按钮。
 *
 *  从 App.tsx 抽出来的。体检必须在**导出前**就看得见——用户原话是
 *  「导出的才发现没解析」。
 */
import { useState } from 'react'
import { ChevronDown, ChevronUp, RefreshCw, SlidersHorizontal, X } from 'lucide-react'
import type { Q } from '@/lib/types'
import { SECTION_LABEL, scoreOf } from '@/lib/paper'
import { DIFF_STARS, dispPoint } from '@/lib/display'
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
        <div className="flex flex-1 items-center justify-center overflow-y-auto p-6">
          <div className="w-full max-w-[440px] rounded-[var(--radius-card)] border border-border
                          bg-surface p-6 text-center shadow-[var(--shadow-card)]">
            <span className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-muted text-ink-faint">
              <SlidersHorizontal size={19} />
            </span>
            <h3 className="mt-3 text-[16px] font-semibold tracking-tight">卷子还是空的</h3>
            <p className="mx-auto mt-1.5 max-w-[340px] text-[11.5px] leading-relaxed text-ink-faint">
              去题库挑题，点卡片上的「加入卷子」。也可以先在右侧打开智能组卷，
              系统按卷面结构挑一套，再逐题替换。
            </p>
            <button onClick={onBack}
              className="press b-btn b-btn-primary mx-auto mt-4 h-8">
              去题库挑题
              <ChevronDown size={13} className="-rotate-90" />
            </button>
            <div className="mt-5 space-y-2 border-t border-border pt-3 text-left">
              {[
                ['01', '挑题', '按考点、来源、难度筛出这次要用的题'],
                ['02', '检查', '每道题都要有答案与解析；缺口会标在这里'],
                ['03', '导出', 'PDF / Word / 分享包；出过的卷子自动存档'],
              ].map(([n, t, d]) => (
                <div key={n} className="flex items-baseline gap-2.5 text-[10.5px]">
                  <span className="tnum shrink-0 text-brand-ink">{n}</span>
                  <span className="w-8 shrink-0 font-medium text-ink-soft">{t}</span>
                  <span className="min-w-0 leading-relaxed text-ink-faint">{d}</span>
                </div>
              ))}
            </div>
          </div>
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
                        {dispPoint(it.point_titles?.[0] || '') || it.key}
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
