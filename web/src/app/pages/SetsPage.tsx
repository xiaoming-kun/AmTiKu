/** 套卷：一份**外来原卷**的整卷视图。
 *
 *  以前的入口只有「题目」：想看「2026 新高考 I 卷」长什么样，得先知道卷名、
 *  再去题库按出处筛，筛完还未必按原题号排。可题库里每道题本来就带着
 *  `source_label` + `source_no`——合起来就是一份完整的卷子。
 *
 *  这一页只做三件事：
 *  ① 左栏列出所有套卷（按年份、题量排），搜卷名；
 *  ② 右栏按**原卷题号**还原整份卷，缺答案/缺解析直接标在头上；
 *  ③ 一键整卷进卷子，或点开单题看详情。
 *
 *  数据全部派生自题目的 meta（见 `amti/papersets.py`），不新建存储。
 */
import { useEffect, useRef, useState } from 'react'
import {
  ArrowRight, FileStack, Layers, Loader2, RefreshCw, Search, TriangleAlert, X,
} from 'lucide-react'
import type { Q, SetsFollow } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import QuestionCard from '@/app/QuestionCard'

type SetItem = {
  id: string; title: string; year: number; region: string; book: string
  stage: string; n: number; answers: number; solutions: number; figures: number
  partial: boolean; types: Record<string, number>
}

const STAGE_LABEL: Record<string, string> = { primary: '小学', junior: '初中', senior: '高中' }

/** 左栏每页份数：2,678 份全量渲染要 18k DOM 节点、一次 700KB ——
 *  分页后首屏只剩几十份，体积与节点都落到可交互区间。 */
const PAGE = 50

/** 上次看的是哪一份套卷。**切去题库改题再切回来**要能回到原处，
 *  否则改个出处回来发现自己站在列表第一份，还得重新搜索。 */
const SET_SEL_KEY = 'amtiku.sets.sel.v1'
const SET_Q_KEY = 'amtiku.sets.q.v1'
const SET_YEAR_KEY = 'amtiku.sets.year.v1'
const SET_FOLLOW_KEY = 'amtiku.sets.followed.v1'

