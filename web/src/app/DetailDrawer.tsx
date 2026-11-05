/** 右侧题目详情抽屉。
 *
 *  从 App.tsx 抽出来的。**宽屏占一栏**（列表自己缩窄，内容不被遮），
 *  窄屏才是盖上去的抽屉；宽度可拖、带记忆。
 */
import type { Q, Facets, SavedHandler } from '@/lib/types'
import { CloseBtn, Grip } from '@/app/ui'
import { Detail } from '@/app/Detail'

export default function DetailDrawer({
  open, closing, width, setWidth, maxWidth, loading, sel, full, facets, kw,
  onClose, onFindPoint, onDeleteAsk, onSaved,
}: {
  open: boolean
  closing: boolean
  width: number
  setWidth: (n: number) => void
  /** 宽度上限：由布局预算算出来，保证列表那一栏不被吃光。 */
  maxWidth?: number
  loading: boolean
  sel: Q | null
  full: Q | null
  facets: Facets | null
  kw?: string
  onClose: () => void
  onFindPoint: (pid: string, title: string) => void
  onDeleteAsk: () => void
  onSaved: SavedHandler
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
                 right-0 z-30 flex flex-col border-l border-border bg-surface
                 shadow-[var(--shadow-pop)] max-xl:max-w-[calc(100vw-64px)]
                 xl:relative xl:inset-auto xl:z-auto xl:h-full xl:max-w-[46vw]
                 xl:shadow-none`}>
      {/* 拖宽的手柄贴在**抽屉左边缘**：覆盖式和占栏式左边都在同一处 */}
      <div className="absolute inset-y-0 -left-[3px] z-40 flex">
        <Grip width={width} setWidth={setWidth} min={380} max={940} />
      </div>
        <div className="flex h-[52px] shrink-0 items-center gap-1 border-b border-border px-3">
          <span className="px-1 text-[12.5px] font-semibold text-ink-soft">题目详情</span>
          <span className="min-w-0 flex-1" />
          <CloseBtn onClick={onClose} title="关闭（Esc）" />
        </div>

        {!sel ? (
          <div className="flex flex-1 items-center justify-center text-[13px] text-ink-faint">
            {loading ? '正在读题…' : '先在列表里选一道题'}
          </div>
        ) : (
          <div key={sel.key} className="anim-fade-in min-h-0 flex-1">
            <Detail q={full && full.key === sel.key ? full : sel} facets={facets}
              kw={kw} refreshing={loading}
              onFindPoint={(pid, title) => { onFindPoint(pid, title); onClose() }}
              onDeleteAsk={onDeleteAsk}
              onSaved={onSaved} />
          </div>
        )}
      </aside>
  )
}
