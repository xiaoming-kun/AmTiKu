/** 右侧题目详情抽屉。
 *
 *  从 App.tsx 抽出来的。**宽屏占一栏**（列表自己缩窄，内容不被遮），
 *  窄屏才是盖上去的抽屉；宽度可拖、带记忆。
 */
import type { Q, Facets, SavedHandler, SourceBatchDone } from '@/lib/types'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { CloseBtn, Grip } from '@/app/ui'
import { Detail } from '@/app/Detail'

export default function DetailDrawer({
  open, closing, width, setWidth, maxWidth, loading, loadingFull, sel, full, facets, kw,
  autoSourceKey, autoSourceN,
  onPrev, onNext, canPrev, canNext, position,
  onClose, onFindPoint, onDeleteAsk, onPick, onSaved, onBatchSource,
}: {
  open: boolean
  closing: boolean
  width: number
  setWidth: (n: number) => void
  /** 宽度上限：由布局预算算出来，保证列表那一栏不被吃光。 */
  maxWidth?: number
  loading: boolean
  /** 完整题目（答案/解析块）还在路上。 */
  loadingFull?: boolean
  sel: Q | null
  full: Q | null
  facets: Facets | null
  kw?: string
  onClose: () => void
  /** 审阅页跳过来：key + 自增序号，匹配且序号变过就自动打开改源码。 */
  autoSourceKey?: string
  autoSourceN?: number
  onPrev?: () => void
  onNext?: () => void
  canPrev?: boolean
  canNext?: boolean
  position?: { i: number; n: number } | null
  onFindPoint: (pid: string, title: string) => void
  onDeleteAsk: () => void
  /** 相似题：点一条就切到那道题。 */
  onPick?: (q: Q) => void
  onSaved: SavedHandler
  /** 详情页「批量改出处」完成：App 负责迁移卷子/列表里的旧 key。 */
  onBatchSource?: (res: SourceBatchDone) => void
}) {
  if (!open) return null

  return (
    /* **占一栏，不覆盖**。
       以前是 `absolute right-0` 浮在列表上：抽屉一开，右边那条题目就被压在
       底下——双曲线那道题只能读到「0<k<」，题干后半截全看不见，而用户正想
       对着看。现在（xl 及以上）它是 flex 的兄弟节点，列表自己缩窄，
       一分内容都不被遮。窄屏还是盖上去——手机/iPad 竖屏没那么多宽度可分。 */
    <aside
      style={{ width, maxWidth }}
      role="complementary"
      aria-label="题目详情"
      className={`${closing ? 'anim-slide-r-out' : 'anim-slide-r'} absolute inset-y-0
                 right-0 z-50 flex flex-col border-l border-border/70
                 bg-surface
                 shadow-[var(--shadow-pop)] max-[1399px]:max-w-[calc(100vw-64px)] max-md:max-w-[100vw]
                 min-[1400px]:relative min-[1400px]:inset-auto min-[1400px]:z-auto min-[1400px]:h-full min-[1400px]:max-w-[46vw]
                 min-[1400px]:shadow-none`}>
      {/* 拖宽的手柄贴在**抽屉左边缘**：覆盖式和占栏式左边都在同一处 */}
      <div className="absolute inset-y-0 -left-[3px] z-40 flex">
        <Grip width={width} setWidth={setWidth} min={380} max={900} />
      </div>
        <span className="pointer-events-none absolute inset-x-0 top-0 h-px
                         bg-gradient-to-r from-transparent via-brand/70 to-transparent" />
        <div className="flex h-12 shrink-0 items-center gap-1 border-b border-border px-3">
          <span className="live-dot ml-1" />
          <span className="px-1 text-[12px] font-semibold text-ink">题目</span>
          <span className="min-w-0 flex-1" />
          {position && (
            <span className="tnum mr-1 hidden text-[10.5px] text-ink-faint sm:inline">
              {position.i} / {position.n}
            </span>
          )}
          <button onClick={onPrev} disabled={!canPrev} title="上一题（↑）"
            aria-label="上一题"
            className="icon-btn h-7 w-7 disabled:opacity-25">
            <ChevronLeft size={16} />
          </button>
          <button onClick={onNext} disabled={!canNext} title="下一题（↓）"
            aria-label="下一题"
            className="icon-btn h-7 w-7 disabled:opacity-25">
            <ChevronRight size={16} />
          </button>
          <CloseBtn onClick={onClose} title="关闭（Esc）" />
        </div>

        {!sel ? (
          <div className="flex flex-1 items-center justify-center text-[13px] text-ink-faint">
            {loading ? '正在读题…' : '先在列表里选一道题'}
          </div>
        ) : (
          <div key={sel.key} className="min-h-0 flex-1">
            <Detail q={full && full.key === sel.key ? full : sel} facets={facets}
              kw={kw} refreshing={loading} loadingFull={loadingFull}
              autoSourceKey={autoSourceKey} autoSourceN={autoSourceN}
              onFindPoint={(pid, title) => { onFindPoint(pid, title); onClose() }}
              onDeleteAsk={onDeleteAsk}
              onPick={onPick}
              onSaved={onSaved}
              onBatchSource={onBatchSource} />
          </div>
        )}
      </aside>
  )
}
