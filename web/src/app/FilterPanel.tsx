/** 题目筛选面板（内容区最左那一列，可收起）。
 *
 *  从 App.tsx 搬出来的。搬动本身就有意义：这一块是「筛什么」的**全部**，
 *  和「列出来什么」「选中哪道」没有一行交互，混在一个 1000 行的组件里
 *  只会让每次改筛选都要重读整个 App。
 *
 *  和旧版的差别不只是搬家：
 *  ① 各个筛选维度从**弹层**改成**平铺**。弹层的问题是选之前看不见有什么，
 *     选完也看不见还选了什么；平铺以后一屏之内全部可见，点击次数减半。
 *  ② 每个维度可折叠，章节树/年份默认展开、排序收起——常看的在上。
 *  ③ 选中的东西统一走「实心胶囊」，一屏里哪几个是活的，一眼可数。
 */
import { useEffect, useState } from 'react'
import { ListFilter, X, ChevronRight } from 'lucide-react'
import type { useQuestionList } from '@/lib/useQuestionList'
import { DIFF_STARS } from '@/lib/display'
import { groupTree } from '@/app/Stats'
import { Chip, Section, FLAG_KEYS } from '@/app/ui'
import { FILTER_PRESETS_KEY, loadPresets, savePresets, type FilterPreset } from '@/lib/filterPresets'

/** 栏宽。**导出**：布局预算要算「还剩多少给列表」（见 App 的 drawerMax）。 */
export const FILTER_W = 252

type L = ReturnType<typeof useQuestionList>

const SCOPE_LABEL: Record<string, string> = {
  single: '有地区/卷别', multi: '跨省', unknown: '地区未知', book: '专题书',
}
const PAPER_LABEL: Record<string, string> = { complete: '完整卷', partial: '试卷节选' }
const STAR_LABEL: Record<string, string> = { rated: '已评级', unrated: '未评级' }
const QUALITY_LABEL: Record<string, string> = { dup: '重复题', lowres: '低清图' }
const ASRC_LABEL: Record<string, string> = {
  human: '人工改过', workbuddy: '模型生成', legacy: '历史存量', 无: '未登记',
}
const REVIEW_LABEL: Record<string, string> = { yes: '已复核', no: '未复核' }

const SORTS: [string, string][] = [
  ['used', '频次 高→低'],
  ['year', '年份 新→旧'], ['year2', '年份 旧→新'],
  ['diff', '易 → 难'], ['diff2', '难 → 易'],
  ['', '题库原序'], ['new', '最新录入'], ['old', '最早录入'], ['solved', '刚解出的'],
]

