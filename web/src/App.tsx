/** AmMath · K12 数学工作站
 *
 *  这一版把「学段」提到最外层：小学 / 初中 / 高中各是一条独立的内容生产线，
 *  切学段之后知识图谱、讲义、题库、组卷都跟着换口径。
 *
 *  页面职责：
 *    总览      → 这个学段进行到哪、下一步做什么
 *    知识图谱  → 教材顺序 + 先修关系 + 诊断入口
 *    讲义      → 一个知识点一份「讲 · 错 · 练」
 *    题库      → 高中走完整工作台；小初走诊断题库
 *    录题      → 选择录入方式，再进同一个核对抽屉
 *    组卷      → 当前卷子、组卷方案、导出
 *    试卷库/体检/回收站/变更记录 → 管理面
 */
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, BookOpenText, BookPlus, Check, ClipboardCheck, ClipboardList, Command as CommandIcon,
  FilePlus2, FileStack, FolderOpen, History, Layers, LayoutDashboard,
  ListFilter, Network, Rows2, Rows3, Sparkles, Trash2, X,
} from 'lucide-react'
import type { Q, Overview, KeyRename, SavedHandler, SetsFollow, SourceBatchDone } from '@/lib/types'
import { api, reportErr, setGlobalErrHandler } from '@/lib/api'
import { paperScore as totalScore } from '@/lib/paper'
import { DIFF_STARS } from '@/lib/display'
import { useQuestionList } from '@/lib/useQuestionList'
import { useWidth, useFlag, useUnmount, useVw } from '@/app/ui'
import HelpButton from '@/app/HelpButton'
import { Changes } from '@/app/Stats'
import { Toaster, toast, dismissToasts } from '@/app/Toast'
import CommandPalette, { type Cmd } from '@/app/CommandPalette'
import { EMPTY_FILTERS, INITIAL_URL, writeUrlState, type UrlFilters } from '@/lib/urlState'
import { readStage, rememberStage, type Stage } from '@/lib/stage'
import { FILTER_W } from '@/lib/layout'
import Shell, { PAGE_META, type PageKey } from '@/app/Shell'
import OverviewPage from '@/app/pages/Overview'
import type { Scope } from '@/app/Health'
import type { IngestMode } from '@/app/ingest/IngestWorkspace'

/** 重页面按路由懒加载：首屏只带工作台要用的代码，其余页面首次进入才拉。
 *
 *  工作台（题库）的列表/详情抽屉共用同一个 <Suspense>（见下方 return），
 *  它们本来就在切到题库时一起挂载，一次骨架比五个各自闪一下更稳。
 *  `import type` 只留类型、不产生静态依赖，所以 Health/IngestWorkspace 的
 *  类型仍可直接引用，组件本身走 lazy。
 */
const ListHeader = lazy(() => import('@/app/ListHeader'))
const BatchTagDialog = lazy(() => import('@/app/BatchTagDialog'))
const PaperBar = lazy(() => import('@/app/PaperBar'))
const QuestionList = lazy(() => import('@/app/QuestionList'))
const DetailDrawer = lazy(() => import('@/app/DetailDrawer'))
const ExportPage = lazy(() => import('@/app/ExportPage'))
const FilterPanel = lazy(() => import('@/app/FilterPanel'))
const FilterBar = lazy(() => import('@/app/FilterBar'))
const MapPage = lazy(() => import('@/app/MapPage'))
const TopicsPage = lazy(() => import('@/app/TopicsPage'))
const Health = lazy(() => import('@/app/Health'))
const Review = lazy(() => import('@/app/pages/Review'))
const DiagnosticBank = lazy(() => import('@/app/pages/DiagnosticBank'))
const IngestHome = lazy(() => import('@/app/pages/IngestHome'))
const IngestWorkspace = lazy(() => import('@/app/ingest/IngestWorkspace'))
const ProofWorkspace = lazy(() => import('@/app/ingest/ProofWorkspace'))
const PaperStudio = lazy(() => import('@/app/pages/PaperStudio'))
const PapersPage = lazy(() => import('@/app/pages/PapersPage'))
const SetsPage = lazy(() => import('@/app/pages/SetsPage'))
const Trash = lazy(() => import('@/app/Trash').then((m) => ({ default: m.Trash })))
const DeleteModal = lazy(() => import('@/app/Trash').then((m) => ({ default: m.DeleteModal })))
// Changes 不 lazy：`app/Stats.tsx` 只有 3.7 kB，且 `groupTree` 已被 useQuestionList
// 静态引用（进 index），单独拆出去只会得到一个 INEFFECTIVE_DYNAMIC_IMPORT 警告。

const PAGES: PageKey[] = ['overview', 'map', 'lectures', 'bank', 'sets', 'ingest', 'paper', 'papers', 'health', 'review', 'trash', 'changes']
const LEGACY_TAB: Record<string, PageKey> = {
  workbench: 'bank', health: 'health', map: 'map', topics: 'lectures',
  changes: 'changes', trash: 'trash',
}
const HINTS: Record<string, PageKey> = {
  o: 'overview', b: 'bank', p: 'paper', g: 'map', t: 'lectures',
  i: 'ingest', q: 'health', a: 'papers', r: 'trash', c: 'changes',
}
/** 当前卷子的本地草稿：只存题号，题目正文仍以题库为准。
 *  组卷往往要几分钟，刷新/误关页面不该把挑好的题全丢掉。 */
const PAPER_DRAFT_KEY = 'amtiku.paper.draft.v1'

/** 详情缓存的条数上限。
 *
 *  hover 预取把整道题（含解析块）放进内存；不设上限的话，鼠标扫过
 *  几页就能攒出几百道。80 条足够覆盖当前页 + 详情往返，再多就淘汰
 *  最久未用的。 */
const FULL_CACHE_MAX = 80

function initialPage(): PageKey {
  if (PAGES.includes(INITIAL_URL.view as PageKey)) return INITIAL_URL.view as PageKey
  return LEGACY_TAB[INITIAL_URL.tab] || 'overview'
}

/** 懒加载页面的占位：沿用工作台同款浅色卡片 + 呼吸条，
 *  尺寸和留白都按页面骨架给，chunk 到位后不会整页跳一下。 */
function PageSkeleton() {
  return (
    <div role="status" aria-label="页面加载中" className="flex h-full flex-col gap-3 overflow-hidden p-4 md:p-6">
      <div className="h-7 w-44 shrink-0 animate-pulse rounded-full bg-muted/70" />
      <div className="grid shrink-0 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-[74px] animate-pulse rounded-[var(--radius-card)] bg-muted/50" />
        ))}
      </div>
      <div className="h-20 shrink-0 animate-pulse rounded-[var(--radius-card)] bg-muted/40" />
      <div className="min-h-0 flex-1 animate-pulse rounded-[var(--radius-card)] bg-muted/30" />
    </div>
  )
}

