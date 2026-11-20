/** 筛选条：**一行**放完全部筛选维度，可整体收起。
 *
 *  早先是左侧抽屉（维度藏起来看不见）、后来是平铺多行（展开后占掉半屏），
 *  两种都不对：老师找题时想「一眼看到现在筛了什么」，但不想为此让出列表高度。
 *  所以做成一行下拉：
 *   · 每个维度一颗按钮，按钮上直接写着当前选了什么（「难度 · 难」「年份 · 2026」）；
 *   · 点开才出胶囊，选完自动收起；
 *   · 一行放不下就横向滚动，**永远不换行**；
 *   · 右边「收起」可以把整条藏掉，表头上留一颗「筛选」随时叫回来。
 *
 *  知识点不在这里：考点树在左侧面板（表头「知识点」按钮），含并集/交集。
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  ArrowUpDown, BarChart3, CalendarDays, ChevronDown, CircleAlert, Filter,
  ListFilter, RotateCcw, Star, Tags, X,
} from 'lucide-react'
import type { useQuestionList } from '@/lib/useQuestionList'
import { DIFF_STARS } from '@/lib/display'
import { Num } from '@/app/ui'
import { loadPresets, savePresets, type FilterPreset } from '@/lib/filterPresets'

type L = ReturnType<typeof useQuestionList>

const SCOPE_LABEL: Record<string, string> = {
  single: '有地区/卷别', multi: '跨省', unknown: '地区未知', book: '专题书',
}
const PAPER_LABEL: Record<string, string> = { complete: '完整卷', partial: '试卷节选' }
const STAR_LABEL: Record<string, string> = { rated: '已评级', unrated: '未评级' }
const QUALITY_LABEL: Record<string, string> = { dup: '同型/重复题', lowres: '低清图' }
const ASRC_LABEL: Record<string, string> = {
  human: '人工改过', workbuddy: '模型生成', legacy: '历史存量', 无: '未登记',
}
const REVIEW_LABEL: Record<string, string> = { yes: '已审', no: '未审' }
const SORTS: [string, string][] = [
  ['used', '频次 高→低'],
  ['year', '年份 新→旧'], ['year2', '年份 旧→新'],
  ['diff', '易 → 难'], ['diff2', '难 → 易'],
  ['raw', '题库原序'], ['new', '最新录入'], ['old', '最早录入'], ['solved', '刚解出的'],
]

/** 胶囊。 */
function Chip({ on, onClick, title, children }: {
  on: boolean; onClick: () => void; title?: string; children: React.ReactNode
}) {
  return (
    <button type="button" onClick={onClick} title={title}
      className={`press rounded-full px-2 py-[2px] text-[11px] transition-colors ${
        on ? 'bg-brand font-medium text-white'
           : 'bg-muted text-ink-soft hover:bg-brand-soft hover:text-brand-ink'}`}>
      {children}
    </button>
  )
}

/** 组内小标题（地区 / 试卷 / 评级…）。 */
function Mini({ children }: { children: React.ReactNode }) {
  return <div className="mb-1 mt-1.5 text-[10px] font-semibold text-ink-faint first:mt-0">{children}</div>
}

/** 一行里的下拉：按钮 + 浮层。
 *
 *  浮层用 **portal + fixed** 挂到 body：筛选条本身是 `overflow-x-auto`
 *  （一行放不下要横滚），绝对定位的浮层会被那个滚动容器裁掉——实测点开
 *  「难度」什么都不出现。挂到 body 后既不被裁，也不会把条撑高。
 */