export default function FilterPanel({ L, onClose }: { L: L; onClose?: () => void }) {
  const {
    facets, q, setQ, type, setType, kind, setKind,
    has, setHas, missing, setMissing, points, setPoints, diffs, setDiffs,
    sources, setSources,
    years, setYears, sort, setSort, openTopics, setOpenTopics,
    scopes, setScopes, paperStates, setPaperStates,
    starStates, setStarStates, qualities, setQualities,
    answerSources, toggleAnswerSource, reviewed, setReviewed,
    setPointSource,
    toggleYear, toggleHas, toggleMissing, togglePoint, toggleDiff,
    toggleSource,
    toggleScope, togglePaper, toggleStar, toggleQuality,
    togglePoints, toggleTopic, activeFilters, scopeName,
    snapshotFilters, loadFilters,
  } = L

  // 折叠状态记忆：老师会固定一种看惯的顺序，不该每次打开都回到默认
  const [open, setOpen] = useState<Record<string, boolean>>(() => {
    try {
      const s = localStorage.getItem('amtiku.filter.sections.v2')
      if (s) return JSON.parse(s)
    } catch { /* 存坏了就用默认，不阻断界面 */ }
    return { points: true, types: true, diff: true, src: true,
             flags: true, years: true, sort: false }
  })
  useEffect(() => {
    localStorage.setItem('amtiku.filter.sections.v2', JSON.stringify(open))
  }, [open])
  const flip = (k: string) => setOpen((o) => ({ ...o, [k]: !o[k] }))

  // 出处的内部搜索词。510 个卷名没法平铺，只列前 8 个常用的；
  // 输入关键词才展开匹配（选中项永远排在最上面，不会"选了就看不见"）。
  // 「我的筛选」：常用组合存 localStorage，一键恢复
  const [presets, setPresets] = useState<FilterPreset[]>(() => loadPresets())
  const [presetName, setPresetName] = useState('')
  // 别的标签页改了预设 → 这一页跟着刷新（否则下次保存会拿旧快照把对方刚存的覆盖掉）
  useEffect(() => {
    const on = (e: StorageEvent) => {
      if (e.key === FILTER_PRESETS_KEY) setPresets(loadPresets())
    }
    window.addEventListener('storage', on)
    return () => window.removeEventListener('storage', on)
  }, [])
  const saveCurrent = () => {
    const name = presetName.trim()
    if (!name) return
    const p: FilterPreset = {
      name, at: new Date().toISOString(), filters: snapshotFilters(), sort,
    }
    // **写之前重读一次**：`presets` 是挂载时的快照，另一个标签页刚存的那几条
    // 不在这里面；直接写回等于把它们删掉。
    const next = [p, ...loadPresets().filter((x) => x.name !== name)]
    setPresets(next); savePresets(next); setPresetName('')
  }
  const applyPreset = (p: FilterPreset) => loadFilters(p.filters, p.sort)
  const delPreset = (name: string) => {
    const next = loadPresets().filter((x) => x.name !== name)
    setPresets(next); savePresets(next)
  }
  const [srcKw, setSrcKw] = useState('')
  const allSources = facets?.sources || []
  const srcList = (() => {
    const kw = srcKw.trim()
    if (kw) return allSources.filter((x) => x.value.includes(kw)).slice(0, 40)
    const chosen = sources.map((v) => allSources.find((x) => x.value === v) || { value: v, n: 0 })
    const rest = allSources.filter((x) => !sources.includes(x.value)).slice(0, 8)
    return [...chosen, ...rest]
  })()

  const tree = groupTree(facets?.points || [])
  const allIds = (facets?.points || []).map((p) => p.value)

  return (
    <aside style={{ width: FILTER_W }}
      className="flex shrink-0 flex-col border-r border-border bg-surface">
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

        {/* ── 类别：高考 / 模拟 ──
            它原先只在左侧导航栏底部的「当前范围」里。但导航会**自动收成图标条**
            （窗口 <1560 且筛选、详情同时开着时），那行「全部/高考/模拟」就变成
            一句不可点的「3 范围」——想筛高考题的人在筛选面板里找一圈也找不到。
            状态仍然只有 `kind` 这一份：这里和导航底部改的是同一件事。 */}
        <Section title="类别" open={open.kind !== false} onToggle={() => flip('kind')}
          hint={kind ? `只看${kind}` : '全部'}
          right={kind && <button onClick={() => setKind('')}
            className="text-[10.5px] text-brand-ink hover:underline">清空</button>}>
          <div className="flex flex-wrap gap-1.5">
            {(facets?.kinds || []).map((k) => (
              <Chip key={k.value} n={k.n} on={kind === k.value}
                title={`只看${k.value}题（共 ${k.n} 道）`}
                onClick={() => setKind(kind === k.value ? '' : k.value)}>{k.value}题</Chip>
            ))}
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

        {/* ── 出处：按卷名筛 ──
            用户报的：「筛选无法筛选出处」。后端早就有 `source=`（`/api/facets`
            也在返回几百个卷名的计数），只是筛选面板从来没把它画出来。
            卷名太长、数量太多，不能像题型那样平铺胶囊：只列前 8 个常用的，
            配一个搜索框。 */}
        <Section title="出处" open={open.src !== false} onToggle={() => flip('src')}
          hint={sources.length ? `已选 ${sources.length}` : `${allSources.length} 个`}
          right={sources.length > 0 && <button onClick={() => setSources([])}
            className="text-[10.5px] text-brand-ink hover:underline">清空</button>}>
          <input value={srcKw} onChange={(e) => setSrcKw(e.target.value)}
            placeholder="搜卷名 / 出处…"
            className="h-[28px] w-full rounded-lg border border-border bg-bg px-2 text-[11.5px]
                       outline-none transition-[border-color,box-shadow] duration-150
                       placeholder:text-ink-faint focus:border-brand-line focus:bg-surface
                       focus:shadow-[0_0_0_3px_var(--color-brand-soft)]" />
          <div className="mt-1.5 max-h-[188px] space-y-[2px] overflow-y-auto pr-0.5">
            {srcList.map((x) => {
              const on = sources.includes(x.value)
              return (
                <button key={x.value} onClick={() => toggleSource(x.value)}
                  title={`${x.value} · ${x.n} 道`}
                  className={`flex w-full items-center gap-1.5 rounded-md px-1.5 py-[3px]
                              text-left text-[11px] transition-colors ${
                    on ? 'bg-brand font-medium text-white'
                       : 'text-ink-soft hover:bg-muted hover:text-ink'}`}>
                  <span className="min-w-0 flex-1 truncate">{x.value}</span>
                  <span className={`tnum shrink-0 text-[10px] ${
                    on ? 'text-white/75' : 'text-ink-faint'}`}>{x.n}</span>
                </button>
              )
            })}
            {!srcList.length && (
              <div className="px-1 py-1 text-[11px] text-ink-faint">没有匹配的出处</div>
            )}
          </div>
          <div className="mt-1.5 text-[10.5px] leading-snug text-ink-faint">
            按卷别精确匹配；找整本书用顶部搜索。
            {srcKw.trim()
              ? `匹配 ${srcList.length} 个${srcList.length >= 40 ? '（只列前 40）' : ''}`
              : '只列前 8 个（按题量），输入关键词可搜全部'}
          </div>
        </Section>

        {/* ── 元数据：地区/试卷完整度/评级/质量 ── */}
        <Section title="元数据" open={open.meta !== false} onToggle={() => flip('meta')}>
          <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">地区</div>
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {(facets?.region_scopes || []).map((x) => (
              <Chip key={x.value} n={x.n} on={scopes.includes(x.value)}
                onClick={() => toggleScope(x.value)}>
                {SCOPE_LABEL[x.value] || x.value}
              </Chip>
            ))}
          </div>
          <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">试卷</div>
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {(facets?.paper_states || []).map((x) => (
              <Chip key={x.value} n={x.n} on={paperStates.includes(x.value)}
                onClick={() => togglePaper(x.value)}>
                {PAPER_LABEL[x.value] || x.value}
              </Chip>
            ))}
          </div>
          <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">答案来源</div>
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {(facets?.answer_sources || []).map((x) => (
              <Chip key={x.value} n={x.n} on={answerSources.includes(x.value)}
                onClick={() => toggleAnswerSource(x.value)}>
                {ASRC_LABEL[x.value] || x.value}
              </Chip>
            ))}
          </div>
          <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">复核</div>
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {(facets?.reviewed_states || []).map((x) => (
              <Chip key={x.value} n={x.n} on={reviewed === x.value}
                onClick={() => setReviewed(reviewed === x.value ? '' : x.value)}>
                {REVIEW_LABEL[x.value] || x.value}
              </Chip>
            ))}
          </div>
          <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">评级 / 质量</div>
          <div className="flex flex-wrap gap-1.5">
            {(facets?.star_states || []).map((x) => (
              <Chip key={x.value} n={x.n} on={starStates.includes(x.value)}
                onClick={() => toggleStar(x.value)}>
                {STAR_LABEL[x.value] || x.value}
              </Chip>
            ))}
            {(facets?.qualities || []).map((x) => (
              <Chip key={x.value} n={x.n} on={qualities.includes(x.value)}
                onClick={() => toggleQuality(x.value)}>
                {QUALITY_LABEL[x.value] || x.value}
              </Chip>
            ))}
          </div>
          <div className="mt-1.5 text-[10.5px] leading-snug text-ink-faint">
            地区按试卷级落盘；跨省/专题书不硬填省；试卷节选是已知的不完整卷
          </div>
        </Section>

        {/* ── 完整度：治「不知道哪些题是半成品」 ── */}
        <Section title="完整度" open={open.flags} onToggle={() => flip('flags')}>
          <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">只看有</div>
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {FLAG_KEYS.map(([k, label, kHas]) => (
              <Chip key={k} size="sm" on={has.includes(kHas)}
                onClick={() => toggleHas(kHas)}>{label}</Chip>
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

        {/* ── 排序 ── */}
        <Section title="排序" open={open.sort} onToggle={() => flip('sort')}>
          <div className="flex flex-wrap gap-1.5">
            {SORTS.map(([v, label]) => (
              <Chip key={v || 'raw'} size="sm" on={sort === v} onClick={() => setSort(v as any)}>{label}</Chip>
            ))}
          </div>
        </Section>

        {/* ── 我的筛选 ──
            老师每天看的就是那几套组合（某本书 + 某章 + 缺解析…）。
            存下来，比每次从头点一遍省事；只进 localStorage，不动题库。 */}
        <Section title="我的筛选" open={open.presets !== false} onToggle={() => flip('presets')}
          hint={presets.length ? `${presets.length} 个` : ''}>
          <div className="flex gap-1.5">
            <input value={presetName} onChange={(e) => setPresetName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveCurrent() }}
              placeholder="给这套筛选起个名…"
              className="h-[28px] min-w-0 flex-1 rounded-lg border border-border bg-bg px-2 text-[11px]
                         outline-none placeholder:text-ink-faint focus:border-brand-line
                         focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]" />
            <button onClick={saveCurrent} disabled={!presetName.trim()}
              title={presetName.trim() ? '把当前搜索词 + 全部筛选存下来' : '先起个名字'}
              className="press h-[28px] shrink-0 rounded-lg border border-brand-line
                         bg-brand-soft px-2 text-[11px] font-medium text-brand-ink
                         disabled:cursor-not-allowed disabled:border-border disabled:bg-muted
                         disabled:text-ink-faint">存下</button>
          </div>
          {presets.length > 0 && (
            <div className="mt-1.5 space-y-[2px]">
              {presets.map((p) => (
                <div key={p.name} className="group flex items-center gap-1 rounded-md hover:bg-muted">
                  <button onClick={() => applyPreset(p)}
                    title="恢复这套筛选（从第 1 页开始）"
                    className="min-w-0 flex-1 truncate px-1.5 py-[3px] text-left text-[11px]
                               text-ink-soft hover:text-brand-ink">{p.name}</button>
                  <button onClick={() => delPreset(p.name)} title="删除预设"
                    className="grid h-5 w-5 shrink-0 place-items-center rounded text-ink-faint
                               opacity-40 hover:bg-warn-soft hover:text-warn group-hover:opacity-100">
                    <X size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="mt-1.5 text-[10.5px] leading-snug text-ink-faint">
            存的是搜索词 + 当前全部筛选条件（不含页码）；点名字即恢复。
          </div>
        </Section>
      </div>

      {/* ── 清空：常驻在底部，不跟着滚动跑掉 ── */}
      {activeFilters > 0 && (
        <div className="anim-fade-up shrink-0 border-t border-border p-2.5">
          <button onClick={() => {
              setHas([]); setMissing([]); setPoints([]); setDiffs([])
              setType(''); setKind(''); setYears([]); setSources([])
              setPointSource('')
              setScopes([]); setPaperStates([]); setStarStates([]); setQualities([])
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
