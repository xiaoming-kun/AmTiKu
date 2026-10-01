import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  ListFilter, SlidersHorizontal, X, Check, ChevronFirst, ChevronLast, ChevronRight,
  ClipboardList, Rows3, Rows2, BookPlus, FileText, ChevronUp, ChevronDown,
  LayoutGrid, ScanLine, FolderTree, Sparkles, Trash2, History,
  Command as CommandIcon,
} from 'lucide-react'
import type { Q, Base } from '@/lib/types'
import { api, reportErr, setGlobalErrHandler } from '@/lib/api'
import { SECTION_LABEL, scoreOf, paperScore as totalScore } from '@/lib/paper'
import { DIFF_STARS } from '@/lib/display'
import { useQuestionList } from '@/lib/useQuestionList'
import { Flags, Grip, useWidth, useFlag, useUnmount, Num, CloseBtn } from '@/app/ui'
import QuestionCard from '@/app/QuestionCard'
import { Trash, DeleteModal } from '@/app/Trash'
import { Detail, TexSource } from '@/app/Detail'
import { Changes } from '@/app/Stats'
import ExportPage from '@/app/ExportPage'
import IngestDrawer from '@/app/IngestDrawer'
import Nav, { NAV_BY_HINT, NAV_GROUPS, type NavKey } from '@/app/Nav'
import TopBar from '@/app/TopBar'
import FilterPanel from '@/app/FilterPanel'
import HelpButton from '@/app/HelpButton'
import { Toaster, toast, dismissToasts } from '@/app/Toast'
import CommandPalette, { type Cmd } from '@/app/CommandPalette'

/** 整屏页面。
 *
 *  **没有「第三栏」了**——内容区只有「筛选 | 题目」两栏：
 *  · 题目列表和当前卷子是**同一栏里的两个视图**（`view` 切换）；
 *  · 题目详情 / LaTeX 源码是**浮在内容区上的抽屉**（`dOpen`，按需开、随时关）。
 *  所以这里只剩「整屏页面」这一种 tab。 */
type Tab = 'workbench' | 'changes' | 'trash'
const FULL_PAGE: Tab[] = ['changes', 'trash']

