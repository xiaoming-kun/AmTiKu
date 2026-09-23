/** 题目筛选面板（内容区最左那一列，可收起）。
 *
 *  从 App.tsx 搬出来的。搬动本身就有意义：这一块是「筛什么」的**全部**，
 *  和「列出来什么」「选中哪道」没有一行交互，混在一个 1000 行的组件里
 *  只会让每次改筛选都要重读整个 App。
 *
 *  和旧版的差别不只是搬家：
 *  ① 五个筛选维度从**弹层**改成**平铺**。弹层的问题是选之前看不见有什么，
 *     选完也看不见还选了什么；平铺以后一屏之内全部可见，点击次数减半。
 *  ② 每个维度可折叠，章节树默认展开、年份/排序默认收起——常看的在上。
 *  ③ 选中的东西统一走「实心胶囊」，一屏里哪几个是活的，一眼可数。
 */
import { useEffect, useState } from 'react'
import { ListFilter, X, ChevronRight, TriangleAlert } from 'lucide-react'
import type { useQuestionList } from '@/lib/useQuestionList'
import { DIFF_STARS } from '@/lib/display'
import { groupTree } from '@/app/Stats'
import { Chip, Section, FLAG_KEYS } from '@/app/ui'

type L = ReturnType<typeof useQuestionList>

const SORTS: [string, string][] = [
  ['used', '频次 高→低'], ['diff', '易 → 难'], ['diff2', '难 → 易'],
  ['', '题库原序'], ['new', '最新录入'], ['old', '最早录入'], ['solved', '刚解出的'],
]

