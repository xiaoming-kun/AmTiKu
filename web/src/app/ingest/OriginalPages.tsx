/** DeepSeek 录题的「原文」列：把 PDF 页图固定放在题卡旁边，逐页对照。
 *
 *  只读；不写库。页面来自 AI 任务的临时缓存（q-*.png / a-*.png），
 *  大图仍走现有的 preview-image 接口和 pageView 弹层。
 */
import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Maximize2, ScanLine } from 'lucide-react'

export default function OriginalPages({ dir, pages, answerPages, onOpen }: {
  dir: string
  pages: number
  answerPages: number
  onOpen: (kind: 'q' | 'a', page: number) => void
}) {
  const [kind, setKind] = useState<'q' | 'a'>('q')
  const [page, setPage] = useState(1)
  const total = kind === 'q' ? pages : answerPages

  useEffect(() => {
    setPage((p) => Math.max(1, Math.min(p, Math.max(1, total))))
  }, [total])

  if (!dir || !pages) return null

  const name = `${kind}-${page}.png`
  const src = `/api/ingest/preview-image?path=${encodeURIComponent(name)}`
    + `&src_dir=${encodeURIComponent(dir)}`

  return (
    <aside className="hidden w-[300px] shrink-0 flex-col border-r border-border bg-surface
                      xl:flex">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2.5">
        <ScanLine size={14} className="text-brand" />
        <span className="text-[12px] font-semibold text-ink">原文对照</span>
        <span className="tnum text-[10px] text-ink-faint">{pages} 页</span>
        <button onClick={() => onOpen(kind, page)} title="放大原页"
          className="icon-btn ml-auto h-6 w-6"><Maximize2 size={12} /></button>
      </div>

      <div className="flex shrink-0 items-center gap-1 border-b border-border px-2 py-1.5">
        <button onClick={() => setKind('q')}
          className={`press rounded px-2 py-[3px] text-[10.5px] ${kind === 'q'
            ? 'bg-brand-soft font-medium text-brand-ink' : 'text-ink-faint hover:text-ink'}`}>
          试题页
        </button>
        {answerPages > 0 && (
          <button onClick={() => setKind('a')}
            className={`press rounded px-2 py-[3px] text-[10.5px] ${kind === 'a'
              ? 'bg-brand-soft font-medium text-brand-ink' : 'text-ink-faint hover:text-ink'}`}>
            答案页
          </button>
        )}
        <span className="ml-auto text-[9.5px] text-ink-faint">与右侧题卡对照</span>
      </div>

      <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-border px-2 py-1.5">
        <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}
          className="icon-btn h-5 w-5 shrink-0 disabled:opacity-25"><ChevronLeft size={11} /></button>
        {Array.from({ length: total }, (_, i) => i + 1).map((n) => (
          <button key={n} onClick={() => setPage(n)}
            className={`tnum shrink-0 rounded px-1.5 py-[2px] text-[10px] ${page === n
              ? 'bg-brand font-medium text-white' : 'bg-muted text-ink-soft hover:text-ink'}`}>
            {n}
          </button>
        ))}
        <button onClick={() => setPage((p) => Math.min(total, p + 1))} disabled={page >= total}
          className="icon-btn h-5 w-5 shrink-0 disabled:opacity-25"><ChevronRight size={11} /></button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-[#e9e9ed] p-2">
        <img src={src} alt={`${kind === 'q' ? '试题' : '答案'}第 ${page} 页`}
          className="mx-auto w-full rounded border border-border bg-white shadow-sm" />
      </div>
      <div className="shrink-0 border-t border-border px-3 py-1.5 text-[9.5px] text-ink-faint">
        {kind === 'q' ? '试题' : '答案'}第 {page} / {total} 页
      </div>
    </aside>
  )
}
