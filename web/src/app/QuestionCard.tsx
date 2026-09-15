/** 题目卡片（列表里的一张）。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1）。
 */
import type { Q } from '@/lib/types'
import { renderBlocks } from '@/lib/render'
import { Flags } from '@/app/ui'

/** 编译期间盖在预览区上的**进度遮罩**。
 *
 *  为什么值得单独做：一次导出要跑两遍 `xelatex`，几十秒很正常。
 *  原先只有按钮上四个字「编译中…」，人会以为卡死了，反复点。
 *
 *  三条设计取舍：
 *  ① **不假装知道百分比**。xelatex 的耗时取决于题量、图、宏包，
 *     估不准。所以走不定长进度条 + 秒表，如实说"还在动、动了多久"。
 *  ② **分阶段报**。按经验把等待切成几段报出来（排版 → 第 1 遍 → 第 2 遍），
 *     让人知道"现在到哪一步了"，而不是一个黑盒。
 *  ③ **秒表要动**。数字每 100ms 跳一次，这是"进程还活着"最直接的证据。 */
export default function Card({ q, active, inPaper, inHandout, selectMode, checked,
                onOpen, onAdd, onAddHandout, onToggle }: {
  q: Q; active: boolean; inPaper: boolean; inHandout: boolean
  selectMode: boolean; checked: boolean
  onOpen: () => void; onAdd: () => void; onAddHandout: () => void; onToggle: () => void
}) {
  /**
   * 点卡片：**详情永远跟着走**，选定模式下再顺带勾选。
   *
   * 早先是 `selectMode ? onToggle : onOpen` —— 选定模式一开（现在是默认），
   * 点卡片就只切勾选、右侧详情纹丝不动，看起来像"点了没反应"。
   * 勾选和看题是两件事，不该互斥。
   */
  const click = () => {
    onOpen()
    if (selectMode) onToggle()
  }
  return (
    <div onClick={click}
      className={`group flex cursor-pointer gap-2.5 rounded-[var(--radius-card)] border px-3 py-2
                  transition-all ${
        selectMode && checked ? 'border-brand bg-brand-soft/50 ring-1 ring-brand/30'
        : active ? 'border-brand/40 bg-brand-soft/40'
                 : 'border-border bg-surface hover:border-brand/25 hover:bg-muted/50'}`}>
      {selectMode && (
        <span className={`mt-[3px] flex h-[15px] w-[15px] shrink-0 items-center justify-center
                          rounded border text-[10px] leading-none transition-colors ${
          checked ? 'border-brand bg-brand text-white' : 'border-border bg-surface text-transparent'}`}>
          ✓
        </span>
      )}
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-1.5">
          <span className="rounded bg-muted px-1.5 py-[1px] text-[10.5px] text-ink-soft">{q.type_label}</span>
          <span className={`rounded px-1.5 py-[1px] text-[10.5px] ${
            q.kind === '高考' ? 'bg-brand text-white' : 'bg-muted text-ink-soft'}`}>{q.kind}</span>
          <Flags flags={q.flags} />
          {/* 使用频次：导出过（试卷/讲义）就标出来 —— 高频题=经典题 */}
          {!!q.used && (
            <span title={`已被导出 ${q.used} 次`}
              className="rounded bg-muted px-1.5 py-[1px] text-[10.5px] tabular-nums text-ink-soft">
              🔥{q.used}
            </span>
          )}
          {/* 单题按钮：**选定模式下也显示** ——
              选定模式是默认开启的，如果只在非选定模式显示，老师
              根本看不到这两个按钮（实测发现）。 */}
          {(
            <span className="ml-auto flex items-center gap-1">
              {/* 加入卷子 */}
              <button onClick={(e) => { e.stopPropagation(); onAdd() }}
                title={inPaper ? '已在卷子里' : '加入卷子'}
                className={`flex h-5 items-center justify-center rounded-md border px-1.5 text-[11px]
                            leading-none transition-colors ${
                  inPaper ? 'border-has/40 bg-has-soft text-has'
                          : 'border-border text-ink-faint opacity-0 group-hover:opacity-100 hover:border-brand/40 hover:text-brand-ink'}`}>
                {inPaper ? '✓卷' : '+卷'}
              </button>
              {/* 加入讲义 */}
              <button onClick={(e) => { e.stopPropagation(); onAddHandout() }}
                title={inHandout ? '已在讲义里' : '加入讲义'}
                className={`flex h-5 items-center justify-center rounded-md border px-1.5 text-[11px]
                            leading-none transition-colors ${
                  inHandout ? 'border-brand/40 bg-brand-soft text-brand-ink'
                            : 'border-border text-ink-faint opacity-0 group-hover:opacity-100 hover:border-brand/40 hover:text-brand-ink'}`}>
                {inHandout ? '✓讲' : '+讲'}
              </button>
            </span>
          )}
          {selectMode && inPaper && (
            <span className="ml-auto shrink-0 text-[10px] text-has">已在卷子</span>
          )}
        </div>
        {/* **两行**而不是三行。列表是用来"扫"的，扫的是题干开头和考点；
            想看全就点进去。三行一屏只放得下四五道，翻页太勤。 */}
        <div className="q-stem line-clamp-2 text-ink">{renderBlocks(q.blocks?.stem)}</div>
        <div className="mt-1 truncate text-[11px] text-ink-faint">
          {q.meta.source_label || q.meta.book}
          {q.point_titles.length > 0 && (
            <span className="ml-2 font-semibold text-ink-soft">· {q.point_titles[0]}{q.point_titles.length > 1 ? ` 等 ${q.point_titles.length} 个考点` : ''}</span>
          )}
        </div>
      </div>
    </div>
  )
}
