/** 题目列表的工具栏（列表头）。
 *
 *  从 App.tsx 抽出来的：这一块只管「现在看什么、怎么显示、选中了怎么批量做」，
 *  不碰卷子、弹层、导出。App 里那 1000 行再往下拆，先拆这块最独立的。
 *
 *  视觉上借了 Linear / GitHub Issues 的「视图选项」：
 *  密度和每页条数不常改，收进一个「显示」弹层；
 *  常驻的只留筛选、多选、命令面板三个入口，表头不再排一长串控件。
 */
import { useEffect, useRef, useState } from 'react'
import {
  Check, ChevronDown, Command as CommandIcon, LayoutGrid, ListFilter, Rows2, Rows3,
  SlidersHorizontal, Tags, X,
} from 'lucide-react'
import type { useQuestionList } from '@/lib/useQuestionList'
import { Num } from '@/app/ui'

type L = ReturnType<typeof useQuestionList>
export type ScopeChip = { key: string; label: string; clear: () => void }

const PAGE_SIZES = [10, 20, 50, 100, 200]

export default function ListHeader({
  L, total, loading, scopeChips, showFilter, onShowFilter, clearAllFilters,
  dense, onDense, compact, onCompact, maskAns, onMaskAns, onPalette, onDeleteChecked, onAddChecked, onBatchEdit, view,
}: {
  L: L
  total: number
  loading: boolean
  scopeChips: ScopeChip[]
  showFilter: boolean
  onShowFilter: () => void
  clearAllFilters: () => void
  dense: boolean
  onDense: () => void
  compact: boolean
  onCompact: () => void
  maskAns: boolean
  onMaskAns: () => void
  onPalette: () => void
  onDeleteChecked: () => void
  onAddChecked: () => void
  onBatchEdit: () => void
  view: 'list' | 'paper'
}) {
  const [viewOpen, setViewOpen] = useState(false)
  const viewRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!viewOpen) return
    const h = (e: MouseEvent) => {
      if (viewRef.current && !viewRef.current.contains(e.target as Node)) setViewOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [viewOpen])

  /* ── 批量操作条：**占同一行**，勾选时整条换掉，列表不跳位（Gmail 做法） ── */
  if (view === 'list' && L.selectMode && L.checked.size > 0) {
    return (
      <div className="anim-fade-in flex h-[52px] shrink-0 items-center gap-2.5
                      border-b border-brand-line bg-brand-soft px-4">
        <span className="shrink-0 text-[14px] font-semibold text-brand-ink">
          已选 <span className="tnum">{L.checked.size}</span> 道
        </span>
        <button onClick={() => L.checkAll(L.items)} title="全选本页"
          className="press shrink-0 whitespace-nowrap rounded-lg border border-brand-line
                     bg-surface px-2.5 py-[4px] text-[12px] text-brand-ink hover:bg-surface-2">
          全选</button>
        <button onClick={L.clearChecked}
          className="press shrink-0 whitespace-nowrap rounded-lg border border-brand-line
                     bg-surface px-2.5 py-[4px] text-[12px] text-brand-ink hover:bg-surface-2">
          清空</button>
        <span className="min-w-0 flex-1" />
        <button onClick={onBatchEdit} title="批量改标签"
          className="press flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg
                     border border-brand-line bg-surface px-2.5 py-[4px] text-[12px]
                     font-medium text-brand-ink hover:bg-surface-2">
          <Tags size={12} />改标签
        </button>
        <button onClick={onDeleteChecked} title="删除选中"
          className="press shrink-0 whitespace-nowrap rounded-lg border border-warn-line
                     bg-surface px-2.5 py-[4px] text-[12px] font-medium text-warn
                     hover:bg-warn-soft">
          删除
        </button>
        <button onClick={onAddChecked}
          className="press shrink-0 rounded-lg bg-brand px-3 py-[4px] text-[12px]
                     font-medium text-white shadow-[var(--shadow-brand)] hover:brightness-105">
          加入卷子
        </button>
        <button onClick={L.exitSelect} title="退出多选（Esc）"
          className="icon-btn h-7 w-7 shrink-0">
          <X size={15} />
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border
                    bg-surface px-4">
      <h1 className="shrink-0 text-[19px] font-semibold tracking-tight">题库</h1>
      <span className="tnum shrink-0 rounded-full bg-muted px-2 py-[2px] text-[11.5px]
                       font-medium text-ink-soft">
        {loading ? '加载中…' : <><Num value={total} /> 道</>}
      </span>

      {/* 生效条件做成可删胶囊：一条一个 ×，点掉哪条撤哪条 */}
      <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 overflow-hidden">
        {scopeChips.length === 0 ? (
          <span className="truncate text-[12px] text-ink-faint">全部题目</span>
        ) : (<>
          {scopeChips.slice(0, 4).map((c) => (
            <button key={c.key} onClick={c.clear} title={`去掉「${c.label}」`}
              className="press group flex shrink-0 items-center gap-1 rounded-full
                         bg-brand-soft px-2 py-[2px] text-[11.5px] font-medium
                         text-brand-ink hover:bg-brand hover:text-white">
              <span className="max-w-[16ch] truncate">{c.label}</span>
              <X size={11} className="opacity-55 group-hover:opacity-100" />
            </button>
          ))}
          {scopeChips.length > 4 && (
            <span className="tnum shrink-0 text-[11.5px] text-ink-faint">
              +{scopeChips.length - 4}
            </span>
          )}
          <button onClick={clearAllFilters}
            className="press shrink-0 rounded-full px-1.5 py-[2px] text-[11.5px]
                       text-ink-faint hover:text-warn">清除</button>
        </>)}
      </span>

      {!showFilter && (
        <button onClick={onShowFilter} title="展开筛选面板（K）"
          className="press flex h-[30px] shrink-0 items-center gap-1.5 rounded-lg border
                     border-border bg-surface px-2.5 text-[12.5px] text-ink-soft
                     hover:border-brand-line hover:text-brand-ink">
          <ListFilter size={14} />筛选
          {L.activeFilters > 0 && (
            <span className="tnum rounded-full bg-brand px-1.5 text-[10px] font-medium
                             leading-[16px] text-white">
              {L.activeFilters}
            </span>
          )}
        </button>
      )}

      {/* 视图选项：密度 / 每页条数。不常改，收进弹层，表头立刻轻一截 */}
      {view === 'list' && (
        <div ref={viewRef} className="relative shrink-0">
          <button onClick={() => setViewOpen((v) => !v)} title="视图选项"
            aria-expanded={viewOpen}
            className={`press flex h-[30px] items-center gap-1.5 rounded-lg border px-2.5
                        text-[12.5px] transition-colors ${viewOpen
                          ? 'border-brand-line bg-brand-soft text-brand-ink'
                          : 'border-border bg-surface text-ink-soft hover:border-border-strong hover:text-ink'}`}>
            <SlidersHorizontal size={13} />
            <span className="hidden lg:inline">显示</span>
            <ChevronDown size={11} className={`transition-transform duration-200 ${viewOpen ? 'rotate-180' : ''}`} />
          </button>
          {viewOpen && (
            <div className="pop absolute right-0 top-[calc(100%+7px)] z-40 w-[224px]
                            rounded-[var(--radius-pop)] border border-border bg-surface p-3
                            shadow-[var(--shadow-pop)]">
              {/* 布局：卡片是"读"的密度，密排是"扫"的密度 */}
              <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-faint">布局</div>
              <div className="mb-3 flex gap-1 rounded-lg bg-muted p-1">
                {([['卡片', false, <LayoutGrid key="card" size={13} />],
                   ['密排', true, <Rows3 key="line" size={13} />]] as const).map(([label, v, icon]) => (
                  <button key={label} onClick={() => { if (compact !== v) onCompact() }}
                    className={`press flex flex-1 items-center justify-center gap-1 rounded-md py-1
                                text-[12px] transition-colors ${compact === v
                                  ? 'bg-surface font-medium text-brand-ink shadow-[var(--shadow-card)]'
                                  : 'text-ink-faint hover:text-ink'}`}>
                    {icon}{label}
                  </button>
                ))}
              </div>
              {!compact && (<>
                <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-faint">密度</div>
                <div className="mb-3 flex gap-1 rounded-lg bg-muted p-1">
                  {([['宽松', false, <Rows2 key="l" size={13} />],
                     ['紧凑', true, <Rows3 key="c" size={13} />]] as const).map(([label, v, icon]) => (
                    <button key={label} onClick={() => { if (dense !== v) onDense() }}
                      className={`press flex flex-1 items-center justify-center gap-1 rounded-md py-1
                                  text-[12px] transition-colors ${dense === v
                                    ? 'bg-surface font-medium text-brand-ink shadow-[var(--shadow-card)]'
                                    : 'text-ink-faint hover:text-ink'}`}>
                      {icon}{label}
                    </button>
                  ))}
                </div>
              </>)}
              <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-faint">答案</div>
              <div className="mb-3 flex gap-1 rounded-lg bg-muted p-1">
                {([['遮住', true], ['显示', false]] as const).map(([label, v]) => (
                  <button key={label} onClick={() => { if (maskAns !== v) onMaskAns() }}
                    className={`press flex-1 rounded-md py-1 text-[12px] transition-colors ${maskAns === v
                      ? 'bg-surface font-medium text-brand-ink shadow-[var(--shadow-card)]'
                      : 'text-ink-faint hover:text-ink'}`}>
                    {label}
                  </button>
                ))}
              </div>
              <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-faint">每页</div>
              <div className="flex flex-wrap gap-1">
                {PAGE_SIZES.map((n) => (
                  <button key={n} onClick={() => { L.setPageSize(n); setViewOpen(false) }}
                    className={`tnum press min-w-[38px] rounded-md border px-2 py-1 text-[11.5px]
                                transition-colors ${L.pageSize === n
                                  ? 'border-brand bg-brand font-medium text-white'
                                  : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:text-brand-ink'}`}>
                    {n}
                  </button>
                ))}
              </div>
              <div className="mt-2 border-t border-border pt-2 text-[10.5px] leading-relaxed text-ink-faint">
                {compact
                  ? '密排一行一道，一屏约 25 道：看点/难点/首行，点一行看详情。'
                  : '一屏 100 道时，紧凑模式更适合扫题；读长题干再切回宽松。'}
              </div>
            </div>
          )}
        </div>
      )}

      <button onClick={onPalette} title="命令面板（⌘K）"
        className="press flex h-[30px] shrink-0 items-center gap-1.5 rounded-lg border
                   border-border bg-surface px-2 text-[12.5px] text-ink-faint
                   hover:border-border-strong hover:text-ink">
        <CommandIcon size={13} />
        <kbd className="hidden text-[10.5px] xl:inline">⌘K</kbd>
      </button>

      {view === 'list' && (
        L.selectMode ? (
          <button onClick={L.exitSelect} title="关掉多选（卡片不再跟着勾选）"
            className="press flex h-[30px] shrink-0 items-center gap-1 rounded-lg border
                       border-brand-line bg-brand-soft px-2.5 text-[12.5px] font-medium
                       text-brand-ink">
            <Check size={13} strokeWidth={2.6} />多选
          </button>
        ) : (
          <button onClick={() => L.setSelectMode(true)} disabled={!L.items.length}
            className="press h-[30px] shrink-0 rounded-lg border border-border bg-surface px-2.5
                       text-[12.5px] text-ink-soft hover:border-border-strong hover:text-ink
                       disabled:opacity-40">
            多选
          </button>
        )
      )}
    </div>
  )
}