export default function SetsPage({
  stage, onAddBatch, onOpenQuestion, onPaper, inPaper,
  refreshSignal = 0, follow = null,
}: {
  stage: string
  onAddBatch: (items: Q[]) => void
  onOpenQuestion: (q: Q) => void
  onPaper: () => void
  /** 这道题是不是已经在当前卷子里（卡片右上角显示「在卷中」）。 */
  inPaper?: (key: string) => boolean
  /** 外部写库（改出处/标签/删除）后自增：套卷列表和当前明细马上重拉，
   *  不用等切页或手动点刷新。 */
  refreshSignal?: number
  /** 改出处导致卷名变了：旧卷名从列表消失时，跟到改名后的那一份。 */
  follow?: SetsFollow | null
}) {
  const [list, setList] = useState<SetItem[] | null>(null)
  const [years, setYears] = useState<number[]>([])
  const [q, setQ] = useState<string>(() => {
    try { return sessionStorage.getItem(SET_Q_KEY) || '' } catch { return '' }
  })
  const [year, setYear] = useState<string>(() => {
    try { return sessionStorage.getItem(SET_YEAR_KEY) || '' } catch { return '' }
  })
  const [sel, setSel] = useState<string>(() => {
    try { return sessionStorage.getItem(SET_SEL_KEY) || '' } catch { return '' }
  })
  const selRef = useRef(sel)
  selRef.current = sel
  const [detail, setDetail] = useState<{ item: SetItem; questions: Q[] } | null>(null)
  const [loading, setLoading] = useState(false)
  /** 右栏滚动容器。换一份套卷必须回到顶部——否则上一份滚到第 18 题，
   *  点下一份还是停在第 18 题，看起来像「这份卷子少了前 17 题」。 */
  const paneRef = useRef<HTMLDivElement>(null)
  /** 切过哪一份卷：只有**换卷**才回到顶部，自动刷新（重新拉数据）不动滚动位置。 */
  const lastSel = useRef('')
  /** 列表正在重拉：详情等它先决定选中项，别对旧卷名发一次必 404 的请求。 */
  const listBusy = useRef(false)
  /** 已经消费过的「跟卷」事件；用户后来点回旧卷时不能又被拽走。
   *  非 0 值也写进 sessionStorage：切走再回来是一个全新的组件实例，
   *  只靠 ref 会忘记「这条跟卷已经处理过了」。 */
  const followedNonce = useRef(0)
  if (!followedNonce.current) {
    try { followedNonce.current = Number(sessionStorage.getItem(SET_FOLLOW_KEY) || 0) || 0 } catch { /* ignore */ }
  }
  const markFollowed = (n: number) => {
    followedNonce.current = n
    try { sessionStorage.setItem(SET_FOLLOW_KEY, String(n)) } catch { /* ignore */ }
  }
  const [busy, setBusy] = useState(false)
  /** 自增即重拉：来自「刷新」按钮，以及**切回本标签页**（录入在另一个标签页）。 */
  const [tick, setTick] = useState(0)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  /** 左栏滚动容器：翻页要回到顶部。 */
  const listRef = useRef<HTMLDivElement>(null)
  /** 筛选条件变没变：变了才把选中项重置到第一份；只是翻页时保留选中。 */
  const filterKeyRef = useRef('')

  // 记住选中项和搜索条件：套卷 → 题目详情（题库）→ 返回套卷时回到原处。
  // 改出处把卷名改掉时，搜索词可能不再命中；列表发现后自动清一次搜索
  // （见下面的 follow 逻辑），否则新卷名根本进不了列表。
  useEffect(() => {
    try {
      if (sel) sessionStorage.setItem(SET_SEL_KEY, sel)
      else sessionStorage.removeItem(SET_SEL_KEY)
      if (q) sessionStorage.setItem(SET_Q_KEY, q)
      else sessionStorage.removeItem(SET_Q_KEY)
      if (year) sessionStorage.setItem(SET_YEAR_KEY, year)
      else sessionStorage.removeItem(SET_YEAR_KEY)
    } catch { /* 隐私模式/配额满：只影响记忆，不影响功能 */ }
  }, [sel, q, year])

  // 新录入的题在**另一个标签页**提交；切回来时套卷必须跟着变，不能只认首屏那一份。
  useEffect(() => {
    const bump = () => {
      if (document.visibilityState === 'visible') setTick((v) => v + 1)
    }
    document.addEventListener('visibilitychange', bump)
    window.addEventListener('focus', bump)
    return () => {
      document.removeEventListener('visibilitychange', bump)
      window.removeEventListener('focus', bump)
    }
  }, [])

  // 筛选一变就回第 1 页；翻页本身不重置选中项（右栏不该跟着跳）。
  const setQuery = (v: string) => { setQ(v); setPage(0) }
  const setYearFilter = (v: string) => { setYear(v); setPage(0) }
  useEffect(() => { setPage(0) }, [stage])
  useEffect(() => { listRef.current?.scrollTo({ top: 0 }) }, [page])

  // 列表：学段跟着顶栏走（小学/初中走诊断题库，套卷目前只有高中原卷）。
  // 年份也在后端筛：前端先拿一页再本地按年过滤会漏掉别的页。
  useEffect(() => {
    listBusy.current = true
    setBusy(true)
    const filterKey = `${stage}|${q.trim()}|${year}`
    const filterChanged = filterKeyRef.current !== filterKey
    filterKeyRef.current = filterKey
    api.sets({ stage, q: q.trim(), year, limit: PAGE, offset: page * PAGE })
      .then((d: any) => {
        const items: SetItem[] = d.items || []
        setList(items)
        setTotal(d.total || 0)
        setYears(d.years || [])
        // 总数变少（删题/改出处/筛掉）后页码可能越界：退到最后一页。
        const pages = Math.max(1, Math.ceil((d.total || 0) / PAGE))
        if (page >= pages) { setPage(pages - 1); return }
        const cur = selRef.current
        // 改出处后旧卷名可能从列表里消失：优先跟到改名后的那一份。
        const f = follow && follow.nonce !== followedNonce.current ? follow : null
        if (f && f.from === cur) {
          if (items.some((x) => x.id === f.to)) {
            markFollowed(f.nonce)
            setSel(f.to)
            return
          }
          if (q.trim() || year) {
            setQ(''); setYear(''); setPage(0)
            return
          }
          if (page > 0) { setPage(0); return }
          // 同一页也找不到：直接按新卷名搜，保证跟过去而不是停在旧卷。
          markFollowed(f.nonce)
          setQuery(f.to)
          return
        }
        // 只有**筛选变了**才自动选第一份；单纯翻页保留右栏。
        if ((filterChanged || !cur) && !items.some((x) => x.id === cur)) {
          setSel(items[0]?.id || '')
        }
      })
      .catch((e) => { reportErr(e); setList([]) })
      .finally(() => { listBusy.current = false; setBusy(false) })
  }, [stage, q, year, page, tick, refreshSignal, follow])

  // 明细：按题号顺序还原
  useEffect(() => {
    if (!sel) { setDetail(null); return }
    // 列表在重拉：等它先决定选中项（改名后旧卷名可能已经不存在了）。
    if (listBusy.current) return
    let alive = true
    setLoading(true)
    api.set(sel)
      .then((d: any) => {
        if (!alive) return
        setDetail({ item: d, questions: (d.items || []) as Q[] })
        // **换一份套卷**才回到顶部：否则上一份滚到第 18 题，点下一份还停在第 18 题，
        // 看起来就像「这份卷子少了前 17 题」。自动刷新时保持滚动位置。
        if (lastSel.current !== sel) {
          paneRef.current?.scrollTo({ top: 0 })
          lastSel.current = sel
        }
      })
      .catch((e) => { if (alive) { reportErr(e); setDetail(null) } })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [sel, tick, refreshSignal, busy])

  // 年份筛选在后端做（分页前），这里不再本地过滤。
  const shown = list || []
  const pages = Math.max(1, Math.ceil(total / PAGE))

  const addAll = (qs: Q[]) => {
    if (!qs.length) return
    onAddBatch(qs)
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-1 overflow-hidden md:grid-cols-[340px_minmax(0,1fr)]">
      {/* ── 左：套卷列表 ── */}
      <aside className="flex min-h-0 flex-col border-r border-border bg-surface">
        <div className="shrink-0 space-y-2 border-b border-border px-3 pb-2.5 pt-3">
          <div className="flex items-center gap-1.5">
            <Layers size={14} className="text-brand" />
            <span className="text-[12.5px] font-semibold">套卷</span>
            <span className="tnum text-[10.5px] text-ink-faint">
              {list === null ? '读取中…' : `${total} 份`}
            </span>
            <button onClick={() => setTick((v) => v + 1)} title="重新读取套卷（新录入的题会出现在这里）"
              className="icon-btn ml-auto h-6 w-6 shrink-0">
              <RefreshCw size={12} className={busy ? 'animate-spin' : ''} />
            </button>
          </div>
          <div className="relative">
            <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input value={q} onChange={(e) => setQuery(e.target.value)}
              placeholder="搜卷名，如 2026 新高考"
              className="b-input h-7 w-full pl-6 pr-6 text-[11.5px]" />
            {q && (
              <button onClick={() => setQuery('')} className="icon-btn absolute right-0.5 top-1/2 h-5 w-5 -translate-y-1/2">
                <X size={10} />
              </button>
            )}
          </div>
          {years.length > 0 && (
            <div className="flex flex-wrap gap-1">
              <button onClick={() => setYearFilter('')}
                className={`b-chip ${year === '' ? 'b-chip-on' : ''}`}>全部年份</button>
              {years.slice(0, 6).map((y) => (
                <button key={y} onClick={() => setYearFilter(String(y))}
                  className={`b-chip ${year === String(y) ? 'b-chip-on' : ''}`}>{y}</button>
              ))}
            </div>
          )}
        </div>

        <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto p-2">
          {list === null ? (
            <div className="flex items-center justify-center gap-2 py-10 text-[11.5px] text-ink-faint">
              <Loader2 size={13} className="animate-spin" />正在整理套卷…
            </div>
          ) : shown.length === 0 ? (
            <div className="px-2 py-10 text-center text-[11.5px] text-ink-faint">
              {stage === 'senior' ? (
                <>
                  没有匹配的套卷<br />
                  <span className="text-[10.5px]">换个关键词，或到题库按「出处」筛</span>
                </>
              ) : (
                <>
                  套卷目前只有高中原卷<br />
                  <span className="text-[10.5px]">小学 / 初中走「诊断题库」，按册章找题</span>
                </>
              )}
            </div>
          ) : (
            shown.map((it) => {
              const missA = it.n - it.answers
              const missS = it.n - it.solutions
              return (
                <button key={it.id} onClick={() => setSel(it.id)}
                  className={`mb-1 block w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                    sel === it.id ? 'border-brand-line bg-brand-soft/50' : 'border-transparent hover:bg-muted'}`}>
                  <div className={`truncate text-[11.5px] ${sel === it.id ? 'font-semibold text-brand-ink' : 'text-ink'}`}
                    title={it.title}>{it.title}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-ink-faint">
                    <span className="tnum">{it.n} 题</span>
                    {!!it.year && <span className="tnum">{it.year}</span>}
                    <span>{STAGE_LABEL[it.stage] || '高中'}</span>
                    {(missA > 0 || missS > 0) && (
                      <span className="text-warn">
                        {missA > 0 && `缺答 ${missA}`}
                        {missA > 0 && missS > 0 && ' · '}
                        {missS > 0 && `缺解 ${missS}`}
                      </span>
                    )}
                  </div>
                </button>
              )
            })
          )}
        </div>

        {list !== null && total > PAGE && (
          <div className="flex shrink-0 items-center justify-between gap-2 border-t border-border px-3 py-1.5 text-[11px] text-ink-faint">
            <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page <= 0}
              className="b-chip disabled:opacity-40">‹ 上一页</button>
            <span className="tnum">第 {page + 1} / {pages} 页</span>
            <button onClick={() => setPage((p) => Math.min(pages - 1, p + 1))} disabled={page >= pages - 1}
              className="b-chip disabled:opacity-40">下一页 ›</button>
          </div>
        )}
      </aside>

      {/* ── 右：整卷还原 ── */}
      <section className="flex min-h-0 flex-col overflow-hidden">
        {!detail ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-ink-faint">
            <FileStack size={30} strokeWidth={1.3} className="text-border-strong" />
            <div className="text-[12.5px]">左边选一份套卷</div>
            <div className="text-[11px]">整卷按原题号排好，可一次全部加入卷子</div>
          </div>
        ) : (
          <>
            <header className="shrink-0 border-b border-border px-4 py-2.5">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h2 className="min-w-0 truncate text-[15px] font-semibold">{detail.item.title}</h2>
                <span className="tnum shrink-0 rounded-full bg-muted px-1.5 py-[1px] text-[10.5px] text-ink-soft">
                  {detail.item.n} 题
                </span>
                {!!detail.item.year && (
                  <span className="tnum shrink-0 text-[10.5px] text-ink-faint">{detail.item.year}</span>
                )}
                {detail.item.partial && (
                  <span className="shrink-0 rounded-full bg-warn-soft px-1.5 py-[1px] text-[10.5px] text-warn"
                    title="这一卷只录了部分题（按节选处理），不是完整原卷">
                    节选
                  </span>
                )}
                <div className="ml-auto flex shrink-0 items-center gap-1.5">
                  <button onClick={() => addAll(detail.questions)}
                    className="b-btn b-btn-secondary h-7 text-[11.5px]">
                    <Layers size={12} />整卷加入
                  </button>
                  <button onClick={() => { addAll(detail.questions); onPaper() }}
                    className="b-btn b-btn-primary h-7 text-[11.5px]">
                    加入并去组卷<ArrowRight size={12} />
                  </button>
                </div>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-ink-faint">
                {Object.entries(detail.item.types || {}).map(([t, n]) => (
                  <span key={t}>{t} <span className="tnum">{n}</span></span>
                ))}
                {(detail.item.answers < detail.item.n || detail.item.solutions < detail.item.n) && (
                  <span className="flex items-center gap-1 text-warn">
                    <TriangleAlert size={10} />
                    {detail.item.answers < detail.item.n && `缺答案 ${detail.item.n - detail.item.answers}`}
                    {detail.item.answers < detail.item.n && detail.item.solutions < detail.item.n && ' · '}
                    {detail.item.solutions < detail.item.n && `缺解析 ${detail.item.n - detail.item.solutions}`}
                  </span>
                )}
              </div>
            </header>

            <div ref={paneRef} className="min-h-0 flex-1 overflow-y-auto">
              {loading && !detail.questions.length ? (
                <div className="flex items-center justify-center gap-2 py-16 text-[11.5px] text-ink-faint">
                  <Loader2 size={14} className="animate-spin" />正在按题号还原…
                </div>
              ) : (
                /* 和题库**同一张卡**：元信息行 / 标签 / 选项预览 / 答案折叠
                   全一致。差别只有两处：前面多一个原卷题号，勾选框不出现
                   （这里是整卷，不是挑题）。 */
                <div className="space-y-2.5 p-4">
                  {detail.questions.map((q, i) => (
                    <QuestionCard key={q.key} q={q}
                      index={q.source_no || i + 1}
                      fullStem
                      detailText
                      active={false}
                      inPaper={inPaper ? inPaper(q.key) : false}
                      selectMode={false} checked={false}
                      maskAns kw=""
                      hideSrc={(q.meta?.source_label || '') === detail.item.title}
                      onSelect={() => onOpenQuestion(q)}
                      onDetail={() => onOpenQuestion(q)}
                      onAdd={() => addAll([q])}
                      onToggle={() => {}} />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  )
}
