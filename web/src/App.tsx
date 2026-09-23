import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ListFilter, SlidersHorizontal, X, Check, ChevronFirst, ChevronLast, ChevronRight,
  ClipboardList,
} from 'lucide-react'
import type { Q, Base } from '@/lib/types'
import { api, reportErr, setGlobalErrHandler } from '@/lib/api'
import { SCORE, SECTION_LABEL } from '@/lib/paper'
import { DIFF_STARS } from '@/lib/display'
import { useQuestionList } from '@/lib/useQuestionList'
import { Flags, useFlag } from '@/app/ui'
import QuestionCard from '@/app/QuestionCard'
import { Trash, DeleteModal } from '@/app/Trash'
import { Detail, TexSource } from '@/app/Detail'
import { Stats, Changes } from '@/app/Stats'
import CanvasEditor from '@/editor/CanvasEditor'
import ExportPage from '@/app/ExportPage'
import IngestDrawer from '@/app/IngestDrawer'
import Nav, { NAV_BY_HINT, type NavKey } from '@/app/Nav'
import TopBar from '@/app/TopBar'
import FilterPanel from '@/app/FilterPanel'
import HelpButton from '@/app/HelpButton'

/** 整屏页面。
 *
 *  **没有「第三栏」了**——内容区只有「筛选 | 题目」两栏：
 *  · 题目列表和当前卷子是**同一栏里的两个视图**（`view` 切换）；
 *  · 题目详情 / LaTeX 源码是**浮在内容区上的抽屉**（`dOpen`，按需开、随时关）。
 *  所以这里只剩「整屏页面」这一种 tab。 */
type Tab = 'workbench' | 'handout' | 'stats' | 'changes' | 'trash'
const FULL_PAGE: Tab[] = ['stats', 'changes', 'trash']

