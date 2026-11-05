/** 密排视图的一行：一道题压成 34px 高的一行。
 *
 *  为什么要有它：卡片视图一屏只放得下 4 道——那是"读"的密度。挑题时更多是"扫"：
 *  看考点、难度、题干第一眼、🔥 用过几次，扫完一屏 25 道再决定点谁。
 *  两套密度不是二选一，是**两个动线**：扫用密排，读用卡片。
 *
 *  交互与卡片严格一致：点行 = 看详情（不勾选），方框 = 勾选（Shift 连选），
 *  hover 出现「加入卷子」。不在这里发明第三套手势。
 */
import { Check, Plus } from 'lucide-react'
import type { Q } from '@/lib/types'
import { Highlight, renderBlocks } from '@/lib/render'
import { DIFF_STARS, starsLabel } from '@/lib/display'
import { SHORT_NAME } from '@/lib/paper'

export default function CompactRow({
  q, active, checked, selectMode, inPaper, kw, onOpen, onToggle, onAdd,
}: {
  q: Q
  active: boolean
  checked: boolean
  selectMode: boolean
  inPaper: boolean
  onOpen: () => void
  onToggle: (shift?: boolean) => void
  onAdd: () => void
  kw?: string
}) {
  const stars = DIFF_STARS[q.difficulty] || q.stars || 0
  const point = q.point_titles?.[0] || ''
  const type = SHORT_NAME[q.type] || q.type_label || ''
  const missing = [!q.flags['答案'] && '答案', !q.flags['解析'] && '解析'].filter(Boolean)

  return (
    <div
      onClick={onOpen}
      aria-current={active ? 'true' : undefined}
      className={`group flex h-[34px] cursor-pointer items-center gap-2.5 border-b border-border/60
                  px-3 text-[12.5px] transition-colors ${
        checked ? 'bg-brand-soft/50' : active ? 'bg-brand-soft/30' : 'hover:bg-muted/50'}`}>

      {selectMode && (
        <button type="button" role="checkbox" aria-checked={checked}
          aria-label="勾选（Shift 连选）" title="勾选（Shift 连选）"
          onClick={(e) => { e.stopPropagation(); onToggle(e.shiftKey) }}
          className="-ml-1 grid h-[22px] w-[22px] shrink-0 place-items-center rounded-md hover:bg-muted">
          <span className={`grid h-[15px] w-[15px] place-items-center rounded-[4px] border
                            transition-all duration-150 ${
            checked ? 'border-brand bg-brand text-white'
                    : 'border-border-strong bg-surface text-transparent'}`}>
            <Check size={10} strokeWidth={3} className={checked ? 'anim-check' : ''} />
          </span>
        </button>
      )}

      {/* 主考点：固定宽度、超出截断——扫的时候这一列是"对齐"的，眼睛能竖着读 */}
      <span title={q.point_titles?.join('、') || '无考点'}
        className={`w-[8.5em] shrink-0 truncate text-[11.5px] ${
          point ? 'font-medium text-brand-ink' : 'text-warn'}`}>
        <Highlight text={point || '无考点'} kw={kw} />
      </span>

      <span title={q.difficulty || '未评级'}
        className={`w-[2.6em] shrink-0 tracking-tight ${stars > 0 ? 'text-warn' : 'text-ink-faint'}`}>
        {stars > 0 ? starsLabel(stars) : '—'}
      </span>

      {/* 题干：块级内容压成一行（见 index.css 的 .q-line） */}
      <span className="q-line min-w-0 flex-1 text-ink">
        {renderBlocks(q.blocks?.stem, kw)}
      </span>

      {missing.length > 0 && (
        <span title={`缺${missing.join('、')}`}
          className="shrink-0 rounded bg-warn-soft px-1 text-[10px] font-medium text-warn">
          缺{missing.join('')}
        </span>
      )}

      <span className="w-[2.6em] shrink-0 text-[11px] text-ink-faint">{type}</span>

      <span className="w-[3.2em] shrink-0 text-right text-[11px] text-warn" title={q.used ? `已导出 ${q.used} 次` : ''}>
        {q.used ? `🔥${q.used}` : ''}
      </span>

      <button type="button" disabled={inPaper}
        onClick={(e) => { e.stopPropagation(); onAdd() }}
        title={inPaper ? '已在卷子里' : '加入卷子（⌘↵）'}
        className={`press grid h-[24px] w-[24px] shrink-0 place-items-center rounded-md border
                    transition-all duration-150 ${inPaper
                      ? 'border-has-line bg-has-soft text-has'
                      : 'border-border bg-surface text-ink-faint opacity-0 group-hover:opacity-100 hover:border-brand-line hover:text-brand-ink'}`}>
        {inPaper ? <Check size={12} strokeWidth={2.8} /> : <Plus size={13} strokeWidth={2.6} />}
      </button>
    </div>
  )
}
