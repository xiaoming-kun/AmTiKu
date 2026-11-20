/** 知识点面板（内容区最左那一列，可收起）。
 *
 *  **只放知识点**。以前这一栏还塞了关键词/类别/年份/题型/难度/完整度/出处/
 *  元数据/排序/预设——于是同一个维度在左边和顶部筛选条各有一套，改了一边
 *  另一边没动，用户看到两处状态不一致。
 *
 *  现在分工是死的：
 *   · 左栏 = 知识点树（152 个考点，带章节、题数、并集/交集）；
 *   · 顶部筛选条 = 其余全部维度（难度/题型/完整度/年份/出处/试卷/质量/排序）。
 *
 *  知识点没法进横条：201 个考点平铺会变成一长串滚动的胶囊，"按章找题"
 *  这件事本身就需要树形结构。
 */
import { useEffect } from 'react'
import { ChevronRight, Network, X } from 'lucide-react'
import type { useQuestionList } from '@/lib/useQuestionList'
import { groupTree } from '@/app/Stats'
// 栏宽挪到 lib/layout：App 算抽屉限宽要用，但它不该为此同步 import 整个面板。
import { FILTER_W } from '@/lib/layout'

type L = ReturnType<typeof useQuestionList>

export default function FilterPanel({ L, onClose, onMap }: {
  L: L
  onClose?: () => void
  onMap?: () => void
  /** 保留旧签名：App 仍在传「清除全部筛选」，知识点这一栏自己清。 */
  onClearAll?: () => void
}) {
  const { facets, points, setPoints, pointMode, setPointMode,
          openTopics, setOpenTopics, togglePoint, togglePoints, toggleTopic, scopeName } = L

  const tree = groupTree(facets?.points || [])

  // 选中的考点所在大类自动展开，否则选完就看不见自己选了什么
  useEffect(() => {
    if (!points.length || !facets) return
    const hit = new Set(facets.points.filter((p) => points.includes(p.value)).map((p) => p.topic))
    if (!hit.size) return
    setOpenTopics((s) => new Set([...s, ...hit]))
  }, [points, facets, setOpenTopics])

  return (
    <aside
      style={{ width: FILTER_W }}
      className="flex h-full max-h-full min-h-0 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex h-12 shrink-0 items-center gap-1.5 border-b border-border px-3">
        <Network size={13} className="shrink-0 text-brand" />
        <span className="text-[12.5px] font-semibold">知识点</span>
        <span className="tnum text-[10.5px] text-ink-faint">
          {facets ? `${facets.points_covered}/${facets.points.length}` : ''}
        </span>
        {onClose && (
          <button onClick={onClose} title="收起知识点面板"
            className="icon-btn ml-auto h-6 w-6"><X size={13} /></button>
        )}
      </div>

      {/* 并集 / 交集：多选考点时「任一命中」还是「全部挂上」。 */}
      <div className="flex shrink-0 items-center gap-1.5 border-b border-border px-3 py-1.5 text-[10.5px]">
        <span className="shrink-0 text-ink-faint">多选</span>
        <span className="flex shrink-0 overflow-hidden rounded-md border border-border">
          {([['any', '并集', '命中任一考点就出现（默认）'],
             ['all', '交集', '选中的考点必须全部挂在这道题上']] as const).map(([k, label, tip]) => (
            <button key={k} type="button" onClick={() => setPointMode(k)} title={tip}
              className={`press whitespace-nowrap px-2 py-[2px] text-[10.5px] transition-colors ${
                pointMode === k ? 'bg-brand font-medium text-white'
                                : 'bg-surface text-ink-faint hover:bg-brand-soft hover:text-brand-ink'}`}>
              {label}
            </button>
          ))}
        </span>
        <span className="min-w-0 flex-1 truncate text-right text-ink-faint">
          {pointMode === 'all'
            ? (points.length < 2 ? '再选 1 个才生效' : `全部 ${points.length} 个都要命中`)
            : '命中任一考点'}
        </span>
      </div>

      {scopeName && (
        <div className="mx-2.5 mt-2 flex shrink-0 items-center gap-1.5 rounded-lg bg-brand-soft
                        px-2 py-1 text-[11px] font-medium text-brand-ink">
          <span className="truncate">{scopeName}</span>
          <button onClick={() => setPoints([])} title="取消"
            className="ml-auto shrink-0 text-brand-ink/60 hover:text-brand-ink">
            <X size={11} />
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 py-2">
        <div className="mb-1 flex items-center gap-1 text-[10.5px] text-ink-faint">
          <button onClick={() => setOpenTopics(new Set(tree.map((g) => g.topic)))}
            className="press rounded-md border border-border px-1.5 py-[1px] hover:border-brand-line hover:text-brand-ink">
            展开
          </button>
          <button onClick={() => setOpenTopics(new Set())}
            className="press rounded-md border border-border px-1.5 py-[1px] hover:border-brand-line hover:text-brand-ink">
            收起
          </button>
          <span className="ml-auto tnum">已选 {points.length}</span>
        </div>

        <div className="space-y-[3px]">
          {tree.map(({ topic, sections }) => {
            const all = sections.flatMap((s) => s.points)
            const cov = all.filter((p) => p.n > 0).length
            const sel = all.filter((p) => points.includes(p.value)).length
            const isOpen = openTopics.has(topic)
            return (
              <div key={topic}
                className={`overflow-hidden rounded-lg border transition-colors ${
                  sel ? 'border-brand-line bg-brand-soft/35' : 'border-transparent'}`}>
                {/* 大类。**箭头管展开、名字管筛选**——用户要的就是"点这一章，
                    题目就剩这一章的"，所以名字本身必须是可点的筛选入口。 */}
                <div className={`flex w-full items-center gap-1 pr-1 transition-colors ${
                  sel ? 'bg-brand-soft/40' : 'hover:bg-muted'}`}>
                  <button onClick={() => toggleTopic(topic)}
                    title={isOpen ? '收起' : '展开'}
                    className="shrink-0 py-[7px] pl-2 pr-0.5 text-ink-faint hover:text-brand-ink">
                    <ChevronRight size={12} strokeWidth={2.6}
                      className={`transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`} />
                  </button>
                  <button onClick={() => {
                      togglePoints(all.map((p) => p.value))
                      if (!isOpen) setOpenTopics((s2) => new Set([...s2, topic]))
                    }}
                    title={`只看「${topic}」这一章的题目（${all.length} 个考点）`}
                    className="flex min-w-0 flex-1 items-center gap-1.5 py-[7px] text-left">
                    <span className={`min-w-0 flex-1 text-[12px] font-semibold leading-tight ${
                      sel ? 'text-brand-ink' : 'text-ink'}`}>{topic}</span>
                    {sel > 0 && (
                      <span className="tnum shrink-0 rounded-full bg-brand px-1.5 text-[9.5px]
                                       font-medium leading-[15px] text-white">{sel}</span>
                    )}
                    <span className={`tnum w-8 shrink-0 text-right text-[10px] ${
                      cov ? 'text-ink-faint' : 'text-warn/80'}`}>{cov}/{all.length}</span>
                  </button>
                </div>

                {isOpen && (
                  <div className="anim-fade-in border-t border-brand-line/40 px-2 pb-1.5 pt-1">
                    {sections.map(({ section, points: list }) => (
                      <div key={section} className="mb-1 last:mb-0">
                        {/* 小类。只有一个考点时不显示——那种情况下小类名和考点名几乎一样。 */}
                        {list.length > 1 && (() => {
                          const ids = list.map((p) => p.value)
                          const secAll = ids.every((i) => points.includes(i))
                          return (
                            <div className={`mb-[2px] flex items-center gap-1 border-l-2 pl-1.5 ${
                              secAll ? 'border-brand' : 'border-border'}`}>
                              <button onClick={() => togglePoints(ids)}
                                title={`只看「${section}」这一节的题目`}
                                className={`min-w-0 flex-1 truncate text-left text-[10.5px] font-medium
                                            leading-tight hover:text-brand-ink ${
                                  secAll ? 'text-brand-ink' : 'text-ink-faint'}`}>
                                {section}
                              </button>
                              <button onClick={() => togglePoints(ids)}
                                className={`press shrink-0 rounded px-1 text-[9.5px] transition-colors ${
                                  secAll ? 'bg-brand text-white'
                                         : 'text-ink-faint hover:bg-brand-soft hover:text-brand-ink'}`}>
                                {secAll ? '已选' : '全节'}
                              </button>
                            </div>
                          )
                        })()}
                        {list.map((p) => {
                          const on = points.includes(p.value)
                          return (
                            <button key={p.value} onClick={() => togglePoint(p.value)}
                              title={`${p.title}${p.n ? ` · ${p.n} 道` : ' · 暂无题目'}`}
                              className={`flex w-full items-center gap-2 rounded-md py-[4px] pl-2 pr-1.5
                                          text-left transition-colors ${
                                on ? 'bg-brand text-white' : 'hover:bg-muted'}`}>
                              <span className={`min-w-0 flex-1 truncate text-[11.5px] ${
                                on ? 'font-medium text-white' : p.n ? 'text-ink-soft' : 'text-ink-faint/60'}`}>
                                {p.title}
                              </span>
                              <span className={`tnum w-6 shrink-0 text-right text-[10px] ${
                                on ? 'text-white/80' : p.n ? 'text-ink-faint' : 'text-warn/60'}`}>
                                {p.n || '—'}
                              </span>
                            </button>
                          )
                        })}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {onMap && (
          <button onClick={onMap}
            className="mt-2 flex w-full items-center gap-1 rounded-lg border border-dashed
                       border-border px-2 py-1.5 text-[10.5px] text-ink-faint
                       hover:border-brand-line hover:text-brand-ink">
            小学—高中 · 按教材顺序的知识地图
            <ChevronRight size={11} className="ml-auto" />
          </button>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1.5 border-t border-border px-3 py-2 text-[10.5px] text-ink-faint">
        <span className="tnum">共 {facets?.points.length ?? 0} 个考点 · 已选 {points.length}</span>
        {points.length > 0 && (
          <button onClick={() => setPoints([])}
            className="press ml-auto rounded px-1.5 py-[1px] text-brand-ink hover:bg-brand-soft">
            清除
          </button>
        )}
      </div>
    </aside>
  )
}
