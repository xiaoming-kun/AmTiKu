/** 题目列表：卡片 + 空态 + 分页。
 *
 *  从 App.tsx 抽出来的。它只认「这页有哪些题」，卷子、详情、导出都由
 *  上层通过回调传进来。
 *
 *  成熟做法（Linear / Gmail）里这一块通常是**虚拟滚动**；这里先不引入依赖，
 *  用 CSS `content-visibility`（见 index.css 的 `.q-card`）把屏外卡片跳过，
 *  100 道一页也不会一次把 KaTeX 全画出来。
 */
import { ChevronFirst, ChevronLast, SearchX } from 'lucide-react'
import type { Q } from '@/lib/types'
import type { useQuestionList } from '@/lib/useQuestionList'
import QuestionCard from '@/app/QuestionCard'
import CompactRow from '@/app/CompactRow'
import { Num } from '@/app/ui'

type L = ReturnType<typeof useQuestionList>

function PageBtn({ children, onClick, disabled }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="press h-[26px] rounded-md border border-border bg-surface px-2 text-[11.5px]
                 transition-colors hover:border-border-strong hover:text-ink disabled:opacity-35">
      {children}
    </button>
  )
}

function ListSkeleton() {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-[var(--radius-card)] border border-border bg-surface p-4">
          <div className="flex gap-2">
            <div className="skeleton h-3 w-20" />
            <div className="skeleton h-3 w-32" />
            <div className="skeleton ml-auto h-3 w-24" />
          </div>
          <div className="skeleton mt-3 h-4 w-[92%]" />
          <div className="skeleton mt-2 h-4 w-[70%]" />
        </div>
      ))}
    </div>
  )
}

