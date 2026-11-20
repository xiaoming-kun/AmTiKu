/** AI 整理 / 校对 · 选题页。
 *
 *  旧版是一张 310px 的窄卡片，搜索只取 8 条、没有筛选项、也没有分页——
 *  看起来像“最近几道题”，不像题库。这里直接复用题库那套检索与筛选
 *  （`useQuestionList` + `FilterPanel`），把“选题”做成一个真正的全库入口：
 *
 *  · 关键词走同一套 `recall()`（题干 / 公式 / 考点 / 出处 / 字段语法）；
 *  · 筛选、排序、分页与题库完全同源，看到的就是题库里那批题；
 *  · 卡片带考点、出处、完整度、复核/答案来源，选中后直接进校对。
 *
 *  视觉上沿用题库的卡片语言（20px 圆角、题干用 KaTeX），只把“校对”
 *  这一件事的强调色从品牌蓝换成暖琥珀——它来自录入页的校对卡片，
 *  和答案/解析的绿、问题的橙是一套。
 */
import { useEffect, useRef, useState } from 'react'
import {
  ArrowRight, ArrowUpDown, Check, ChevronDown, ChevronLeft, ChevronRight,
  ChevronsLeft, ChevronsRight, Clock3, Flame, Image as ImageIcon, Loader2,
  Search, SearchX, ShieldCheck, SlidersHorizontal, Sparkles, X,
} from 'lucide-react'
import type { Q } from '@/lib/types'
import type { Stage } from '@/lib/stage'
import { STAGE_BY_KEY } from '@/lib/stage'
import type { QuestionList, SortKey } from '@/lib/useQuestionList'
import { EMPTY_FILTERS } from '@/lib/urlState'
import {
  DIFF_STARS, dispPoint, hasImageOptions, optionRange, starsLabel,
} from '@/lib/display'
import { Highlight, renderBlocks } from '@/lib/render'
import FilterPanel from '@/app/FilterPanel'
import { Flags, Num, useFlag } from '@/app/ui'

const SEARCH_HISTORY_KEY = 'ammath.proof.search.history.v1'

const SORTS: { value: SortKey; label: string }[] = [
  { value: 'used', label: '频次 高→低' },
  { value: 'new', label: '最新录入' },
  { value: 'old', label: '最早录入' },
  { value: 'year', label: '年份 新→旧' },
  { value: 'year2', label: '年份 旧→新' },
  { value: 'diff', label: '难度 易→难' },
  { value: 'diff2', label: '难度 难→易' },
  { value: 'solved', label: '最近解出' },
  { value: 'raw', label: '题库原序' },
]

const ASRC_LABEL: Record<string, string> = {
  workbuddy: '模型答案', human: '人工答案', legacy: '历史答案', 无: '来源未记',
}
const REVIEW_LABEL: Record<string, string> = {
  stale: '复核过期', needs_fix: '待修正', flagged: '已标疑',
}
const SCOPE_LABEL: Record<string, string> = {
  single: '有地区/卷别', multi: '跨省', unknown: '地区未知', book: '专题书',
}
const PAPER_LABEL: Record<string, string> = { complete: '完整卷', partial: '试卷节选' }
const STAR_LABEL: Record<string, string> = { rated: '已评级', unrated: '未评级' }
const QUALITY_LABEL: Record<string, string> = { dup: '同型/重复题', lowres: '低清图' }

function readHistory(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(SEARCH_HISTORY_KEY) || '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(0, 8) : []
  } catch { return [] }
}

function answerPreview(ans: string): string {
  const s = (ans || '').trim()
  if (!s) return '缺答案'
  if (/^[A-D]{1,6}$/.test(s)) return s
  if (s.includes('见解析')) return '见解析'
  return '已收录'
}

/** 卡片右栏的一行状态：答案 / 解析 / 配图。缺的用暖色，一眼看到。 */
function Field({ label, value, tone }: {
  label: string; value: React.ReactNode; tone: 'ok' | 'warn' | 'muted'
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="shrink-0 text-ink-faint">{label}</span>
      <span className={`min-w-0 flex-1 truncate text-right font-medium ${
        tone === 'ok' ? 'text-has' : tone === 'warn' ? 'text-warn' : 'text-ink-faint'}`}>
        {value}
      </span>
    </div>
  )
}

function Tag({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <span title={title}
      className="inline-flex items-center rounded-md bg-muted px-1.5 py-[1px] text-[10.5px]
                 font-medium text-ink-soft">
      {children}
    </span>
  )
}

