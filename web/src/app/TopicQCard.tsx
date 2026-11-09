/** 专题里的一张题目卡（纸面样式，和工作台共用同一套块渲染）。 */
import { renderBlocks } from '@/lib/render'

export type TQ = {
  key: string; type_label: string; difficulty: string
  options: { label: string; text: string }[]
  blocks?: { stem?: unknown[]; options?: unknown[][]; answer?: unknown[]; solution?: unknown[] }
}

export default function TopicQCard({ q, index, onOpen, onRemove, showAnswer = true }: {
  q: TQ; index?: number
  onOpen: (key: string) => void
  onRemove?: (key: string) => void
  /** 学生版：答案与解析不展开，也不发请求 */
  showAnswer?: boolean
}) {
  return (
    <article className="rounded-lg border border-[#e3ebf3] bg-[#fbfdff] p-3">
      <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] text-[#6b7686]">
        {index != null && <span className="tnum font-semibold text-[#3b4757]">{index}</span>}
        <span className="rounded border border-[#dbe4ee] px-1">{q.type_label}</span>
        <span className="rounded bg-[#eef2f7] px-1">{q.difficulty}</span>
        {onRemove && (
          <button onClick={() => onRemove(q.key)}
            className="ml-auto shrink-0 rounded border border-[#dbe4ee] px-1.5 py-[1px]
                       text-[9.5px] text-[#6b7686] hover:border-[#d9534f] hover:text-[#d9534f]">
            移出
          </button>
        )}
        <button onClick={() => onOpen(q.key)}
          className={`${onRemove ? '' : 'ml-auto '}shrink-0 rounded border border-[#dbe4ee] px-1.5 py-[1px]
                     text-[9.5px] text-[#6b7686] hover:border-[#c2185b] hover:text-[#c2185b]`}>
          工作台打开 ↗
        </button>
      </div>
      <div className="q-stem text-[12.5px] text-[#1f2430]">{renderBlocks(q.blocks?.stem as never)}</div>
      {!!q.blocks?.options?.length && (
        <div className="mt-1.5 grid gap-1 sm:grid-cols-2">
          {(q.blocks.options as never[][]).map((opt, j) => (
            <div key={j} className="flex items-baseline gap-1 text-[12px] text-[#33404f]">
              <span className="font-medium text-[#6b7686]">{q.options?.[j]?.label || j + 1}.</span>
              <span className="min-w-0">{renderBlocks(opt)}</span>
            </div>
          ))}
        </div>
      )}
      {showAnswer ? <details className="mt-1.5 border-t border-[#e3ebf3] pt-1.5">
        <summary className="cursor-pointer text-[10.5px] text-[#6b7686]">答案与解析</summary>
        <div className="mt-1 space-y-1 text-[12px]">
          <div className="flex gap-1.5">
            <span className="shrink-0 text-[10.5px] font-semibold text-[#c2185b]">答案</span>
            <div className="min-w-0 flex-1 text-[#1f2430]">{renderBlocks(q.blocks?.answer as never)}</div>
          </div>
          {q.blocks?.solution?.length ? (
            <div className="flex gap-1.5">
              <span className="shrink-0 text-[10.5px] font-semibold text-[#6b7686]">解析</span>
              <div className="min-w-0 flex-1 text-[#33404f]">{renderBlocks(q.blocks.solution as never)}</div>
            </div>
          ) : null}
        </div>
      </details> : (
        <div className="mt-1.5 border-t border-[#e3ebf3] pt-1.5 text-[10.5px] text-[#6b7686]">
          答案与解析已隐藏 · 学生版
        </div>
      )}
    </article>
  )
}
