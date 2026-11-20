/** 卷子条：一行计数 + 切到当前卷子 + 清空/导出。
 *
 *  从 App.tsx 抽出来的。它只认「卷子」这一件事，不该和筛选、列表、详情
 *  混在一个 1000 行的组件里。
 */
import { Check, ChevronRight, ClipboardList, TriangleAlert } from 'lucide-react'
import type { Q } from '@/lib/types'
import { Num } from '@/app/ui'

export default function PaperBar({
  paper, paperScore, answered, view, onToggleView, onClear, onExport,
}: {
  paper: Q[]
  paperScore: number
  answered: number
  view: 'list' | 'paper'
  onToggleView: () => void
  onClear: () => void
  onExport: () => void
}) {
  if (!paper.length) return null
  // 「能不能印」在这里就给结论——别让人排完、点导出、编译完才在报告里
  // 看到"3 道缺解析"。答案/解析两样都齐才算可印。
  const missingAns = paper.filter((q) => !q.flags?.['答案']).length
  const missingSol = paper.length - answered
  const ready = missingAns === 0 && missingSol === 0
  return (
    <div className={`anim-slide-d flex shrink-0 items-center gap-2.5 border-b px-4 py-2
                     text-[12.5px] ${view === 'paper'
                       ? 'border-brand-line bg-brand-soft/40'
                       : 'border-border bg-surface'}`}>
      <button onClick={onToggleView}
        className="press flex min-w-0 flex-1 items-center gap-2.5 text-left">
        <ClipboardList size={14}
          className={view === 'paper' ? 'shrink-0 text-brand' : 'shrink-0 text-ink-faint'} />
        <span className="inline-flex shrink-0 items-baseline gap-1">
          <span className={view === 'paper' ? 'font-semibold text-brand-ink' : 'font-semibold text-ink'}>
            {view === 'paper' ? '当前卷子' : '卷子'}
          </span>
          <Num value={paper.length} className="font-semibold text-brand-ink" />
          <span className={view === 'paper' ? 'text-brand-ink' : 'text-ink'}>题</span>
        </span>
        <span className="shrink-0 text-ink-soft">
          <Num value={paperScore} /> 分
        </span>
        {ready ? (
          <span className="flex shrink-0 items-center gap-1 rounded-full bg-has-soft px-1.5 py-[1px]
                           text-[11px] font-medium text-has"
            title="每一道都有答案和解析，可以直接导出印刷">
            <Check size={10} strokeWidth={3} />可以印
          </span>
        ) : (
          <span className="flex shrink-0 items-center gap-1 rounded-full bg-warn-soft px-1.5 py-[1px]
                           text-[11px] font-medium text-warn"
            title="导出仍会继续，但报告里会列出这些题——先补完再印更像一份正式卷">
            <TriangleAlert size={10} />
            {missingAns > 0 && <>缺答案 <Num value={missingAns} /></>}
            {missingAns > 0 && missingSol > 0 && <span className="opacity-60">·</span>}
            {missingSol > 0 && <>缺解析 <Num value={missingSol} /></>}
          </span>
        )}
        <span className="hidden min-w-0 flex-1 truncate text-[11.5px] text-ink-faint md:block">
          {view === 'paper'
            ? '每题右侧 ▲▼ 在题型内调顺序，✕ 移出，或直接导出'
            : '点这里查看卷子'}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-1 font-medium text-brand-ink">
          {view === 'paper' ? '返回题目' : '查看卷子'}
          <ChevronRight size={13} className={view === 'paper' ? 'rotate-180' : ''} />
        </span>
      </button>
      <button onClick={onClear} title="清空卷子（可以撤销）"
        className="press shrink-0 rounded-md border border-border bg-surface px-2
                   py-[3px] text-[11.5px] text-ink-faint transition-colors
                   hover:border-warn-line hover:text-warn">
        清空
      </button>
      {/* ⚠️ 不要在这里写「⌘↵」：全局 ⌘↵ 是**把当前这道题加进卷子**
          （见 App.tsx 的快捷键），不是导出。按钮上标错会让人按了以后
          卷子多一道、导出弹层却没出现。 */}
      <button onClick={onExport} title="导出这份卷子"
        className="press grad-primary shrink-0 rounded-full px-3 py-[5px] text-[11.5px]
                   font-medium text-white hover:brightness-105">
        导出
      </button>
    </div>
  )
}