export default function App() {
  const [stage, setStageState] = useState<Stage>(() => readStage(INITIAL_URL.stage))
  const [page, setPage] = useState<PageKey>(initialPage)
  /** 试卷库里要定位到哪一份（题库卡片「组过 N 卷」跳过来时带名字）。 */
  const [paperFocus, setPaperFocus] = useState('')
  const L = useQuestionList({ stage })

  const [overview, setOverview] = useState<Overview | null>(null)
  const [ovLoading, setOvLoading] = useState(true)
  useEffect(() => {
    let alive = true
    setOvLoading(true)
    api.overview(stage)
      .then((d) => { if (alive) setOverview(d) })
      .catch(reportErr)
      .finally(() => { if (alive) setOvLoading(false) })
    return () => { alive = false }
  }, [stage, L.reload])

  useEffect(() => {
    if (!overview || overview.stage.key !== stage) return
    if (smallInit.current === stage) return
    smallInit.current = stage
    setSmallBank((overview.bank.total || 0) > 0 ? 'formal' : 'diagnostic')
  }, [overview, stage])
  // 学段包（按学段导出的独立库）里知识地图只剩一个学段。
  // 地址栏/上次记忆可能还停在别的学段：落到包里没有的那个学段，
  // 页面会空着，用户以为包坏了。以服务端给的 stages 为准纠一次。
  useEffect(() => {
    const ss = overview?.stages
    if (!ss?.length) return
    if (ss.some((s) => s.key === stage)) return
    const first = ss[0].key as Stage
    setStageState(first)
    rememberStage(first)
  }, [overview, stage])

  const [globalErr, setGlobalErr] = useState('')
  const [showExport, setShowExport] = useState(false)
  const [palette, setPalette] = useState(false)
  const [ingestMode, setIngestMode] = useState<IngestMode | ''>(
    ['ai', 'latex', 'curate', 'proof'].includes(INITIAL_URL.ingest || '') ? INITIAL_URL.ingest as IngestMode : '')
  const [batchOpen, setBatchOpen] = useState(false)
  /** 套卷页的刷新信号 / 跟卷提示：改出处后正在看的套卷要实时跟着变。 */
  const [setsRefresh, setSetsRefresh] = useState(0)
  const [setsFollow, setSetsFollow] = useState<SetsFollow | null>(null)
  const [diagPoint, setDiagPoint] = useState('')
  /** 小学/初中题库里同时有「诊断题」和「正式题」两个来源；默认看正式题（有的话）。 */
  const [smallBank, setSmallBank] = useState<'formal' | 'diagnostic'>('diagnostic')
  const smallInit = useRef('')

  /** 详情抽屉：默认开在宽屏上，关掉后记住选择。 */
  const [dOpen, setDOpen] = useFlag('amtiku.detail',
    typeof window !== 'undefined' && window.innerWidth >= 1400)
  const { shown: dShown, closing: dClosing } = useUnmount(dOpen, 170)
  const { shown: exportShown, closing: exportClosing } = useUnmount(showExport, 160)
  const [dW, setDW] = useWidth('amtiku.w.drawer.v2', 560, 380, 900)
  const [dense, setDense] = useFlag('amtiku.dense', false)
  const [compact, setCompact] = useFlag('amtiku.compact', false)
  const [maskAns, setMaskAns] = useFlag('amtiku.maskAns', true)
  const [showFilter, setShowFilter] = useFlag('amtiku.showFilter', false)
  /** 顶部筛选条是否显示（收起后表头留一颗「筛选」叫回来）。 */
  const [barOn, setBarOn] = useFlag('amtiku.filterbar.visible', true)
  const [zen, setZen] = useFlag('amtiku.zen', false)
  /** 从知识卡片跳到某一讲讲义；n 自增以允许重复点同一张卡。 */
  const [lecturePick, setLecturePick] = useState<{ id: string; n: number } | null>(null)
  const [findNote, setFindNote] = useState('')
  /** 方向键每次移动自增一次；QuestionList 只在“键盘移动”时滚动，
   *  鼠标点卡片不该把列表突然居中。 */
  const [scrollSel, setScrollSel] = useState(0)
  const searchRef = useRef<HTMLInputElement>(null)

  const vw = useVw()
  const listMin = 520
  const drawerMax = Math.max(380, Math.min(940,
    vw - 236 - (showFilter ? FILTER_W : 0) - listMin))

  /** 全量记录：列表只带题干 IR，详情要答案/解析。 */
  const [full, setFull] = useState<Q | null>(null)
  const [fullLoading, setFullLoading] = useState(false)
  /** 从「审阅」跳过来改源码：key + 自增序号。序号变一次，详情就自动打开源码编辑器。 */
  const [autoSrc, setAutoSrc] = useState<{ key: string; n: number }>({ key: '', n: 0 })
  /** 已经拿到的完整题目 + 正在请求的 key。
   *  列表 hover 就预取，点开时直接命中；避免每次打开详情都空一下再填。 */
  const fullCache = useRef(new Map<string, Q>())
  const fullPending = useRef(new Set<string>())
  const selKeyRef = useRef('')
  selKeyRef.current = L.sel?.key || ''
  /** 写入并维护 LRU：同一 key 先删再插，超上限淘汰最久未用的。 */
  const rememberFull = (key: string, d: Q) => {
    const c = fullCache.current
    c.delete(key)
    c.set(key, d)
    while (c.size > FULL_CACHE_MAX) {
      const oldest = c.keys().next().value
      if (oldest === undefined) break
      c.delete(oldest)
    }
  }
  const fetchFull = (key: string, quiet = false) => {
    if (!key || fullPending.current.has(key)) return
    const cached = fullCache.current.get(key)
    if (cached) {
      // 命中也要挪到队尾，否则“最近看过的”会被当成最旧的淘汰。
      fullCache.current.delete(key)
      fullCache.current.set(key, cached)
      if (selKeyRef.current === key) { setFull(cached); setFullLoading(false) }
      return
    }
    fullPending.current.add(key)
    if (selKeyRef.current === key) setFullLoading(true)
    api.get(key)
      .then((d) => {
        rememberFull(key, d)
        if (selKeyRef.current === key) setFull(d)
      })
      .catch((e) => { if (!quiet) reportErr(e) })
      .finally(() => {
        fullPending.current.delete(key)
        if (selKeyRef.current === key) setFullLoading(false)
      })
  }
  useEffect(() => {
    const k = L.sel?.key
    if (!k) { setFull(null); setFullLoading(false); return }
    const cached = fullCache.current.get(k)
    if (cached) {
      fullCache.current.delete(k)
      fullCache.current.set(k, cached)
      setFull(cached); setFullLoading(false)
      return
    }
    fetchFull(k)
  }, [L.sel?.key])

  useEffect(() => {
    setGlobalErrHandler(setGlobalErr)
    return () => setGlobalErrHandler(null)
  }, [])

  /* ── 卷子 ─────────────────────────────────────────── */
  const [paperMap, setPaperMap] = useState<Map<string, Q>>(new Map())
  const paper = useMemo(() => [...paperMap.values()], [paperMap])
  const paperScore = totalScore(paper)
  const answered = paper.filter((x) => x.flags['解析']).length
  const exportFrom = '卷子'
  /** 键盘 ⌘↵ 的监听器会在 effect 里闭包住 `addToPaper`；只依赖 `paperMap`
   *  会拿到旧值（实测：已入卷后按 ⌘↵ 仍提示“已加入”）。用 ref 让旧闭包
   *  也能看到当前卷子里的 key。 */
  const paperKeysRef = useRef<Set<string>>(new Set())
  paperKeysRef.current = new Set(paperMap.keys())
  /** 草稿已经读完/确认没有，才允许把当前卷子写回 localStorage；
   *  否则首屏那个空 Map 会先把上一次的草稿覆盖成 `[]`。 */
  const paperHydrated = useRef(false)

  /** 开页恢复上次的当前卷子。只存题号，不存正文——正文仍以题库为准。 */
  useEffect(() => {
    let alive = true
    let keys: string[] = []
    try {
      const raw = localStorage.getItem(PAPER_DRAFT_KEY)
      if (!raw) { paperHydrated.current = true; return }
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        keys = parsed.filter((k): k is string => typeof k === 'string' && !!k)
      }
    } catch {
      try { localStorage.removeItem(PAPER_DRAFT_KEY) } catch { /* ignore */ }
      paperHydrated.current = true
      return
    }
    if (!keys.length) { paperHydrated.current = true; return }

    ;(async () => {
      const items: Q[] = []
      let failed = false
      try {
        // `keys=` 接口一次最多 1000 道；草稿超过就分块，顺序仍按草稿。
        for (let i = 0; i < keys.length; i += 1000) {
          const chunk = keys.slice(i, i + 1000)
          const d: any = await api.list({
            keys: chunk.join(','), limit: String(chunk.length), lite: '1',
          })
          items.push(...((d?.items || []) as Q[]))
        }
      } catch (e) {
        failed = true
        reportErr(e)
      }
      if (!alive) return
      if (items.length) {
        setPaperMap((cur) => {
          const merged = new Map(items.map((q) => [q.key, q]))
          // 恢复是异步的：这期间用户手动加的题优先，不能被回填盖掉。
          for (const [k, v] of cur) merged.set(k, v)
          return merged
        })
        toast(`已恢复上次的卷子 · ${items.length} 道`, { tone: 'info' })
      } else if (!failed) {
        // 题都被删了/改名了：草稿没有价值，清掉，免得每次开页都白读一遍。
        try { localStorage.removeItem(PAPER_DRAFT_KEY) } catch { /* ignore */ }
      }
      paperHydrated.current = true
    })()

    return () => { alive = false }
  }, [])

  /** 卷子一变就落一份题号草稿（很小，不需要防抖）。
   *  导出/存档仍然走「试卷库」；这里只兜“组到一半刷新/误关”。 */
  useEffect(() => {
    if (!paperHydrated.current) return
    try {
      localStorage.setItem(PAPER_DRAFT_KEY, JSON.stringify([...paperMap.keys()]))
    } catch { /* 隐私模式或配额满：草稿存不下，但不阻断组卷 */ }
  }, [paperMap])

  const addToPaper = (it: Q, force = false) => {
    // 卡片按钮已 disabled；快捷键/撤销仍可能走到这里。
    // `force` 只给「从卷子移出 → 撤销」用：那个回调闭包里攥着旧的
    // `paperMap`，不能拿它判断“已在卷子里”。
    if (!force && paperKeysRef.current.has(it.key)) {
      toast('这道题已经在卷子里了', { tone: 'info' })
      return
    }
    setPaperMap((m) => new Map(m).set(it.key, it))
    toast(`已加入卷子 · ${it.point_titles?.[0] || it.type_label}`, {
      action: { label: '撤销', run: () => removeFromPaper(it.key) },
    })
  }
  /** 一次加一批：知识图谱「按学习路径组卷」、套卷「整卷加入」共用。
   *  文案别写死「学习路径」——套卷进来时那句会张冠李戴。 */
  const addPaperBatch = (items: Q[]) => {
    const fresh = items.filter((x) => !paperMap.has(x.key))
    if (!fresh.length) {
      toast('这些题已经在卷子里了')
      return
    }
    setPaperMap((m) => {
      const n = new Map(m)
      for (const x of items) n.set(x.key, x)
      return n
    })
    toast(`已加入卷子 · ${fresh.length} 道题`, {
      action: { label: '看卷子', run: () => setPage('paper') },
    })
  }
  const removeFromPaper = (k: string) =>
    setPaperMap((m) => { const n = new Map(m); n.delete(k); return n })

  const moveInPaper = (key: string, d: -1 | 1) => {
    setPaperMap((m) => {
      const q = m.get(key)
      if (!q) return m
      const arr = [...m.entries()]
      const same = arr.filter(([, v]) => v.type === q.type)
      const i = same.findIndex(([k]) => k === key)
      const j = i + d
      if (i < 0 || j < 0 || j >= same.length) return m
      const next = [...arr]
      const a = arr.indexOf(same[i])
      const b = arr.indexOf(same[j])
      ;[next[a], next[b]] = [next[b], next[a]]
      return new Map(next)
    })
  }
  const removeFromPaperUndo = (k: string) => {
    const it = paperMap.get(k)
    removeFromPaper(k)
    if (it) toast('已从卷子移出', { action: { label: '撤销', run: () => addToPaper(it, true) } })
  }
  const clearPaper = () => {
    if (!paper.length) return
    const gone = [...paperMap.entries()]
    setPaperMap(new Map())
    dismissToasts()
    toast(`已清空卷子（${gone.length} 道）`, {
      tone: 'warn', ms: 8000,
      action: {
        label: '撤销',
        run: () => setPaperMap((m) => {
          const n = new Map(m)
          for (const [k, v] of gone) if (!n.has(k)) n.set(k, v)
          return n
        }),
      },
    })
  }
  const loadPaper = (items: Q[]) => {
    setPaperMap(new Map(items.map((q) => [q.key, q])))
    setPage('paper')
    toast(`已载入 ${items.length} 道题`, { tone: 'info' })
  }
  const openSavedPaper = async (name: string) => {
    try {
      const p: any = await api.paper(name)
      if (!p?.keys?.length) { toast('这份存档没有题号', { tone: 'warn' }); return }
      if (p.keys.length > 1000) { toast('存档超过 1000 道，暂不支持一次载入', { tone: 'warn' }); return }
      const d: any = await api.list({ keys: p.keys.join(','), limit: '1000', lite: '1' })
      loadPaper((d.items || []) as Q[])
    } catch (e) { reportErr(e) }
  }

  const showDetail = (it: Q) => {
    L.setSel(it); setDOpen(true)
    const cached = fullCache.current.get(it.key)
    if (cached) { setFull(cached); setFullLoading(false) }
    else { setFullLoading(true); fetchFull(it.key) }
  }

  const findPoint = (pid: string, title: string) => {
    // **定位，不是反选**：这是详情里「找同类」的入口，点谁就该看到谁。
    // 用 toggle 的话，当前筛 A 点 B 会变成 A∪B，点 A 自己反而取消筛选变成全库。
    L.setPoints([pid])
    L.setQ('')
    L.setPage(1)
    setFindNote(title)
    setShowFilter(true)
  }

  /* ── 删除 / 批量 ──────────────────────────────────── */
  const [deleteAsk, setDeleteAsk] = useState<
    { qs: Q[]; keys?: never } | { keys: string[]; qs?: never } | null>(null)
  const deleteQuestions = (keys: string[], reason: string) => {
    // 删除会顺手从当前卷子里摘掉；撤销时把它们放回去（位置排到最后，
    // 但至少不用重新找一遍题）。卷子顺序的完整还原留给「试卷库」。
    const fromPaper = keys
      .map((k) => paperMap.get(k))
      .filter((q): q is Q => !!q)
    return api.trashBatch(keys, reason).then(() => {
      const ks = new Set(keys)
      const goneVisible = L.items.filter((x) => ks.has(x.key)).length
      L.setItems((xs) => xs.filter((x) => !ks.has(x.key)))
      L.setTotal((t) => Math.max(0, t - goneVisible))
      L.setSel((cur) => {
        if (!cur || !ks.has(cur.key)) return cur
        const i = L.items.findIndex((x) => x.key === cur.key)
        const after = L.items.slice(Math.max(0, i + 1)).find((x) => !ks.has(x.key))
        const before = L.items.slice(0, Math.max(0, i)).reverse().find((x) => !ks.has(x.key))
        return after ?? before ?? null
      })
      for (const k of keys) fullCache.current.delete(k)
      setFull((f) => (f && ks.has(f.key) ? null : f))
      setFullLoading(false)
      setPaperMap((m) => { const n = new Map(m); for (const k of ks) n.delete(k); return n })
      L.setChecked((c) => { const n = new Set(c); for (const k of ks) n.delete(k); return n })
      L.setCheckedMap((m) => { const n = new Map(m); for (const k of ks) n.delete(k); return n })
      L.refreshSilent()
      setSetsRefresh((v) => v + 1)
      toast(`已移入回收站 ${keys.length} 道`, {
        tone: 'warn', ms: 8000,
        action: {
          label: '撤销',
          run: () => {
            api.trashRestore(keys).then(() => {
              if (fromPaper.length) {
                setPaperMap((m) => {
                  const n = new Map(m)
                  for (const q of fromPaper) n.set(q.key, q)
                  return n
                })
              }
              L.refreshSilent()
              setSetsRefresh((v) => v + 1)
            }).catch(reportErr)
          },
        },
      })
    }).catch((e) => {
      // 交给删除弹窗显示；**不要吞掉**，否则失败也像成功一样关窗。
      reportErr(e)
      throw e
    })
  }

  const addChecked = () => {
    const picked = [...L.checkedMap.values()]
    const added = picked.filter((x) => !paperMap.has(x.key))
    setPaperMap((m) => {
      const n = new Map(m)
      for (const x of picked) n.set(x.key, x)
      return n
    })
    L.exitSelect()
    if (added.length) {
      toast(`已加入卷子 ${added.length} 道`, {
        action: { label: '撤销', run: () => setPaperMap((m) => {
          const n = new Map(m); for (const x of added) n.delete(x.key); return n
        }) },
      })
    }
  }

  const remapKey = (oldKey: string, q: Q) => {
    if (!oldKey || !q?.key || oldKey === q.key) return
    const swap = (m: Map<string, Q>) => {
      if (!m.has(oldKey)) return m
      const arr = [...m.entries()]
      const i = arr.findIndex(([k]) => k === oldKey)
      if (i < 0) return m
      arr[i] = [q.key, q]
      return new Map(arr)
    }
    setPaperMap(swap)
    L.setCheckedMap(swap)
    L.setChecked((s) => {
      if (!s.has(oldKey)) return s
      const n = new Set(s); n.delete(oldKey); n.add(q.key); return n
    })
  }

  /** 批量改出处后的本地引用迁移。
   *
   *  后端会把 `书/卷名#号` 重拼成新 key 并回传 `renames`；但 `paperMap`
   *  只存题对象，不会自己跟着变。不迁的话，卷子里那道题仍拿旧 key，
   *  导出时才报「找不到题」。单题保存已有 `remapKey`，这里是它的批量版。 */
  const remapBatch = (renames: KeyRename[]) => {
    if (!renames.length) return
    const byOld = new Map(renames.map((r) => [r.old, r]))
    const patched = (q: Q, r: KeyRename): Q => {
      const meta: Record<string, unknown> = {
        ...q.meta,
        book: r.book ?? q.meta?.book ?? '',
        source_label: r.label ?? q.meta?.source_label ?? '',
      }
      if (r.year === '' || r.year == null) delete meta.year
      else meta.year = r.year
      return { ...q, key: r.new, meta: meta as Q['meta'] }
    }
    setPaperMap((m) => {
      let changed = false
      const next = new Map<string, Q>()
      for (const [k, q] of m) {
        const r = byOld.get(k)
        if (r) { next.set(r.new, patched(q, r)); changed = true }
        else next.set(k, q)
      }
      return changed ? next : m
    })
    // 勾选也存 key：批量改出处后不清，下一次「加入卷子/删除选中」会拿旧 key 去查。
    // （勾选里没有改名的题时原样返回，避免无谓重渲染。）
    L.setChecked((s) => {
      let changed = false
      const next = new Set<string>()
      for (const k of s) {
        const r = byOld.get(k)
        if (r) { next.add(r.new); changed = true }
        else next.add(k)
      }
      return changed ? next : s
    })
    L.setCheckedMap((m) => {
      let changed = false
      const next = new Map<string, Q>()
      for (const [k, q] of m) {
        const r = byOld.get(k)
        if (r) { next.set(r.new, patched(q, r)); changed = true }
        else next.set(k, q)
      }
      return changed ? next : m
    })
    for (const r of renames) {
      const cached = fullCache.current.get(r.old)
      if (cached) {
        fullCache.current.delete(r.old)
        rememberFull(r.new, patched(cached, r))
      }
    }
    setFull((f) => {
      const r = f ? byOld.get(f.key) : undefined
      return f && r ? patched(f, r) : f
    })
    L.setSel((cur) => {
      const r = cur ? byOld.get(cur.key) : undefined
      return cur && r ? patched(cur, r) : cur
    })
    L.setItems((xs) => {
      let changed = false
      const next = xs.map((x) => {
        const r = byOld.get(x.key)
        if (!r) return x
        changed = true
        return patched(x, r)
      })
      return changed ? next : xs
    })
  }
  /** 详情页保存成功后的统一落点（单题改标签 / 改源码 / 批量改出处共用）。
   *
   *  以前这段逻辑内联在 `<DetailDrawer onSaved={…}>` 里；批量改出处也要
   *  用同一套（换 key、刷缓存、更新当前题），抽出来免得两份口径分叉。 */
  const applySaved: SavedHandler = (d, opts) => {
    const oldKey = (full ?? L.sel)?.key || d.key
    if (oldKey !== d.key) remapKey(oldKey, d)
    const freshen = (m: Map<string, Q>) => m.has(d.key) ? new Map(m).set(d.key, d) : m
    setPaperMap(freshen)
    L.setSel(d)
    setFull(d)
    setFullLoading(false)
    if (oldKey !== d.key) fullCache.current.delete(oldKey)
    rememberFull(d.key, d)
    L.setItems((xs) => xs.map((x) => (x.key === d.key ? { ...x, ...d } : x)))
    if (opts?.refreshList) {
      if (opts.silent) L.refreshSilent()
      else L.setReload((v) => v + 1)
    }
    // 套卷列表/明细派生自 `meta.source_label`：改出处（或年份/书名）后，
    // 正在看的套卷也要实时变。卷名变了就告诉 SetsPage 从旧卷跟到新卷——
    // 否则旧标题从列表里消失，页面会跳去第一份卷，而不是改名后的那一份。
    const prevQ = full ?? L.sel
    const prevLabel = String(prevQ?.meta?.source_label || '')
    const nextLabel = String(d.meta?.source_label || '')
    if (prevQ && prevLabel && nextLabel && prevLabel !== nextLabel) {
      // nonce 用时间戳：刷新页面后计数器会归零，时间戳不会和上一轮
      // 「已消费」的 nonce 撞车（SetsPage 用 sessionStorage 记住消费过的值）。
      setSetsFollow({ from: prevLabel, to: nextLabel, nonce: Date.now() })
    }
    setSetsRefresh((v) => v + 1)
  }

  /** 批量改出处完成：**先迁 key**（卷子/勾选/详情缓存都存 key），
   *  再用后端回传的当前题刷新详情。没回传就静默重拉列表。 */
  const batchSourceDone = (res: SourceBatchDone) => {
    remapBatch(res.renames || [])
    if (res.current) applySaved(res.current, { refreshList: true, silent: true })
    else {
      L.refreshSilent()
      setSetsRefresh((v) => v + 1)
    }
  }

  const replaceInPaper = (oldKey: string, q: Q) => {
    const old = paperMap.get(oldKey)
    setPaperMap((m) => {
      const arr = [...m.entries()]
      const i = arr.findIndex(([k]) => k === oldKey)
      if (i < 0) return m
      arr[i] = [q.key, q]
      return new Map(arr)
    })
    if (old) {
      toast(`已换题 · ${q.point_titles?.[0] || q.type_label}`, {
        action: {
          label: '撤销',
          run: () => setPaperMap((m) => {
            const arr = [...m.entries()]
            const i = arr.findIndex(([k]) => k === q.key)
            if (i < 0) return m
            arr[i] = [old.key, old]
            return new Map(arr)
          }),
        },
      })
    }
  }

  /* ── 导航 ─────────────────────────────────────────── */
  const gotoPaper = () => {
    setPage('paper')
    if (!paper.length) toast('卷子还是空的 —— 先在题库里点「加入卷子」', { tone: 'info' })
  }

  /** 录入是独立工作区：从当前页面开一个新标签页，原页面（筛选、卷子、详情）
   *  一概不动。新页只带 `view=ingest` 和当前学段。
   *
   *  用 `window.open` 而不是 `target=_blank` 的链接，是为了在浏览器拦截
   *  新窗口时能明确告诉用户，而不是“点了没反应”。 */
  const openIngestTab = () => {
    const url = new URL(window.location.href)
    const sp = new URLSearchParams()
    sp.set('view', 'ingest')
    if (stage !== 'senior') sp.set('stage', stage)
    url.search = sp.toString()
    url.hash = ''
    const w = window.open(url.toString(), '_blank')
    if (!w) {
      toast('浏览器拦截了新页面：请允许本站弹窗后再点「录入」', { tone: 'warn' })
      return
    }
    try { w.opener = null } catch { /* same-origin 下一般能设；设不了也不影响使用 */ }
  }

  /** 录入页在另一个标签页提交后，通过 localStorage 广播回来；
   *  原工作台收到就把列表和总览数字刷新一遍。 */
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== 'ammath.ingest.updated') return
      L.setReload((v) => v + 1)
      api.overview(stage).then(setOverview).catch(() => { /* 刷新失败不打断原页面 */ })
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [stage, L.setReload])

  const switchStage = (s: Stage) => {
    if (s === stage) return
    setStageState(s)
    rememberStage(s)
    L.loadFilters(EMPTY_FILTERS, 'used')
    setDiagPoint('')
    setFindNote('')
  }

  /** 卡片「组过 N 卷」→ 试卷库，并把搜索框钉在那份卷名上。 */
  const openPaperInArchive = (name: string) => {
    setPaperFocus(name)
    setPage('papers')
  }

  const openTask = (p: PageKey, filters: Record<string, string>) => {
    setPage(p)
    if (p === 'bank') {
      L.loadFilters({ ...EMPTY_FILTERS, ...filters } as UrlFilters, 'used')
      setShowFilter(true)
    }
  }

  const openPoint = (id: string, pointStage?: Stage) => {
    const target = pointStage || stage
    if (target !== stage) {
      setStageState(target)
      rememberStage(target)
      L.loadFilters(EMPTY_FILTERS, 'used')
    }
    setPage('bank')
    setShowFilter(false)
    setFindNote('')
    if (target === 'senior') {
      L.loadFilters({ ...EMPTY_FILTERS, point: id }, 'used')
      setDiagPoint('')
    } else {
      setDiagPoint(id)
    }
  }

  /** 把一道题带到题库工作台：**清掉旧筛选**、按 key 搜索、选中并开详情。
   *
   *  讲义「工作台打开」和审阅「去改源码」共用这一条路。以前 `openQuestion`
   *  只把 key 塞进搜索框，旧的考点/出处/难度筛选还留着：目标题被筛掉时
   *  会落到 0 结果，用户以为题没了。 */
  const focusQuestion = async (key: string, openSourceEditor = false) => {
    setPage('bank')
    setShowFilter(false)
    L.loadFilters({ ...EMPTY_FILTERS, q: key }, 'used')
    try {
      const d: Q = await api.get(key)
      rememberFull(key, d)
      setFull(d)
      setFullLoading(false)
      L.setSel(d)
      setDOpen(true)
      // 让列表把选中项滚进视口（搜索 key 可能命中同前缀的十来道）。
      setScrollSel((n) => n + 1)
      if (openSourceEditor) setAutoSrc((x) => ({ key, n: x.n + 1 }))
    } catch (e) {
      reportErr(e)
    }
  }

  const openQuestion = (key: string) => {
    if (stage !== 'senior') {
      setPage('bank')
      return
    }
    void focusQuestion(key)
  }

  /** 从审阅工作台跳过来：顺便直接打开「改源码」。 */
  const openSourceQuestion = (key: string) => { void focusQuestion(key, true) }

  const openScope = (s: Scope) => {
    setPage('bank')
    L.loadFilters({
      ...EMPTY_FILTERS,
      q: s.q ?? '',
      point: (s.points ?? []).join(','),
      missing: (s.missing ?? []).join(','),
      year: (s.years ?? []).join(','),
      psrc: s.pointSource ?? '',
      reviewed: s.reviewed ?? '',
    }, 'used')
    setFindNote(s.note ?? '')
    setShowFilter(true)
  }

  /* ── 地址栏 ───────────────────────────────────────── */
  useEffect(() => {
    writeUrlState({
      filters: {
        q: L.filters.q, type: L.filters.type, kind: L.filters.kind,
        point: L.filters.point, pm: L.filters.point_mode,
        diff: L.filters.difficulty, year: L.filters.year,
        source: L.filters.source, has: L.filters.has, missing: L.filters.missing,
        inc: L.filters.incomplete,
        scope: L.filters.region_scope, paper: L.filters.paper_state,
        star: L.filters.star_state, quality: L.filters.quality,
        psrc: L.filters.point_source, asrc: L.filters.answer_source,
        reviewed: L.filters.reviewed,
      },
      sort: L.sort, page: L.page, tab: '', view: page, stage,
      ingest: page === 'ingest' ? ingestMode : '',
    })
  }, [L.filters, L.sort, L.page, page, stage, ingestMode])

  // 离开录入页就回到“选择来源”，下一次从导航进来是干净的入口。
  useEffect(() => {
    if (page !== 'ingest' && ingestMode) setIngestMode('')
  }, [page, ingestMode])

  useEffect(() => { setFindNote('') }, [L.q, L.has, L.missing, L.diffs, L.years])

  /* ── 快捷键 ───────────────────────────────────────── */
  useEffect(() => {
    const typing = () => {
      const el = document.activeElement as HTMLElement | null
      if (!el) return false
      const tag = el.tagName
      return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.isComposing || e.keyCode === 229) return
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault(); setPalette((v) => !v); return
      }
      if (e.key === 'Escape' && palette) { e.preventDefault(); setPalette(false); return }
      if (e.key === '/' && !typing()) {
        e.preventDefault(); searchRef.current?.focus(); return
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        if (showExport || palette) return
        if (L.sel) addToPaper(L.sel)
        return
      }
      if (palette) return
      if (e.key === 'Escape') {
        if (showExport) { setShowExport(false); return }
        if (dOpen) { setDOpen(false); return }
        if (L.selectMode && L.checkedMap.size) { L.exitSelect(); return }
        return
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (typing()) return
      if (showExport) return
      // 录入页是独立工作区：单键导航在这里一律不生效，避免误触把页面带走。
      if (page === 'ingest') return

      const k = e.key.toLowerCase()
      if (HINTS[k]) {
        e.preventDefault()
        if (HINTS[k] === 'ingest') openIngestTab()
        else setPage(HINTS[k])
        return
      }
      if (k === 'z' && (page === 'bank' || zen)) { e.preventDefault(); setZen((v) => !v); return }
      if (page !== 'bank') return

      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (!L.items.length) return
        e.preventDefault()
        const cur = L.items.findIndex((x) => x.key === L.sel?.key)
        const step = e.key === 'ArrowDown' ? 1 : -1
        const next = cur < 0 ? 0 : Math.max(0, Math.min(L.items.length - 1, cur + step))
        L.setSel(L.items[next])
        // 滚动/扩容由 QuestionList 负责：密排是 div，卡片也只渲染前 N 张，
        // 在这里用 `querySelectorAll('article')` 两种视图都会漏。
        setScrollSel((n) => n + 1)
        return
      }
      const onControl = !!(document.activeElement as HTMLElement | null)
        ?.closest?.('button, [role="checkbox"], a')
      if (onControl) return
      if (e.key === 'Enter' && L.sel) { e.preventDefault(); setDOpen(true); return }
      if (e.key === ' ' && L.sel) {
        e.preventDefault()
        const i = L.items.findIndex((x) => x.key === L.sel!.key)
        L.toggleCheck(L.sel, i >= 0 ? i : null, e.shiftKey)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [L.items, L.sel, page, dOpen, palette, showExport, stage])

  /* ── 命令面板 ─────────────────────────────────────── */
  const commands: Cmd[] = useMemo(() => {
    const navIcon: Record<PageKey, React.ReactNode> = {
      overview: <LayoutDashboard size={13} />, map: <Network size={13} />,
      lectures: <BookOpenText size={13} />, bank: <ListFilter size={13} />,
      sets: <Layers size={13} />,
      ingest: <FilePlus2 size={13} />, paper: <FileStack size={13} />,
      papers: <FolderOpen size={13} />, health: <Activity size={13} />,
      review: <ClipboardCheck size={13} />, trash: <Trash2 size={13} />,
      changes: <History size={13} />,
    }
    const navWords: Record<PageKey, string> = {
      overview: 'zonglan overview home 总览 首页 工作台',
      map: 'zhishitupu map knowledge 知识图谱 教材 先修 小学 初中 高中',
      lectures: 'jiangyi lecture topic 讲义 专题 易错 练习',
      bank: 'tiku bank quest 题库 找题 搜题',
      sets: 'taojuan sets 套卷 原卷 整卷 高考卷 真题卷',
      ingest: 'luru ingest import 录题 录入 新建',
      paper: 'zujuan paper 组卷 导出 pdf',
      papers: 'shijuan library 试卷库 存档 合集',
      health: 'tijian health 体检 缺口 覆盖',
      review: 'shenye review 审阅 复核 抽样 风险 队列',
      trash: 'huishouzhan trash 回收站 删除',
      changes: 'biangeng changes 变更 记录',
    }
    const out: Cmd[] = PAGES.map((p) => ({
      id: `nav:${p}`, label: PAGE_META[p].title, group: '去',
      icon: navIcon[p], keywords: navWords[p],
      hint: p === 'ingest' ? '新页' : undefined,
      run: () => {
        if (p !== 'ingest') { setPage(p); return }
        if (page !== 'ingest') openIngestTab()
      },
    }))
    out.push(
      { id: 'view:filter', label: showFilter ? '收起筛选面板' : '展开筛选面板', group: '看',
        icon: <ListFilter size={13} />, keywords: 'shaixuan filter 筛选 考点',
        run: () => { setPage('bank'); setShowFilter(!showFilter) } },
      { id: 'view:dense', label: dense ? '切换成宽松卡片' : '切换成紧凑卡片', group: '看',
        icon: dense ? <Rows3 size={13} /> : <Rows2 size={13} />,
        keywords: 'midu density 密度 紧凑', run: () => setDense(!dense) },
      { id: 'view:compact', label: compact ? '切回卡片视图' : '切到密排视图（一行一道）', group: '看',
        icon: compact ? <LayoutDashboard size={13} /> : <Rows3 size={13} />,
        keywords: 'mipai compact 密排 一行 列表 布局', run: () => setCompact(!compact) },
      { id: 'view:select', label: L.selectMode ? '关掉多选模式' : '打开多选模式', group: '看',
        icon: <Check size={13} />, keywords: 'duoxuan select 多选 勾选',
        run: () => (L.selectMode ? L.exitSelect() : L.setSelectMode(true)) },
      { id: 'act:export', label: '打开组卷导出', group: '做', icon: <Sparkles size={13} />,
        keywords: 'daochu export zujuan pdf 导出 组卷', run: () => setShowExport(true) },
      { id: 'act:ingest', label: '录入题目', group: '做', icon: <FilePlus2 size={13} />,
        hint: 'I', keywords: 'luru ingest 录题 录入 手工 粘贴',
        run: () => { if (page !== 'ingest') openIngestTab() } },
      { id: 'act:help', label: '查看键盘快捷键', group: '做', icon: <CommandIcon size={13} />,
        hint: '?', keywords: 'kuaijiejian shortcut help 快捷键 帮助',
        run: () => window.dispatchEvent(new CustomEvent('amtiku:help')) },
      { id: 'act:points-clear', label: `清除全部筛选（${L.activeFilters} 项）`, group: '做',
        icon: <X size={13} />, keywords: 'qingchu clear filter 清除 重置',
        run: () => { setPage('bank'); clearAllFilters() } },
    )
    if (paper.length) {
      out.push(
        { id: 'act:paper-view', label: `看卷子（${paper.length} 题 · ${paperScore} 分）`, group: '做',
          icon: <ClipboardList size={13} />, keywords: 'juanzi 卷子 查看', run: gotoPaper },
        { id: 'act:paper-clear', label: `清空卷子（${paper.length} 题）`, group: '做',
          icon: <Trash2 size={13} />, keywords: 'qingkong 清空 卷子', run: clearPaper },
      )
    }
    if (L.facets?.kinds) {
      for (const k of L.facets.kinds) {
        out.push({
          id: `kind:${k.value}`, label: L.kind === k.value ? `回到全部（现在只看${k.value}）` : `只看${k.value}题`,
          group: '看', icon: <BookPlus size={13} />, keywords: `${k.value} fanwei scope 范围`,
          run: () => { setPage('bank'); L.setKind(L.kind === k.value ? '' : k.value) },
        })
      }
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [L.facets, L.kind, L.selectMode, showFilter, dense, compact, paper.length, paperScore, L.activeFilters, stage, page])

  /* ── 筛选胶囊 ─────────────────────────────────────── */
  const clearAllFilters = () => {
    L.setHas([]); L.setMissing([]); L.setIncomplete(false)
    L.setPoints([]); L.setDiffs([])
    L.setYears([]); L.setSources([]); L.setPointSource(''); L.setType(''); L.setKind(''); L.setQ('')
    L.setScopes([]); L.setPaperStates([]); L.setStarStates([]); L.setQualities([])
    L.setAnswerSources([]); L.setReviewed('')
    setFindNote('')
  }
  const scopeChips: { key: string; label: string; clear: () => void }[] = (() => {
    const out: { key: string; label: string; clear: () => void }[] = []
    if (L.q.trim()) out.push({ key: 'q', label: `搜「${L.q.trim()}」`, clear: () => L.setQ('') })
    if (L.scopeName) {
      out.push({ key: 'scope', label: L.scopeName, clear: () => L.setPoints([]) })
    } else if (L.points.length === 1) {
      const title = findNote
        || (L.facets?.points || []).find((x) => x.value === L.points[0])?.title
        || L.points[0]
      out.push({ key: 'p1', label: `考点 · ${title}`, clear: () => { L.setPoints([]); setFindNote('') } })
    } else if (L.points.length > 1) {
      out.push({ key: 'pn', label: `考点 · ${L.points.length} 个`, clear: () => L.setPoints([]) })
    }
    if (L.type) out.push({
      key: 'type', label: L.facets?.types.find((t) => t.value === L.type)?.label || L.type,
      clear: () => L.setType(''),
    })
    if (L.kind) out.push({ key: 'kind', label: `${L.kind}题`, clear: () => L.setKind('') })
    for (const s of L.sources) out.push({
      key: `src-${s}`, label: `出处 · ${s}`,
      clear: () => L.setSources((xs) => xs.filter((x) => x !== s)),
    })
    if (L.pointSource) out.push({
      key: 'psrc',
      label: L.pointSource === '无' ? '考点来源未记' : `考点来源 · ${L.pointSource}`,
      clear: () => L.setPointSource(''),
    })
    for (const d of L.diffs) out.push({
      key: `d${d}`, label: `难度 ${'★'.repeat(DIFF_STARS[d] || 0)}`,
      clear: () => L.setDiffs((xs) => xs.filter((x) => x !== d)),
    })
    for (const y of L.years) out.push({
      key: `y${y}`, label: `${y} 年`, clear: () => L.setYears((xs) => xs.filter((x) => x !== y)),
    })
    for (const m of L.missing) out.push({
      key: `m${m}`, label: `缺${m}`, clear: () => L.setMissing((xs) => xs.filter((x) => x !== m)),
    })
    for (const h of L.has) out.push({
      key: `h${h}`, label: h.startsWith('有') ? h : `有${h}`,
      clear: () => L.setHas((xs) => xs.filter((x) => x !== h)),
    })
    for (const s of L.scopes) out.push({
      key: `sc-${s}`, label: `地区 · ${s}`, clear: () => L.setScopes((xs) => xs.filter((x) => x !== s)),
    })
    for (const s of L.paperStates) out.push({
      key: `ps-${s}`, label: `试卷 · ${s}`, clear: () => L.setPaperStates((xs) => xs.filter((x) => x !== s)),
    })
    for (const s of L.starStates) out.push({
      key: `ss-${s}`, label: `星级 · ${s}`, clear: () => L.setStarStates((xs) => xs.filter((x) => x !== s)),
    })
    for (const s of L.qualities) out.push({
      key: `ql-${s}`, label: `质量 · ${s}`, clear: () => L.setQualities((xs) => xs.filter((x) => x !== s)),
    })
    for (const s of L.answerSources) out.push({
      key: `as-${s}`,
      label: `答案来源 · ${({ human: '人工', workbuddy: '模型', legacy: '历史存量' } as Record<string, string>)[s] || s}`,
      clear: () => L.setAnswerSources((xs) => xs.filter((x) => x !== s)),
    })
    if (L.reviewed) out.push({
      key: 'rv', label: L.reviewed === 'yes' ? '已复核' : '未复核',
      clear: () => L.setReviewed(''),
    })
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  })()

  /* ── 渲染 ─────────────────────────────────────────── */
  const openLecture = (id: string) => {
    setLecturePick((p) => ({ id, n: (p?.n || 0) + 1 }))
    setPage('lectures')
  }
  const selIdx = L.sel ? L.items.findIndex((x) => x.key === L.sel!.key) : -1
  const canPrev = selIdx > 0
  const canNext = selIdx >= 0 && selIdx < L.items.length - 1
  const stepSel = (delta: number) => {
    if (!L.items.length) return
    const cur = selIdx < 0 ? (delta > 0 ? -1 : L.items.length) : selIdx
    const next = Math.max(0, Math.min(L.items.length - 1, cur + delta))
    if (next === selIdx) return
    L.setSel(L.items[next])
    setScrollSel((n) => n + 1)
  }
  const workbench = (
    <div className="flex h-full min-h-0 flex-col">
      {/* 筛选条**横跨列表与详情两列**：放在两列之外的上方，
          列表列再窄也不会把它挤断（之前塞在列表列里，完整度/质量被裁掉）。 */}
      {/* 专注模式下也留着：专注是「少点干扰」，不是「不能筛」——
          一进专注就把筛选藏掉，反而要退出专注才能换条件。 */}
      {barOn && (
        <FilterBar L={L} total={L.total} loading={L.loading}
          onHide={() => setBarOn(false)} />
      )}
      <div className="relative flex min-h-0 flex-1">
      {showFilter && (<>
        <div className="absolute inset-0 z-40 bg-scrim xl:hidden" onClick={() => setShowFilter(false)} />
        <div className="relative z-50 flex max-xl:absolute max-xl:inset-y-0 max-xl:left-0
                        max-xl:shadow-[var(--shadow-pop)] xl:relative">
          {/* 单独给边界：知识点栏首次展开时才加载，加载期间只空出这一栏，
              不要把整页（列表/详情）换成骨架。 */}
          <Suspense fallback={null}>
            <FilterPanel L={L} onClose={() => setShowFilter(false)} onMap={() => setPage('map')}
              onClearAll={clearAllFilters} />
          </Suspense>
        </div>
      </>)}
      <section className="flex min-w-0 flex-1 flex-col">
        <ListHeader
          L={L} total={L.total} loading={L.loading} scopeChips={scopeChips}
          showFilter={showFilter} onShowFilter={() => setShowFilter(true)}
          barHidden={!barOn} onShowBar={() => setBarOn(true)}
          clearAllFilters={clearAllFilters}
          dense={dense} onDense={() => setDense(!dense)}
          compact={compact} onCompact={() => setCompact(!compact)}
          maskAns={maskAns} onMaskAns={() => setMaskAns(!maskAns)}
          zen={zen} onZen={() => setZen(!zen)}
          onDeleteChecked={() => setDeleteAsk({ qs: [...L.checkedMap.values()] })}
          onAddChecked={addChecked}
          onBatchEdit={() => setBatchOpen(true)}
          view="list" />
        <PaperBar paper={paper} paperScore={paperScore} answered={answered}
          view="list" onToggleView={gotoPaper}
          onClear={clearPaper} onExport={() => setShowExport(true)} />
        <QuestionList L={L} dense={dense} compact={compact} maskAns={maskAns}
          paperMap={paperMap} scrollSignal={scrollSel}
          onSelect={(it) => L.setSel(it)}
          onOpen={showDetail} onAdd={addToPaper}
          onOpenPaper={openPaperInArchive}
          onPrefetch={(k) => fetchFull(k, true)}
          onClearFilters={clearAllFilters} />
      </section>
      <DetailDrawer open={dShown} closing={dClosing} width={dW} setWidth={setDW}
        sel={L.sel} full={full} loadingFull={fullLoading} facets={L.facets} loading={L.loading} kw={L.q.trim()}
        maxWidth={vw >= 1400 ? drawerMax : undefined}
        onClose={() => setDOpen(false)} onFindPoint={findPoint}
        onPrev={() => stepSel(-1)} onNext={() => stepSel(1)}
        canPrev={canPrev} canNext={canNext}
        position={selIdx >= 0 ? { i: selIdx + 1, n: L.items.length } : null}
        autoSourceKey={autoSrc.key} autoSourceN={autoSrc.n}
        onDeleteAsk={() => L.sel && setDeleteAsk({ qs: [L.sel] })}
        onPick={(it) => {
          L.setSel(it); setFull(it); setFullLoading(false)
          rememberFull(it.key, it); setDOpen(true)
        }}
        onSaved={applySaved}
        onBatchSource={batchSourceDone} />
      </div>
    </div>
  )

  const bankView = stage === 'senior' ? workbench : (
    <div className="flex h-full min-h-0 flex-col">
      {(overview?.bank.total || 0) > 0 && (
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-border
                        bg-surface px-4 py-1.5">
          <button onClick={() => setSmallBank('formal')}
            className={`b-chip ${smallBank === 'formal' ? 'b-chip-on' : ''}`}>
            正式题库 <span className="tnum">{overview?.bank.total || 0}</span>
          </button>
          <button onClick={() => setSmallBank('diagnostic')}
            className={`b-chip ${smallBank === 'diagnostic' ? 'b-chip-on' : ''}`}>
            诊断题 <span className="tnum">{overview?.diagnostics.total || 0}</span>
          </button>
          <span className="ml-1 text-[10.5px] text-ink-faint">
            正式题按册章筛；诊断题按教材位置筛
          </span>
        </div>
      )}
      <div className="min-h-0 flex-1">
        {smallBank === 'formal' ? workbench : (
          <DiagnosticBank stage={stage} point={diagPoint} search={L.q} onSearch={L.setQ}
            onClearPoint={() => setDiagPoint('')}
            onOpenPoint={openPoint} onIngest={openIngestTab}
            onBank={() => setPage('bank')} />
        )}
      </div>
    </div>
  )

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      <div className="app-ambient" aria-hidden>
        <div className="app-aurora" />
        <div className="app-grid" />
        <span className="orb orb-cyan" />
        <span className="orb orb-violet" />
        <span className="orb orb-magenta" />
      </div>
      <div className="relative z-10 flex min-h-0 flex-1 flex-col">
      {globalErr && (
        <div className="anim-slide-d flex shrink-0 items-center gap-2 border-b border-warn-line
                        bg-warn-soft px-4 py-2 text-[12.5px] text-warn">
          <span className="font-semibold">出错了</span>
          <span className="min-w-0 flex-1 truncate" title={globalErr}>{globalErr}</span>
          <button onClick={() => setGlobalErr('')} className="icon-btn h-6 w-6 shrink-0"><X size={14} /></button>
        </div>
      )}
      <div className="min-h-0 flex-1">
        <Shell
          stage={stage} onStage={switchStage} page={page} onPage={setPage}
          data={overview} paperCount={paper.length}
          query={L.q} onQuery={(v) => { L.setQ(v); if (page !== 'bank' && v) setPage('bank') }}
          onPalette={() => setPalette(true)} zen={zen} onZen={() => setZen(false)} detailOpen={dShown}
          onPaper={gotoPaper}
          onOpenIngest={openIngestTab}
          onHelp={() => window.dispatchEvent(new CustomEvent('amtiku:help'))}
          searchRef={searchRef}>
          <Suspense fallback={<PageSkeleton />}>
          {page === 'overview' ? (
            <OverviewPage stage={stage} data={overview} loading={ovLoading}
              onStage={switchStage} onPage={setPage} onTask={openTask}
              onPaper={gotoPaper} onIngest={openIngestTab}
              onReview={() => setPage('review')}
              onOpenPaper={openSavedPaper}
              paper={paper} score={paperScore} answered={answered} />
          ) : page === 'map' ? (
            <MapPage stage={stage} onPickPoint={openPoint} onAddPaper={addPaperBatch} onOpenLecture={openLecture} />
          ) : page === 'lectures' ? (
            <TopicsPage stage={stage} onPickPoint={openPoint} onOpenQuestion={openQuestion} initialPick={lecturePick} />
          ) : page === 'bank' ? (
            bankView
          ) : page === 'ingest' ? (
            ingestMode === 'proof' || ingestMode === 'curate' ? (
              <ProofWorkspace stage={stage}
                onBack={() => setIngestMode('')}
                onDone={() => {
                  L.setReload((n) => n + 1)
                  api.overview(stage).then(setOverview).catch(() => { /* 页面内会显示错误 */ })
                }} />
            ) : ingestMode ? (
              <IngestWorkspace mode={ingestMode} stage={stage} facets={L.facets}
                onBack={() => setIngestMode('')}
                onDone={() => {
                  L.setReload((n) => n + 1)
                  api.overview(stage).then(setOverview).catch(() => { /* 新页自己也有错误提示 */ })
                }} />
            ) : (
              <IngestHome stage={stage}
                onOpen={(mode) => setIngestMode(mode)}
                onBank={() => setPage('bank')} />
            )
          ) : page === 'paper' ? (
            <PaperStudio stage={stage} paper={paper} score={paperScore} answered={answered}
              onOpenQuestion={openQuestion} onRemove={removeFromPaperUndo}
              onMove={moveInPaper} onSwap={replaceInPaper}
              onExport={() => setShowExport(true)} onBank={() => setPage('bank')}
              onPapers={() => setPage('papers')} onGenerate={() => setShowExport(true)} />
          ) : page === 'sets' ? (
            <SetsPage stage={stage} onAddBatch={addPaperBatch}
              // 套卷页自己没有详情抽屉（DetailDrawer 在题库工作台里）。
              // 走和讲义/审阅同一个入口：切到题库、按 key 定位、打开详情。
              onOpenQuestion={(it) => openQuestion(it.key)}
              onPaper={gotoPaper}
              inPaper={(k) => paperMap.has(k)}
              refreshSignal={setsRefresh} follow={setsFollow} />
          ) : page === 'papers' ? (
            <PapersPage onLoad={loadPaper} onPaper={gotoPaper} focus={paperFocus} />
          ) : page === 'health' ? (
            <div className="b-scroll h-full overflow-y-auto"><Health stage={stage} onScope={openScope}
              onMap={() => setPage('map')} onIngest={openIngestTab}
              onReview={() => setPage('review')} /></div>
          ) : page === 'review' ? (
            <Review stage={stage} onChanged={() => L.setReload((v) => v + 1)}
              onOpenSource={openSourceQuestion} />
          ) : page === 'trash' ? (
            <div className="b-scroll h-full overflow-y-auto">
              <Trash onChanged={() => { L.setReload((v) => v + 1) }} />
            </div>
          ) : (
            <div className="b-scroll h-full overflow-y-auto"><Changes /></div>
          )}
          </Suspense>
        </Shell>
      </div>

      <HelpButton />
      <CommandPalette open={palette} onClose={() => setPalette(false)}
        commands={commands}
        onSearch={(w) => { setPage('bank'); L.setQ(w) }} />
      <Toaster />

      {/* 导出是全屏浮层：chunk 到位前不画东西，别拿骨架盖住背后的页面。 */}
      {exportShown && (
        <Suspense fallback={null}>
          <ExportPage closing={exportClosing} init={paper} from={exportFrom}
            pageItems={L.items} filters={L.filters}
            onClose={() => setShowExport(false)} />
        </Suspense>
      )}

      {batchOpen && (
        <Suspense fallback={null}>
        <BatchTagDialog keys={[...L.checkedMap.keys()]} facets={L.facets}
          onClose={() => setBatchOpen(false)}
          onDone={(res) => {
            setBatchOpen(false)
            // 批量改书名/卷名会换 key：卷子、详情缓存、当前选中都得一起迁，
            // 否则它们还拿着旧 key，导出时才报「找不到题」。
            remapBatch(Array.isArray(res?.renames) ? res.renames : [])
            L.clearChecked()
            L.refreshSilent()
            setSetsRefresh((v) => v + 1)
          }}
          onTrimTo={(n) => {
            const keep = [...L.checkedMap.entries()].slice(0, n)
            L.setChecked(new Set(keep.map(([k]) => k)))
            L.setCheckedMap(new Map(keep))
          }} />
        </Suspense>
      )}

      {deleteAsk && (
        <Suspense fallback={null}>
        <DeleteModal qs={deleteAsk.qs ?? L.items.filter((x) => (deleteAsk.keys || []).includes(x.key))}
          keys={deleteAsk.keys}
          onCancel={() => setDeleteAsk(null)}
          onConfirm={(reason) =>
            deleteQuestions(deleteAsk.keys ?? (deleteAsk.qs || []).map((x) => x.key), reason)
              .then(() => setDeleteAsk(null))} />
        </Suspense>
      )}

      </div>
    </div>
  )
}
