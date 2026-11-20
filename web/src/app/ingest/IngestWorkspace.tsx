/** 独立录入页：从原工作台点「录入」时在新标签页打开。
 *
 *  和旧抽屉的区别：
 *  ① 它是页面，不再盖住原工作台；原标签页的状态原样保留。
 *  ② 顶部有「来源 → 核对 → 入库」三步和当前选中量，编辑时知道自己在哪。
 *  ③ 左栏是来源/出处，右栏是逐题检查；窄屏用底部「来源 / 核对」切换。
 *  ④ 录入完成后向其他标签页广播一次，原工作台的统计可以自己刷新。
 */
import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Check, FileText, Sparkles } from 'lucide-react'
import { STAGE_BY_KEY, type Stage } from '@/lib/stage'
import { CloseBtn } from '@/app/ui'
import { IngestProvider } from '@/app/ingest/IngestContext'
import { useIngest } from '@/app/ingest/useIngest'
import SourceStage from '@/app/ingest/SourceStage'
import ReviewStage from '@/app/ingest/ReviewStage'
import OriginalPages from '@/app/ingest/OriginalPages'

export type IngestMode = 'latex' | 'ai' | 'curate' | 'proof'

const STEPS = [
  { n: 1, label: '来源' },
  { n: 2, label: '核对' },
  { n: 3, label: '入库' },
]

export default function IngestWorkspace({ mode, stage, facets, onBack, onDone }: {
  mode: Exclude<IngestMode, 'curate' | 'proof'>
  stage: Stage
  facets: any
  onBack: () => void
  onDone: () => void
}) {
  const finish = () => {
    onDone()
    // 通知其他标签页（原工作台）重新读统计；不需要它知道录入细节。
    try { localStorage.setItem('ammath.ingest.updated', String(Date.now())) } catch { /* ignore */ }
  }
  const ing = useIngest({ ai: mode === 'ai', facets, onClose: onBack, onDone: finish })
  const { pageView, setPageView, closeSafely, pv, report, selected, text, busy, aiPageDir, aiReport } = ing
  const [pane, setPane] = useState<'source' | 'review'>('source')
  const hadPv = useRef(false)

  // 第一次解析出题卡时自动切到右栏；之后用户自己切，不再抢。
  useEffect(() => {
    if (pv && !hadPv.current) {
      hadPv.current = true
      setPane('review')
    }
    if (!pv) hadPv.current = false
  }, [pv])

  // AI 读取报告的「查看题卡」：桌面两栏都开着，窄屏需要把右栏切出来。
  useEffect(() => {
    const go = () => setPane('review')
    window.addEventListener('ammath:ingest-review', go)
    return () => window.removeEventListener('ammath:ingest-review', go)
  }, [])

  const step = report ? 3 : pv ? 2 : 1
  const status = pv
    ? `${selected.length}/${pv.count} 道已勾选`
    : text.trim() ? '材料已就绪，等待解析' : '等待材料'

  return (
    <IngestProvider value={ing}>
      <div className="flex h-full min-h-0 flex-col bg-bg">
        <header className="shrink-0 border-b border-border bg-surface px-4 py-2.5">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[10px] grad-primary
                             text-[14px] font-bold text-white shadow-[var(--shadow-brand)]" aria-hidden>A</span>
            <span className="hidden text-[13px] font-semibold tracking-[-.02em] sm:inline">AmMath</span>
            <span className="hidden text-border-strong sm:inline">/</span>
            <button onClick={closeSafely}
              className="press inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-[12px]
                         text-ink-faint hover:bg-muted hover:text-ink"
              title="返回录入方式选择；材料会保存为草稿">
              <ArrowLeft size={14} />录入
            </button>
            <span className="text-border-strong">/</span>
            <h1 className="flex items-center gap-1.5 text-[15px] font-semibold tracking-tight">
              {mode === 'ai' ? <Sparkles size={15} className="text-brand" /> : <FileText size={15} className="text-brand" />}
              {mode === 'ai' ? 'DeepSeek 录题' : '手工录题'}
            </h1>
            <span className="rounded border border-border bg-bg px-1.5 py-[1px] text-[10px] text-ink-faint">
              {mode === 'ai' ? 'DeepSeek' : '手工'}
            </span>

            <div className="ml-auto flex items-center gap-2">
              <div className="hidden items-center gap-1 sm:flex" aria-label="录入步骤">
                {STEPS.map((s) => {
                  const done = s.n < step
                  const on = s.n === step
                  return (
                    <span key={s.n} className="flex items-center gap-1">
                      <span className={`inline-flex items-center gap-1 rounded-[5px] px-1.5 py-[2px]
                        text-[10px] ${on ? 'bg-brand-soft font-semibold text-brand-ink'
                          : done ? 'text-has' : 'text-ink-faint'}`}>
                        {done ? <Check size={10} /> : <span className="tnum">{s.n}</span>}
                        {s.label}
                      </span>
                      {s.n < 3 && <span className="h-px w-3 bg-border" />}
                    </span>
                  )
                })}
              </div>
              <span className="tnum rounded bg-bg px-2 py-[2px] text-[10px] text-ink-faint">
                {busy ? '检查中…' : status}
              </span>
              <CloseBtn onClick={closeSafely} title="关闭录入（材料会保存为草稿）" />
            </div>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10.5px] text-ink-faint">
            <span>{STAGE_BY_KEY[stage].name} · 先给材料 → 解析后逐题核对 → 勾选确认才入库</span>
            <span className="text-border-strong">·</span>
            <span>右栏六项检查分别看结构、规范、查重、图片、答案解析和勾选</span>
            <span className="ml-auto max-sm:hidden">
              {STAGE_BY_KEY[stage].name} · 独立录入页 · 原工作台保持不变
            </span>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <div className={`${pane === 'source' ? 'flex' : 'hidden'} min-h-0 w-full shrink-0
                           border-r border-border bg-surface lg:flex lg:w-[460px] xl:w-[500px]`}>
            <SourceStage />
          </div>
          {mode === 'ai' && aiReport && aiPageDir && (
            <OriginalPages dir={aiPageDir}
              pages={Number(aiReport.stats?.pages || 0)}
              answerPages={Number(aiReport.stats?.answer_pages || 0)}
              onOpen={(kind, page) => setPageView({
                dir: aiPageDir,
                name: `${kind}-${page}.png`,
                title: `${kind === 'q' ? '试题' : '答案'}第 ${page} 页`,
              })} />
          )}
          <div className={`${pane === 'review' ? 'flex' : 'hidden'} min-h-0 min-w-0 flex-1 lg:flex`}>
            <ReviewStage />
          </div>
        </div>

        {/* 窄屏只显示一栏，用底部的两个页签切换；它是页面内的导航，不是第三个抽屉。 */}
        <div className="flex shrink-0 items-stretch border-t border-border bg-surface p-1 lg:hidden">
          <button onClick={() => setPane('source')}
            className={`press flex flex-1 items-center justify-center gap-1.5 rounded-md py-2
                       text-[11.5px] ${pane === 'source' ? 'bg-brand-soft font-semibold text-brand-ink'
                         : 'text-ink-faint'}`}>
            <FileText size={13} />来源
          </button>
          <button onClick={() => setPane('review')} disabled={!pv}
            className={`press flex flex-1 items-center justify-center gap-1.5 rounded-md py-2
                       text-[11.5px] disabled:opacity-40 ${pane === 'review'
                         ? 'bg-brand-soft font-semibold text-brand-ink' : 'text-ink-faint'}`}>
            <Check size={13} />核对{pv ? ` (${pv.count})` : ''}
          </button>
        </div>

        {pageView && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
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
