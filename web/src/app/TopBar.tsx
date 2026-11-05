/** 顶栏：全局搜索 + 全库状态 + 三个动作。
 *
 *  旧顶栏是「AmTiKu 高中数学题库 …… 存量未改动 录入题目 导出」，
 *  而**真正高频的搜索却挤在左栏顶上**（还是个 12.5px 的小框）。
 *  这里把两件事对调：搜索升到顶栏正中、占最宽的一格；
 *  状态和动作收到右侧一排。
 *
 *  「存量对账」的明细弹层也搬进来了 —— 它本来就是顶栏那个状态点的一部分，
 *  留在 App.tsx 里会让 App 多背四个 state。
 */
import { useEffect, useRef, useState } from 'react'
import { Search, Plus, X, ChevronDown, ShieldCheck, ShieldAlert, ClipboardList, History } from 'lucide-react'
import type { Base } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import { BaseRow } from '@/app/ui'

export default function TopBar({
  q, onQ, inputRef, base, paperCount, recent, onClearRecent, onPaper, onExport, onReload,
}: {
  q: string
  onQ: (v: string) => void
  inputRef: React.RefObject<HTMLInputElement | null>
  base: Base | null
  paperCount: number
  /** 最近搜过（localStorage，最多 8 条） */
  recent?: string[]
  onClearRecent?: () => void
  onPaper: () => void
  onExport: () => void
  onReload: () => void
}) {
  const [openBase, setOpenBase] = useState(false)
  const [sure, setSure] = useState(false)
  const [msg, setMsg] = useState('')
  const box = useRef<HTMLDivElement>(null)
  const searchBox = useRef<HTMLDivElement>(null)
  const [showRecent, setShowRecent] = useState(false)
  const recents = recent || []

  // 点搜索框外面收起「最近搜索」；和存量对账那个弹层同一套做法
  useEffect(() => {
    if (!showRecent) return
    const h = (e: MouseEvent) => {
      if (searchBox.current && !searchBox.current.contains(e.target as Node)) setShowRecent(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [showRecent])

  // 点外面收起。不做成模态——对账时经常要一边点一边看列表
  useEffect(() => {
    if (!openBase) return
    const h = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) { setOpenBase(false); setSure(false) }
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [openBase])

  const dirty = (base?.内容变化 ?? 0) > 0

  return (
    <header className="relative z-30 flex h-[56px] shrink-0 items-center gap-3 border-b border-border
                       bg-surface px-4">
      {/* ── 搜索：顶栏最宽的一格 ── */}
      <div ref={searchBox} className="relative min-w-0 flex-1 max-w-[620px]">
        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => {
            const v = e.target.value
            onQ(v)
            setShowRecent(!v && recents.length > 0)
          }}
          onFocus={() => { if (!q && recents.length) setShowRecent(true) }}
          onClick={() => { if (!q && recents.length) setShowRecent(true) }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') { onQ(''); setShowRecent(false); (e.target as HTMLInputElement).blur() }
          }}
          placeholder="搜索题目、答案、考点、出处…"
          className="h-[36px] w-full rounded-[10px] border border-border bg-bg pl-9 pr-16
                     text-[13px] outline-none transition-[border-color,background-color,box-shadow]
                     duration-150 placeholder:text-ink-faint
                     focus:border-brand-line focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]"
        />
        {/* 最近搜索：输入框空着、聚焦时才出现；点一条直接回填 */}
        {showRecent && !q && recents.length > 0 && (
          <div className="absolute left-0 right-0 top-[40px] z-40 overflow-hidden rounded-xl
                          border border-border bg-surface shadow-[var(--shadow-pop)]">
            <div className="flex items-center gap-1.5 border-b border-border px-2.5 py-1.5
                            text-[10.5px] text-ink-faint">
              <History size={11} />最近搜索
              <button onClick={() => { onClearRecent?.(); setShowRecent(false) }}
                className="ml-auto text-[10.5px] text-brand-ink hover:underline">清空</button>
            </div>
            <div className="max-h-[260px] overflow-y-auto p-1">
              {recents.map((s) => (
                <button key={s} onMouseDown={(e) => e.preventDefault()}
                  onClick={() => { onQ(s); setShowRecent(false) }}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-[5px] text-left
                             text-[12px] text-ink-soft hover:bg-muted hover:text-ink">
                  <Search size={11} className="shrink-0 text-ink-faint" />
                  <span className="min-w-0 flex-1 truncate">{s}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {q ? (
          <button onClick={() => { onQ(''); if (recents.length) setShowRecent(true) }}
            title="清空"
            className="icon-btn absolute right-2 top-1/2 h-6 w-6 -translate-y-1/2">
            <X size={14} />
          </button>
        ) : (
          <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded
                          border border-border bg-surface-2 px-1.5 text-[10.5px] leading-[17px]
                          text-ink-faint sm:block">
            /
          </kbd>
        )}
      </div>

      {/* ── 右侧动作 ── */}
      <div className="ml-auto flex shrink-0 items-center gap-1.5">
        {/* 存量对账：平时只有一个状态点，点开才看明细。
            早先是六段文字并排，把标题都挤没了，而这六段里平时
            只有第一段（有没有异常）需要一眼看到。 */}
        {base && (
          <div ref={box} className="relative">
            <button onClick={() => setOpenBase((v) => !v)}
              title="点开看存量对账明细"
              className={`press flex h-[30px] items-center gap-1.5 rounded-full border px-2.5
                          text-[12px] transition-colors ${dirty
                            ? 'border-warn-line bg-warn-soft text-warn hover:brightness-[.98]'
                            : 'border-has-line bg-has-soft text-has hover:brightness-[.98]'}`}>
              {dirty ? <ShieldAlert size={13} /> : <ShieldCheck size={13} />}
              <span className="hidden font-medium sm:inline">
                {dirty ? `存量有 ${base.内容变化} 处异常` : '存量未改动'}
              </span>
              <ChevronDown size={12} className={`transition-transform duration-200 ${openBase ? 'rotate-180' : ''}`} />
            </button>

            {openBase && (
              <div className="pop absolute right-0 top-[calc(100%+8px)] w-[286px] rounded-[var(--radius-pop)]
                              border border-border bg-surface p-3 shadow-[var(--shadow-pop)]">
                <div className="mb-2 flex items-baseline justify-between">
                  <span className="text-[12.5px] font-semibold">存量对账</span>
                  <span className="tnum text-[10.5px] text-ink-faint">
                    基线 {base.基线} · 当前 {base.当前}
                  </span>
                </div>
                <div className="space-y-1 text-[12px]">
                  <BaseRow label="内容变化" n={base.内容变化} tone="warn" hint="没登记过的改动，这才要看" />
                  <BaseRow label="界面补录" n={base.界面补录 ?? 0} hint="你在界面上改了答案/解析/题型" />
                  <BaseRow label="规则迁移" n={base.规则迁移 ?? 0} hint="批量规范化改的（有变更记录为证）" />
                  <BaseRow label="求解写入" n={base.求解写入 ?? 0} hint="求解器一道一道做的" />
                  <BaseRow label="录入升级" n={base.录入升级 ?? 0} hint="点「用这份更新」升级的" />
                </div>
                <div className="mt-2.5 border-t border-border pt-2 text-[10.5px] leading-relaxed text-ink-faint">
                  后四项都是有意的，只作记录。有意改完数据后把当前状态存成新基线，下次报警才是真有事。
                </div>
                {!sure ? (
                  <button onClick={() => { setSure(true); setMsg('') }}
                    className="press mt-2 w-full rounded-lg border border-border bg-bg px-2 py-1.5
                               text-[12px] text-ink-soft hover:border-brand-line hover:text-brand-ink">
                    把当前 {base.当前} 道存成新基线
                  </button>
                ) : (
                  <div className="anim-fade-up mt-2 flex items-center gap-1.5 rounded-lg border
                                  border-brand-line bg-brand-soft p-1.5">
                    <span className="min-w-0 flex-1 text-[11.5px] text-brand-ink">
                      把当前 {base.当前} 道存成基线？
                    </span>
                    <button
                      onClick={() => {
                        api.snapshot()
                          .then((d: any) => {
                            setSure(false)
                            setMsg(`✓ 基线已更新（${d.questions} 道）`)
                            onReload()
                            setTimeout(() => setMsg(''), 4000)
                          })
                          .catch((e) => { setSure(false); reportErr(e) })
                      }}
                      className="press rounded-md bg-brand px-2 py-[3px] text-[11.5px] font-medium text-white">
                      确定
                    </button>
                    <button onClick={() => setSure(false)}
                      className="press rounded-md border border-border bg-surface px-2 py-[3px] text-[11.5px] text-ink-soft">
                      取消
                    </button>
                  </div>
                )}
                {msg && <div className="mt-1.5 text-center text-[11.5px] text-has">{msg}</div>}
              </div>
            )}
          </div>
        )}

        {/* 当前卷子：随手一点就能看卷子，不用先切标签页 */}
        <button onClick={onPaper} title="当前卷子（P）"
          className={`press flex h-[30px] items-center gap-1.5 rounded-lg border px-2.5 text-[12.5px]
                      transition-colors ${paperCount
                        ? 'border-brand-line bg-brand-soft font-medium text-brand-ink'
                        : 'border-border bg-surface text-ink-soft hover:border-border-strong hover:text-ink'}`}>
          <ClipboardList size={14} />
          <span className="tnum">{paperCount}</span>
          <span className="hidden lg:inline">题</span>
        </button>


        {/* 主按钮：全屏只有一个，就是它 */}
        <button onClick={onExport} title="组卷并导出（B）"
          className="press flex h-[30px] items-center gap-1.5 rounded-lg bg-brand px-3 text-[12.5px]
                     font-medium text-white shadow-[var(--shadow-brand)]
                     transition-[filter] hover:brightness-105">
          <Plus size={15} strokeWidth={2.4} />
          <span className="hidden sm:inline">新建试卷</span>
        </button>
      </div>
    </header>
  )
}
