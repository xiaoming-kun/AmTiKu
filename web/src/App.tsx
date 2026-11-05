import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  ListFilter, X, Check, ClipboardList, Rows3, Rows2, BookPlus, FileText,
  LayoutGrid, ScanLine, FolderTree, Sparkles,
  Trash2, History, Command as CommandIcon,
} from 'lucide-react'
import type { Q, Base } from '@/lib/types'
import { api, reportErr, setGlobalErrHandler } from '@/lib/api'
import { paperScore as totalScore } from '@/lib/paper'
import { DIFF_STARS } from '@/lib/display'
import { useQuestionList } from '@/lib/useQuestionList'
import { useWidth, useFlag, useUnmount, useVw } from '@/app/ui'
import { Trash, DeleteModal } from '@/app/Trash'
import ListHeader from '@/app/ListHeader'
import BatchTagDialog from '@/app/BatchTagDialog'
import PaperBar from '@/app/PaperBar'
import QuestionList from '@/app/QuestionList'
import PaperPanel from '@/app/PaperPanel'
import DetailDrawer from '@/app/DetailDrawer'
import { Changes } from '@/app/Stats'
import ExportPage from '@/app/ExportPage'
import IngestDrawer from '@/app/IngestDrawer'
import Nav, { NAV_BY_HINT, NAV_GROUPS, NAV_W_OPEN, NAV_W_SHUT, type NavKey } from '@/app/Nav'
import TopBar from '@/app/TopBar'
import FilterPanel, { FILTER_W } from '@/app/FilterPanel'
import HelpButton from '@/app/HelpButton'
import Health, { type Scope } from '@/app/Health'
import { Toaster, toast, dismissToasts } from '@/app/Toast'
import CommandPalette, { type Cmd } from '@/app/CommandPalette'
import { INITIAL_URL, writeUrlState } from '@/lib/urlState'

/** 整屏页面。
 *
 *  **没有「第三栏」了**——内容区只有「筛选 | 题目」两栏：
 *  · 题目列表和当前卷子是**同一栏里的两个视图**（`view` 切换）；
 *  · 题目详情是**占一栏的抽屉**（`dOpen`，默认展开，可关，选择会记住）。
 *  所以这里只剩「整屏页面」这一种 tab。 */
type Tab = 'workbench' | 'health' | 'changes' | 'trash'
const FULL_PAGE: Tab[] = ['changes', 'trash']