export default function App() {
  // 列表数据与筛选 → useQuestionList（一行拿到全部筛选状态，见 lib/useQuestionList.ts）
  const L = useQuestionList()
  const {
    facets, items, setItems, total, sel, setSel, loading, reload, setReload,
    page, setPage, pageSize, setPageSize, pageInput, setPageInput, jumpPage, listRef,
    q, setQ, kind, setKind, has, setHas, missing, setMissing, points, setPoints,
    diffs, setDiffs, years, setYears, sort, checked, setChecked,
    selectMode, setSelectMode, exitSelect, activeFilters,
  } = L

  const [base, setBase] = useState<Base | null>(null)
  const [tab, setTab] = useState<Tab>('workbench')
  const [showExport, setShowExport] = useState(false)
  const [showIngest, setShowIngest] = useState(false)
  const [handoutN, setHandoutN] = useState(0)
  const [globalErr, setGlobalErr] = useState('')

  /** 题目栏里现在显示哪一个视图：题目列表 or 当前卷子。
   *  两者**共用同一栏**（不是两个栏目），所以切换不改变任何宽度。 */
  const [view, setView] = useState<'list' | 'paper'>('list')
  /** 详情抽屉开着没有。它浮在内容区上（不占栏），Esc / ✕ 关掉。 */
  const [dOpen, setDOpen] = useState(false)
  const [dTab, setDTab] = useState<'detail' | 'tex'>('detail')

  // 可收起的区域。开合都记忆 —— 老师会固定一种摆法，不该每次打开都回到默认。
  // 首次打开按窗口宽度定：窄屏默认收起筛选面板，把宽度让给题目。
  const vw = typeof window === 'undefined' ? 1600 : window.innerWidth
  const [navShut, setNavShut] = useState(false)
  const [showFilter, setShowFilter] = useFlag('amtiku.showFilter', vw >= 1180)
  const [filterHot, setFilterHot] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)

  /** 详情页用的**全量**记录。
   *  列表接口为了省 CPU 只返回题干块 IR，而详情要画答案/解析 →
   *  选中后按 key 补一次全量。 */
  const [full, setFull] = useState<Q | null>(null)
  useEffect(() => {
    const k = sel?.key
    if (!k) { setFull(null); return }
    let alive = true
    api.get(k).then((d) => { if (alive) setFull(d) }).catch(reportErr)
    return () => { alive = false }
  }, [sel?.key])

  // 顶栏的「存量未改动」状态（与 facets 一起随 reload 刷新）
  useEffect(() => { api.baseline().then(setBase).catch(reportErr) }, [reload])
  // 导航栏上显示「已有 N 份讲义」
  useEffect(() => {
    api.handouts().then((d) => setHandoutN((d.items || []).length)).catch(() => {})
  }, [tab])

  /** 全局错误提示。
   *  以前请求失败是**静默**的：接口 400 返回 {detail}，前端当数据用，
   *  界面表现成"没题""没变化"。现在 request() 统一抛错，这里接住并显示。 */
  useEffect(() => {
    setGlobalErrHandler(setGlobalErr)
    return () => setGlobalErrHandler(null)
  }, [])

  /* ── 卷子 / 讲义两个收集夹 ───────────────────────────
     讲义和卷子**分开收**：卷子要打印成试卷，讲义要排成讲课稿，
     用途不同。同一道题既进卷子又进讲义是常态，不能共用一个集合。 */
  const [paperMap, setPaperMap] = useState<Map<string, Q>>(new Map())
  const [handoutMap, setHandoutMap] = useState<Map<string, Q>>(new Map())
  const paper = useMemo(() => [...paperMap.values()], [paperMap])
  const handout = useMemo(() => [...handoutMap.values()], [handoutMap])
  const paperScore = paper.reduce((s, x) => s + (SCORE[x.type] || 0), 0)
  const answered = paper.filter((x) => x.flags['解析']).length
  const [sureClear, setSureClear] = useState(false)
  /** 往卷子里加东西时让卷子那条计数**跳一下**。
   *
   *  加完不再自动跳到卷子视图了（批量挑题时每加一次就切走，等于逼人再切回来），
   *  所以得有个轻量回执告诉用户"收到了"。这就是那个回执。 */
  const [paperBump, setPaperBump] = useState(0)
  const bumpPaper = () => {
    setPaperBump((v) => v + 1)
    setTimeout(() => setPaperBump(0), 400)
  }

  // 导出对象**只认卷子**，默认为空。
  // 早先卷子一空就自动拿「当前筛选结果」顶上，于是刚进页面就显示
  // 「导出 38」——用户还没说要导出什么，程序先替他决定了。不对。
  const exportFrom = `卷子（${paper.length} 题）`

  const addToPaper = (it: Q) => { setPaperMap((m) => new Map(m).set(it.key, it)); bumpPaper() }
  const removeFromPaper = (k: string) => setPaperMap((m) => { const n = new Map(m); n.delete(k); return n })
  const addOneToHandout = (it: Q) => setHandoutMap((m) => new Map(m).set(it.key, it))

  /** 从详情点考点跳过来：列表立刻切成「只看这个考点」，并把该考点
   *  所在大类展开，这样侧栏能看见自己选中了什么。 */
  const [findNote, setFindNote] = useState('')
  const findPoint = (pid: string, title: string) => {
    setPoints([pid]); setQ(''); setPage(1)
    const p = (facets?.points || []).find((x: any) => x.value === pid)
    if (p) L.setOpenTopics((s) => new Set([...s, p.topic]))
    setFindNote(title)
    setShowFilter(true)
  }
  // 手动改筛选（不是从详情点考点跳过来）就把那句说明收掉
  useEffect(() => { setFindNote('') }, [q, has, missing, diffs, years])

  /** 删一道题：走 `/api/questions/{key}/trash`，**移进回收站不是真删**。 */
  const [deleteAsk, setDeleteAsk] = useState<
    { qs: Q[]; keys?: never } | { keys: string[]; qs?: never } | null>(null)
  const deleteQuestions = (keys: string[], reason: string, password: string) =>
    api.trashBatch(keys, reason, password).then(() => {
      const ks = new Set(keys)
      // 卷子里、勾选里的也要一起清掉——不然删除后它们还挂在那儿
      setPaperMap((m) => { const n = new Map(m); for (const k of ks) n.delete(k); return n })
      setChecked((c) => { const n = new Set(c); for (const k of ks) n.delete(k); return n })
      setReload((v) => v + 1)
    }).catch(reportErr)

  /** 把勾中的题一次性加进卷子 / 讲义 */
  const addChecked = () => {
    setPaperMap((m) => {
      const n = new Map(m)
      for (const x of items) if (checked.has(x.key)) n.set(x.key, x)
      return n
    })
    exitSelect()
    // **加完不跳走**：批量挑题时每加一次就切视图，等于逼人再切回来。
    // 卷子那条计数会自己跳一下（见下面的 bump），足够说明"收到了"。
    bumpPaper()
  }
  const addCheckedToHandout = () => {
    setHandoutMap((m) => {
      const n = new Map(m)
      for (const x of items) if (checked.has(x.key)) n.set(x.key, x)
      return n
    })
    exitSelect(); setTab('handout')
  }

  /* ── 导航动作 ── */
  const navActive: NavKey =
    tab === 'stats' ? 'stats' : tab === 'trash' ? 'trash' : tab === 'changes' ? 'changes'
    : tab === 'handout' ? 'handout'
    : view === 'paper' ? 'paper' : 'workbench'

  const pick = (k: NavKey) => {
    if (k === 'ingest') { setShowIngest(true); return }
    if (k === 'export') { setShowExport(true); return }
    if (k === 'points') {
      // 「知识点」= 把筛选面板亮出来并闪一下，而不是切走 ——
      // 它本来就在这一屏上，切页面反而多一次往返。
      setShowFilter(true); setTab('workbench')
      setFilterHot(true); setTimeout(() => setFilterHot(false), 900)
      return
    }
    // 「试卷管理」不是另一个页面，就是题目栏切到卷子那个视图
    if (k === 'paper') { setTab('workbench'); setView('paper'); return }
    setTab(k as Tab)
  }

  /* ── 心跳：页面活着服务器就活着，**页面一关服务器就退出** ──
     每 8 秒 ping 一次；关页面时用 sendBeacon 补最后一声。
     服务端只认「有没有 ping」：浏览器崩溃、断电、强杀都发不出关闭帧，
     但心跳停了就说明人走了。 */
  useEffect(() => {
    const ping = () => fetch('/api/alive', { method: 'POST' }).catch(() => {})
    ping()
    const t = setInterval(ping, 8000)
    const bye = () => { try { navigator.sendBeacon('/api/gone') } catch { /* 尽力而为 */ } }
    window.addEventListener('pagehide', bye)
    window.addEventListener('beforeunload', bye)
    return () => {
      clearInterval(t)
      window.removeEventListener('pagehide', bye)
      window.removeEventListener('beforeunload', bye)
    }
  }, [])

  /* ── 键盘 ──────────────────────────────────────────
     设计文档 §键盘优先。三条取舍：
     ① **单键只在没在输入框里时生效**，且忽略输入法合成中的按键
        （不然打中文时按到 W 会把页面跳走）。
     ② 上下移动用 ↑/↓ 而不是 j/k —— `K` 已经是「知识点」的单键，
        再让 `k` 管光标必然打架；箭头键也不受输入法影响。
     ③ 单键是**加速器不是唯一入口**：每一项都能用鼠标点到。 */
  useEffect(() => {
    const typing = () => {
      const el = document.activeElement as HTMLElement | null
      if (!el) return false
      const tag = el.tagName
      return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.isComposing || e.keyCode === 229) return   // 输入法合成中，一律不接管

      if (e.key === '/' && !typing()) {
        e.preventDefault(); searchRef.current?.focus(); return
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault(); setShowExport(true); return
      }
      if (e.key === 'Escape') { setDOpen(false); setShowExport(false); setShowIngest(false); return }
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (typing()) return
      // 有弹层/全屏编辑器时，单键和方向键都让给它 ——
      // 否则在导出弹层里按 ↓，背后的列表光标会跟着乱跑
      if (showExport || showIngest || tab === 'handout') return

      const k = e.key.toLowerCase()
      if (NAV_BY_HINT[k]) { e.preventDefault(); pick(NAV_BY_HINT[k]); return }

      // ↑/↓ 在列表里移光标，Enter 把光标那题加进卷子
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (!items.length) return
        e.preventDefault()
        const cur = items.findIndex((x) => x.key === sel?.key)
        const step = e.key === 'ArrowDown' ? 1 : -1
        const next = cur < 0 ? 0 : Math.max(0, Math.min(items.length - 1, cur + step))
        setSel(items[next])
        listRef.current
          ?.querySelectorAll('article')[next]
          ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
        return
      }
      if (e.key === 'Enter' && sel) { e.preventDefault(); addToPaper(sel) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, sel, setSel, listRef, showExport, showIngest, tab, dOpen])

  /** 列表头那句「现在看的是哪一批题」。
   *  写成函数而不是嵌套三元表达式：这东西有六层，塞在 JSX 里没人读得懂。 */
  const scopeText = (() => {
    if (L.scopeName) return L.scopeName
    if (points.length === 1) {
      const title = findNote
        || (facets?.points || []).find((x: any) => x.value === points[0])?.title
        || points[0]
      return `考点 · ${title}`
    }
    if (points.length > 1) return `考点 · ${points.length} 个`
    if (findNote) return findNote
    if (missing.length === 2 && missing.includes('答案') && missing.includes('解析'))
      return '没解析也没答案（还没做的题）'
    if (missing.length) return `缺：${missing.join('、')}`
    if (has.length) return `有：${has.join('、')}`
    return '全部题目'
  })()

  return (
    <div className="flex h-full flex-col">
      {/* 全局错误带。请求失败**必须看得见**，不能表现成"没数据"。 */}
      {globalErr && (
        <div className="anim-slide-d flex shrink-0 items-center gap-2 border-b border-warn-line
                        bg-warn-soft px-4 py-2 text-[12.5px] text-warn">
          <span className="font-semibold">出错了</span>
          <span className="min-w-0 flex-1 truncate" title={globalErr}>{globalErr}</span>
          <button onClick={() => setGlobalErr('')} className="icon-btn h-6 w-6 shrink-0">
            <X size={14} />
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <Nav active={navActive} onPick={pick} collapsed={navShut} onCollapsed={setNavShut}
          kind={kind} onKind={setKind} kinds={facets?.kinds || []}
          total={total} pointsCovered={facets?.points_covered || 0}
          pointsTotal={facets?.points.length || 0} />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar q={q} onQ={setQ} inputRef={searchRef} base={base} paperCount={paper.length}
            onPaper={() => { setTab('workbench'); setView('paper') }}
            onExport={() => setShowExport(true)}
            onIngest={() => setShowIngest(true)} onReload={() => setReload((v) => v + 1)} />

          {FULL_PAGE.includes(tab) ? (
            <main className="anim-fade-in min-h-0 flex-1 overflow-y-auto">
              {tab === 'stats' ? <Stats key={reload} />
                : tab === 'trash' ? <Trash onChanged={() => setReload((v) => v + 1)} />
                : <Changes />}
            </main>
          ) : (
            <div className="relative flex min-h-0 flex-1">
              {/* ── 筛选面板 ──
                  按 K（知识点）时给一道粉色高亮**从面板内侧亮一下**：
                  面板自己不透明，所以闪光要画在它上面的一层覆盖物里，
                  直接给容器加背景色是看不见的。 */}
              {showFilter && (
                <div className="relative flex">
                  <FilterPanel L={L} onClose={() => setShowFilter(false)} />
                  {filterHot && (
                    <span className="anim-flash pointer-events-none absolute inset-0 z-10
                                     ring-2 ring-brand ring-inset" />
                  )}
                </div>
              )}

              {/* ── 题目栏：**题目列表和卷子是同一栏里的两个视图** ──
                  内容区到这儿就结束了（没有第三栏）。 */}
              <section className="flex min-w-0 flex-1 flex-col">
                {/* 列表头：**一眼看出"现在看的是哪一批题"** */}
                <div className="flex h-[52px] shrink-0 items-center gap-2.5 border-b border-border
                                bg-surface px-4">
                  <h1 className="shrink-0 text-[19px] font-semibold tracking-tight">题库</h1>
                  <span className="tnum shrink-0 rounded-full bg-muted px-2 py-[2px] text-[11.5px]
                                   font-medium text-ink-soft">
                    {loading ? '加载中…' : `${total.toLocaleString()} 道`}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[12px] text-ink-faint">{scopeText}</span>
                  {!showFilter && (
                    <button onClick={() => setShowFilter(true)} title="展开筛选面板（K）"
                      className="press flex h-[30px] shrink-0 items-center gap-1.5 rounded-lg border
                                 border-border bg-surface px-2.5 text-[12.5px] text-ink-soft
                                 hover:border-brand-line hover:text-brand-ink">
                      <ListFilter size={14} />筛选
                      {activeFilters > 0 && (
                        <span className="tnum rounded-full bg-brand px-1.5 text-[10px] font-medium
                                         leading-[16px] text-white">
                          {activeFilters}
                        </span>
                      )}
                    </button>
                  )}
                  {/* 每页 / 多选只对题目列表有意义，切到卷子视图就收起来 */}
                  {view === 'list' && (<>
                  <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}
                    title="每页显示多少道"
                    className="press h-[30px] shrink-0 rounded-lg border border-border bg-surface
                               px-1.5 text-[12px] text-ink-soft outline-none hover:border-border-strong">
                    {[10, 20, 50, 100, 200].map((n) => <option key={n} value={n}>每页 {n}</option>)}
                  </select>
                  {!selectMode ? (
                    <button onClick={() => setSelectMode(true)} disabled={!items.length}
                      className="press h-[30px] shrink-0 rounded-lg border border-border bg-surface px-2.5
                                 text-[12.5px] text-ink-soft hover:border-border-strong hover:text-ink
                                 disabled:opacity-40">
                      多选
                    </button>
                  ) : (
                    /* 多选是**默认开着**的（挑题进卷子是主流程），所以它不该长成
                       一个抢眼的粉色主按钮——那会让人以为"必须退出"。做成一个
                       安静的开关，打开时用一个勾表示状态就够。 */
                    <button onClick={exitSelect} title="关掉多选（卡片不再跟着勾选）"
                      className="press flex h-[30px] shrink-0 items-center gap-1 rounded-lg border
                                 border-brand-line bg-brand-soft px-2.5 text-[12.5px] font-medium
                                 text-brand-ink">
                      <Check size={13} strokeWidth={2.6} />多选
                    </button>
                  )}
                  </>)}
                </div>

                {/* ── 卷子条 ──
                    卷子不再单独占一栏，就在这儿：**一条计数 + 点开切视图**。
                    有题时常驻（提醒"你手上已经有几道了"）；空卷子不占地方。 */}
                {(paper.length > 0 || view === 'paper') && (
                  <div
                    className={`flex shrink-0 items-center gap-2.5 border-b px-4 py-2
                                text-[12.5px] ${view === 'paper'
                      ? 'border-brand-line bg-brand-soft/60'
                      : 'border-border bg-surface-2'}`}>
                    <button onClick={() => setView(view === 'paper' ? 'list' : 'paper')}
                      className="press flex min-w-0 flex-1 items-center gap-2.5 text-left">
                      <ClipboardList size={14}
                        className={view === 'paper' ? 'shrink-0 text-brand' : 'shrink-0 text-ink-faint'} />
                      {/* 只让**计数**跳一下就够。整条是满宽的，给它加 scale 动画
                          会在动画那一帧里顶出视口 80px（还闪一下横向滚动条）。 */}
                      <span key={paperBump} className="anim-bump inline-flex shrink-0 items-baseline gap-1">
                        <span className={view === 'paper' ? 'font-semibold text-brand-ink' : 'font-semibold text-ink'}>
                          {view === 'paper' ? '当前卷子' : '已选'}
                        </span>
                        <span className="tnum font-semibold text-brand-ink">{paper.length}</span>
                        <span className={view === 'paper' ? 'text-brand-ink' : 'text-ink'}>题</span>
                      </span>
                      <span className="tnum shrink-0 text-ink-soft">{paperScore} 分</span>
                      <span className={`tnum shrink-0 ${answered === paper.length && paper.length
                        ? 'text-has' : 'text-warn'}`}>
                        有解析 {answered}/{paper.length}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-faint">
                        {view === 'paper' ? '在下面调整顺序、删题，或直接导出' : '点这里查看卷子'}
                      </span>
                      <span className="flex shrink-0 items-center gap-1 font-medium text-brand-ink">
                        {view === 'paper' ? '返回题目' : '查看卷子'}
                        {view === 'paper'
                          ? <ChevronRight size={13} className="rotate-180" />
                          : <ChevronRight size={13} />}
                      </span>
                    </button>
                    {/* **一键清空**：挑卷子经常推倒重来，一道一道点 ✕ 太慢。
                        但这是手工挑出来的，误点代价大——所以点第一下只是变成
                        「确认清空？」，点第二下才真清，鼠标移开就自动收回。 */}
                    <button
                      onClick={() => { if (sureClear) { setSureClear(false); setPaperMap(new Map()) }
                                       else setSureClear(true) }}
                      onMouseLeave={() => setSureClear(false)}
                      className={`press shrink-0 rounded-md border px-2 py-[3px] text-[11.5px]
                                  transition-colors ${sureClear
                        ? 'border-warn-line bg-warn-soft font-medium text-warn'
                        : 'border-border bg-surface text-ink-faint hover:border-warn-line hover:text-warn'}`}>
                      {sureClear ? '确认清空？' : '清空'}
                    </button>
                    <button onClick={() => setShowExport(true)}
                      className="press shrink-0 rounded-md bg-brand px-2.5 py-[4px] text-[11.5px]
                                 font-medium text-white shadow-[var(--shadow-brand)] hover:brightness-105">
                      导出 ⌘↵
                    </button>
                  </div>
                )}

                {/* 多选工具条：勾了才出现，平时不占地方 */}
                {view === 'list' && selectMode && checked.size > 0 && (
                  <div className="anim-slide-d flex shrink-0 items-center gap-2 border-b border-brand-line
                                  bg-brand-soft/60 px-4 py-2 text-[12.5px]">
                    <span className="font-semibold text-brand-ink">
                      已选 <span className="tnum">{checked.size}</span> 道
                    </span>
                    <button onClick={() => setChecked(new Set(items.map((x) => x.key)))}
                      className="press rounded-md border border-border bg-surface px-2 py-[3px]
                                 text-[11.5px] text-ink-soft hover:bg-muted">全选本页</button>
                    <button onClick={() => setChecked(new Set())}
                      className="press rounded-md border border-border bg-surface px-2 py-[3px]
                                 text-[11.5px] text-ink-soft hover:bg-muted">清空</button>
                    <div className="ml-auto flex items-center gap-1.5">
                      {/* **批量删除**：一道一道删太慢；走的是同一个删除弹窗，
                          原因和口令一样都不能少（批量更危险，规矩一条不减）。 */}
                      <button onClick={() => setDeleteAsk({ keys: [...checked] })}
                        className="press rounded-md border border-warn-line bg-surface px-2.5 py-[4px]
                                   text-[11.5px] font-medium text-warn hover:bg-warn-soft">
                        删除选中
                      </button>
                      <button onClick={addCheckedToHandout}
                        className="press rounded-md border border-brand-line bg-surface px-2.5 py-[4px]
                                   text-[11.5px] font-medium text-brand-ink hover:bg-brand-soft">
                        加入讲义
                      </button>
                      <button onClick={addChecked}
                        className="press rounded-md bg-brand px-2.5 py-[4px] text-[11.5px]
                                   font-medium text-white shadow-[var(--shadow-brand)] hover:brightness-105">
                        加入卷子
                      </button>
                    </div>
                  </div>
                )}

                {/* ── 栏内主体：题目列表 / 当前卷子 ── */}
                {view === 'paper' ? (
                  <PaperPanel paper={paper}
                    onOpen={(it) => { setSel(it); setDOpen(true) }}
                    onRemove={removeFromPaper} />

                ) : (<>
                {/* 用 `key` 把这一层绑到「页码 + 筛选条件」上：变了就整块重挂载，
                    逐条入场动画才会重新跑一遍。不这么做的话，翻页时新内容会
                    "啪"地出现，看不出列表已经换了一批。 */}
                <div
                  key={`${page}|${q}|${points.join()}|${diffs.join()}|${years.join()}|${sort}|${missing.join()}|${has.join()}`}
                  ref={(el) => { listRef.current = el }}
                  className="anim-stagger min-h-0 flex-1 space-y-2.5 overflow-y-auto p-4">
                  {loading && !items.length && <ListSkeleton />}
                  {items.map((it) => (
                    <QuestionCard key={it.key} q={it} active={sel?.key === it.key}
                      inPaper={paperMap.has(it.key)} inHandout={handoutMap.has(it.key)}
                      selectMode={selectMode} checked={checked.has(it.key)}
                      onOpen={() => { setSel(it); if (!selectMode) setDOpen(true) }}
                      onDetail={() => { setSel(it); setDOpen(true) }}
                      onAdd={() => { addToPaper(it) }}
                      onAddHandout={() => addOneToHandout(it)}
                      onToggle={() => L.toggleCheck(it.key)} />
                  ))}
                  {!loading && items.length === 0 && (
                    <div className="anim-fade-in flex flex-col items-center gap-2 py-16 text-ink-faint">
                      <span className="text-[13.5px]">没有匹配的题</span>
                      <button onClick={() => {
                          setHas([]); setMissing([]); setPoints([]); setDiffs([])
                          setYears([]); setQ('')
                        }}
                        className="press rounded-lg border border-border bg-surface px-3 py-1.5
                                   text-[12.5px] hover:border-brand-line hover:text-brand-ink">
                        清除全部筛选
                      </button>
                    </div>
                  )}
                  {items.length > 0 && <div className="h-1" />}
                </div>

                {/* 分页条。**总页数大于 1 才出现**——只有一页时占地方没意义。 */}
                {total > pageSize && (
                  <div className="flex shrink-0 items-center gap-1.5 border-t border-border bg-surface
                                  px-4 py-2 text-[12px] text-ink-faint">
                    <PageBtn onClick={() => { setPage(1); listRef.current?.scrollTo(0, 0) }}
                      disabled={page <= 1}><ChevronFirst size={13} /></PageBtn>
                    <PageBtn onClick={() => { setPage((p) => Math.max(1, p - 1)); listRef.current?.scrollTo(0, 0) }}
                      disabled={page <= 1}>‹ 上一页</PageBtn>
                    <span className="flex items-center gap-1 px-1">
                      第
                      <input value={pageInput} onChange={(e) => setPageInput(e.target.value)}
                        onBlur={jumpPage}
                        onKeyDown={(e) => { if (e.key === 'Enter') jumpPage() }}
                        className="tnum h-[26px] w-11 rounded-md border border-border bg-bg px-1
                                   text-center text-[12px] outline-none focus:border-brand-line" />
                      / <span className="tnum">{Math.max(1, Math.ceil(total / pageSize))}</span> 页
                    </span>
                    <PageBtn onClick={() => { setPage((p) => p + 1); listRef.current?.scrollTo(0, 0) }}
                      disabled={page >= Math.ceil(total / pageSize)}>下一页 ›</PageBtn>
                    <PageBtn onClick={() => { setPage(Math.ceil(total / pageSize)); listRef.current?.scrollTo(0, 0) }}
                      disabled={page >= Math.ceil(total / pageSize)}><ChevronLast size={13} /></PageBtn>
                    <span className="tnum ml-auto">
                      第 {pageSize * (page - 1) + 1}–{Math.min(total, page * pageSize)} 道，共 {total.toLocaleString()} 道
                    </span>
                  </div>
                )}
                </>)}
              </section>

              {/* ── 详情抽屉 ──
                  **浮在内容区上，不占栏**：看完就 Esc，题目栏的宽度一分不少。
                  不做点击遮罩关闭 —— 组卷时经常要"点一道看一道"，
                  抽屉开着还能继续点后面的卡片才顺手。 */}
              {dOpen && (
                <aside className="anim-slide-r absolute inset-y-0 right-0 z-30 flex
                                  w-[min(620px,64%)] flex-col border-l border-border bg-surface
                                  shadow-[var(--shadow-pop)]">
                  <div className="flex h-[52px] shrink-0 items-center gap-1 border-b border-border px-3">
                    {([['detail', '题目详情'], ['tex', 'LaTeX 源码']] as const).map(([t, label]) => (
                      <button key={t} onClick={() => setDTab(t)}
                        className={`press h-[30px] rounded-lg px-2.5 text-[12.5px] transition-colors ${
                          dTab === t ? 'bg-brand-soft font-semibold text-brand-ink'
                                     : 'text-ink-soft hover:bg-muted'}`}>
                        {label}
                      </button>
                    ))}
                    <span className="min-w-0 flex-1" />
                    <button onClick={() => setDOpen(false)} title="关闭（Esc）"
                      className="icon-btn h-[30px] w-[30px]">
                      <X size={16} />
                    </button>
                  </div>

                  {!sel ? (
                    <div className="flex flex-1 items-center justify-center text-[13px] text-ink-faint">
                      先在列表里选一道题
                    </div>
                  ) : dTab === 'tex' ? (
                    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
                      <div className="mb-2.5 flex flex-wrap items-baseline gap-2">
                        <span className="text-[13px] font-semibold">
                          {sel.point_titles?.[0] || sel.key}
                        </span>
                        <span className="text-[11.5px] text-ink-faint">
                          {sel.type_label} · <code className="font-mono">{sel.key}</code>
                        </span>
                      </div>
                      <TexSource qkey={sel.key} />
                    </div>
                  ) : (
                    <div key={sel.key} className="anim-fade-in min-h-0 flex-1">
                      <Detail q={full && full.key === sel.key ? full : sel} facets={facets}
                        onFindPoint={(pid, title) => {
                          // 点了考点就跳回列表去看那一批题：抽屉留着反而是挡路的
                          findPoint(pid, title); setDOpen(false)
                        }}
                        onDeleteAsk={() => setDeleteAsk({ qs: [sel] })}
                        onSaved={(d) => {
                          setSel(d)                              // 详情立刻反映新标签
                          setItems((xs) => xs.map((x) => (x.key === d.key ? { ...x, ...d } : x)))
                        }} />
                    </div>
                  )}
                </aside>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 快捷键浮球：这一版的单键导航没有面板可看就没人知道，所以常驻一个入口 */}
      {!FULL_PAGE.includes(tab) && tab !== 'handout' && <HelpButton />}

      {showExport && <ExportPage init={paper} pool={items} from={exportFrom}
        filters={{ q, type: L.type, kind, point: points.join(','),
                   difficulty: diffs.join(','), has: has.join(','),
                   year: years.join(',') }}
        onClose={() => setShowExport(false)} />}

      {deleteAsk && (
        <DeleteModal
          qs={deleteAsk.qs ?? items.filter((x) => (deleteAsk.keys || []).includes(x.key))}
          keys={deleteAsk.keys}
          onCancel={() => setDeleteAsk(null)}
          onConfirm={(reason, _note, pw) =>
            deleteQuestions(deleteAsk.keys ?? (deleteAsk.qs || []).map((x) => x.key), reason, pw)
              .then(() => setDeleteAsk(null))} />
      )}

      {showIngest && <IngestDrawer facets={facets} onClose={() => setShowIngest(false)}
        onDone={() => setReload((n) => n + 1)} />}

      {/* ── 讲义编辑器（全屏覆盖）──
          三栏排版需要整屏宽度；塞在面板里会被压成一条。
          这里用 fixed 覆盖整个窗口，自带关闭按钮。 */}
      {tab === 'handout' && (
        <div className="anim-fade-in fixed inset-0 z-40 flex flex-col bg-surface">
          <div className="flex h-[52px] shrink-0 items-center gap-3 border-b border-border px-4">
            <span className="text-[14px] font-semibold">讲义制作</span>
            <span className="text-[11.5px] text-ink-faint">
              拖左侧题目到中间 · 拖 ⠿ 调整顺序 · 点文字直接编辑
            </span>
            <span className="ml-auto text-[11.5px] text-ink-faint">
              共 {handoutN} 份讲义
            </span>
            <button onClick={() => setTab('workbench')}
              className="press rounded-lg border border-border bg-surface px-3 py-1.5 text-[12.5px]
                         text-ink-soft hover:border-border-strong hover:text-ink">
              退出编辑
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <CanvasEditor handoutQs={handout.length ? handout : paper} />
          </div>
        </div>
      )}
    </div>
  )
}

/* ══ 小块 ══════════════════════════════════════════ */

function PageBtn({ children, onClick, disabled }: any) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="press h-[26px] rounded-md border border-border bg-surface px-2 text-[11.5px]
                 transition-colors hover:border-border-strong hover:text-ink disabled:opacity-35">
      {children}
    </button>
  )
}

/** 首次加载的骨架。比转圈更早给出「内容大概长这样」。 */
function ListSkeleton() {
  return (
    <div className="space-y-2.5">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="rounded-[var(--radius-card)] border border-border bg-surface p-4">
          <div className="skeleton h-3 w-40" />
          <div className="mt-2.5 flex gap-1.5">
            <div className="skeleton h-4 w-14" /><div className="skeleton h-4 w-12" /><div className="skeleton h-4 w-16" />
          </div>
          <div className="mt-3 space-y-2">
            <div className="skeleton h-3.5 w-[92%]" />
            <div className="skeleton h-3.5 w-[70%]" />
          </div>
        </div>
      ))}
    </div>
  )
}

