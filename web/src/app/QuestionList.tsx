/** 题目列表：卡片 + 空态 + 分页。
 *
 *  从 App.tsx 抽出来的。它只认「这页有哪些题」，卷子、详情、导出都由
 *  上层通过回调传进来。
 *
 *  成熟做法（Linear / Gmail）里这一块通常是**虚拟滚动**；这里先不引入依赖，
 *  用 CSS `content-visibility`（见 index.css 的 `.q-card`）把屏外卡片跳过，
 *  100 道一页也不会一次把 KaTeX 全画出来。
 */
import { useEffect, useRef, useState } from 'react'
import { ChevronFirst, ChevronLast, SearchX } from 'lucide-react'
import type { Q } from '@/lib/types'
import type { useQuestionList } from '@/lib/useQuestionList'
import QuestionCard from '@/app/QuestionCard'
import CompactRow from '@/app/CompactRow'
import { Num } from '@/app/ui'

type L = ReturnType<typeof useQuestionList>

function PageBtn({ children, onClick, disabled, className = '' }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean; className?: string
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`press inline-flex h-9 min-w-9 items-center justify-center rounded-md border
                 border-border bg-surface px-2 text-[11.5px] transition-colors
                 hover:border-border-strong hover:text-ink disabled:opacity-35
                 sm:h-[26px] sm:min-w-0 ${className}`}>
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
  L, dense, compact, maskAns, paperMap, scrollSignal, onSelect, onOpen, onAdd,
  onClearFilters, onPrefetch, onOpenPaper, leading,
}: {
  L: L
  dense: boolean
  /** 密排：一行一道（扫题用），和卡片视图二选一 */
  compact: boolean
  /** 答案默认遮住（点「显示」或展开才给） */
  maskAns: boolean
  paperMap: Map<string, Q>
  /** 方向键移动时自增；鼠标点卡片不自增，所以只有键盘才触发滚动。 */
  scrollSignal: number
  /** 卡片点一下只移光标（详情抽屉若已开着会跟着换）。 */
  onSelect: (q: Q) => void
  /** 明确打开详情：卡片右上角 ✎、密排点行。 */
  onOpen: (q: Q) => void
  onAdd: (q: Q) => void
  onClearFilters: () => void
  /** 点卡片上的「组过 N 卷」：跳到试卷库那份存档。 */
  onOpenPaper?: (name: string) => void
  /** 列表**滚动区顶部**的内容（筛选条）。放进来是为了让它跟着列表一起滚走，
   *  不长期占着一行高度；表头的「筛选」按钮仍是它收起后的入口。 */
  leading?: React.ReactNode
  /** 悬停/按下就预取完整题目，点开详情时直接命中缓存。 */
  onPrefetch?: (key: string) => void
}) {
  const { items, total, loading, sel, listRef, page, setPage, pageSize,
          pageInput, setPageInput, jumpPage, selectMode, checked, toggleCheck } = L
  const maxPage = Math.max(1, Math.ceil(total / pageSize))
  // 搜索 0 结果时给两条**有依据**的出路：出处/考点里真有含这个词的值，
  // 一键改成「只看这个出处/考点」——比「换个关键词」有用得多。
  const kw = L.q.trim()
  const kwl = kw.toLowerCase()
  // 一页可能 100 道，但一次只挂 20 张卡；滚到底再续。
  // 卡片正文的 KaTeX 是列表最贵的一块，10 万道时也必须保持首屏常数。
  const [visible, setVisible] = useState(compact ? 40 : 10)
  useEffect(() => {
    // 列表刷新时不要缩回“首屏 10 张”：键盘可能已经移到第 50 张，
    // 缩回去会让选中项突然从 DOM 里消失。按当前选中项的下标兜底。
    const base = compact ? 40 : 10
    const idx = sel ? items.findIndex((x) => x.key === sel.key) : -1
    setVisible(Math.max(base, Math.min(items.length, idx + 1)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, compact])
  const shown = items.slice(0, visible)
  const loadMore = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    if (el.scrollTop + el.clientHeight > el.scrollHeight - 320) {
      setVisible((v) => (v >= items.length ? v : Math.min(items.length, v + 20)))
    }
  }

  /** 把选中项滚进视口。
   *
   *  方向键由 App 改 `L.sel`，但列表只渲染前 `visible` 张；选到第 11 张时
   *  DOM 里根本没有它。以前 App 用 `querySelectorAll('article')` 自己找，
   *  密排视图的根是 `div`，一张都找不到；卡片视图超过 10 张也找不到。
   *  所以交给列表自己：先按需扩容，再滚到元素。
   *
   *  `pendingScroll` 只用于“扩容后补滚”这一种情况 —— 不能把 `visible`
   *  直接放进滚动 effect 的依赖：用户向下滚动触发 `loadMore` 时，
   *  那会把选中项又拽回屏幕中间。 */
  const pendingScroll = useRef<string | null>(null)
  const scrollTimer = useRef<number | null>(null)
  const scrollToKey = (key: string) => {
    const box = listRef.current
    if (!box) return
    const paint = (smooth: boolean) => {
      const hit = [...box.querySelectorAll('[data-qkey]')]
        .find((el) => el.getAttribute('data-qkey') === key)
      if (!hit) return
      const boxRect = box.getBoundingClientRect()
      const tooTall = hit.getBoundingClientRect().height > boxRect.height - 8
      hit.scrollIntoView({
        // 普通卡片用 nearest：已经看得见就别动，键盘往下不会每按一次就把
        // 整张卡顶到最上面。卡片本身比列表还高时（宽屏 + 筛选栏 + 详情抽屉）
        // nearest 会把题首裁掉，这时用 start 保证从题干开头读。
        block: compact || !tooTall ? 'nearest' : 'start',
        behavior: smooth ? 'smooth' : 'auto',
      })
    }
    paint(true)
    // 卡片里的 KaTeX 是进入视口后才排版的，高度会在滚动开始后再变一次；
    // 平滑滚动按旧高度算，到位后可能又“沉”下去。等一拍再校正一次，
    // 且只在它仍是当前选中项时——用户已经往下翻就别拽回来。
    if (scrollTimer.current) window.clearTimeout(scrollTimer.current)
    if (!compact) {
      scrollTimer.current = window.setTimeout(() => {
        scrollTimer.current = null
        const still = [...box.querySelectorAll('[data-qkey][aria-current="true"]')]
          .some((el) => el.getAttribute('data-qkey') === key)
        if (still) paint(false)
      }, 500)
    }
  }
  useEffect(() => {
    if (!scrollSignal) return
    const key = L.sel?.key
    if (!key) {
      pendingScroll.current = null
      if (scrollTimer.current) { window.clearTimeout(scrollTimer.current); scrollTimer.current = null }
      return
    }
    const idx = items.findIndex((x) => x.key === key)
    if (idx < 0) return
    if (idx >= visible) {
      pendingScroll.current = key
      setVisible(Math.min(items.length, idx + 1))
      return
    }
    scrollToKey(key)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollSignal])
  useEffect(() => {
    const key = pendingScroll.current
    if (!key) return
    pendingScroll.current = null
    if (L.sel?.key !== key) return
    scrollToKey(key)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible])
  useEffect(() => () => {
    if (scrollTimer.current) window.clearTimeout(scrollTimer.current)
  }, [])
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

  const hoverTimer = useRef<number | null>(null)
  const hoverKey = useRef('')
  const prefetchFrom = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = (e.target as HTMLElement).closest('[data-qkey]')
    const k = el?.getAttribute('data-qkey')
    if (!k || k === hoverKey.current) return
    hoverKey.current = k
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current)
    // hover 意图：停在同一张卡上 120ms 才预取。鼠标扫过一页不会打 100 个全量请求。
    hoverTimer.current = window.setTimeout(() => {
      hoverTimer.current = null
      onPrefetch?.(k)
    }, 120)
  }
  const cancelPrefetch = () => {
    if (hoverTimer.current) {
      window.clearTimeout(hoverTimer.current)
      hoverTimer.current = null
    }
    hoverKey.current = ''
  }
  useEffect(() => () => {
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current)
  }, [])

  return (
    <>
      <div
        key={`${page}|${L.q}|${L.points.join()}|${L.diffs.join()}|${L.years.join()}|${L.sort}|${L.missing.join()}|${L.has.join()}`}
        ref={(el) => { listRef.current = el }}
        aria-label="题目列表"
        onScroll={loadMore}
        onPointerOver={prefetchFrom}
        onPointerDown={prefetchFrom}
        onPointerLeave={cancelPrefetch}
        className="anim-stagger list-scroll min-h-0 flex-1 overflow-y-auto">
        {leading}
        <div className={compact ? '' : 'space-y-2.5 p-4'}>
        {loading && !items.length && <ListSkeleton />}
        {compact && shown.map((it, i) => (
          <CompactRow key={it.key} q={it} active={sel?.key === it.key}
            inPaper={paperMap.has(it.key)} selectMode={selectMode} checked={checked.has(it.key)}
            kw={kw}
            onOpen={() => onOpen(it)}
            onAdd={() => onAdd(it)}
            onToggle={(shift?: boolean) => toggleCheck(it, i, shift)} />
        ))}
        {!compact && shown.map((it, i) => (
          <QuestionCard key={it.key} q={it} active={sel?.key === it.key}
            inPaper={paperMap.has(it.key)}
            selectMode={selectMode} checked={checked.has(it.key)} dense={dense}
            maskAns={maskAns} kw={kw}
            onSelect={() => onSelect(it)}
            onDetail={() => onOpen(it)}
            onAdd={() => onAdd(it)}
            onOpenPaper={onOpenPaper}
            onToggle={(shift?: boolean) => toggleCheck(it, i, shift)} />
        ))}
        {!loading && visible < items.length && (
          <div className="py-4 text-center text-[11px] text-ink-faint">
            继续向下滚动，加载更多
          </div>
        )}
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
      </div>

      {/* 总页数大于 1 才出现；`pr-20` 给右下角快捷键浮球让位 */}
      {total > pageSize && (
        // `flex-wrap` + `whitespace-nowrap`：栏太窄时**换行**，别被压成竖排字
        //（列表被挤到 270px 时，「第 1 / 123 页」会一个字一行）
        <div className="flex shrink-0 flex-wrap items-center gap-x-1.5 gap-y-1 whitespace-nowrap
                        border-t border-border bg-surface py-2 pl-3 pr-14 text-[12px] text-ink-faint
                        sm:pl-4 sm:pr-20">
          <PageBtn onClick={() => { setPage(1); listRef.current?.scrollTo(0, 0) }}
            disabled={page <= 1} className="hidden sm:inline-flex"><ChevronFirst size={13} /></PageBtn>
          <PageBtn onClick={() => { setPage((p) => Math.max(1, p - 1)); listRef.current?.scrollTo(0, 0) }}
            disabled={page <= 1}>
            <span className="hidden sm:inline">‹ 上一页</span><span className="sm:hidden">‹</span>
          </PageBtn>
          <span className="flex items-center gap-1 px-0.5 sm:px-1">
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
            disabled={page >= maxPage}>
            <span className="hidden sm:inline">下一页 ›</span><span className="sm:hidden">›</span>
          </PageBtn>
          <PageBtn onClick={() => { setPage(maxPage); listRef.current?.scrollTo(0, 0) }}
            disabled={page >= maxPage} className="hidden sm:inline-flex"><ChevronLast size={13} /></PageBtn>
          <span className="tnum ml-auto hidden sm:inline">
            第 {pageSize * (page - 1) + 1}–{Math.min(total, page * pageSize)} 道，共 <Num value={total} /> 道
          </span>
        </div>
      )}
    </>
  )
}