export default function App() {
  // 列表数据与筛选 → useQuestionList（一行拿到全部筛选状态，见 lib/useQuestionList.ts）
  const L = useQuestionList()
  const {
    facets, items, setItems, total, setTotal, sel, setSel, loading, reload, setReload,
    refreshSilent,
    setPage, listRef, q, setQ, type, setType, kind, setKind, has, setHas, missing, setMissing,
    points, setPoints, diffs, setDiffs, years, setYears, sources, setSources,
    scopes, setScopes, paperStates, setPaperStates,
    starStates, setStarStates, qualities, setQualities,
    pointSource, setPointSource,
    setChecked, setCheckedMap, checkedMap, setReviewed,
    toggleCheck,
    selectMode, setSelectMode, exitSelect, activeFilters,
  } = L

  const [base, setBase] = useState<Base | null>(null)
  // 页面也进地址栏：刷新/收藏一个「题库体检」或「变更记录」视图不会回到工作台
  const TABS: Tab[] = ['workbench', 'health', 'changes', 'trash']
  const [tab, setTab] = useState<Tab>(() =>
    TABS.includes(INITIAL_URL.tab as Tab) ? INITIAL_URL.tab as Tab : 'workbench')
  const [showExport, setShowExport] = useState(false)
  const [showIngest, setShowIngest] = useState(false)
  const [globalErr, setGlobalErr] = useState('')

  /** 题目栏里现在显示哪一个视图：题目列表 or 当前卷子。
   *  两者**共用同一栏**（不是两个栏目），所以切换不改变任何宽度。 */
  const [view, setView] = useState<'list' | 'paper'>('list')
  /** 详情抽屉开着没有。**默认就是开的**：打开软件直接是"左边列表 + 右边题目"
   *  这种阅读态，少一次点击；宽屏才有这个默认值（窄屏开着一进来就把列表盖住）。
   *  关掉之后按你的选择记着——不想看详情的人不用每次都关。 */
  const [dOpen, setDOpen] = useFlag('amtiku.detail',
    typeof window !== 'undefined' && window.innerWidth >= 1280)
  // 退场动画播完再卸载，不然抽屉"啪"地消失（见 ui.tsx 的 useUnmount）
  const { shown: dShown, closing: dClosing } = useUnmount(dOpen, 170)
  // 弹层同理：Esc / 点关闭都要能播完退场再卸载
  const { shown: exportShown, closing: exportClosing } = useUnmount(showExport, 160)
  const { shown: ingestShown, closing: ingestClosing } = useUnmount(showIngest, 170)

  /** 抽屉宽度可拖、带记忆（和筛选面板同一套 Grip/useWidth）。
   *  详情里有题图和长解析，固定 620 对某些题太窄、对另一些又浪费。 */
  const [dW, setDW] = useWidth('amtiku.w.drawer', 620, 380, 940)
  /** 列表密度。成熟产品（Notion / Linear / Gmail）都有这个开关：
   *  挑题时要的是"一屏多扫几道"，读题时要的是"宽松好读"。 */
  const [dense, setDense] = useFlag('amtiku.dense', false)
  /** 密排（一行一道）。和 dense 不是一回事：dense 是卡片的紧凑，compact 是换布局。 */
  const [compact, setCompact] = useFlag('amtiku.compact', false)
  /** 答案遮罩：默认开。投屏/学生在场时答案别摊在列表上。 */
  const [maskAns, setMaskAns] = useFlag('amtiku.maskAns', true)
  /** 命令面板（⌘K）——设计文档 §原则4 里就写了，这一版补上。 */
  const [palette, setPalette] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)

  // 可收起的区域。开合都记忆 —— 老师会固定一种摆法，不该每次打开都回到默认。
  // **首次打开默认收起筛选面板**：它是 280px 的常驻栏，而"找题"的主视野是题目
  // 本身。收起来之后表头那颗「筛选」按钮和胶囊一样能进；打开过一次就记住了，
  // 常看知识树的老师不会被反复打扰。
  const [navShut, setNavShut] = useState(false)
  const [showFilter, setShowFilter] = useFlag('amtiku.showFilter', false)

  /** **多少宽度分给谁**——四栏同时开的时候这是唯一的准绳。
   *
   *  实测：1400 宽的窗口里，导航 208 + 筛选 252 + 详情 620 一摆，
   *  列表只剩 278px——卡片标题被截成「主1.3 集合的…」，分页被压成竖排。
   *  所以定两条规矩：
   *  ① 空间紧（<1560）且筛选和详情同时开着 → **导航先自动收成图标条**（240→60）；
   *  ② 详情栏的宽度封顶，**列表永远留够 520px**。用户手动拖宽/展开则优先听他。
   */
  const vw = useVw()
  const [navPinned, setNavPinned] = useState(false)   // 手动展开过：本次会话不再自动收
  const tight = vw < 1560 && showFilter && dOpen
  const navCollapsed = navShut || (tight && !navPinned)
  const listMin = 520
  const drawerMax = Math.max(380, Math.min(940,
    vw - (navCollapsed ? NAV_W_SHUT : NAV_W_OPEN) - (showFilter ? FILTER_W : 0) - listMin))
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

  /** **地址栏 = 当前视图**：筛选/搜索/页码/页面变了就 replaceState。
   *  刷新、收藏、把链接发给同事都能直接回到同一屏；不产生历史记录，
   *  后退键仍然是离开页面，不会在几十条筛选里倒退。 */
  useEffect(() => {
    writeUrlState({
      filters: {
        q: L.filters.q, type: L.filters.type, kind: L.filters.kind,
        point: L.filters.point, diff: L.filters.difficulty, year: L.filters.year,
        source: L.filters.source, has: L.filters.has, missing: L.filters.missing,
        scope: L.filters.region_scope, paper: L.filters.paper_state,
        star: L.filters.star_state, quality: L.filters.quality,
        psrc: L.filters.point_source, asrc: L.filters.answer_source,
        reviewed: L.filters.reviewed,
      },
      sort: L.sort, page: L.page, tab,
    })
  }, [L.filters, L.sort, L.page, tab])

  /** 最近搜过：停手 900ms 才记，避免把「2026」「2026精」这些半截词也存进去。 */
  const [recent, setRecent] = useState<string[]>(() => {
    try {
      const v = JSON.parse(localStorage.getItem('amtiku.recentSearches') || '[]')
      return Array.isArray(v) ? v.filter((x) => typeof x === 'string').slice(0, 8) : []
    } catch { return [] }
  })
  useEffect(() => {
    const s = q.trim()
    if (s.length < 2) return
    const t = window.setTimeout(() => {
      setRecent((xs) => {
        const next = [s, ...xs.filter((x) => x !== s)].slice(0, 8)
        try { localStorage.setItem('amtiku.recentSearches', JSON.stringify(next)) } catch { /* 不记忆 */ }
        return next
      })
    }, 900)
    return () => window.clearTimeout(t)
  }, [q])
  const clearRecent = () => {
    setRecent([])
    try { localStorage.removeItem('amtiku.recentSearches') } catch { /* 忽略 */ }
  }
  /** 全局错误提示。
   *  以前请求失败是**静默**的：接口 400 返回 {detail}，前端当数据用，
   *  界面表现成"没题""没变化"。现在 request() 统一抛错，这里接住并显示。 */
  useEffect(() => {
    setGlobalErrHandler(setGlobalErr)
    return () => setGlobalErrHandler(null)
  }, [])

  /* ── 卷子收集夹 ───────────────────────────────────────
     选题只为打印成试卷；讲义排版走导出页的「讲义」模式。 */
  const [paperMap, setPaperMap] = useState<Map<string, Q>>(new Map())
  const paper = useMemo(() => [...paperMap.values()], [paperMap])
  const paperScore = totalScore(paper)
  const answered = paper.filter((x) => x.flags['解析']).length
  // 导出对象**只认卷子**，默认为空。
  // 早先卷子一空就自动拿「当前筛选结果」顶上，于是刚进页面就显示
  // 「导出 38」——用户还没说要导出什么，程序先替他决定了。不对。
  // 这里只给**来源名**；题数由导出页按 `list.length` 实时算
  // （在导出页里「加本页 / 清空」之后，来源标签不能还挂着旧的题数）。
  const exportFrom = '卷子'

  /* ── 卷子的增删：**一律配撤销，不配确认框** ──────────────────
     「宁可给撤销，也不要弹确认框」：确认框在**做之前**拦你（每次都要多点一下），
     撤销在**做之后**兜你（只有真错了才用）。挑卷子是高到不能再高的频操作，
     所以这里连「清空」的两段式确认都撤掉了 —— 一条「已清空 12 道 · 撤销」
     比「确认清空？」更快也更安全（错点了也回得来）。 */
  const addToPaper = (it: Q) => {
    setPaperMap((m) => new Map(m).set(it.key, it))
    toast(`已加入卷子 · ${it.point_titles?.[0] || it.type_label}`, {
      action: { label: '撤销', run: () => removeFromPaper(it.key) },
    })
  }
  const removeFromPaper = (k: string) => setPaperMap((m) => { const n = new Map(m); n.delete(k); return n })

  /** 在卷子里上下挪一道题。
   *
   *  **只在同一题型内部换位**：卷面是按题型分节的（`amti/paper.py` 固定按
   *  单选 → 多选 → 填空 → 解答 分节，节内保持你给的顺序），
   *  所以"把这道单选挪到填空那一节去"根本没有意义。
   *  实现上就是把这题的 key 和同题型里相邻那题在 Map 里换个位置——
   *  Map 的迭代顺序就是插入顺序，也就是卷面顺序。 */
  const moveInPaper = (key: string, d: -1 | 1) => {
    setPaperMap((m) => {
      const q = m.get(key)
      if (!q) return m
      const arr = [...m.entries()]
      const same = arr.filter(([, v]) => v.type === q.type)
      const i = same.findIndex(([k]) => k === key)
      const j = i + d
      if (i < 0 || j < 0 || j >= same.length) return m   // 到顶/到底就不动
      const next = [...arr]
      const a = arr.indexOf(same[i])
      const b = arr.indexOf(same[j])
      ;[next[a], next[b]] = [next[b], next[a]]
      return new Map(next)
    })
  }
  /** 带撤销的移出（卷子视图里点 ✕ 走这条） */
  const removeFromPaperUndo = (k: string) => {
    const it = paperMap.get(k)
    removeFromPaper(k)
    if (it) toast('已从卷子移出', { action: { label: '撤销', run: () => addToPaper(it) } })
  }
  /** 清空卷子：直接清 + 给撤销（不再两段确认）。
   *
   *  撤销是**增量**的（把刚才清掉的那些加回来），不是"恢复整张快照"——
   *  快照式撤销跟别的操作交错时会吃掉中间的改动：清空 → 又加了两道 → 撤销清空，
   *  快照一盖，那两道就没了。加回来不会。 */
  const clearPaper = () => {
    if (!paper.length) return
    const gone = [...paperMap.entries()]
    setPaperMap(new Map())
    dismissToasts()   // 清空之后，之前那几条"已加入"的撤销已经没意义了
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

  /** 点题目就看这道题：**详情永远跟着走**，点下一道自动换成下一道。
   *
   *  以前这里写的是 `setSel(it); if (!selectMode) setDOpen(true)` ——
   *  而多选是**默认模式**，于是默认状态下点卡片只勾选、右边纹丝不动，
   *  想看一眼题得先点 ✕ 关掉上一道、再去点「放大」。
   *  `QuestionCard` 里那句注释「详情永远跟着走」当时只改了一半：
   *  卡片把 onOpen 叫出来了，onOpen 自己却把门关了。 */
  const showDetail = (it: Q) => { setSel(it); setDOpen(true) }

  /** 从详情点考点跳过来：列表立刻切成「只看这个考点」，并把该考点
   *  所在大类展开，这样侧栏能看见自己选中了什么。 */
  const [findNote, setFindNote] = useState('')
  const findPoint = (pid: string, title: string) => {
    // **在现有条件上切换这个考点**，不再把别的考点清掉：
    // 以前是 `setPoints([pid])`——你在筛选面板里挑了 6 个考点，详情里点一下
    // 某个考点，整块筛选就没了（还没法撤销）。现在点一下是「加上它」，
    // 再点一下是「去掉它」。关键词仍然清掉：它是临时搜索，
    // 和"看这个考点"叠在一起多半筛成 0 道。
    L.togglePoints([pid])
    setQ(''); setPage(1)
    const p = (facets?.points || []).find((x: any) => x.value === pid)
    if (p) L.setOpenTopics((s) => new Set([...s, p.topic]))
    setFindNote(title)
    setShowFilter(true)
  }
  // 手动改筛选（不是从详情点考点跳过来）就把那句说明收掉
  useEffect(() => { setFindNote('') }, [q, has, missing, diffs, years])

  /** **卷子空了就别停在卷子视图上。**
   *
   *  清空、或撤销掉最后一次加入之后，原来会留在「当前卷子 0 题」那一屏：
   *  整屏只剩一句"卷子还是空的"，而表头还写着「题库 20,934 道」——
   *  看着跟"筛不出题"一模一样（用户就是这么被绕进去的）。 */
  useEffect(() => {
    if (view === 'paper' && !paper.length) setView('list')
  }, [view, paper.length])

  /** 删一道题：走 `/api/questions/{key}/trash`，**移进回收站不是真删**。 */
  const [deleteAsk, setDeleteAsk] = useState<
    { qs: Q[]; keys?: never } | { keys: string[]; qs?: never } | null>(null)
  const deleteQuestions = (keys: string[], reason: string) =>
    api.trashBatch(keys, reason).then(() => {
      const ks = new Set(keys)
      // **删除成功后本地当场删行**：接口已经返回，不该再让人等第二轮刷新。
      // 当前页先去掉这些题（详情也跟着切走），随后再静默校正分页/计数/筛选。
      const goneVisible = items.filter((x) => ks.has(x.key)).length
      setItems((xs) => xs.filter((x) => !ks.has(x.key)))
      setTotal((t) => Math.max(0, t - goneVisible))
      setSel((cur) => {
        if (!cur || !ks.has(cur.key)) return cur
        // 优先往下找一道没被删的；到底了再往回找
        const i = items.findIndex((x) => x.key === cur.key)
        const after = items.slice(Math.max(0, i + 1)).find((x) => !ks.has(x.key))
        const before = items.slice(0, Math.max(0, i)).reverse().find((x) => !ks.has(x.key))
        return after ?? before ?? null
      })
      setFull((f) => (f && ks.has(f.key) ? null : f))
      // 卷子、勾选里的也要一起清掉——不然删除后它们还挂在那儿。
      setPaperMap((m) => { const n = new Map(m); for (const k of ks) n.delete(k); return n })
      setChecked((c) => { const n = new Set(c); for (const k of ks) n.delete(k); return n })
      setCheckedMap((m) => { const n = new Map(m); for (const k of ks) n.delete(k); return n })
      // 后台静默刷新：把当前页补满、总数/筛选项校正；**不闪刷新条**
      refreshSilent()
    }).catch(reportErr)

  /** 把勾中的题一次性加进卷子 / 讲义 */
  const addChecked = () => {
    // **勾选集合不是当前页**：跨页勾过的题也要一起加进去
    const picked = [...checkedMap.values()]
    // 只记**这次真正新增的**——撤销就删这几个，不去动别人后来加的东西
    const added = picked.filter((x) => !paperMap.has(x.key))
    setPaperMap((m) => {
      const n = new Map(m)
      for (const x of picked) n.set(x.key, x)
      return n
    })
    exitSelect()
    // **加完不跳走**：批量挑题时每加一次就切视图，等于逼人再切回来。
    // 回执交给两件事：卷子条上的数字**滚**过去 + 一条带撤销的提示。
    if (added.length) {
      toast(`已加入卷子 ${added.length} 道`, {
        action: { label: '撤销', run: () => setPaperMap((m) => {
          const n = new Map(m); for (const x of added) n.delete(x.key); return n
        }) },
      })
    }
  }

  /** 切到「当前卷子」这个视图。
   *
   *  **空卷子不切过去**：不然整屏变成"当前卷子 0 题"，而表头还写着
   *  「题库 48 道」——看着就像"筛不出题"（用户就是这么被绕进去的）。
   *  空的时候留在列表上，用一条提示说清楚。 */
  const gotoPaper = () => {
    setTab('workbench')
    if (!paper.length) {
      setView('list')
      toast('卷子还是空的 —— 先在题目卡片上点「加入组卷」', { tone: 'info' })
      return
    }
    setView('paper')
  }

  /** 从题库体检跳到工作台：先清掉旧筛选，再套上体检页给的范围。 */
  const openScope = (s: Scope) => {
    setTab('workbench')
    setView('list')
    setQ(s.q ?? '')
    setPoints(s.points ?? [])
    setMissing(s.missing ?? [])
    setYears(s.years ?? [])
    setPointSource(s.pointSource ?? '')
    setReviewed(s.reviewed ?? '')
    setDiffs([]); setHas([]); setType(''); setKind('')
    setPage(1)
    setFindNote(s.note ?? '')
    setShowFilter(true)
  }

  /** 题目**改名**（改出处/改题号）后，把内存里三份按 key 存的集合换到新 key。
   *
   *  后端会把存档（`试卷/存档.json`、`讲义/讲义存档.json`）里的引用迁到新 key
   *  （`_migrate_key_refs`），但**当前页面内存里的**卷子/讲义/勾选它看不见——
   *  不跟着换的话，导出的卷子会按旧 key 找不到题，静默少一道（不报错）。
   *  Map 保持原顺序：卷子/讲义的顺序就是卷面顺序，不能因为改名而挪位。 */
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
    setCheckedMap(swap)
    setChecked((s) => {
      if (!s.has(oldKey)) return s
      const n = new Set(s); n.delete(oldKey); n.add(q.key); return n
    })
  }

  /** 单题换题：只改当前卷子的这一格，保持它在卷子里的位置。 */
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

  /* ── 导航动作 ── */
  const navActive: NavKey =
    tab === 'trash' ? 'trash' : tab === 'changes' ? 'changes'
    : tab === 'health' ? 'health'
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
    if (k === 'paper') { gotoPaper(); return }
    setTab(k as Tab)
  }

  /* ── 心跳：页面活着服务器就活着，**页面关掉 30 秒后服务器退出** ──
     每 8 秒 ping 一次；关页面时用 sendBeacon 补最后一声。
     服务端只认「有没有 ping」：浏览器崩溃、断电、强杀都发不出关闭帧，
     但心跳停了就说明人走了。

     **只挂 pagehide，不挂 beforeunload。** 两个都挂会在关页面时发两次
     beacon（实测日志里两条「页面说要走」），除了把退出倒计时连按两次，
     没有好处；`pagehide` 覆盖关标签、关窗口、刷新、跳转。 */
  useEffect(() => {
    const ping = () => fetch('/api/alive', { method: 'POST' }).catch(() => {})
    ping()
    const t = setInterval(ping, 8000)
    const bye = () => { try { navigator.sendBeacon('/api/gone') } catch { /* 尽力而为 */ } }
    window.addEventListener('pagehide', bye)
    return () => {
      clearInterval(t)
      window.removeEventListener('pagehide', bye)
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

      // ⌘K / Ctrl+K 命令面板。**在任何地方都要能唤起**（包括输入框里）——
      // 它本来就是"手不离键盘"的入口，在搜索框里打了一半想跳走是最需要它的时候。
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault(); setPalette((v) => !v); return
      }
      if (e.key === 'Escape' && palette) { e.preventDefault(); setPalette(false); return }

      if (e.key === '/' && !typing()) {
        e.preventDefault(); searchRef.current?.focus(); return
      }
      // **⌘↵ = 把当前这道题加进卷子**（"确认"级别的动作给它）
      // 弹层/全屏编辑器开着时不响应：否则在导出弹层里按一下，
      // 背后列表悄悄多一道题，而用户以为它在执行"导出"。
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        if (showExport || showIngest || palette) return
        if (sel) addToPaper(sel)
        return
      }
      // 命令面板开着的时候，下面的单键和方向键都归它 —— 不能两处一起动
      if (palette) return
      if (e.key === 'Escape') {
        // 按"最上层先关"的顺序：弹层 → 详情 → 多选。
        // 以前 Esc 只会关详情/弹层，多选一直挂着，用户只能去点那个 ×。
        if (showExport || showIngest) { setShowExport(false); setShowIngest(false); return }
        if (dOpen) { setDOpen(false); return }
        if (selectMode && checkedMap.size) { exitSelect(); return }
        return
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (typing()) return
      // 有弹层/全屏编辑器时，单键和方向键都让给它 ——
      // 否则在导出弹层里按 ↓，背后的列表光标会跟着乱跑
      if (showExport || showIngest) return

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
      // **↵ = 看这道题，空格 = 勾选**。
      // 以前 ↵ 是直接加卷子：↑↓ 之后手一抖就多一道，而且界面上从没写过这个键。
      // 看题是高频动作，勾选是"准备批量"，两个都给键盘留了路。
      //
      // 焦点在按钮/复选框上时**让给浏览器**：原生 button 的 ↵/空格本来就会
      // 触发它自己，这里再接管一次就等于连按两下（勾了又取消）。
      const onControl = !!(document.activeElement as HTMLElement | null)
        ?.closest?.('button, [role="checkbox"], a')
      if (onControl) return
      if (e.key === 'Enter' && sel) { e.preventDefault(); setDOpen(true); return }
      if (e.key === ' ' && sel) {
        e.preventDefault()
        const i = items.findIndex((x) => x.key === sel.key)
        toggleCheck(sel, i >= 0 ? i : null, e.shiftKey)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, sel, setSel, listRef, showExport, showIngest, tab, dOpen, palette])

  /** ── 命令面板的内容 ──────────────────────────────────────
   *  三组：**去**（导航）、**做**（动作）、**看**（视图与范围）。
   *  `keywords` 里塞拼音和英文别名 —— 中文输入法切来切去很烦，
   *  敲 `daoshu` 就能到「导数」，敲 `export` 就能到导出。 */
  const commands: Cmd[] = useMemo(() => {
    const navIcon: Record<string, ReactNode> = {
      workbench: <LayoutGrid size={13} />, ingest: <ScanLine size={13} />,
      points: <FolderTree size={13} />,
      export: <Sparkles size={13} />, paper: <ClipboardList size={13} />,
      trash: <Trash2 size={13} />,
      changes: <History size={13} />,
    }
    const navWords: Record<string, string> = {
      workbench: 'gongzuotai workbench home list 题库 找题',
      ingest: 'luru ingest import 录题 录入 新建',
      points: 'zhishidian points topics 考点 章节',
      export: 'zujuan export 组卷 导出 pdf',
      paper: 'shijuan paper 卷子 试卷',
      trash: 'huishouzhan trash 回收站 删除',
      changes: 'biangeng changes 变更 记录',
    }
    const out: Cmd[] = NAV_GROUPS.flatMap((g) => g.items.map((it) => ({
      id: `nav:${it.key}`,
      label: it.label,
      group: '去',
      icon: navIcon[it.key],
      hint: it.hint,
      keywords: `${navWords[it.key] || ''} ${it.desc}`,
      run: () => pick(it.key),
    })))

    out.push(
      { id: 'view:list', label: '切到题目列表', group: '看', icon: <ListFilter size={13} />,
        keywords: 'timu list 题目 列表', run: () => { setTab('workbench'); setView('list') } },
      { id: 'view:paper', label: '切到当前卷子', group: '看', icon: <ClipboardList size={13} />,
        keywords: 'juanzi paper 卷子', run: gotoPaper },
      { id: 'view:filter', label: showFilter ? '收起筛选面板' : '展开筛选面板', group: '看',
        icon: <ListFilter size={13} />, keywords: 'shaixuan filter 筛选 考点',
        run: () => setShowFilter(!showFilter) },
      { id: 'view:dense', label: dense ? '切换成宽松卡片' : '切换成紧凑卡片', group: '看',
        icon: dense ? <Rows3 size={13} /> : <Rows2 size={13} />,
        keywords: 'midu density compact 密度 紧凑', run: () => setDense(!dense) },
      { id: 'view:compact', label: compact ? '切回卡片视图' : '切到密排视图（一行一道）', group: '看',
        icon: compact ? <LayoutGrid size={13} /> : <Rows3 size={13} />,
        keywords: 'mipai compact 密排 一行 列表 布局', run: () => setCompact(!compact) },
      { id: 'view:select', label: selectMode ? '关掉多选模式' : '打开多选模式', group: '看',
        icon: <Check size={13} />, keywords: 'duoxuan select 多选 勾选',
        run: () => (selectMode ? exitSelect() : setSelectMode(true)) },
      { id: 'act:export', label: '新建试卷 / 组卷导出', group: '做', icon: <Sparkles size={13} />,
        keywords: 'daochu export zujuan pdf 导出 组卷', run: () => setShowExport(true) },
      { id: 'act:ingest', label: '手工录入题目', group: '做', icon: <ScanLine size={13} />,
        hint: 'I', keywords: 'luru ingest 录题 录入 手工 粘贴', run: () => setShowIngest(true) },
      { id: 'act:help', label: '查看键盘快捷键', group: '做', icon: <CommandIcon size={13} />,
        hint: '?', keywords: 'kuaijiejian shortcut help 快捷键 帮助',
        run: () => window.dispatchEvent(new CustomEvent('amtiku:help')) },
      { id: 'act:points-clear', label: `清除全部筛选（${activeFilters} 项）`, group: '做',
        icon: <X size={13} />, keywords: 'qingchu clear filter 清除 重置',
        run: () => {
          setHas([]); setMissing([]); setPoints([]); setDiffs([])
          setYears([]); setType(''); setKind(''); setQ('')
        } },
    )

    if (paper.length) {
      out.push(
        { id: 'act:paper-view', label: `看卷子（${paper.length} 题 · ${paperScore} 分）`, group: '做',
          icon: <ClipboardList size={13} />, keywords: 'juanzi 卷子 查看',
          run: gotoPaper },
        { id: 'act:paper-clear', label: `清空卷子（${paper.length} 题）`, group: '做',
          icon: <Trash2 size={13} />, keywords: 'qingkong 清空 卷子', run: clearPaper },
      )
    }
    if (sel) {
      out.push({
        id: 'act:detail', label: '打开当前这道题的详情', group: '做',
        icon: <FileText size={13} />, keywords: 'xiangqing detail 详情 答案 解析',
        run: () => setDOpen(true),
      })
    }

    // 范围（高考 / 模拟）：换一下整个题库的口径就变了，值得进命令面板
    for (const k of facets?.kinds || []) {
      out.push({
        id: `kind:${k.value}`, label: kind === k.value ? `回到全部（现在只看${k.value}）` : `只看${k.value}题`,
        group: '看', icon: <BookPlus size={13} />,
        keywords: `${k.value} fanwei scope 范围`,
        run: () => setKind(kind === k.value ? '' : k.value),
      })
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facets, kind, showFilter, dense, selectMode, paper, paperScore, sel, activeFilters, pick])

  /** 列表头那串「现在筛了什么」。
   *
   *  以前这里是一句拼出来的中文（`缺：解析` / `有：图` / `考点 · 导数`），
   *  既看不出是几条，也没法单独去掉一条 —— 只能"清除全部"从头再来。
   *  成熟做法（Linear / GitHub Issues 的筛选条）是**把生效的条件做成可删的胶囊**：
   *  一条一个 ×，点掉哪条就撤哪条，剩下的继续生效。
   *
   *  `clear` 里只撤这一条、其它不动，所以每个胶囊要带着自己的"怎么撤"。 */
  const clearAllFilters = () => {
    setHas([]); setMissing([]); setPoints([]); setDiffs([])
    setYears([]); setSources([]); setPointSource(''); setType(''); setKind(''); setQ('')
    // 以下四个维度也必须清 —— `activeFilters` 把她们算进去了，
    // 少清一个就会出现「徽标写 1 项、点了清除列表没变、表头还写全部题目」。
    setScopes([]); setPaperStates([]); setStarStates([]); setQualities([])
    setFindNote('')
  }
  const scopeChips: { key: string; label: string; clear: () => void }[] = (() => {
    const out: { key: string; label: string; clear: () => void }[] = []
    if (q.trim()) out.push({ key: 'q', label: `搜「${q.trim()}」`, clear: () => setQ('') })
    if (L.scopeName) {
      out.push({ key: 'scope', label: L.scopeName, clear: () => setPoints([]) })
    } else if (points.length === 1) {
      const title = findNote
        || (facets?.points || []).find((x: any) => x.value === points[0])?.title
        || points[0]
      out.push({ key: 'p1', label: `考点 · ${title}`, clear: () => { setPoints([]); setFindNote('') } })
    } else if (points.length > 1) {
      out.push({ key: 'pn', label: `考点 · ${points.length} 个`, clear: () => setPoints([]) })
    }
    if (type) out.push({
      key: 'type', label: facets?.types.find((t) => t.value === type)?.label || type,
      clear: () => setType(''),
    })
    if (kind) out.push({ key: 'kind', label: `${kind}题`, clear: () => setKind('') })
    for (const s of sources) out.push({
      key: `src-${s}`, label: `出处 · ${s}`,
      clear: () => setSources((xs) => xs.filter((x) => x !== s)),
    })
    if (pointSource) out.push({
      key: 'psrc',
      label: pointSource === '无' ? '考点来源未记' : `考点来源 · ${pointSource}`,
      clear: () => setPointSource(''),
    })
    for (const d of diffs) out.push({
      key: `d${d}`, label: `难度 ${'★'.repeat(DIFF_STARS[d] || 0)}`,
      clear: () => setDiffs((xs) => xs.filter((x) => x !== d)),
    })
    for (const y of years) out.push({
      key: `y${y}`, label: `${y} 年`, clear: () => setYears((xs) => xs.filter((x) => x !== y)),
    })
    for (const m of missing) out.push({
      key: `m${m}`, label: `缺${m}`, clear: () => setMissing((xs) => xs.filter((x) => x !== m)),
    })
    for (const h of has) out.push({
      key: `h${h}`, label: h.startsWith('有') ? h : `有${h}`,
      clear: () => setHas((xs) => xs.filter((x) => x !== h)),
    })
    // 地区 / 试卷完整度 / 星级 / 质检：筛选面板能筛，胶囊也必须能显示和单独撤，
    // 否则只有这四项生效时表头会写「全部题目」，看着像没筛。
    for (const s of scopes) out.push({
      key: `sc-${s}`, label: `地区 · ${s}`, clear: () => setScopes((xs) => xs.filter((x) => x !== s)),
    })
    for (const s of paperStates) out.push({
      key: `ps-${s}`, label: `试卷 · ${s}`, clear: () => setPaperStates((xs) => xs.filter((x) => x !== s)),
    })
    for (const s of starStates) out.push({
      key: `ss-${s}`, label: `星级 · ${s}`, clear: () => setStarStates((xs) => xs.filter((x) => x !== s)),
    })
    for (const s of qualities) out.push({
      key: `ql-${s}`, label: `质量 · ${s}`, clear: () => setQualities((xs) => xs.filter((x) => x !== s)),
    })
    for (const s of L.answerSources) out.push({
      key: `as-${s}`,
      label: `答案来源 · ${({ human: '人工', workbuddy: '模型', legacy: '历史存量' } as any)[s] || s}`,
      clear: () => L.setAnswerSources((xs) => xs.filter((x) => x !== s)),
    })
    if (L.reviewed) out.push({
      key: 'rv',
      label: L.reviewed === 'yes' ? '已复核' : '未复核',
      clear: () => L.setReviewed(''),
    })
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        <Nav active={navActive} onPick={pick} collapsed={navCollapsed}
          onCollapsed={(v) => { setNavShut(v); setNavPinned(!v) }}
          kind={kind} onKind={setKind} kinds={facets?.kinds || []}
          total={total} pointsCovered={facets?.points_covered || 0}
          pointsTotal={facets?.points.length || 0} />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar q={q} onQ={setQ} inputRef={searchRef} base={base} paperCount={paper.length}
            recent={recent} onClearRecent={clearRecent}
            onPaper={gotoPaper}
            onExport={() => setShowExport(true)}
            onReload={() => setReload((v) => v + 1)} />

          {tab === 'health' ? (
            <main className="anim-fade-in flex min-h-0 flex-1 flex-col overflow-hidden">
              <Health onScope={openScope} />
            </main>
          ) : FULL_PAGE.includes(tab) ? (
            <main className="anim-fade-in min-h-0 flex-1 overflow-y-auto">
              {tab === 'trash' ? <Trash onChanged={() => setReload((v) => v + 1)} />
                : <Changes />}
            </main>
          ) : (
            <div className="relative flex min-h-0 flex-1">
              {/* ── 筛选面板 ──
                  按 K（知识点）时给一道粉色高亮**从面板内侧亮一下**：
                  面板自己不透明，所以闪光要画在它上面的一层覆盖物里，
                  直接给容器加背景色是看不见的。 */}
              {showFilter && (<>
                {/* 窄屏：筛选不再是常驻栏，而是盖在列表上的抽屉。
                    常驻一栏在 <1280 时会把题目区挤得太窄（实测 1200px 下只剩 700px）。 */}
                <div className="absolute inset-0 z-40 bg-scrim xl:hidden"
                  onClick={() => setShowFilter(false)} />
                <div className="relative z-50 flex max-xl:absolute max-xl:inset-y-0 max-xl:left-0
                                max-xl:shadow-[var(--shadow-pop)] xl:relative">
                  <FilterPanel L={L} onClose={() => setShowFilter(false)} />
                  {filterHot && (
                    <span className="anim-flash pointer-events-none absolute inset-0 z-10
                                     ring-2 ring-brand ring-inset" />
                  )}
                </div>
              </>)}

              {/* ── 题目栏：**题目列表和卷子是同一栏里的两个视图** ──
                  内容区到这儿就结束了（没有第三栏）。 */}
              <section className="flex min-w-0 flex-1 flex-col">
                {/* 列表头。
                    **勾了题的时候，这一行整条换成批量操作条**（Gmail 的做法）——
                    旧版是在下面另起一行，列表会往下跳一格；换成"占同一行"之后
                    勾选不再引起位移。 */}
                <ListHeader
                  L={L} total={total} loading={loading} scopeChips={scopeChips}
                  showFilter={showFilter} onShowFilter={() => setShowFilter(true)}
                  clearAllFilters={clearAllFilters}
                  dense={dense} onDense={() => setDense(!dense)}
                  compact={compact} onCompact={() => setCompact(!compact)}
                  maskAns={maskAns} onMaskAns={() => setMaskAns(!maskAns)}
                  onPalette={() => setPalette(true)}
                  onDeleteChecked={() => setDeleteAsk({ qs: [...checkedMap.values()] })}
                  onAddChecked={addChecked}
                  onBatchEdit={() => setBatchOpen(true)}
                  view={view} />

                {/* ── 卷子条 ──
                    卷子不再单独占一栏，就在这儿：**一条计数 + 点开切视图**。
                    有题时常驻（提醒"你手上已经有几道了"）；空卷子不占地方。 */}
                <PaperBar paper={paper} paperScore={paperScore} answered={answered}
                  view={view} onToggleView={() => setView(view === 'paper' ? 'list' : 'paper')}
                  onClear={clearPaper} onExport={() => setShowExport(true)} />

                {/* ── 栏内主体：题目列表 / 当前卷子 ── */}
                {view === 'paper' ? (
                  <PaperPanel key="paper" paper={paper}
                    onOpen={(it) => { setSel(it); setDOpen(true) }}
                    onRemove={removeFromPaperUndo} onMove={moveInPaper}
                    onSwap={replaceInPaper}
                    onBack={() => setView('list')} />
                ) : (
                  <QuestionList L={L} dense={dense} compact={compact} maskAns={maskAns}
                    paperMap={paperMap}
                    onOpen={showDetail} onAdd={addToPaper}
                    onClearFilters={clearAllFilters} />
                )}
              </section>

              {/* ── 详情抽屉 ──
                  **宽屏占一栏**：以前浮在列表上，右边那条题目被压掉半截——
                  用户正想对着题干看，结果读不全。现在它是 flex 的兄弟节点，
                  列表缩窄、内容一分不遮（窄屏仍然盖上去，没那么多宽度可分）。
                  不做点击遮罩关闭 —— 组卷时经常要"点一道看一道"，
                  抽屉开着还能继续点后面的卡片才顺手。 */}
              <DetailDrawer open={dShown} closing={dClosing} width={dW} setWidth={setDW}
                sel={sel} full={full} facets={facets} loading={loading} kw={q.trim()}
                maxWidth={vw >= 1280 ? drawerMax : undefined}
                onClose={() => setDOpen(false)} onFindPoint={findPoint}
                onDeleteAsk={() => sel && setDeleteAsk({ qs: [sel] })}
                onSaved={(d, opts) => {
                  // 改出处/改题号会**换 key**：先把卷子/讲义/勾选里的旧 key
                  // 换成新的，再更新详情。`full` 是抽屉优先显示的那份，
                  // 它就是被编辑的题；没有就用 `sel`。
                  const oldKey = (full ?? sel)?.key || d.key
                  if (oldKey !== d.key) remapKey(oldKey, d)
                  // **卷子里存的是加入那一刻的 Q 快照**：补完解析、改了答案
                  // 或题型，不换掉这份快照，卷子条的「有解析 0/1」和分数会一直
                  // 是旧值（导出 PDF 按 key 取盘上新数据，于是显示与产物不一致）。
                  const freshen = (m: Map<string, Q>) =>
                    m.has(d.key) ? new Map(m).set(d.key, d) : m
                  setPaperMap(freshen)
                  setSel(d)
                  // **详情正文也要跟着换**：DetailDrawer 优先用 `full`，
                  // 只更新 `sel` 的话改完答案/解析/源码，右栏还显示改之前的内容。
                  setFull(d)
                  setItems((xs) => xs.map((x) => (x.key === d.key ? { ...x, ...d } : x)))
                  // 难度/考点是**筛选条件**：改完可能就该从当前这一页消失
                  // （比如筛「简单题」时改成「难题」）。原地合并做不到这件事，
                  // 所以再让列表带着筛选条件重新拉一遍——用户要的「自动刷新」。
                  // 源码/答案/解析/题型只是内容变了，详情已经用返回值更新过，
                  // 列表在后台**静默**校正即可，别再闪「正在刷新列表…」。
                  if (opts?.refreshList) {
                    if (opts.silent) refreshSilent()
                    else setReload((v) => v + 1)
                  }
                }} />
            </div>
          )}
        </div>
      </div>

      {/* 快捷键浮球：这一版的单键导航没有面板可看就没人知道，所以常驻一个入口 */}
      {!FULL_PAGE.includes(tab) && <HelpButton />}

      {/* ⌘K 命令面板 + 轻提示（带撤销） */}
      <CommandPalette open={palette} onClose={() => setPalette(false)}
        commands={commands}
        onSearch={(w) => { setTab('workbench'); setView('list'); setQ(w) }} />
      <Toaster />

      {exportShown && <ExportPage closing={exportClosing} init={paper} from={exportFrom}
        pageItems={items} poolTotal={total} filters={L.filters}
        onClose={() => setShowExport(false)} />}

      {batchOpen && (
        <BatchTagDialog
          keys={[...checkedMap.keys()]}
          facets={facets}
          onClose={() => setBatchOpen(false)}
          onDone={() => {
            setBatchOpen(false)
            L.clearChecked()
            refreshSilent()
          }} />
      )}

      {deleteAsk && (
        <DeleteModal
          qs={deleteAsk.qs ?? items.filter((x) => (deleteAsk.keys || []).includes(x.key))}
          keys={deleteAsk.keys}
          onCancel={() => setDeleteAsk(null)}
          onConfirm={(reason) =>
            deleteQuestions(deleteAsk.keys ?? (deleteAsk.qs || []).map((x) => x.key), reason)
              .then(() => setDeleteAsk(null))} />
      )}

      {ingestShown && <IngestDrawer closing={ingestClosing} facets={facets}
        onClose={() => setShowIngest(false)} onDone={() => setReload((n) => n + 1)} />}
    </div>
  )
}
