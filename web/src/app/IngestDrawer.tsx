/** 录入抽屉壳：只负责布局、Provider 和源页查看。
 *
 *  状态/handlers 在 `useIngest`；来源/逐题确认/提交分别在
 *  `SourceStage`、`ReviewStage`、`CommitBar`。
 */
import { FileText, Sparkles } from 'lucide-react'
import { CloseBtn } from '@/app/ui'
import { IngestProvider } from '@/app/ingest/IngestContext'
import { useIngest } from '@/app/ingest/useIngest'
import SourceStage from '@/app/ingest/SourceStage'
import ReviewStage from '@/app/ingest/ReviewStage'

export default function IngestDrawer({ onClose, onDone, facets, closing, ai = false }: {
  onClose: () => void; onDone: () => void; facets: any
  closing?: boolean
  ai?: boolean
}) {
  const ing = useIngest({ ai, facets, onClose, onDone })
  const { pageView, setPageView, closeSafely } = ing
  return (
    <IngestProvider value={ing}>
      <div className={`${closing ? 'anim-slide-r-out' : 'anim-slide-r'} fixed inset-0 z-50
                      flex flex-col border-l border-border bg-surface
                      shadow-[var(--shadow-pop)]`} onClick={closeSafely}>
        <div className="flex min-h-0 flex-1 flex-col" onClick={(e) => e.stopPropagation()}>
        <header className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-5 py-3.5">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand-ink">
            {ai ? <Sparkles size={15} /> : <FileText size={15} />}
          </span>
          <span className="shrink-0 text-[15px] font-semibold tracking-tight text-ink">
            {ai ? '大模型录题' : '录入题目'}
          </span>
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-faint">
            {ai
              ? '整份 PDF / 照片交给 DeepSeek → 逐题核对 → 勾选入库（读的过程中不写库）'
              : '粘贴整份试卷 → 自动切题 → 逐题确认 → 勾选入库（干跑什么都不写）'}
          </span>
          <CloseBtn onClick={closeSafely} className="ml-auto" />
        </header>

          <div className="flex min-h-0 flex-1">
            <SourceStage />
            <ReviewStage />
          </div>
        </div>

      {pageView && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-6"
          onClick={(e) => { e.stopPropagation(); setPageView(null) }}>
          <div className="max-h-full max-w-[min(1100px,92vw)] overflow-auto rounded-xl
                          border border-border bg-surface p-2 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between gap-3 px-2 py-1">
              <span className="text-[12px] font-medium text-ink-soft">{pageView.title}</span>
              <button onClick={() => setPageView(null)}
                className="text-[11px] text-ink-faint underline hover:text-ink">关闭</button>
            </div>
            <img
              src={`/api/ingest/preview-image?path=${encodeURIComponent(pageView.name)}`
                + `&src_dir=${encodeURIComponent(pageView.dir)}`}
              alt={pageView.title}
              className="max-h-[82vh] max-w-full object-contain" />
          </div>
        </div>
      )}
      </div>
    </IngestProvider>
  )
}
