/** 编辑器左栏：按考点选题 / 搜索。
 *
 *  从 CanvasEditor 拆出来的（审查报告 REACT-4：一个组件管 8 件事）。
 *  纯展示 + 回调，状态在 `useDrawer` 里。
 */
import type { Q } from '@/lib/types'
import { QuestionRow } from '@/editor/shared'
import type { TopicGroup } from '@/editor/useDrawer'

export default function PointDrawer({ handoutQs, q, setQ, searchResults, topics,
  openTopic, setOpenTopic, openPoint, pointQs, loadingPt, togglePoint, addQuestion }: {
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
}) {
  return (
        <div className="flex w-[250px] shrink-0 flex-col border-r border-border bg-surface">
      <div className="border-b border-border px-2.5 py-2">
        <div className="mb-1.5 text-[11px] font-semibold text-ink-faint">
          题库 <span className="font-normal">（拖到画布）</span>
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜题干…"
          className="w-full rounded-md border border-border bg-bg px-2 py-1 text-[11.5px]
                     outline-none focus:border-brand/40" />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 py-2">
        {handoutQs.length > 0 && (
          <>
            {/* 来源：优先用「加入讲义」选的题；
                没有才退回卷子的选题目录（老师可能直接用卷子的选择） */}
            <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">
              已选的题（{handoutQs.length}）
            </div>
            {handoutQs.map((qq) => (
              <QuestionRow key={`p-${qq.key}`} q={qq} onAdd={() => addQuestion(qq)} />
            ))}
            <div className="my-2 border-t border-border" />
          </>
        )}
        {q.trim() ? (
          <>
            {/* 搜索时用平铺结果（覆盖考点树，找题更快） */}
            <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">
              搜索结果{searchResults === null ? '…' : `（${searchResults.length}）`}
            </div>
            {(searchResults || []).map((qq) => (
              <QuestionRow key={qq.key} q={qq} onAdd={() => addQuestion(qq)} />
            ))}
          </>
        ) : (
          <>
            <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">
              按考点选题
            </div>
            {topics.map((t) => (
              <div key={t.name} className="mb-0.5">
                {/* 章级：点击展开该章的考点 */}
                <button onClick={() => setOpenTopic(openTopic === t.name ? '' : t.name)}
                  className="flex w-full items-center gap-1 rounded px-1 py-1 text-left
                             text-[11.5px] font-medium text-ink hover:bg-muted/60">
                  <span className="w-3 shrink-0 text-ink-faint">
                    {openTopic === t.name ? '▾' : '▸'}
                  </span>
                  <span className="truncate">{t.name}</span>
                  <span className="ml-auto shrink-0 text-[10px] tabular-nums text-ink-faint">{t.count}</span>
                </button>
                {/* 考点级：点击展开该考点的题（懒加载） */}
                {openTopic === t.name && (
                  <div className="ml-3 border-l border-border pl-1.5">
                    {t.points.map((pt) => (
                      <div key={pt.value}>
                        <button onClick={() => togglePoint(pt.value)}
                          className="flex w-full items-center gap-1 rounded px-1 py-[3px]
                                     text-left text-[11px] text-ink-soft hover:bg-muted/60">
                          <span className="w-2.5 shrink-0 text-ink-faint">
                            {openPoint === pt.value ? '▾' : '·'}
                          </span>
                          <span className="truncate">{pt.title}</span>
                          <span className="ml-auto shrink-0 text-[10px] tabular-nums text-ink-faint">{pt.n}</span>
                        </button>
                        {openPoint === pt.value && (
                          <div className="mb-1 ml-2.5">
                            {loadingPt === pt.value && (
                              <div className="px-1 py-1 text-[10.5px] text-ink-faint">加载中…</div>
                            )}
                            {!loadingPt && (pointQs[pt.value] || []).length > 0 && (
                              <div className="px-1 pb-0.5 text-[10px] text-ink-faint">
                                共 {pointQs[pt.value].length} 道，点击加入画布
                              </div>
                            )}
                            {(pointQs[pt.value] || []).map((qq) => (
                              <QuestionRow key={qq.key} q={qq} onAdd={() => addQuestion(qq)} />
                            ))}
                            {!loadingPt && !(pointQs[pt.value] || []).length && (
                              <div className="px-1 py-1 text-[10.5px] text-ink-faint">该考点暂无题</div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