/** 卷子面板：挑好的题 + 「齐不齐」的体检 + 导出按钮。
 *  体检必须在**导出前**就看得见 —— 用户的原话是「导出的才发现没解析」。 */
function PaperPanel({ paper, onOpen, onRemove }: {
  paper: Q[]; onOpen: (q: Q) => void; onRemove: (k: string) => void
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {paper.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center text-ink-faint">
          <SlidersHorizontal size={22} className="text-border-strong" />
          <span className="text-[13px]">卷子还是空的</span>
          <span className="text-[11.5px] leading-relaxed">
            回到题目列表，在卡片上点 <b className="text-brand-ink">加入组卷</b>，
            或按住 <kbd className="rounded border border-border bg-muted px-1">↑</kbd>
            <kbd className="ml-0.5 rounded border border-border bg-muted px-1">↓</kbd> 选好再按
            <kbd className="mx-0.5 rounded border border-border bg-muted px-1">Enter</kbd>
          </span>
        </div>
      ) : (<>
        {/* 题量/分数/有解析那一行**搬到卷子条上了**（题目栏顶部那条）——
            两处都写一遍是重复，而且两处数字还可能不一致。 */}
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {/* 限宽：题目栏可能很宽，行拉满时标题和右侧的难度星会离成两截。
              840px 是「一眼能扫完一行」的宽度。 */}
          <div className="mx-auto w-full max-w-[840px] space-y-3">
          {SECTION_LABEL.map(([t, label]) => {
            const group = paper.filter((x) => x.type === t)
            if (!group.length) return null
            return (
              <div key={t}>
                <div className="mb-1.5 flex items-baseline gap-2 text-[11.5px] text-ink-faint">
                  <span className="font-semibold text-ink-soft">{label}</span>
                  <span className="tnum">{group.length} 题 · {SCORE[t] * group.length} 分</span>
                </div>
                <ol className="space-y-1.5">
                  {group.map((it, i) => (
                    <li key={it.key} onClick={() => onOpen(it)} title="点击看详情"
                      className="press group flex cursor-pointer items-center gap-2 rounded-lg border
                                 border-border bg-surface px-2.5 py-1.5 transition-colors
                                 hover:border-brand-line hover:bg-brand-soft/30">
                      <span className="tnum w-4 shrink-0 text-right text-[11.5px] text-ink-faint">{i + 1}</span>
                      <span className="min-w-0 flex-1 truncate text-[12.5px]">
                        {it.point_titles?.[0] || it.key}
                      </span>
                      {it.difficulty && (
                        <span title={it.difficulty}
                          className="shrink-0 text-[10.5px] tracking-tight text-warn">
                          {'★'.repeat(DIFF_STARS[it.difficulty] || 0)}
                        </span>
                      )}
                      <Flags flags={it.flags} />
                      <button onClick={(e) => { e.stopPropagation(); onRemove(it.key) }}
                        className="icon-btn h-5 w-5 shrink-0 opacity-0 group-hover:opacity-100"
                        title="从卷子移除">
                        <X size={13} />
                      </button>
                    </li>
                  ))}
                </ol>
              </div>
            )
          })}
          </div>
        </div>
      </>)}
    </div>
  )
}