function ProofCard({ q, kw, active, picking, onPick }: {
  q: Q; kw: string; active: boolean; picking: boolean; onPick: () => void
}) {
  const points = q.point_titles || []
  const src = q.meta?.source_label || q.meta?.book || ''
  const year = q.meta?.year || ''
  const stars = DIFF_STARS[q.difficulty] || q.stars || 0
  const hasAns = !!q.flags?.['答案']
  const hasSol = !!q.flags?.['解析']
  const figN = q.figures?.length || 0
  const imgOpts = hasImageOptions(q)
  const review = REVIEW_LABEL[q.review?.status || ''] || ''
  const modelAns = q.meta?.answer_source === 'workbuddy'
  const kwTrim = kw.trim()
  const kwl = kwTrim.toLowerCase()
  const keyHit = !!kwl && String(q.key || '').toLowerCase().includes(kwl)
  const srcHit = !!kwl && [q.meta?.book, q.meta?.source_label, q.meta?.region]
    .some((x) => String(x || '').toLowerCase().includes(kwl))
  const ptHit = !!kwl && (q.point_titles || [])
    .some((x) => String(x || '').toLowerCase().includes(kwl))
  const optHit = !!kwl && (q.options || [])
    .some((x) => String(x?.text || '').toLowerCase().includes(kwl))
  const stemHit = !!kwl && String(q.stem || '').toLowerCase().includes(kwl)
  const visibleHit = srcHit || ptHit || optHit || stemHit || keyHit
  const deepHit = !!kwl && !visibleHit
    && [q.answer, q.solution].some((x) => String(x || '').toLowerCase().includes(kwl))
  const keyOnlyHit = keyHit && !srcHit && !ptHit && !optHit && !stemHit

  const open = () => { if (!picking) onPick() }

  return (
    <article
      data-qkey={q.key}
      data-on={active ? '1' : '0'}
      role="button"
      tabIndex={0}
      aria-label={`选择题目 ${q.key} 进入校对`}
      onClick={open}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() }
      }}
      className="@container question-card card-lift group relative cursor-pointer overflow-hidden
                 rounded-[20px] border border-border outline-none
                 focus-visible:ring-2 focus-visible:ring-brand/35"
    >
      <div className="flex flex-col gap-3 p-4 @[880px]:flex-row @[880px]:gap-5">
        {/* ── 题干区 ─────────────────────────────────────── */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
            {points.length ? points.slice(0, 2).map((t, i) => (
              <span key={i} title={points.map(dispPoint).join('、')}
                className={`shrink-0 rounded-full px-1.5 py-[1px] font-medium ${
                  i === 0 ? 'bg-brand-soft text-brand-ink' : 'bg-muted text-ink-soft'}`}>
                {i === 0 && <span className="mr-0.5 text-[9px] font-normal opacity-60">主</span>}
                <Highlight text={dispPoint(t)} kw={kwTrim} />
              </span>
            )) : (
              <span className="shrink-0 rounded-full bg-warn-soft px-1.5 py-[1px] font-medium text-warn">
                无考点
              </span>
            )}
            {points.length > 2 && (
              <span className="shrink-0 text-[10px] text-ink-faint">+{points.length - 2}</span>
            )}
            {src && (
              <span className="min-w-0 max-w-[26ch] truncate text-ink-faint" title={src}>
                <Highlight text={src} kw={kwTrim} />
              </span>
            )}
            {!!year && !src.includes(String(year)) && (
              <span className="shrink-0 text-ink-faint">{year} 年</span>
            )}
            {!!q.used && (
              <span className="ml-auto flex shrink-0 items-center gap-0.5 text-warn" title={`被导出 ${q.used} 次`}>
                <Flame size={10} />{q.used}
              </span>
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Tag>{q.type_label}</Tag>
            <Tag>{q.kind}题</Tag>
            <Tag title={stars ? `难度：${q.difficulty}` : '星级未评级'}>
              <span className={stars ? 'text-warn' : 'text-ink-faint'}>{starsLabel(stars)}</span>
              {stars > 0 && <span className="ml-0.5">{q.difficulty?.replace('题', '')}</span>}
            </Tag>
            {modelAns && (
              <span className="inline-flex items-center gap-0.5 rounded-md bg-warn-soft px-1.5 py-[1px]
                               text-[10.5px] font-medium text-warn" title="答案由模型生成，建议优先校对">
                模型答案
              </span>
            )}
            {review && (
              <span className="inline-flex items-center gap-0.5 rounded-md bg-warn-soft px-1.5 py-[1px]
                               text-[10.5px] font-medium text-warn">{review}</span>
            )}
            {q.flags?.['存疑'] && (
              <span className="inline-flex items-center gap-0.5 rounded-md bg-warn-soft px-1.5 py-[1px]
                               text-[10.5px] font-medium text-warn">存疑</span>
            )}
            {keyOnlyHit && (
              <span className="inline-flex items-center rounded-md bg-brand-soft px-1.5 py-[1px]
                               text-[10.5px] font-medium text-brand-ink"
                title="关键词匹配题号">
                题号命中
              </span>
            )}
            {deepHit && (
              <span className="inline-flex items-center rounded-md bg-brand-soft px-1.5 py-[1px]
                               text-[10.5px] font-medium text-brand-ink"
                title="关键词出现在答案或解析里，不在题干/考点/出处中">
                答案/解析命中
              </span>
            )}
            {q.meta?.figure_low_res && <Tag title="配图宽度小于 400px">低清图</Tag>}
            <Flags flags={q.flags} type={q.type} />
          </div>

          <div className="q-stem q-compact mt-2.5 max-h-[7.2em] overflow-hidden text-[14px]
                          leading-[1.8] text-ink">
            {renderBlocks(q.blocks?.stem, kwTrim) || q.stem}
          </div>

          {imgOpts ? (
            <div className="mt-1.5 text-[11px] text-ink-faint">选项见图（{optionRange(q)}）</div>
          ) : (q.options?.length || 0) > 1 && (
            <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-0.5 @[520px]:grid-cols-2">
              {q.options.slice(0, 6).map((o, i) => (
                <div key={o.label} className="flex min-w-0 gap-1.5 text-[12.5px] text-ink-soft">
                  <span className="shrink-0 font-medium text-ink-faint">{o.label}.</span>
                  <span className="line-clamp-1 min-w-0">
                    {renderBlocks(q.blocks?.options?.[i], kwTrim)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── 状态 + 动作：宽卡片靠右，窄卡片落到题干下面 ─────── */}
        <div className="flex shrink-0 flex-row items-end justify-between gap-3 border-t
                        border-border/60 pt-3 @[880px]:w-[196px] @[880px]:flex-col
                        @[880px]:items-stretch @[880px]:border-l @[880px]:border-t-0
                        @[880px]:pl-5 @[880px]:pt-0">
          <div className="min-w-0 flex-1 space-y-1 text-[11px] @[880px]:flex-none">
            <Field label="答案" value={answerPreview(q.answer)} tone={hasAns ? 'ok' : 'warn'} />
            <Field label="解析" value={hasSol ? '已收录' : '缺解析'} tone={hasSol ? 'ok' : 'warn'} />
            <Field label="配图" tone={figN ? 'ok' : 'muted'}
              value={figN ? <span className="inline-flex items-center gap-0.5">
                <ImageIcon size={10} />{figN} 张
              </span> : '无图'} />
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); open() }}
            disabled={picking}
            className="press flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-xl
                       border border-warn-line bg-warn-soft px-3 text-[11.5px] font-semibold
                       text-warn transition-colors hover:border-warn hover:brightness-105
                       disabled:opacity-60 @[880px]:mt-2 @[880px]:w-full">
            {picking ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
            {picking ? '正在打开…' : '校对这道题'}
            {!picking && <ArrowRight size={12} />}
          </button>
        </div>
      </div>
    </article>
  )
}

function CardSkeleton() {
  return (
    <div className="rounded-[20px] border border-border bg-surface p-4">
      <div className="flex gap-2">
        <div className="skeleton h-3 w-20" />
        <div className="skeleton h-3 w-40" />
        <div className="skeleton ml-auto h-3 w-16" />
      </div>
      <div className="skeleton mt-3 h-4 w-[90%]" />
      <div className="skeleton mt-2 h-4 w-[66%]" />
      <div className="skeleton mt-4 h-3 w-36" />
    </div>
  )
}

function PageBtn({ children, onClick, disabled, title }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean; title?: string
}) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      className="press grid h-7 w-7 place-items-center rounded-lg border border-border bg-surface
                 text-[11px] text-ink-soft transition-colors hover:border-border-strong
                 hover:text-ink disabled:pointer-events-none disabled:opacity-30">
      {children}
    </button>
  )
}

export default function ProofPicker({
  stage, L, activeKey, pickingKey, error, version = 0, onPick, onDismissError,
}: {
  stage: Stage
  /** 与校对三栏共用同一份筛选/分页状态，左栏改筛选时这里立刻同步 */
  L: QuestionList
  /** 已在右侧打开过的题：回到选题页时高亮它 */
  activeKey?: string
  pickingKey?: string
  /** 打开某道题失败时的错误（列表请求自己的错误走全局条） */
  error?: string
  /** 写回/改源码后自增，选题列表跟着刷新 */
  version?: number
  onPick: (key: string) => void
  onDismissError?: () => void
}) {
  const meta = STAGE_BY_KEY[stage]
  const [showFilter, setShowFilter] = useFlag(
    'ammath.proof.filters',
    typeof window !== 'undefined' && window.innerWidth >= 1280,
  )
  const [histOpen, setHistOpen] = useState(false)
  const [hist, setHist] = useState<string[]>(readHistory)
  const [sortOpen, setSortOpen] = useState(false)
  const searchBox = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const sortBox = useRef<HTMLDivElement>(null)

  // 写回答案/解析后，回到选题页时卡片状态要跟着变。
  useEffect(() => {
    if (version > 0) L.setReload((v) => v + 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version])

  useEffect(() => {
    if (!histOpen) return
    const on = (e: MouseEvent) => {
      if (searchBox.current && !searchBox.current.contains(e.target as Node)) setHistOpen(false)
    }
    document.addEventListener('mousedown', on)
    return () => document.removeEventListener('mousedown', on)
  }, [histOpen])

  useEffect(() => {
    if (!sortOpen) return
    const on = (e: MouseEvent) => {
      if (sortBox.current && !sortBox.current.contains(e.target as Node)) setSortOpen(false)
    }
    document.addEventListener('mousedown', on)
    return () => document.removeEventListener('mousedown', on)
  }, [sortOpen])

  // 和题库一致：按 / 直接聚焦搜索框。焦点在输入框里时不再抢。
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return
      const t = e.target as HTMLElement | null
      if (t?.closest('input, textarea, select, [contenteditable="true"]')) return
      e.preventDefault()
      inputRef.current?.focus()
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [])

  // 换筛选/翻页后回到列表顶部，否则新结果会停在上一批的滚动位置。
  useEffect(() => {
    L.listRef.current?.scrollTo(0, 0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [L.filters, L.page])
  // 窄屏上筛选面板是覆盖式抽屉，桌面端记住的“展开”不该把手机一打开就盖满。
  useEffect(() => {
    if (window.innerWidth < 1280) setShowFilter(false)
    const on = () => { if (window.innerWidth < 1280) setShowFilter(false) }
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [setShowFilter])


  const rememberSearch = (v: string) => {
    const s = v.trim()
    if (!s) return
    setHist((cur) => {
      const next = [s, ...cur.filter((x) => x !== s)].slice(0, 8)
      try { localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
  }
  const clearSearchHist = () => {
    setHist([])
    try { localStorage.removeItem(SEARCH_HISTORY_KEY) } catch { /* ignore */ }
  }

  const clearAll = () => L.loadFilters(EMPTY_FILTERS, 'used')
  const maxPage = Math.max(1, Math.ceil(L.total / L.pageSize))
  const start = L.total ? (L.page - 1) * L.pageSize + 1 : 0
  const end = Math.min(L.total, L.page * L.pageSize)
  const sortLabel = L.sort === 'used' && L.q.trim()
    ? '相关度'
    : (SORTS.find((x) => x.value === L.sort)?.label || '排序')

  // 生效条件做成可删胶囊：和题库顶栏一样，点掉哪条撤哪条。
  const chips: { key: string; label: string; clear: () => void }[] = (() => {
    const out: { key: string; label: string; clear: () => void }[] = []
    if (L.q.trim()) out.push({ key: 'q', label: `搜「${L.q.trim()}」`, clear: () => L.setQ('') })
    if (L.scopeName) {
      out.push({ key: 'scope', label: L.scopeName, clear: () => L.setPoints([]) })
    } else if (L.points.length === 1) {
      const title = L.facets?.points.find((x) => x.value === L.points[0])?.title || L.points[0]
      out.push({ key: 'p1', label: `考点 · ${dispPoint(title)}`, clear: () => L.setPoints([]) })
    } else if (L.points.length > 1) {
      out.push({ key: 'pn', label: `考点 · ${L.points.length} 个`, clear: () => L.setPoints([]) })
    }
    if (L.type) out.push({
      key: 'type', label: L.facets?.types.find((x) => x.value === L.type)?.label || L.type,
      clear: () => L.setType(''),
    })
    if (L.kind) out.push({ key: 'kind', label: `${L.kind}题`, clear: () => L.setKind('') })
    for (const s of L.sources) out.push({
      key: `src-${s}`, label: `出处 · ${s}`,
      clear: () => L.setSources((xs) => xs.filter((x) => x !== s)),
    })
    if (L.pointSource) out.push({
      key: 'psrc', label: L.pointSource === '无' ? '考点来源未记' : `考点来源 · ${L.pointSource}`,
      clear: () => L.setPointSource(''),
    })
    for (const d of L.diffs) out.push({
      key: `d-${d}`, label: `难度 ${'★'.repeat(DIFF_STARS[d] || 0)}`,
      clear: () => L.setDiffs((xs) => xs.filter((x) => x !== d)),
    })
    for (const y of L.years) out.push({
      key: `y-${y}`, label: `${y} 年`,
      clear: () => L.setYears((xs) => xs.filter((x) => x !== y)),
    })
    for (const m of L.missing) out.push({
      key: `m-${m}`, label: `缺${m}`,
      clear: () => L.setMissing((xs) => xs.filter((x) => x !== m)),
    })
    for (const h of L.has) out.push({
      key: `h-${h}`, label: h.startsWith('有') ? h : `有${h}`,
      clear: () => L.setHas((xs) => xs.filter((x) => x !== h)),
    })
    if (L.reviewed) out.push({
      key: 'reviewed', label: L.reviewed === 'yes' ? '已复核' : '未复核',
      clear: () => L.setReviewed(''),
    })
    for (const a of L.answerSources) out.push({
      key: `as-${a}`, label: ASRC_LABEL[a] || `答案 · ${a}`,
      clear: () => L.setAnswerSources((xs) => xs.filter((x) => x !== a)),
    })
    for (const x of L.scopes) out.push({
      key: `sc-${x}`, label: `地区 · ${SCOPE_LABEL[x] || x}`,
      clear: () => L.setScopes((xs) => xs.filter((v) => v !== x)),
    })
    for (const x of L.paperStates) out.push({
      key: `ps-${x}`, label: `试卷 · ${PAPER_LABEL[x] || x}`,
      clear: () => L.setPaperStates((xs) => xs.filter((v) => v !== x)),
    })
    for (const x of L.starStates) out.push({
      key: `ss-${x}`, label: `评级 · ${STAR_LABEL[x] || x}`,
      clear: () => L.setStarStates((xs) => xs.filter((v) => v !== x)),
    })
    for (const x of L.qualities) out.push({
      key: `ql-${x}`, label: `质量 · ${QUALITY_LABEL[x] || x}`,
      clear: () => L.setQualities((xs) => xs.filter((v) => v !== x)),
    })
    return out
  })()

  const quick = [
    {
      key: 'reviewed', label: '未复核', on: L.reviewed === 'no',
      run: () => L.setReviewed(L.reviewed === 'no' ? '' : 'no'),
    },
    {
      key: 'model', label: '模型答案', on: L.answerSources.includes('workbuddy'),
      run: () => L.toggleAnswerSource('workbuddy'),
    },
    {
      key: 'nosol', label: '缺解析', on: L.missing.includes('解析'),
      run: () => L.toggleMissing('解析'),
    },
    {
      key: 'nopoint', label: '缺考点', on: L.missing.includes('标签'),
      run: () => L.toggleMissing('标签'),
    },
    {
      key: 'figure', label: '有配图', on: L.has.includes('有图'),
      run: () => L.toggleHas('有图'),
    },
  ]

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* ── 标题 + 搜索 ─────────────────────────────────── */}
      <section className="relative shrink-0 border-b border-border/70">
        <div className="absolute inset-0 bg-surface/55 backdrop-blur-2xl" />
        <div className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            background:
              'radial-gradient(55% 100% at 0% 0%, var(--color-warn-soft), transparent 62%),'
              + 'radial-gradient(55% 100% at 100% 0%, var(--color-brand-soft), transparent 64%)',
          }} />

        <div className="relative mx-auto w-full max-w-[1320px] px-4 pb-3.5 pt-4 md:px-6">
          <div className="flex flex-wrap items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-[14px] border
                             border-warn-line bg-warn-soft text-warn shadow-[0_10px_24px_-18px_var(--color-warn)]">
              <ShieldCheck size={21} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-[20px] font-semibold tracking-[-.02em]">从题库选一道题</h1>
                <span className="rounded-full border border-border bg-surface/70 px-2 py-[2px]
                                 text-[10px] font-medium text-ink-faint">全库检索</span>
              </div>
              <p className="mt-1 max-w-[760px] text-[11.5px] leading-relaxed text-ink-soft">
                按题干、公式、考点、出处搜，支持
                <code className="mx-1 rounded bg-surface/80 px-1 py-[1px] text-[10.5px] text-ink-soft">
                  考点:三角 年份:2024
                </code>
                这类语法；选中后在同一页做校对/整理：独立做一遍，缺考点/难度/答案/解析可补齐。
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <div className="rounded-xl border border-border/80 bg-surface/75 px-3 py-1.5 text-right
                              shadow-[var(--shadow-card)]">
                <div className="text-[9.5px] text-ink-faint">
                  {(L.q.trim() || L.activeFilters > 0) ? '匹配题目' : '本学段可校对'}
                </div>
                <div className="mt-0.5 flex items-baseline justify-end gap-1">
                  <Num value={L.total} className="text-[16px] font-semibold" />
                  <span className="text-[10px] text-ink-faint">道</span>
                  {L.loading && <Loader2 size={10} className="animate-spin text-warn" />}
                </div>
              </div>
              <span className="hidden max-w-[92px] text-[10px] leading-relaxed text-ink-faint lg:inline">
                只生成建议<br />不自动写库
              </span>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <div ref={searchBox} className="relative min-w-[240px] flex-1">
              <Search size={15}
                className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" />
              <input
                ref={inputRef}
                value={L.q}
                onChange={(e) => { L.setQ(e.target.value); if (histOpen) setHistOpen(false) }}
                onFocus={() => setHistOpen(true)}
                onBlur={() => {
                  window.setTimeout(() => setHistOpen(false), 140)
                  if (L.q.trim()) rememberSearch(L.q)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                    rememberSearch(L.q); setHistOpen(false)
                    ;(e.currentTarget as HTMLInputElement).blur()
                  } else if (e.key === 'Escape') {
                    L.setQ(''); setHistOpen(false)
                  }
                }}
                aria-label="搜索选题"
                placeholder="搜题干 / 公式 / 考点 / 题号 / 出处…"
                title="公式：cosB、3/4、x^2；字段：考点:三角 年份:2024 类型:多选 难度:中档 出处:…；-词 排除"
                className="h-10 w-full rounded-xl border border-border bg-surface/90 pl-10 pr-20
                           text-[13px] text-ink
                           outline-none transition-[border-color,box-shadow,background-color] duration-150
                           placeholder:text-ink-faint focus:border-brand-line focus:bg-surface
                           focus:shadow-[0_0_0_4px_var(--color-brand-soft)]"
              />
              {L.q ? (
                <button onClick={() => L.setQ('')} title="清空搜索"
                  className="press absolute right-2.5 top-1/2 grid h-6 w-6 -translate-y-1/2
                             place-items-center rounded-md text-ink-faint hover:bg-muted hover:text-ink">
                  <X size={13} />
                </button>
              ) : (
                <span className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2
                                 items-center gap-1 text-[10px] text-ink-faint sm:flex">
                  <kbd className="rounded border border-border bg-surface px-1 text-[9.5px] leading-[16px]">↵</kbd>
                  输入即搜
                </span>
              )}

              {histOpen && (
                <div className="absolute left-0 right-0 top-[calc(100%+7px)] z-50 overflow-hidden
                                rounded-[var(--radius-card)] border border-border bg-surface py-1
                                shadow-[var(--shadow-pop)]">
                  {hist.length > 0 ? (<>
                    <div className="flex items-center px-3 py-1.5 text-[10.5px] text-ink-faint">
                      <Clock3 size={11} className="mr-1" />最近搜索
                      <button onMouseDown={(e) => e.preventDefault()} onClick={clearSearchHist}
                        className="ml-auto text-ink-faint transition-colors hover:text-ink">清空</button>
                    </div>
                    {hist.map((h) => (
                      <button key={h} onMouseDown={(e) => e.preventDefault()}
                        onClick={() => {
                          L.setQ(h); rememberSearch(h); setHistOpen(false)
                          inputRef.current?.blur()
                        }}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px]
                                   text-ink-soft transition-colors hover:bg-brand-soft/50 hover:text-brand-ink">
                        <Search size={11} className="shrink-0 text-ink-faint" />
                        <span className="truncate">{h}</span>
                      </button>
                    ))}
                  </>) : (
                    <div className="px-3 py-2 text-[11px] leading-relaxed text-ink-soft">
                      试试搜 <b className="font-medium">「导数」</b>、
                      <b className="font-medium">「cosB」</b> 或
                      <b className="font-medium">「考点:三角」</b>；也可以直接搜题号。
                    </div>
                  )}
                  <div className="mt-1 border-t border-border/60 px-3 py-1.5 text-[10px] leading-relaxed text-ink-faint">
                    语法：考点:三角 · 年份:2024 · 类型:多选 · 难度:中档 · 出处:… · -词 排除
                  </div>
                </div>
              )}
            </div>

            <button onClick={() => setShowFilter((v) => !v)} aria-pressed={showFilter}
              className={`press flex h-10 shrink-0 items-center gap-1.5 rounded-xl border px-3
                          text-[12px] font-medium transition-colors ${showFilter
                ? 'border-brand-line bg-brand-soft text-brand-ink'
                : 'border-border bg-surface/90 text-ink-soft hover:border-border-strong hover:text-ink'}`}>
              <SlidersHorizontal size={14} />筛选
              {L.activeFilters > 0 && (
                <span className="tnum rounded-full bg-brand px-1.5 text-[10px] leading-[16px] text-white">
                  {L.activeFilters}
                </span>
              )}
            </button>

            <div ref={sortBox} className="relative shrink-0">
              <button onClick={() => setSortOpen((v) => !v)} aria-expanded={sortOpen}
                className={`press flex h-10 items-center gap-1.5 rounded-xl border px-3 text-[12px]
                            transition-colors ${sortOpen
                  ? 'border-brand-line bg-brand-soft text-brand-ink'
                  : 'border-border bg-surface/90 text-ink-soft hover:border-border-strong hover:text-ink'}`}>
                <ArrowUpDown size={13} />
                <span className="max-w-[108px] truncate">{sortLabel}</span>
                <ChevronDown size={11} className={`transition-transform ${sortOpen ? 'rotate-180' : ''}`} />
              </button>
              {sortOpen && (
                <div className="pop absolute right-0 top-[calc(100%+7px)] z-40 w-[188px]
                                rounded-[var(--radius-card)] border border-border bg-surface p-1.5
                                shadow-[var(--shadow-pop)]">
                  <div className="px-2 py-1 text-[10px] font-semibold tracking-wide text-ink-faint">排序</div>
                  {SORTS.map((s) => (
                    <button key={s.value}
                      onClick={() => { L.setSort(s.value); setSortOpen(false) }}
                      className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11.5px]
                                  transition-colors ${L.sort === s.value
                        ? 'bg-brand-soft font-medium text-brand-ink'
                        : 'text-ink-soft hover:bg-muted hover:text-ink'}`}>
                      {s.value === 'used' && L.q.trim() ? '相关度（搜索）' : s.label}
                      {L.sort === s.value && <Check size={11} className="ml-auto" />}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="mr-0.5 inline-flex items-center gap-1 text-[10px] font-semibold
                             tracking-[.06em] text-ink-faint">
              <Sparkles size={11} className="text-warn" />快筛
            </span>
            {quick.map((x) => (
              <button key={x.key} onClick={x.run} aria-pressed={x.on}
                className={`press rounded-full border px-2.5 py-[3px] text-[11px] font-medium
                            transition-colors ${x.on
                  ? 'border-warn-line bg-warn-soft text-warn'
                  : 'border-border bg-surface/70 text-ink-soft hover:border-warn-line hover:text-warn'}`}>
                {x.label}
              </button>
            ))}
            {L.activeFilters > 0 && (
              <button onClick={clearAll}
                className="press ml-1 text-[10.5px] text-ink-faint underline underline-offset-2 hover:text-warn">
                清除全部筛选（{L.activeFilters}）
              </button>
            )}
            <span className="ml-auto hidden text-[10px] text-ink-faint lg:inline">
              选中一道题 → 看现有答案/解析 → 让 DeepSeek 独立做一遍
            </span>
          </div>
        </div>
      </section>

      {error && (
        <div className="mx-auto w-full max-w-[1320px] px-4 pt-3 md:px-6">
          <div className="flex items-start gap-2 rounded-xl border border-warn-line bg-warn-soft
                          px-3 py-2 text-[11.5px] text-warn">
            <span className="min-w-0 flex-1">{error}</span>
            {onDismissError && (
              <button onClick={onDismissError} className="shrink-0 underline">知道了</button>
            )}
          </div>
        </div>
      )}

      {/* ── 结果区 ─────────────────────────────────────── */}
      <div className="relative flex min-h-0 flex-1">
        {showFilter && (<>
          <div className="absolute inset-0 z-40 bg-scrim xl:hidden" onClick={() => setShowFilter(false)} />
          <div className="relative z-50 flex max-xl:absolute max-xl:inset-y-0 max-xl:left-0
                          max-xl:shadow-[var(--shadow-pop)] xl:relative">
            <FilterPanel L={L} onClose={() => setShowFilter(false)} onClearAll={clearAll} />
          </div>
        </>)}

        <section className="flex min-w-0 flex-1 flex-col">
          <div className="flex min-h-11 shrink-0 flex-wrap items-center gap-x-2 gap-y-1
                          border-b border-border/60 bg-surface/45 px-4 py-1.5 backdrop-blur-xl md:px-5">
            <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
              <Num value={L.total} className="text-[13.5px] font-semibold text-ink" />
              <span className="text-[10.5px] text-ink-faint">道</span>
              {L.loading && <Loader2 size={10} className="animate-spin text-warn" />}
            </span>
            {chips.length > 0 && (
              <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
                {chips.slice(0, 4).map((c) => (
                  <button key={c.key} onClick={c.clear} title={`去掉「${c.label}」`}
                    className="press group flex shrink-0 items-center gap-1 rounded-full bg-brand-soft
                               px-2 py-[2px] text-[10.5px] font-medium text-brand-ink
                               transition-colors hover:bg-brand hover:text-white">
                    <span className="max-w-[15ch] truncate">{c.label}</span>
                    <X size={10} className="opacity-55 group-hover:opacity-100" />
                  </button>
                ))}
                {chips.length > 4 && (
                  <span className="tnum shrink-0 text-[10px] text-ink-faint">+{chips.length - 4}</span>
                )}
                <button onClick={clearAll}
                  className="press shrink-0 rounded-full px-1.5 py-[2px] text-[10.5px]
                             text-ink-faint hover:text-warn">清除</button>
              </span>
            )}
            <span className="ml-auto text-[10px] text-ink-faint">
              第 <span className="tnum text-ink-soft">{L.page}</span> / <span className="tnum">{maxPage}</span> 页
            </span>
          </div>

          <div ref={L.listRef} className="b-scroll min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-[1320px] p-4 md:p-5">
              {L.loading && !L.items.length ? (
                <div className="space-y-2.5">
                  {Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)}
                </div>
              ) : L.items.length > 0 ? (
                <div className="anim-stagger space-y-2.5">
                  {L.items.map((q) => (
                    <ProofCard key={q.key} q={q} kw={L.q}
                      active={activeKey === q.key}
                      picking={pickingKey === q.key}
                      onPick={() => onPick(q.key)} />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
                  <span className="grid h-14 w-14 place-items-center rounded-2xl border border-border
                                   bg-surface text-ink-faint shadow-[var(--shadow-card)]">
                    <SearchX size={25} strokeWidth={1.5} />
                  </span>
                  <div>
                    <div className="text-[14px] font-medium text-ink">
                      {L.q.trim() || L.activeFilters > 0 ? '没有匹配的题' : `${meta.name}题库还是空的`}
                    </div>
                    <div className="mt-1 text-[11.5px] text-ink-faint">
                      {L.q.trim() || L.activeFilters > 0
                        ? '换个关键词，或去掉一两个筛选项'
                        : '回录入页换一个学段，或先去录题'}
                    </div>
                  </div>
                  {(L.q.trim() || L.activeFilters > 0) && (
                    <div className="flex flex-wrap items-center justify-center gap-2">
                      {L.q.trim() && (
                        <button onClick={() => L.setQ('')}
                          className="press rounded-lg border border-border bg-surface px-3 py-1.5
                                     text-[11.5px] text-ink-soft hover:border-border-strong hover:text-ink">
                          清空搜索词
                        </button>
                      )}
                      <button onClick={clearAll}
                        className="press rounded-lg border border-brand-line bg-brand-soft px-3 py-1.5
                                   text-[11.5px] font-medium text-brand-ink hover:bg-brand-soft/70">
                        清除全部筛选
                      </button>
                    </div>
                  )}
                  <div className="mt-1 max-w-[430px] text-[10.5px] leading-relaxed text-ink-faint">
                    支持按题干、公式、考点、出处搜索；也可以写「考点:三角 年份:2024」或「-词」排除。
                  </div>
                </div>
              )}
            </div>
          </div>

          {L.total > 0 && (
            <div className="flex min-h-12 shrink-0 flex-wrap items-center gap-2 border-t
                            border-border/60 bg-surface/70 px-4 py-2 backdrop-blur-xl md:px-5">
              <span className="tnum text-[10.5px] text-ink-faint">
                第 {start}–{end} 道，共 <Num value={L.total} /> 道
              </span>
              <div className="ml-auto flex items-center gap-1">
                <PageBtn onClick={() => { L.setPage(1); L.listRef.current?.scrollTo(0, 0) }}
                  disabled={L.page <= 1} title="第一页"><ChevronsLeft size={13} /></PageBtn>
                <PageBtn onClick={() => { L.setPage((p) => Math.max(1, p - 1)); L.listRef.current?.scrollTo(0, 0) }}
                  disabled={L.page <= 1} title="上一页"><ChevronLeft size={13} /></PageBtn>
                <span className="flex items-center gap-1 px-1 text-[11px] text-ink-faint">
                  第
                  <input value={L.pageInput} onChange={(e) => L.setPageInput(e.target.value)}
                    onBlur={L.jumpPage}
                    onKeyDown={(e) => { if (e.key === 'Enter') L.jumpPage() }}
                    aria-label="页码"
                    className="tnum h-7 w-10 rounded-lg border border-border bg-bg px-1 text-center
                               text-[11px] text-ink outline-none focus:border-brand-line" />
                  / <span className="tnum">{maxPage}</span> 页
                </span>
                <PageBtn onClick={() => { L.setPage((p) => Math.min(maxPage, p + 1)); L.listRef.current?.scrollTo(0, 0) }}
                  disabled={L.page >= maxPage} title="下一页"><ChevronRight size={13} /></PageBtn>
                <PageBtn onClick={() => { L.setPage(maxPage); L.listRef.current?.scrollTo(0, 0) }}
                  disabled={L.page >= maxPage} title="最后一页"><ChevronsRight size={13} /></PageBtn>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