export default function FilterPanel({ L, onClose }: { L: L; onClose?: () => void }) {
  const {
    facets, q, setQ, type, setType, setKind,
    has, setHas, missing, setMissing, points, setPoints, diffs, setDiffs,
    years, setYears, sort, setSort, openTopics, setOpenTopics,
    toggleYear, toggleHas, toggleMissing, togglePoint, toggleDiff,
    togglePoints, toggleTopic, activeFilters, scopeName,
  } = L

  // 折叠状态记忆：老师会固定一种看惯的顺序，不该每次打开都回到默认
  const [open, setOpen] = useState<Record<string, boolean>>(() => {
    try {
      const s = localStorage.getItem('amtiku.filter.sections')
      if (s) return JSON.parse(s)
    } catch { /* 存坏了就用默认，不阻断界面 */ }
    return { points: true, types: true, diff: true, flags: true, years: false, sort: false }
  })
  useEffect(() => {
    localStorage.setItem('amtiku.filter.sections', JSON.stringify(open))
  }, [open])
  const flip = (k: string) => setOpen((o) => ({ ...o, [k]: !o[k] }))

  const tree = groupTree(facets?.points || [])
  const allIds = (facets?.points || []).map((p) => p.value)

  return (
    <aside className="flex w-[252px] shrink-0 flex-col border-r border-border bg-surface">
      {/* ── 面板头 ── */}
      <div className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border px-3.5">
        <ListFilter size={15} className="shrink-0 text-brand" />
        <span className="text-[14px] font-semibold tracking-tight">题目筛选</span>
        {activeFilters > 0 && (
          <span className="tnum rounded-full bg-brand px-1.5 text-[10.5px] font-medium leading-[17px] text-white">
            {activeFilters}
          </span>
        )}
        {onClose && (
          <button onClick={onClose} title="收起筛选面板（筛）" className="icon-btn ml-auto h-7 w-7">
            <X size={15} />
          </button>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3.5 py-3.5">
        {/* ── 搜索留在面板里也留一份：手在面板上时不用回顶栏 ── */}
        <input value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="关键词…  按 / 回顶栏"
          className="h-[32px] w-full rounded-lg border border-border bg-bg px-2.5 text-[12.5px]
                     outline-none transition-[border-color,box-shadow] duration-150
                     placeholder:text-ink-faint focus:border-brand-line focus:bg-surface
                     focus:shadow-[0_0_0_3px_var(--color-brand-soft)]" />

        {/* ── 知识点：这一栏的总纲 ── */}
        <Section title="知识点" open={open.points} onToggle={() => flip('points')}
          hint={facets ? `${facets.points_covered}/${facets.points.length}` : ''}
          right={
            <span className="flex gap-1">
              <button onClick={() => setOpenTopics(new Set(tree.map((g) => g.topic)))}
                className="press rounded-md border border-border px-1.5 py-[1px] text-[10.5px]
                           text-ink-faint hover:border-brand-line hover:text-brand-ink">
                展开
              </button>
              <button onClick={() => setOpenTopics(new Set())}
                className="press rounded-md border border-border px-1.5 py-[1px] text-[10.5px]
                           text-ink-faint hover:border-brand-line hover:text-brand-ink">
                收起
              </button>
            </span>
          }>
          {scopeName && (
            <div className="mb-1.5 flex items-center gap-1.5 rounded-lg bg-brand-soft px-2 py-1
                            text-[11px] font-medium text-brand-ink">
              <span className="truncate">{scopeName}</span>
              <button onClick={() => setPoints([])} title="取消"
                className="ml-auto shrink-0 text-brand-ink/60 hover:text-brand-ink">
                <X size={11} />
              </button>
            </div>
          )}
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
                  {/* 大类。**箭头管展开、名字管筛选**——
                      用户要的就是"点这一章，题目就剩这一章的"，
                      所以名字本身必须是可点的筛选入口，不能只是展开。 */}
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
                          {/* 小类。只有一个考点时不显示——那种情况下小类名和
                              考点名几乎一样，纯属噪声。 */}
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
                                  on ? 'bg-brand text-white'
                                     : 'hover:bg-muted'}`}>
                                <span className={`min-w-0 flex-1 truncate text-[11.5px] ${
                                  on ? 'font-medium text-white'
                                     : p.n ? 'text-ink-soft' : 'text-ink-faint/60'}`}>
                                  {p.title}
                                </span>
                                <span className={`tnum w-6 shrink-0 text-right text-[10px] ${
                                  on ? 'text-white/80'
                                     : p.n ? 'text-ink-faint' : 'text-warn/60'}`}>
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
        </Section>

        {/* ── 题型 ── */}
        <Section title="题型" open={open.types} onToggle={() => flip('types')}
          right={type && <button onClick={() => setType('')}
            className="text-[10.5px] text-brand-ink hover:underline">清空</button>}>
          <div className="flex flex-wrap gap-1.5">
            {(facets?.types || []).map((t) => (
              <Chip key={t.value} n={t.n} on={type === t.value}
                onClick={() => setType(type === t.value ? '' : t.value)}>{t.label}</Chip>
            ))}
          </div>
        </Section>

        {/* ── 难度 ── */}
        <Section title="难度" open={open.diff} onToggle={() => flip('diff')}
          right={diffs.length > 0 && <button onClick={() => setDiffs([])}
            className="text-[10.5px] text-brand-ink hover:underline">清空</button>}>
          <div className="flex flex-wrap gap-1.5">
            {(facets?.difficulties || []).map((d) => (
              <Chip key={d.value} n={d.n} on={diffs.includes(d.value)} onClick={() => toggleDiff(d.value)}
                title="由主考点派生；手动改过的以手动的为准">
                <span className="tracking-tight">{'★'.repeat(DIFF_STARS[d.value] || 0)}</span>
                <span className="ml-1 text-[11px]">{d.value.replace('题', '')}</span>
              </Chip>
            ))}
          </div>
          <div className="mt-1.5 text-[10.5px] leading-snug text-ink-faint">
            由主考点派生；手动改过的以手动的为准
          </div>
        </Section>

        {/* ── 完整度：治「不知道哪些题是半成品」 ── */}
        <Section title="完整度" open={open.flags} onToggle={() => flip('flags')}>
          {/* 一键：「没解析也没答案」。这是**最常用的一个视角**——
              它出来的就是还没做的题（求解器的活）。 */}
          <button onClick={() => {
              const on = missing.length === 2 && missing.includes('答案') && missing.includes('解析')
              setMissing(on ? [] : ['答案', '解析'])
            }}
            className={`press mb-2.5 flex w-full items-center gap-1.5 rounded-lg border px-2.5 py-2
                        text-left text-[12px] font-medium transition-colors ${
              missing.includes('答案') && missing.includes('解析') && missing.length === 2
                ? 'border-warn-line bg-warn-soft text-warn'
                : 'border-border bg-bg text-ink-soft hover:border-warn-line hover:text-warn'}`}>
            <TriangleAlert size={13} className="shrink-0" />
            没解析也没答案
            <span className="ml-auto text-[10.5px] font-normal opacity-70">还没做</span>
          </button>

          <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">只看有</div>
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {FLAG_KEYS.map(([k, label]) => (
              <Chip key={k} size="sm" on={has.includes(k)} onClick={() => toggleHas(k)}>{label}</Chip>
            ))}
          </div>

          <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">只看缺</div>
          <div className="flex flex-wrap gap-1.5">
            {FLAG_KEYS.map(([k, label]) => (
              <Chip key={k} size="sm" on={missing.includes(k)} onClick={() => toggleMissing(k)}>{label}</Chip>
            ))}
          </div>
          <div className="mt-1.5 text-[10.5px] leading-snug text-ink-faint">
            同时选多个「缺」，表示<b className="font-medium text-ink-soft">这些全都缺</b>
          </div>
        </Section>

        {/* ── 年份：四五十个，用密排的数字格而不是长胶囊 ── */}
        <Section title="年份" open={open.years} onToggle={() => flip('years')}
          hint={years.length ? `已选 ${years.length}` : ''}
          right={years.length > 0 && <button onClick={() => setYears([])}
            className="text-[10.5px] text-brand-ink hover:underline">清空</button>}>
          <div className="flex flex-wrap gap-[3px]">
            {(facets?.years || []).map((y) => {
              const on = years.includes(y.value)
              return (
                <button key={y.value} onClick={() => toggleYear(y.value)}
                  title={`${y.value} 年 · ${y.n} 道`}
                  className={`tnum press rounded-md px-1.5 py-[3px] text-[11px] transition-colors ${
                    on ? 'bg-brand font-medium text-white'
                       : 'bg-muted text-ink-soft hover:bg-brand-soft hover:text-brand-ink'}`}>
                  {y.value}
                </button>
              )
            })}
          </div>
        </Section>

        {/* ── 排序 ── */}
        <Section title="排序" open={open.sort} onToggle={() => flip('sort')}>
          <div className="flex flex-wrap gap-1.5">
            {SORTS.map(([v, label]) => (
              <Chip key={v || 'raw'} size="sm" on={sort === v} onClick={() => setSort(v as any)}>{label}</Chip>
            ))}
          </div>
        </Section>
      </div>

      {/* ── 清空：常驻在底部，不跟着滚动跑掉 ── */}
      {activeFilters > 0 && (
        <div className="anim-fade-up shrink-0 border-t border-border p-2.5">
          <button onClick={() => {
              setHas([]); setMissing([]); setPoints([]); setDiffs([])
              setType(''); setKind(''); setYears([])
            }}
            className="press w-full rounded-lg border border-border bg-bg py-1.5 text-[12px]
                       text-ink-soft transition-colors hover:border-warn-line hover:bg-warn-soft hover:text-warn">
            清除全部筛选（{activeFilters}）
          </button>
        </div>
      )}
      {/* 全部考点都是 0 题的年份格会挤满面板；给一个总数兜底，方便核对 */}
      <div className="shrink-0 border-t border-border px-3 py-1.5 text-[10.5px] text-ink-faint">
        共 {allIds.length} 个考点 · 已选 {points.length}
      </div>
    </aside>
  )
}