export default function QuestionList({
  L, dense, compact, maskAns, paperMap, onOpen, onAdd, onClearFilters,
}: {
  L: L
  dense: boolean
  /** 密排：一行一道（扫题用），和卡片视图二选一 */
  compact: boolean
  /** 答案默认遮住（点「显示」或展开才给） */
  maskAns: boolean
  paperMap: Map<string, Q>
  onOpen: (q: Q) => void
  onAdd: (q: Q) => void
  onClearFilters: () => void
}) {
  const { items, total, loading, sel, listRef, page, setPage, pageSize,
          pageInput, setPageInput, jumpPage, selectMode, checked, toggleCheck } = L
  const maxPage = Math.max(1, Math.ceil(total / pageSize))
  // 搜索 0 结果时给两条**有依据**的出路：出处/考点里真有含这个词的值，
  // 一键改成「只看这个出处/考点」——比「换个关键词」有用得多。
  const kw = L.q.trim()
  const kwl = kw.toLowerCase()
  const srcHit = kw
    ? (L.facets?.sources || [])
        .filter((x) => x.value.toLowerCase().includes(kwl))
        .sort((a, b) => b.n - a.n)[0]
    : undefined
  const ptHit = kw
    ? (L.facets?.points || [])
        .filter((x) => x.title.includes(kw) || x.value === kw)
        .sort((a, b) => b.n - a.n)[0]
    : undefined

  return (
    <>
      <div
        key={`${page}|${L.q}|${L.points.join()}|${L.diffs.join()}|${L.years.join()}|${L.sort}|${L.missing.join()}|${L.has.join()}`}
        ref={(el) => { listRef.current = el }}
        aria-label="题目列表"
        className={`anim-stagger list-scroll min-h-0 flex-1 overflow-y-auto ${
          compact ? '' : 'space-y-2.5 p-4'}`}>
        {loading && !items.length && <ListSkeleton />}
        {compact && items.map((it, i) => (
          <CompactRow key={it.key} q={it} active={sel?.key === it.key}
            inPaper={paperMap.has(it.key)} selectMode={selectMode} checked={checked.has(it.key)}
            kw={kw}
            onOpen={() => onOpen(it)}
            onAdd={() => onAdd(it)}
            onToggle={(shift?: boolean) => toggleCheck(it, i, shift)} />
        ))}
        {!compact && items.map((it, i) => (
          <QuestionCard key={it.key} q={it} active={sel?.key === it.key}
            inPaper={paperMap.has(it.key)}
            selectMode={selectMode} checked={checked.has(it.key)} dense={dense}
            maskAns={maskAns} kw={kw}
            onOpen={() => onOpen(it)}
            onDetail={() => onOpen(it)}
            onAdd={() => onAdd(it)}
            onToggle={(shift?: boolean) => toggleCheck(it, i, shift)} />
        ))}
        {!loading && items.length === 0 && (
          <div className="anim-fade-in flex flex-col items-center gap-3 py-20 text-ink-faint">
            <SearchX size={30} strokeWidth={1.4} className="text-border-strong" />
            <div className="text-center">
              <div className="text-[13.5px] font-medium text-ink-soft">没有匹配的题</div>
              <div className="mt-0.5 text-[11.5px]">换个关键词，或去掉一两个筛选项</div>
            </div>
            {(srcHit || ptHit) && (
              <div className="flex max-w-[420px] flex-wrap items-center justify-center gap-1.5">
                <span className="text-[11px] text-ink-faint">换个方式：</span>
                {srcHit && (
                  <button onClick={() => {
                      // 当前组合已经 0 结果了，别把冲突的筛选（如 kind=高考）留着；
                      // 清掉其它条件，只保留这一个出处，才真能点得动。
                      onClearFilters(); L.setSources([srcHit.value]); L.setPage(1)
                    }}
                    title={`只看这个出处（${srcHit.n} 道）`}
                    className="press max-w-full truncate rounded-lg border border-brand-line
                               bg-brand-soft px-2.5 py-1 text-[11.5px] text-brand-ink
                               hover:bg-brand-soft/70">
                    只看出处「{srcHit.value}」（{srcHit.n}）
                  </button>
                )}
                {ptHit && (
                  <button onClick={() => {
                      onClearFilters(); L.setPoints([ptHit.value]); L.setPage(1)
                    }}
                    title={`只看这个考点（${ptHit.n} 道）`}
                    className="press max-w-full truncate rounded-lg border border-brand-line
                               bg-brand-soft px-2.5 py-1 text-[11.5px] text-brand-ink
                               hover:bg-brand-soft/70">
                    只看考点「{ptHit.title}」（{ptHit.n}）
                  </button>
                )}
              </div>
            )}
            <button onClick={onClearFilters}
              className="press rounded-lg border border-border bg-surface px-3 py-1.5
                         text-[12.5px] hover:border-brand-line hover:text-brand-ink">
              清除全部筛选
            </button>
          </div>
        )}
        {items.length > 0 && <div className="h-1" />}
      </div>

      {/* 总页数大于 1 才出现；`pr-20` 给右下角快捷键浮球让位 */}
      {total > pageSize && (
        // `flex-wrap` + `whitespace-nowrap`：栏太窄时**换行**，别被压成竖排字
        //（列表被挤到 270px 时，「第 1 / 123 页」会一个字一行）
        <div className="flex shrink-0 flex-wrap items-center gap-x-1.5 gap-y-1 whitespace-nowrap
                        border-t border-border bg-surface py-2 pl-4 pr-20 text-[12px] text-ink-faint">
          <PageBtn onClick={() => { setPage(1); listRef.current?.scrollTo(0, 0) }}
            disabled={page <= 1}><ChevronFirst size={13} /></PageBtn>
          <PageBtn onClick={() => { setPage((p) => Math.max(1, p - 1)); listRef.current?.scrollTo(0, 0) }}
            disabled={page <= 1}>‹ 上一页</PageBtn>
          <span className="flex items-center gap-1 px-1">
            第
            <input value={pageInput} onChange={(e) => setPageInput(e.target.value)}
              onBlur={jumpPage}
              onKeyDown={(e) => { if (e.key === 'Enter') jumpPage() }}
              aria-label="页码"
              className="tnum h-[26px] w-11 rounded-md border border-border bg-bg px-1
                         text-center text-[12px] outline-none focus:border-brand-line" />
            / <span className="tnum">{maxPage}</span> 页
          </span>
          <PageBtn onClick={() => { setPage((p) => p + 1); listRef.current?.scrollTo(0, 0) }}
            disabled={page >= maxPage}>下一页 ›</PageBtn>
          <PageBtn onClick={() => { setPage(maxPage); listRef.current?.scrollTo(0, 0) }}
            disabled={page >= maxPage}><ChevronLast size={13} /></PageBtn>
          <span className="tnum ml-auto">
            第 {pageSize * (page - 1) + 1}–{Math.min(total, page * pageSize)} 道，共 <Num value={total} /> 道
          </span>
        </div>
      )}
    </>
  )
}
