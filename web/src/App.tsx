/** AmTiKu · K12 数学题库
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
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, BookOpenText, BookPlus, Check, ClipboardCheck, ClipboardList, Command as CommandIcon,
  FilePlus2, FileStack, FolderOpen, History, LayoutDashboard,
  ListFilter, Network, Rows2, Rows3, Sparkles, Trash2, X,
} from 'lucide-react'
import type { Q, Overview } from '@/lib/types'
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
import DetailDrawer from '@/app/DetailDrawer'
import { Changes } from '@/app/Stats'
import ExportPage from '@/app/ExportPage'
import IngestDrawer from '@/app/IngestDrawer'
import FilterPanel, { FILTER_W } from '@/app/FilterPanel'
import HelpButton from '@/app/HelpButton'
import Health, { type Scope } from '@/app/Health'
import MapPage from '@/app/MapPage'
import TopicsPage from '@/app/TopicsPage'
import { Toaster, toast, dismissToasts } from '@/app/Toast'
import CommandPalette, { type Cmd } from '@/app/CommandPalette'
import { INITIAL_URL, writeUrlState, type UrlFilters } from '@/lib/urlState'
import { readStage, rememberStage, type Stage } from '@/lib/stage'
import Shell, { PAGE_META, type PageKey } from '@/app/Shell'
import OverviewPage from '@/app/pages/Overview'
import DiagnosticBank from '@/app/pages/DiagnosticBank'
import IngestHome from '@/app/pages/IngestHome'
import PaperStudio from '@/app/pages/PaperStudio'
import PapersPage from '@/app/pages/PapersPage'
import Review from '@/app/pages/Review'

const PAGES: PageKey[] = ['overview', 'map', 'lectures', 'bank', 'ingest', 'paper', 'papers', 'health', 'review', 'trash', 'changes']
const LEGACY_TAB: Record<string, PageKey> = {
  workbench: 'bank', health: 'health', map: 'map', topics: 'lectures',
  changes: 'changes', trash: 'trash',
}
const HINTS: Record<string, PageKey> = {
  o: 'overview', m: 'map', t: 'lectures', b: 'bank', i: 'ingest',
  p: 'paper', s: 'papers', h: 'health', r: 'trash', c: 'changes',
}
const EMPTY_FILTERS: UrlFilters = {
  q: '', type: '', kind: '', point: '', diff: '', year: '', source: '',
  has: '', missing: '', scope: '', paper: '', star: '', quality: '',
  psrc: '', asrc: '', reviewed: '',
}

/** 批量改出处后，后端回传的单题改名映射（old key → new key）。 */
type KeyRename = {
  old: string; new: string
  book?: string; label?: string; year?: number | string
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

export default function App() {
  const [stage, setStageState] = useState<Stage>(() => readStage(INITIAL_URL.stage))
  const [page, setPage] = useState<PageKey>(initialPage)
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
  const [showIngest, setShowIngest] = useState(false)
  const [ingestAI, setIngestAI] = useState(false)
  const [palette, setPalette] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [diagPoint, setDiagPoint] = useState('')
  /** 小学/初中题库里同时有「诊断题」和「正式题」两个来源；默认看正式题（有的话）。 */
  const [smallBank, setSmallBank] = useState<'formal' | 'diagnostic'>('diagnostic')
  const smallInit = useRef('')

  /** 详情抽屉：默认开在宽屏上，关掉后记住选择。 */
  const [dOpen, setDOpen] = useFlag('amtiku.detail',
    typeof window !== 'undefined' && window.innerWidth >= 1400)
  const { shown: dShown, closing: dClosing } = useUnmount(dOpen, 170)
  const { shown: exportShown, closing: exportClosing } = useUnmount(showExport, 160)
  const { shown: ingestShown, closing: ingestClosing } = useUnmount(showIngest, 170)
  const [dW, setDW] = useWidth('amtiku.w.drawer', 620, 380, 940)
  const [dense, setDense] = useFlag('amtiku.dense', false)
  const [compact, setCompact] = useFlag('amtiku.compact', false)
  const [maskAns, setMaskAns] = useFlag('amtiku.maskAns', true)
  const [showFilter, setShowFilter] = useFlag('amtiku.showFilter', false)
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
  /** 知识图谱「按学习路径组卷」：一次加一批（可能跨十来个考点）。 */
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
    toast(`已按学习路径加入 ${fresh.length} 道题`, {
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
    if (!paper.length) toast('卷子还是空的 —— 先在题库里点「加入组卷」', { tone: 'info' })
  }

  const switchStage = (s: Stage) => {
    if (s === stage) return
    setStageState(s)
    rememberStage(s)
    L.loadFilters(EMPTY_FILTERS, 'used')
    setDiagPoint('')
    setFindNote('')
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
        point: L.filters.point, diff: L.filters.difficulty, year: L.filters.year,
        source: L.filters.source, has: L.filters.has, missing: L.filters.missing,
        scope: L.filters.region_scope, paper: L.filters.paper_state,
        star: L.filters.star_state, quality: L.filters.quality,
        psrc: L.filters.point_source, asrc: L.filters.answer_source,
        reviewed: L.filters.reviewed,
      },
      sort: L.sort, page: L.page, tab: '', view: page, stage,
    })
  }, [L.filters, L.sort, L.page, page, stage])

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
        if (showExport || showIngest || palette) return
        if (L.sel) addToPaper(L.sel)
        return
      }
      if (palette) return
      if (e.key === 'Escape') {
        if (showExport || showIngest) { setShowExport(false); setShowIngest(false); return }
        if (dOpen) { setDOpen(false); return }
        if (L.selectMode && L.checkedMap.size) { L.exitSelect(); return }
        return
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (typing()) return
      if (showExport || showIngest) return

      const k = e.key.toLowerCase()
      if (HINTS[k]) { e.preventDefault(); setPage(HINTS[k]); return }
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
  }, [L.items, L.sel, page, dOpen, palette, showExport, showIngest])

  /* ── 命令面板 ─────────────────────────────────────── */
  const commands: Cmd[] = useMemo(() => {
    const navIcon: Record<PageKey, React.ReactNode> = {
      overview: <LayoutDashboard size={13} />, map: <Network size={13} />,
      lectures: <BookOpenText size={13} />, bank: <ListFilter size={13} />,
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
      icon: navIcon[p], keywords: navWords[p], run: () => setPage(p),
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
        run: () => setPage('ingest') },
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
  }, [L.facets, L.kind, L.selectMode, showFilter, dense, compact, paper.length, paperScore, L.activeFilters])

  /* ── 筛选胶囊 ─────────────────────────────────────── */
  const clearAllFilters = () => {
    L.setHas([]); L.setMissing([]); L.setPoints([]); L.setDiffs([])
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
    <div className="relative flex h-full min-h-0">
      {showFilter && (<>
        <div className="absolute inset-0 z-40 bg-scrim xl:hidden" onClick={() => setShowFilter(false)} />
        <div className="relative z-50 flex max-xl:absolute max-xl:inset-y-0 max-xl:left-0
                        max-xl:shadow-[var(--shadow-pop)] xl:relative">
          <FilterPanel L={L} onClose={() => setShowFilter(false)} onMap={() => setPage('map')}
            onClearAll={clearAllFilters} />
        </div>
      </>)}
      <section className="flex min-w-0 flex-1 flex-col">
        <ListHeader
          L={L} total={L.total} loading={L.loading} scopeChips={scopeChips}
          showFilter={showFilter} onShowFilter={() => setShowFilter(true)}
          clearAllFilters={clearAllFilters}
          dense={dense} onDense={() => setDense(!dense)}
          compact={compact} onCompact={() => setCompact(!compact)}
          maskAns={maskAns} onMaskAns={() => setMaskAns(!maskAns)}
          onPalette={() => setPalette(true)} zen={zen} onZen={() => setZen(!zen)}
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
        onSaved={(d, opts) => {
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
        }} />
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
            onOpenPoint={openPoint} onIngest={() => setPage('ingest')}
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
          onPaper={gotoPaper} onIngest={() => setPage('ingest')}
          onHelp={() => window.dispatchEvent(new CustomEvent('amtiku:help'))}
          searchRef={searchRef}>
          {page === 'overview' ? (
            <OverviewPage stage={stage} data={overview} loading={ovLoading}
              onStage={switchStage} onPage={setPage} onTask={openTask}
              onPaper={gotoPaper} onIngest={() => setPage('ingest')}
              onBankFilter={() => { setPage('bank'); setShowFilter(true) }}
              onReview={() => setPage('review')}
              onOpenPaper={openSavedPaper} />
          ) : page === 'map' ? (
            <MapPage stage={stage} onPickPoint={openPoint} onAddPaper={addPaperBatch} onOpenLecture={openLecture} />
          ) : page === 'lectures' ? (
            <TopicsPage stage={stage} onPickPoint={openPoint} onOpenQuestion={openQuestion} initialPick={lecturePick} />
          ) : page === 'bank' ? (
            bankView
          ) : page === 'ingest' ? (
            <IngestHome stage={stage} onOpen={(ai) => { setIngestAI(ai); setShowIngest(true) }}
              onBank={() => setPage('bank')} />
          ) : page === 'paper' ? (
            <PaperStudio stage={stage} paper={paper} score={paperScore} answered={answered}
              onOpenQuestion={openQuestion} onRemove={removeFromPaperUndo}
              onMove={moveInPaper} onSwap={replaceInPaper}
              onExport={() => setShowExport(true)} onBank={() => setPage('bank')}
              onPapers={() => setPage('papers')} onGenerate={() => setShowExport(true)} />
          ) : page === 'papers' ? (
            <PapersPage onLoad={loadPaper} onPaper={gotoPaper} />
          ) : page === 'health' ? (
            <div className="b-scroll h-full overflow-y-auto"><Health stage={stage} onScope={openScope}
              onMap={() => setPage('map')} onIngest={() => setPage('ingest')}
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
        </Shell>
      </div>

      {page !== 'paper' && <HelpButton />}
      <CommandPalette open={palette} onClose={() => setPalette(false)}
        commands={commands}
        onSearch={(w) => { setPage('bank'); L.setQ(w) }} />
      <Toaster />

      {exportShown && <ExportPage closing={exportClosing} init={paper} from={exportFrom}
        pageItems={L.items} poolTotal={L.total} filters={L.filters}
        onClose={() => setShowExport(false)} />}

      {batchOpen && (
        <BatchTagDialog keys={[...L.checkedMap.keys()]} facets={L.facets}
          onClose={() => setBatchOpen(false)}
          onDone={(res) => {
            setBatchOpen(false)
            // 批量改书名/卷名会换 key：卷子、详情缓存、当前选中都得一起迁，
            // 否则它们还拿着旧 key，导出时才报「找不到题」。
            remapBatch(Array.isArray(res?.renames) ? res.renames : [])
            L.clearChecked()
            L.refreshSilent()
          }}
          onTrimTo={(n) => {
            const keep = [...L.checkedMap.entries()].slice(0, n)
            L.setChecked(new Set(keep.map(([k]) => k)))
            L.setCheckedMap(new Map(keep))
          }} />
      )}

      {deleteAsk && (
        <DeleteModal qs={deleteAsk.qs ?? L.items.filter((x) => (deleteAsk.keys || []).includes(x.key))}
          keys={deleteAsk.keys}
          onCancel={() => setDeleteAsk(null)}
          onConfirm={(reason) =>
            deleteQuestions(deleteAsk.keys ?? (deleteAsk.qs || []).map((x) => x.key), reason)
              .then(() => setDeleteAsk(null))} />
      )}

      {ingestShown && <IngestDrawer closing={ingestClosing} facets={L.facets} ai={ingestAI}
        onClose={() => setShowIngest(false)}
        onDone={() => { L.setReload((n) => n + 1) }} />}
      </div>
    </div>
  )
}