export default function App() {
  // 列表数据与筛选 → useQuestionList（一行拿到全部筛选状态，见 lib/useQuestionList.ts）
  const L = useQuestionList()
  const {
    facets, items, setItems, total, sel, setSel, loading, reload, setReload,
    page, setPage, pageSize, setPageSize, pageInput, setPageInput, jumpPage, listRef,
    q, setQ, type, setType, kind, setKind, has, setHas, missing, setMissing, points, setPoints,
    diffs, setDiffs, years, setYears, sort, checked, setChecked,
    selectMode, setSelectMode, exitSelect, activeFilters,
  } = L

  const [base, setBase] = useState<Base | null>(null)
  const [tab, setTab] = useState<Tab>('workbench')
  const [showExport, setShowExport] = useState(false)
  const [showIngest, setShowIngest] = useState(false)
  const [globalErr, setGlobalErr] = useState('')

  /** 题目栏里现在显示哪一个视图：题目列表 or 当前卷子。
   *  两者**共用同一栏**（不是两个栏目），所以切换不改变任何宽度。 */
  const [view, setView] = useState<'list' | 'paper'>('list')
  /** 详情抽屉开着没有。它浮在内容区上（不占栏），Esc / ✕ 关掉。 */
  const [dOpen, setDOpen] = useState(false)
  const [dTab, setDTab] = useState<'detail' | 'tex'>('detail')
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
  /** 命令面板（⌘K）——设计文档 §原则4 里就写了，这一版补上。 */
  const [palette, setPalette] = useState(false)

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

  /** 全局错误提示。
   *  以前请求失败是**静默**的：接口 400 返回 {detail}，前端当数据用，
   *  界面表现成"没题""没变化"。现在 request() 统一抛错，这里接住并显示。 */
  useEffect(() => {
    setGlobalErrHandler(setGlobalErr)
    return () => setGlobalErrHandler(null)
  }, [])

  /* ── 卷子收集夹 ─────────────────────────────────────
     组卷导出用：勾中的题进这里，导出页和「当前卷子」视图都读它。 */
  const [paperMap, setPaperMap] = useState<Map<string, Q>>(new Map())
  const paper = useMemo(() => [...paperMap.values()], [paperMap])
  const paperScore = totalScore(paper)
  const answered = paper.filter((x) => x.flags['解析']).length
  // 导出对象**只认卷子**，默认为空。
  // 早先卷子一空就自动拿「当前筛选结果」顶上，于是刚进页面就显示
  // 「导出 38」——用户还没说要导出什么，程序先替他决定了。不对。
  const exportFrom = `卷子（${paper.length} 题）`

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
    setPoints([pid]); setQ(''); setPage(1)
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
  const deleteQuestions = (keys: string[], reason: string, password: string) =>
    api.trashBatch(keys, reason, password).then(() => {
      const ks = new Set(keys)
      // 卷子里、勾选里的也要一起清掉——不然删除后它们还挂在那儿
      setPaperMap((m) => { const n = new Map(m); for (const k of ks) n.delete(k); return n })
      setChecked((c) => { const n = new Set(c); for (const k of ks) n.delete(k); return n })
      setReload((v) => v + 1)
    }).catch(reportErr)

  /** 把勾中的题一次性加进卷子 */
  const addChecked = () => {
    const picked = items.filter((x) => checked.has(x.key))
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

  /* ── 导航动作 ── */
  const navActive: NavKey =
    tab === 'trash' ? 'trash' : tab === 'changes' ? 'changes'
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

      // ⌘K / Ctrl+K 命令面板。**在任何地方都要能唤起**（包括输入框里）——
      // 它本来就是"手不离键盘"的入口，在搜索框里打了一半想跳走是最需要它的时候。
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault(); setPalette((v) => !v); return
      }
      if (e.key === 'Escape' && palette) { e.preventDefault(); setPalette(false); return }

      if (e.key === '/' && !typing()) {
        e.preventDefault(); searchRef.current?.focus(); return
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault(); setShowExport(true); return
      }
      // 命令面板开着的时候，下面的单键和方向键都归它 —— 不能两处一起动
      if (palette) return
      if (e.key === 'Escape') { setDOpen(false); setShowExport(false); setShowIngest(false); return }
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (typing()) return
      // 有弹层/全屏编辑器时，单键和方向键都让给它 ——
      // 否则在导出弹层里按 ↓，背后的列表光标会跟着乱跑
      if (showExport || showIngest || FULL_PAGE.includes(tab)) return

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
      { id: 'view:select', label: selectMode ? '关掉多选模式' : '打开多选模式', group: '看',
        icon: <Check size={13} />, keywords: 'duoxuan select 多选 勾选',
        run: () => (selectMode ? exitSelect() : setSelectMode(true)) },
      { id: 'act:export', label: '新建试卷 / 组卷导出', group: '做', icon: <Sparkles size={13} />,
        hint: '⌘↵', keywords: 'daochu export zujuan pdf 导出 组卷', run: () => setShowExport(true) },
      { id: 'act:ingest', label: '录入新题', group: '做', icon: <ScanLine size={13} />,
        hint: 'I', keywords: 'luru ingest 录题 录入', run: () => setShowIngest(true) },
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
    setYears([]); setType(''); setKind(''); setQ('')
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
      key: `h${h}`, label: `有${h}`, clear: () => setHas((xs) => xs.filter((x) => x !== h)),
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
        <Nav active={navActive} onPick={pick} collapsed={navShut} onCollapsed={setNavShut}
          kind={kind} onKind={setKind} kinds={facets?.kinds || []}
          total={total} pointsCovered={facets?.points_covered || 0}
          pointsTotal={facets?.points.length || 0} />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar q={q} onQ={setQ} inputRef={searchRef} base={base} paperCount={paper.length}
            onPaper={gotoPaper}
            onExport={() => setShowExport(true)}
            onIngest={() => setShowIngest(true)} onReload={() => setReload((v) => v + 1)} />

          {FULL_PAGE.includes(tab) ? (
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
                {/* 列表头。
                    **勾了题的时候，这一行整条换成批量操作条**（Gmail 的做法）——
                    旧版是在下面另起一行，列表会往下跳一格；换成"占同一行"之后
                    勾选不再引起位移。 */}
                {view === 'list' && selectMode && checked.size > 0 ? (
                  <div className="anim-fade-in flex h-[52px] shrink-0 items-center gap-2.5
                                  border-b border-brand-line bg-brand-soft px-4">
                    <span className="shrink-0 text-[14px] font-semibold text-brand-ink">
                      已选 <span className="tnum">{checked.size}</span> 道
                    </span>
                    <button onClick={() => setChecked(new Set(items.map((x) => x.key)))}
                      className="press rounded-lg border border-brand-line bg-surface px-2.5 py-[4px]
                                 text-[12px] text-brand-ink hover:bg-surface-2">全选本页</button>
                    <button onClick={() => setChecked(new Set())}
                      className="press rounded-lg border border-brand-line bg-surface px-2.5 py-[4px]
                                 text-[12px] text-brand-ink hover:bg-surface-2">清空</button>
                    <span className="min-w-0 flex-1" />
                    {/* **批量删除**：一道一道删太慢；走的是同一个删除弹窗，
                        原因和口令一样都不能少（批量更危险，规矩一条不减）。 */}
                    <button onClick={() => setDeleteAsk({ keys: [...checked] })}
                      className="press shrink-0 rounded-lg border border-warn-line bg-surface px-2.5
                                 py-[4px] text-[12px] font-medium text-warn hover:bg-warn-soft">
                      删除选中
                    </button>
                    <button onClick={addChecked}
                      className="press shrink-0 rounded-lg bg-brand px-3 py-[4px] text-[12px]
                                 font-medium text-white shadow-[var(--shadow-brand)] hover:brightness-105">
                      加入卷子
                    </button>
                    <button onClick={exitSelect} title="退出多选（Esc）"
                      className="icon-btn h-7 w-7 shrink-0">
                      <X size={15} />
                    </button>
                  </div>
                ) : (
                <div className="flex h-[52px] shrink-0 items-center gap-2.5 border-b border-border
                                bg-surface px-4">
                  <h1 className="shrink-0 text-[19px] font-semibold tracking-tight">题库</h1>
                  <span className="tnum shrink-0 rounded-full bg-muted px-2 py-[2px] text-[11.5px]
                                   font-medium text-ink-soft">
                    {loading ? '加载中…' : <><Num value={total} /> 道</>}
                  </span>
                  {/* **筛了什么，直接摆出来、逐个能摘**。
                      以前这里是一句拼出来的中文（「缺：解析」「有：图」），
                      既看不出是几条，也没法单独去掉一条——只能"清除全部"重来。
                      成熟做法（Linear / GitHub Issues）是把生效的条件做成可删的胶囊。 */}
                  <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 overflow-hidden">
                    {scopeChips.length === 0 ? (
                      <span className="truncate text-[12px] text-ink-faint">全部题目</span>
                    ) : (<>
                      {scopeChips.slice(0, 4).map((c) => (
                        <button key={c.key} onClick={c.clear} title={`去掉「${c.label}」`}
                          className="press group flex shrink-0 items-center gap-1 rounded-full
                                     bg-brand-soft px-2 py-[2px] text-[11.5px] font-medium
                                     text-brand-ink hover:bg-brand hover:text-white">
                          <span className="max-w-[16ch] truncate">{c.label}</span>
                          <X size={11} className="opacity-55 group-hover:opacity-100" />
                        </button>
                      ))}
                      {scopeChips.length > 4 && (
                        <span className="tnum shrink-0 text-[11.5px] text-ink-faint">
                          +{scopeChips.length - 4}
                        </span>
                      )}
                      <button onClick={clearAllFilters}
                        className="press shrink-0 rounded-full px-1.5 py-[2px] text-[11.5px]
                                   text-ink-faint hover:text-warn">清除</button>
                    </>)}
                  </span>
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
                  {/* ⌘K：面板里能做的事最多，但入口得看得见，不然没人知道 */}
                  <button onClick={() => setPalette(true)} title="命令面板（⌘K）"
                    className="press flex h-[30px] shrink-0 items-center gap-1.5 rounded-lg border
                               border-border bg-surface px-2 text-[12.5px] text-ink-faint
                               hover:border-border-strong hover:text-ink">
                    <CommandIcon size={13} />
                    <kbd className="hidden text-[10.5px] xl:inline">⌘K</kbd>
                  </button>
                  {/* 密度：挑题时想一屏多扫几道，读题时想宽松。
                      图标按钮 + title，不占地方。 */}
                  {view === 'list' && (
                    <button onClick={() => setDense(!dense)}
                      title={dense ? '切换成宽松卡片' : '切换成紧凑卡片'}
                      className={`press grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg
                                  border transition-colors ${dense
                        ? 'border-brand-line bg-brand-soft text-brand-ink'
                        : 'border-border bg-surface text-ink-faint hover:text-ink'}`}>
                      {dense ? <Rows2 size={14} /> : <Rows3 size={14} />}
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
                )}

                {/* ── 卷子条 ──
                    卷子不再单独占一栏，就在这儿：**一条计数 + 点开切视图**。
                    有题时常驻（提醒"你手上已经有几道了"）；空卷子不占地方。 */}
                {paper.length > 0 && (
                  <div
                    className={`anim-slide-d flex shrink-0 items-center gap-2.5 border-b px-4 py-2
                                text-[12.5px] ${view === 'paper'
                      ? 'border-brand-line bg-brand-soft/60'
                      : 'border-border bg-surface-2'}`}>
                    <button onClick={() => setView(view === 'paper' ? 'list' : 'paper')}
                      className="press flex min-w-0 flex-1 items-center gap-2.5 text-left">
                      <ClipboardList size={14}
                        className={view === 'paper' ? 'shrink-0 text-brand' : 'shrink-0 text-ink-faint'} />
                      {/* 只让**计数**跳一下就够。整条是满宽的，给它加 scale 动画
                          会在动画那一帧里顶出视口 80px（还闪一下横向滚动条）。 */}
                      {/* 数字**滚过去**而不是跳过去（见 ui.tsx 的 Num）——
                          这本身就是"加进去了"的回执，不用再叠个 scale 跳动。 */}
                      <span className="inline-flex shrink-0 items-baseline gap-1">
                        <span className={view === 'paper' ? 'font-semibold text-brand-ink' : 'font-semibold text-ink'}>
                          {view === 'paper' ? '当前卷子' : '已选'}
                        </span>
                        <Num value={paper.length} className="font-semibold text-brand-ink" />
                        <span className={view === 'paper' ? 'text-brand-ink' : 'text-ink'}>题</span>
                      </span>
                      <span className="shrink-0 text-ink-soft">
                        <Num value={paperScore} /> 分
                      </span>
                      <span className={`tnum shrink-0 ${answered === paper.length && paper.length
                        ? 'text-has' : 'text-warn'}`}>
                        有解析 {answered}/{paper.length}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-faint">
                        {view === 'paper'
                          ? '每题右侧 ▲▼ 在题型内调顺序，✕ 移出，或直接导出'
                          : '点这里查看卷子'}
                      </span>
                      <span className="flex shrink-0 items-center gap-1 font-medium text-brand-ink">
                        {view === 'paper' ? '返回题目' : '查看卷子'}
                        {view === 'paper'
                          ? <ChevronRight size={13} className="rotate-180" />
                          : <ChevronRight size={13} />}
                      </span>
                    </button>
                    {/* **一键清空**：挑卷子经常推倒重来，一道一道点 ✕ 太慢。
                        这里**不再要两段确认**——确认框是"每次都要多点一下"的税，
                        而撤销只在真错的时候用。清空后那条提示留 8 秒给撤销。 */}
                    <button onClick={clearPaper}
                      title="清空卷子（可以撤销）"
                      className="press shrink-0 rounded-md border border-border bg-surface px-2
                                 py-[3px] text-[11.5px] text-ink-faint transition-colors
                                 hover:border-warn-line hover:text-warn">
                      清空
                    </button>
                    <button onClick={() => setShowExport(true)}
                      className="press shrink-0 rounded-md bg-brand px-2.5 py-[4px] text-[11.5px]
                                 font-medium text-white shadow-[var(--shadow-brand)] hover:brightness-105">
                      导出 ⌘↵
                    </button>
                  </div>
                )}

                {/* ── 栏内主体：题目列表 / 当前卷子 ── */}
                {view === 'paper' ? (
                  <PaperPanel key="paper" paper={paper}
                    onOpen={(it) => { setSel(it); setDOpen(true) }}
                    onRemove={removeFromPaperUndo} onMove={moveInPaper}
                    onBack={() => setView('list')} />

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
                      inPaper={paperMap.has(it.key)}
                      selectMode={selectMode} checked={checked.has(it.key)} dense={dense}
                      onOpen={() => showDetail(it)}
                      onDetail={() => showDetail(it)}
                      onAdd={() => { addToPaper(it) }}
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

                {/* 分页条。**总页数大于 1 才出现**——只有一页时占地方没意义。
                    `pr-16`：右下角那颗快捷键浮球是 fixed 的，列表栏拉满时
                    它会**压住「第 1–20 道，共 … 道」**，给它让出 64px。 */}
                {total > pageSize && (
                  <div className="flex shrink-0 items-center gap-1.5 border-t border-border bg-surface
                                  py-2 pl-4 pr-20 text-[12px] text-ink-faint">
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
              {dShown && (<>
                {/* 详情里有题图和长解析，固定宽度对某些题太窄、对另一些又浪费——
                    和筛选面板一样给一条能拖的边。
                    拖拽条**绝对定位到抽屉左边缘**，不能留在 flex 流里：
                    留在流里会给内容区多挤出 1px，而且抽屉是 absolute、会把它盖住。 */}
                <div className="absolute inset-y-0 z-40 flex" style={{ right: dW - 3 }}>
                  <Grip width={dW} setWidth={setDW} min={380} max={940} />
                </div>
                <aside style={{ width: dW }}
                  className={`${dClosing ? 'anim-slide-r-out' : 'anim-slide-r'} absolute inset-y-0
                             right-0 z-30 flex flex-col border-l border-border bg-surface
                             shadow-[var(--shadow-pop)]`}>
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
                    <CloseBtn onClick={() => setDOpen(false)} title="关闭（Esc）" />
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
              </>)}
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

      {exportShown && <ExportPage closing={exportClosing} init={paper} pool={items} from={exportFrom}
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

      {ingestShown && <IngestDrawer closing={ingestClosing} facets={facets}
        onClose={() => setShowIngest(false)} onDone={() => setReload((n) => n + 1)} />}
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
function PaperPanel({ paper, onOpen, onRemove, onMove, onBack }: {
  paper: Q[]; onOpen: (q: Q) => void; onRemove: (k: string) => void
  onMove: (k: string, d: -1 | 1) => void; onBack: () => void
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {paper.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center text-ink-faint">
          <SlidersHorizontal size={22} className="text-border-strong" />
          <span className="text-[13px]">卷子还是空的</span>
          <span className="text-[11.5px] leading-relaxed">
            在题目列表的卡片上点 <b className="text-brand-ink">加入组卷</b>，
            或按住 <kbd className="rounded border border-border bg-muted px-1">↑</kbd>
            <kbd className="ml-0.5 rounded border border-border bg-muted px-1">↓</kbd> 选好再按
            <kbd className="mx-0.5 rounded border border-border bg-muted px-1">Enter</kbd>
          </span>
          {/* 正常走不到这儿（空卷子会被 gotoPaper / 那个 effect 拦在列表上），
              留个出口以防万一 */}
          <button onClick={onBack}
            className="press mt-1 rounded-lg bg-brand px-3.5 py-2 text-[12.5px] font-medium
                       text-white shadow-[var(--shadow-brand)] hover:brightness-105">
            返回题目列表
          </button>
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
                  <span className="tnum">{group.length} 题 · {scoreOf(t, group.length)} 分</span>
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
                      {/* 顺序：卷子是按题型分节的，所以只能**在节内**上下挪。
                          到顶/到底时按钮置灰，不做无声无息的无操作。 */}
                      <span className="flex shrink-0 items-center gap-0.5">
                        <button onClick={(e) => { e.stopPropagation(); onMove(it.key, -1) }}
                          disabled={i === 0} title="在这一节里上移"
                          className="icon-btn h-5 w-5 disabled:opacity-25 disabled:hover:bg-transparent">
                          <ChevronUp size={13} />
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); onMove(it.key, 1) }}
                          disabled={i === group.length - 1} title="在这一节里下移"
                          className="icon-btn h-5 w-5 disabled:opacity-25 disabled:hover:bg-transparent">
                          <ChevronDown size={13} />
                        </button>
                      </span>
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
