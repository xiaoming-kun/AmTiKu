/** 编辑器左栏：按考点选题 / 搜索。
 *
 *  从 CanvasEditor 拆出来的（审查报告 REACT-4：一个组件管 8 件事）。
 *  纯展示 + 回调，状态在 `useDrawer` 里。
 *
 *  视觉：面板底 = bg-surface，与中间画布区的 bg-bg 用 border-r 分开。
 *  层级只有三层：面板头（52px）/ 搜索 / 树，靠留白和 11px 的小节标题
 *  分段，不再用密集的边框把每一行都框起来。
 */
import { ChevronDown, ChevronRight, LibraryBig, Search } from 'lucide-react'
import type { Q } from '@/lib/types'
import { QuestionRow } from '@/editor/shared'
import type { TopicGroup } from '@/editor/useDrawer'

export default function PointDrawer({ handoutQs, q, setQ, searchResults, topics,
  openTopic, setOpenTopic, openPoint, pointQs, loadingPt, togglePoint,
  addQuestion, previewQuestion }: {
  handoutQs: Q[]
  q: string; setQ: (s: string) => void
  searchResults: Q[] | null
  topics: TopicGroup[]
  openTopic: string; setOpenTopic: (s: string) => void
  openPoint: string
  pointQs: Record<string, Q[]>
  loadingPt: string
  togglePoint: (pv: string) => void
  addQuestion: (qq: Q) => void
  previewQuestion: (qq: Q) => void
}) {
  return (
    <aside className="flex w-[254px] shrink-0 flex-col border-r border-border bg-surface">
      {/* ── 面板头 ── */}
      <div className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border px-3.5">
        <LibraryBig size={15} className="shrink-0 text-brand" />
        <span className="text-[14px] font-semibold tracking-tight">题库</span>
        <span className="ml-auto shrink-0 text-[11px] text-ink-faint">（点题看详情）</span>
      </div>

      {/* ── 搜索：手在左栏时不用回顶栏 ── */}
      <div className="shrink-0 border-b border-border px-3.5 py-3">
        <div className="relative">
          <Search size={13}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜题干…"
            className="h-[32px] w-full rounded-lg border border-border bg-bg pl-7 pr-2.5 text-[12.5px]
                       outline-none transition-[border-color,box-shadow] duration-150
                       placeholder:text-ink-faint focus:border-brand-line focus:bg-surface
                       focus:shadow-[0_0_0_3px_var(--color-brand-soft)]" />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3.5">
        {handoutQs.length > 0 && (
          <section className="mb-4">
            {/* 来源：优先用「加入讲义」选的题；
                没有才退回卷子的选题目录（老师可能直接用卷子的选择） */}
            <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold
                            tracking-[0.08em] text-ink-faint">
              已选的题
              <span className="tnum rounded-full bg-brand-soft px-1.5 text-[10.5px] font-medium
                               leading-[16px] text-brand-ink">
                {handoutQs.length}
              </span>
            </div>
            <div className="space-y-1">
              {handoutQs.map((qq) => (
                <QuestionRow key={`p-${qq.key}`} q={qq}
                  onAdd={() => addQuestion(qq)} onOpen={() => previewQuestion(qq)} />
              ))}
            </div>
          </section>
        )}
        {q.trim() ? (
          <section>
            {/* 搜索时用平铺结果（覆盖考点树，找题更快） */}
            <div className="mb-2 text-[11px] font-semibold tracking-[0.08em] text-ink-faint">
              搜索结果{searchResults === null ? '…' : `（${searchResults.length}）`}
            </div>
            <div className="space-y-1">
              {(searchResults || []).map((qq) => (
                <QuestionRow key={qq.key} q={qq}
                  onAdd={() => addQuestion(qq)} onOpen={() => previewQuestion(qq)} />
              ))}
            </div>
          </section>
        ) : (
          <section>
            <div className="mb-2 text-[11px] font-semibold tracking-[0.08em] text-ink-faint">
              按考点选题
            </div>
            <div className="space-y-[3px]">
              {topics.map((t) => {
                const tOpen = openTopic === t.name
                return (
                  <div key={t.name}>
                    {/* 章级：点击展开该章的考点 */}
                    <button onClick={() => setOpenTopic(tOpen ? '' : t.name)}
                      className={`press flex w-full items-center gap-1.5 rounded-lg px-2 py-[6px]
                                  text-left text-[12.5px] font-medium transition-colors ${
                        tOpen ? 'bg-brand-soft text-brand-ink' : 'text-ink hover:bg-muted'}`}>
                      {tOpen
                        ? <ChevronDown size={13} className="shrink-0 text-brand" />
                        : <ChevronRight size={13} className="shrink-0 text-ink-faint" />}
                      <span className="min-w-0 flex-1 truncate">{t.name}</span>
                      <span className="tnum ml-auto shrink-0 text-[10.5px] text-ink-faint">{t.count}</span>
                    </button>
                    {/* 考点级：点击展开该考点的题（懒加载） */}
                    {tOpen && (
                      <div className="anim-fade-in ml-3.5 border-l border-border pb-0.5 pl-1.5 pt-[3px]">
                        {t.points.map((pt) => (
                          <div key={pt.value}>
                            <button onClick={() => togglePoint(pt.value)}
                              className="flex w-full items-center gap-1.5 rounded-md px-1.5 py-[4px]
                                         text-left text-[11.5px] text-ink-soft transition-colors
                                         hover:bg-muted hover:text-ink">
                              <ChevronRight size={11}
                                className={`shrink-0 text-ink-faint transition-transform duration-200 ${
                                  openPoint === pt.value ? 'rotate-90' : ''}`} />
                              <span className="min-w-0 flex-1 truncate">{pt.title}</span>
                              <span className="tnum ml-auto shrink-0 text-[10.5px] text-ink-faint">{pt.n}</span>
                            </button>
                            {openPoint === pt.value && (
                              <div className="mb-1.5 ml-3.5">
                                {loadingPt === pt.value && (
                                  <div className="px-1 py-1 text-[11px] text-ink-faint">加载中…</div>
                                )}
                                {!loadingPt && (pointQs[pt.value] || []).length > 0 && (
                                  <div className="px-1 pb-1 text-[10.5px] text-ink-faint">
                                    共 {pointQs[pt.value].length} 道，点击加入画布
                                  </div>
                                )}
                                <div className="space-y-1">
                                  {(pointQs[pt.value] || []).map((qq) => (
                                    <QuestionRow key={qq.key} q={qq}
                                      onAdd={() => addQuestion(qq)} onOpen={() => previewQuestion(qq)} />
                                  ))}
                                </div>
                                {!loadingPt && !(pointQs[pt.value] || []).length && (
                                  <div className="px-1 py-1 text-[11px] text-ink-faint">该考点暂无题</div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )}
      </div>
    </aside>
  )
}