function Drop({ icon, label, count, active, children, width = 280, align = 'left' }: {
  icon: React.ReactNode
  label: string
  count?: number
  active?: boolean
  children: (close: () => void) => React.ReactNode
  width?: number
  align?: 'left' | 'right'
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const btnRef = useRef<HTMLButtonElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const r = btnRef.current?.getBoundingClientRect()
      if (!r) return
      const left = align === 'right' ? r.right - width : r.left
      setPos({
        top: Math.min(r.bottom + 4, window.innerHeight - 120),
        left: Math.max(8, Math.min(left, window.innerWidth - width - 8)),
      })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open, align, width])

  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => {
      const t = e.target as Node
      if (btnRef.current?.contains(t) || boxRef.current?.contains(t)) return
      setOpen(false)
    }
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', h)
    document.addEventListener('keydown', k)
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k) }
  }, [open])

  return (
    <>
      <button ref={btnRef} onClick={() => setOpen((v) => !v)}
        className={`press flex h-[26px] max-w-[220px] shrink-0 items-center gap-1 whitespace-nowrap
                    rounded-lg border px-2 text-[11.5px] transition-colors ${active
                      ? 'border-brand-line bg-brand-soft text-brand-ink'
                      : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:text-ink'}`}>
        {icon}
        <span className="truncate">{label}</span>
        {!!count && (
          <span className="tnum ml-0.5 shrink-0 rounded-full bg-brand px-1 text-[9.5px]
                           font-medium leading-[14px] text-white">{count}</span>
        )}
        <ChevronDown size={10} className={`shrink-0 opacity-60 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && createPortal(
        <div ref={boxRef} style={{ top: pos.top, left: pos.left, width }}
          className="fixed z-[60] max-h-[60vh] overflow-y-auto rounded-xl border border-border
                     bg-surface p-2 shadow-[var(--shadow-pop)]">
          {children(() => setOpen(false))}
        </div>, document.body)}
    </>
  )
}

export default function FilterBar({ L, total, loading, onHide }: {
  L: L
  total: number
  loading: boolean
  /** 把整条收起来（表头会留一颗「筛选」叫回来）。 */
  onHide: () => void
}) {
  const [srcKw, setSrcKw] = useState('')
  const [presets, setPresets] = useState<FilterPreset[]>(() => loadPresets())
  const [presetName, setPresetName] = useState('')

  const f = L.facets
  const diffs = f?.difficulties || []
  const types = f?.types || []
  const kinds = f?.kinds || []
  const years = f?.years || []
  const allSources = (f?.sources || []).filter((x) => x.n > 0)
  const topSources = allSources.slice(0, 8)
  const srcMatches = srcKw.trim()
    ? allSources.filter((x) => x.value.toLowerCase().includes(srcKw.trim().toLowerCase())).slice(0, 60)
    : topSources

  const savePreset = () => {
    const name = presetName.trim()
    if (!name) return
    const p: FilterPreset = {
      name, at: new Date().toISOString(), filters: L.snapshotFilters(), sort: L.sort,
    }
    const next = [p, ...loadPresets().filter((x) => x.name !== name)]
    savePresets(next); setPresets(next); setPresetName('')
  }
  const delPreset = (name: string) => {
    const next = loadPresets().filter((x) => x.name !== name)
    savePresets(next); setPresets(next)
  }

  /** 按钮上的当前值摘要。 */
  const diffText = L.diffs.length
    ? L.diffs.map((d) => d.replace('题', '')).join('/')
    : ''
  const typeText = [L.type && (f?.types || []).find((t) => t.value === L.type)?.label.replace('题', ''),
                    L.kind && L.kind.replace('题', '')].filter(Boolean).join(' · ')
  const flagCount = L.missing.length + L.has.length + (L.incomplete ? 1 : 0)
  const yearText = L.years.length ? L.years.join('/') : ''
  const srcText = L.sources.length ? (L.sources.length === 1 ? L.sources[0] : `${L.sources.length} 个卷`) : ''
  const paperCount = L.scopes.length + L.paperStates.length
  const qualityCount = L.starStates.length + L.qualities.length + L.answerSources.length + (L.reviewed ? 1 : 0)

  return (
    <div className="flex h-[34px] shrink-0 items-center gap-1.5 border-b border-border bg-surface px-3">
      <span className="flex shrink-0 items-center gap-1 pr-0.5 text-[10.5px] text-ink-faint">
        <Filter size={11} />筛选
      </span>

      {/* 一行放不下就横滚，**永远不换行** */}
      <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto
                      [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <Drop icon={<BarChart3 size={11} />} count={L.diffs.length}
          label={diffText ? `难度 · ${diffText}` : '难度'} active={!!L.diffs.length} width={330}>
          {() => (
            <div className="flex flex-wrap gap-1.5">
              <Chip on={!L.diffs.length} onClick={() => L.setDiffs([])}>全部</Chip>
              {diffs.map((d) => (
                <Chip key={d.value} on={L.diffs.includes(d.value)} onClick={() => L.toggleDiff(d.value)}
                  title={`${d.value} · ${d.n} 道`}>
                  <span className="tracking-tight">{'★'.repeat(DIFF_STARS[d.value] || 0)}</span>
                  <span className="ml-1">{d.value.replace('题', '')}</span>
                  <span className={`ml-1.5 text-[9.5px] tabular-nums ${L.diffs.includes(d.value) ? 'opacity-70' : 'text-ink-faint'}`}>
                    <Num value={d.n} />
                  </span>
                </Chip>
              ))}
            </div>
          )}
        </Drop>

        <Drop icon={<ListFilter size={11} />} count={(L.type ? 1 : 0) + (L.kind ? 1 : 0)}
          label={typeText || '题型'} active={!!(L.type || L.kind)} width={320}>
          {() => (
            <>
              <Mini>题型</Mini>
              <div className="flex flex-wrap gap-1.5">
                <Chip on={!L.type} onClick={() => L.setType('')}>全部</Chip>
                {types.map((t) => (
                  <Chip key={t.value} on={L.type === t.value}
                    onClick={() => L.setType(L.type === t.value ? '' : t.value)}
                    title={`${t.label} · ${t.n} 道`}>
                    {t.label.replace('题', '')}
                    <span className={`ml-1.5 text-[9.5px] tabular-nums ${L.type === t.value ? 'opacity-70' : 'text-ink-faint'}`}>
                      <Num value={t.n} />
                    </span>
                  </Chip>
                ))}
              </div>
              <Mini>类别</Mini>
              <div className="flex flex-wrap gap-1.5">
                <Chip on={!L.kind} onClick={() => L.setKind('')}>全部</Chip>
                {kinds.map((k) => (
                  <Chip key={k.value} on={L.kind === k.value}
                    onClick={() => L.setKind(L.kind === k.value ? '' : k.value)}
                    title={`${k.value} · ${k.n} 道`}>
                    {k.value.replace('题', '')}
                  </Chip>
                ))}
              </div>
            </>
          )}
        </Drop>

        <Drop icon={<CircleAlert size={11} />} count={flagCount}
          label={L.incomplete ? '完整度 · 待补' : '完整度'} active={flagCount > 0}>
          {() => (
            <div className="flex flex-wrap gap-1.5">
              <Chip on={!flagCount} onClick={() => {
                L.setMissing([]); L.setHas([]); L.setIncomplete(false)
              }}>全部</Chip>
              {/* 「待补」= 缺答案**或**缺解析；`missing` 是"两样都缺"。 */}
              <Chip on={L.incomplete} onClick={() => L.setIncomplete(!L.incomplete)}
                title="缺答案或缺解析（任一不全）——导出前先看这一批">待补</Chip>
              <Chip on={L.missing.includes('答案')} onClick={() => L.toggleMissing('答案')}>缺答案</Chip>
              <Chip on={L.missing.includes('解析')} onClick={() => L.toggleMissing('解析')}>缺解析</Chip>
              <Chip on={L.missing.includes('标签')} onClick={() => L.toggleMissing('标签')}>缺考点</Chip>
              <Chip on={L.has.includes('有图')} onClick={() => L.toggleHas('有图')}>有图</Chip>
            </div>
          )}
        </Drop>

        <Drop icon={<CalendarDays size={11} />} count={L.years.length}
          label={yearText ? `年份 · ${yearText}` : '年份'} active={!!L.years.length} width={300}>
          {() => (
            <div className="flex flex-wrap gap-1.5">
              <Chip on={!L.years.length} onClick={() => L.setYears([])}>全部</Chip>
              {years.map((y) => (
                <Chip key={y.value} on={L.years.includes(y.value)}
                  onClick={() => L.toggleYear(y.value)} title={`${y.value} 年 · ${y.n} 道`}>
                  {y.value}
                </Chip>
              ))}
            </div>
          )}
        </Drop>

        <Drop icon={<Tags size={11} />} count={L.sources.length}
          label={srcText ? `出处 · ${srcText}` : '出处'} active={!!L.sources.length} width={340}>
          {() => (
            <>
              <input value={srcKw} onChange={(e) => setSrcKw(e.target.value)}
                placeholder={`搜卷名（共 ${allSources.length} 个）`}
                className="mb-1.5 h-[26px] w-full rounded-lg border border-border bg-bg px-2 text-[11px]
                           outline-none placeholder:text-ink-faint focus:border-brand-line focus:bg-surface" />
              <div className="flex max-h-[240px] flex-wrap gap-1.5 overflow-y-auto">
                <Chip on={!L.sources.length} onClick={() => L.setSources([])}>全部</Chip>
                {srcMatches.map((s) => (
                  <Chip key={s.value} on={L.sources.includes(s.value)}
                    onClick={() => L.toggleSource(s.value)} title={`${s.value} · ${s.n} 道`}>
                    <span className="max-w-[18ch] truncate align-bottom">{s.value}</span>
                    <span className={`ml-1.5 text-[9.5px] tabular-nums ${L.sources.includes(s.value) ? 'opacity-70' : 'text-ink-faint'}`}>
                      {s.n}
                    </span>
                  </Chip>
                ))}
                {!srcMatches.length && (
                  <span className="px-1 py-1 text-[11px] text-ink-faint">没有匹配的卷名</span>
                )}
              </div>
            </>
          )}
        </Drop>

        <Drop icon={<Filter size={11} />} count={paperCount}
          label="试卷" active={paperCount > 0} width={320}>
          {() => (
            <>
              <Mini>地区</Mini>
              <div className="flex flex-wrap gap-1.5">
                <Chip on={!L.scopes.length} onClick={() => L.setScopes([])}>全部</Chip>
                {(f?.region_scopes || []).map((x) => (
                  <Chip key={x.value} on={L.scopes.includes(x.value)} onClick={() => L.toggleScope(x.value)}
                    title={`${SCOPE_LABEL[x.value] || x.value} · ${x.n} 道`}>
                    {SCOPE_LABEL[x.value] || x.value}
                  </Chip>
                ))}
              </div>
              <Mini>试卷</Mini>
              <div className="flex flex-wrap gap-1.5">
                <Chip on={!L.paperStates.length} onClick={() => L.setPaperStates([])}>全部</Chip>
                {(f?.paper_states || []).map((x) => (
                  <Chip key={x.value} on={L.paperStates.includes(x.value)} onClick={() => L.togglePaper(x.value)}
                    title={`${PAPER_LABEL[x.value] || x.value} · ${x.n} 道`}>
                    {PAPER_LABEL[x.value] || x.value}
                  </Chip>
                ))}
              </div>
            </>
          )}
        </Drop>

        <Drop icon={<Star size={11} />} count={qualityCount}
          label="质量" active={qualityCount > 0} width={330}>
          {() => (
            <>
              <Mini>评级</Mini>
              <div className="flex flex-wrap gap-1.5">
                <Chip on={!L.starStates.length} onClick={() => L.setStarStates([])}>全部</Chip>
                {(f?.star_states || []).map((x) => (
                  <Chip key={x.value} on={L.starStates.includes(x.value)} onClick={() => L.toggleStar(x.value)}
                    title={`${STAR_LABEL[x.value] || x.value} · ${x.n} 道`}>
                    {STAR_LABEL[x.value] || x.value}
                  </Chip>
                ))}
                {(f?.qualities || []).map((x) => (
                  <Chip key={x.value} on={L.qualities.includes(x.value)} onClick={() => L.toggleQuality(x.value)}>
                    {QUALITY_LABEL[x.value] || x.value}
                  </Chip>
                ))}
              </div>
              <Mini>答案来源</Mini>
              <div className="flex flex-wrap gap-1.5">
                <Chip on={!L.answerSources.length} onClick={() => L.setAnswerSources([])}>全部</Chip>
                {(f?.answer_sources || []).map((x) => (
                  <Chip key={x.value} on={L.answerSources.includes(x.value)}
                    onClick={() => L.toggleAnswerSource(x.value)}>
                    {ASRC_LABEL[x.value] || x.value}
                  </Chip>
                ))}
              </div>
              <Mini>复核</Mini>
              <div className="flex flex-wrap gap-1.5">
                <Chip on={!L.reviewed} onClick={() => L.setReviewed('')}>全部</Chip>
                {(f?.reviewed_states || []).map((x) => (
                  <Chip key={x.value} on={L.reviewed === x.value}
                    onClick={() => L.setReviewed(L.reviewed === x.value ? '' : x.value)}>
                    {REVIEW_LABEL[x.value] || x.value}
                  </Chip>
                ))}
              </div>
            </>
          )}
        </Drop>
      </div>

      {/* 排序与「我的筛选」放在右端固定位：不进横滚区，随时点得到 */}
      <Drop icon={<ArrowUpDown size={11} />} label={SORTS.find(([v]) => v === L.sort)?.[1] || '排序'}
        align="right" width={190}>
        {() => (
          <div className="space-y-[2px]">
            {SORTS.map(([v, label]) => (
              <button key={v || 'raw'} onClick={() => L.setSort(v as typeof L.sort)}
                className={`flex w-full items-center gap-1.5 rounded-md px-2 py-[4px] text-left text-[11.5px] ${
                  L.sort === v ? 'bg-brand text-white' : 'text-ink-soft hover:bg-muted'}`}>
                {label}
              </button>
            ))}
          </div>
        )}
      </Drop>

      <Drop icon={<Star size={11} />} label={`我的筛选${presets.length ? ` · ${presets.length}` : ''}`}
        align="right" width={250}>
        {() => (
          <>
            <div className="flex gap-1.5">
              <input value={presetName} onChange={(e) => setPresetName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') savePreset() }}
                placeholder="给这套筛选起个名…"
                className="h-[26px] min-w-0 flex-1 rounded-lg border border-border bg-bg px-2 text-[11px]
                           outline-none placeholder:text-ink-faint focus:border-brand-line" />
              <button onClick={savePreset} disabled={!presetName.trim()}
                className="press h-[26px] shrink-0 rounded-lg border border-brand-line bg-brand-soft px-2
                           text-[11px] font-medium text-brand-ink disabled:border-border disabled:bg-muted
                           disabled:text-ink-faint">存下</button>
            </div>
            <div className="mt-1.5 space-y-[2px]">
              {!presets.length && (
                <div className="px-1 py-1 text-[10.5px] text-ink-faint">还没存过筛选组合</div>
              )}
              {presets.map((p) => (
                <div key={p.name} className="group flex items-center gap-1 rounded hover:bg-muted">
                  <button onClick={() => { L.loadFilters(p.filters, p.sort); setPresetName('') }}
                    title="恢复这套筛选（从第 1 页开始）"
                    className="min-w-0 flex-1 truncate px-1.5 py-[3px] text-left text-[11px] text-ink-soft hover:text-brand-ink">
                    {p.name}
                  </button>
                  <button onClick={() => delPreset(p.name)} title="删除预设"
                    className="grid h-5 w-5 shrink-0 place-items-center rounded text-ink-faint
                               opacity-40 hover:bg-warn-soft hover:text-warn group-hover:opacity-100">
                    <X size={11} />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </Drop>

      {/* 右侧：条件数 · 结果数 · 清空 · 收起整条 */}
      {L.activeFilters > 0 && (
        <span className="flex shrink-0 items-center gap-1 text-[10.5px] text-ink-faint">
          <span className="tnum font-medium text-brand-ink">{L.activeFilters}</span> 项
          <span className="opacity-60">·</span>
          {loading ? <span>筛选中…</span> : <><span className="tnum">{total}</span> 道</>}
          <button onClick={() => L.loadFilters({ ...L.snapshotFilters(), point: '', pm: '' } as never, L.sort)}
            title="清空筛选（保留排序）"
            className="press ml-0.5 rounded p-[2px] hover:bg-muted hover:text-ink">
            <RotateCcw size={11} />
          </button>
        </span>
      )}
      <button onClick={onHide} title="收起筛选条（表头「筛选」可叫回来）"
        className="press ml-0.5 grid h-[22px] w-[22px] shrink-0 place-items-center rounded-md
                   text-ink-faint hover:bg-muted hover:text-ink">
        <X size={13} />
      </button>
    </div>
  )
}
