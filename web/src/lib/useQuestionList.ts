/** 题库列表的数据与筛选状态。
 *
 *  从 App.tsx 抽出来的（审查报告 CPLX-1：App 曾是全文件最大的组件）。
 *  只管「列出哪些题」这件事：筛选项、分页、勾选、列表数据。
 *  详情页、录入、导出、组卷都不在这里。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Q, Facets } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import { useDebounced } from '@/lib/useDebounced'
import { groupTree } from '@/app/Stats'
import { INITIAL_URL, type UrlFilters } from '@/lib/urlState'

export type SortKey = 'used' | 'new' | 'old' | 'solved' | 'diff' | 'diff2' | 'year' | 'year2' | ''

const SORT_KEYS = new Set<string>(['used', 'new', 'old', 'solved', 'diff', 'diff2', 'year', 'year2', ''])
const split = (s?: string) => (s || '').split(',').filter(Boolean)

export function useQuestionList() {
  const [facets, setFacets] = useState<Facets | null>(null)
  const [items, setItems] = useState<Q[]>([])
  const [total, setTotal] = useState(0)
  const [sel, setSel] = useState<Q | null>(null)
  const [loading, setLoading] = useState(false)
  const [reload, setReload] = useState(0)

  // ── 分页 ──
  const [page, setPage] = useState(INITIAL_URL.page)
  // 默认每页 100 道。后端有块级 IR 缓存，一页 100 条实测 0.02s；
  // 老师挑题时更愿意一次看到一大片，20 条翻页太勤。
  const [pageSize, setPageSize] = useState(100)
  const [pageInput, setPageInput] = useState('1')
  const listRef = useRef<HTMLDivElement>(null)

  const jumpPage = () => {
    const max = Math.max(1, Math.ceil(total / pageSize))
    const n = Math.min(max, Math.max(1, parseInt(pageInput, 10) || 1))
    setPage(n); setPageInput(String(n))
    listRef.current?.scrollTo(0, 0)
  }

  // ── 筛选项 ──
  // 初值从地址栏来：刷新/收藏一个筛选视图时，第一次请求就带着它
  const [q, setQ] = useState(INITIAL_URL.filters.q)
  const [type, setType] = useState(INITIAL_URL.filters.type)
  const [kind, setKind] = useState(INITIAL_URL.filters.kind)
  const [has, setHas] = useState<string[]>(split(INITIAL_URL.filters.has))
  // **缺什么**。后端 `missing` 是"全都缺"的语义，所以
  // `missing=答案,解析` 正好是「没解析也没答案」——最常用的一个视角：
  // 这些就是还没做的题。
  const [missing, setMissing] = useState<string[]>(split(INITIAL_URL.filters.missing))
  const [points, setPoints] = useState<string[]>(split(INITIAL_URL.filters.point))
  const [diffs, setDiffs] = useState<string[]>(split(INITIAL_URL.filters.diff))
  /** 出处（卷别）筛选。值就是 `facets.sources` 里的卷名，后端按
   *  `_source_of()`（region 优先，否则 source_label 去掉年份前缀）比对。 */
  const [sources, setSources] = useState<string[]>(split(INITIAL_URL.filters.source))
  const [scopes, setScopes] = useState<string[]>(split(INITIAL_URL.filters.scope))
  const [paperStates, setPaperStates] = useState<string[]>(split(INITIAL_URL.filters.paper))
  const [starStates, setStarStates] = useState<string[]>(split(INITIAL_URL.filters.star))
  const [qualities, setQualities] = useState<string[]>(split(INITIAL_URL.filters.quality))
  /** 考点标注来源：''=不筛；'无'=没记来源（体检页「无标签来源」点进来）。 */
  const [pointSource, setPointSource] = useState(INITIAL_URL.filters.psrc)
  /** 答案来源：human / workbuddy / legacy。回填后每道都有，能按可信度筛。 */
  const [answerSources, setAnswerSources] = useState<string[]>(split(INITIAL_URL.filters.asrc))
  /** 复核：'' / 'yes' / 'no'（有 reviewed_at 或答案是人填的算已复核）。 */
  const [reviewed, setReviewed] = useState(INITIAL_URL.filters.reviewed || '')
  const [openTopics, setOpenTopics] = useState<Set<string>>(new Set())
  // 排序：默认按**使用频次**（导出过多次的经典题排前面）。
  // `seq` 是录入先后（append 只追加，所以文件顺序就是录入顺序）。
  const [sort, setSort] = useState<SortKey>(
    INITIAL_URL.sort === null ? 'used'
      : (SORT_KEYS.has(INITIAL_URL.sort) ? INITIAL_URL.sort as SortKey : 'used'))
  const [years, setYears] = useState<string[]>(split(INITIAL_URL.filters.year))
  const toggleYear = (v: string) =>
    setYears((xs) => (xs.includes(v) ? xs.filter((x) => x !== v) : [...xs, v]))

  // 选定模式**默认开启**——绝大多数操作都是「挑几道题加进卷子」，
  // 默认开着省一次点击。但不预先勾选任何题：**选什么由你决定**。
  const [selectMode, setSelectMode] = useState(true)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  /** 勾选的那些题**本身**，不只是题号。
   *
   *  以前批量操作是拿 `items`（当前这一页）去筛 `checked`：第 1 页勾两道、
   *  翻到第 2 页再勾一道、点「加入卷子」——只有第 2 页那道进得去，前两道被
   *  静默丢掉，`exitSelect` 还会顺手清空勾选，连补救的机会都没有。
   *  勾选时就把题记下来，跨页批量才和表头的「已选 N 道」是同一件事。 */
  const [checkedMap, setCheckedMap] = useState<Map<string, Q>>(new Map())

  const toggleMissing = (k: string) =>
    setMissing((xs) => (xs.includes(k) ? xs.filter((x) => x !== k) : [...xs, k]))
  const toggleHas = (k: string) =>
    setHas((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]))
  const toggle = (set: (f: (s: string[]) => string[]) => void) => (k: string) =>
    set((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]))
  const togglePoint = toggle(setPoints)
  const toggleDiff = toggle(setDiffs)
  const togglePoints = (ids: string[]) => setPoints((cur) => {
    const allOn = ids.every((i) => cur.includes(i))
    const rest = cur.filter((i) => !ids.includes(i))
    return allOn ? rest : [...rest, ...ids.filter((i) => !cur.includes(i))]
  })
  const toggleTopic = (t: string) => setOpenTopics((s) => {
    const n = new Set(s); n.has(t) ? n.delete(t) : n.add(t); return n
  })
  /** Shift 连选的锚点：上一次点勾选的是第几道。 */
  const [anchor, setAnchor] = useState<number | null>(null)

  /** 勾选一道题。`shift` 时从上次那一道连选到这一道。
   *
   *  连选是勾上的方向由**目标那道**当前状态决定：它是未勾 → 整段勾上；
   *  它是已勾 → 整段取消。这样 Shift 点两下就等于反悔。 */
  const toggleCheck = (q: Q, i: number | null = null, shift = false) => {
    const k = q.key
    if (shift && anchor != null && i != null && anchor !== i) {
      const [a, b] = anchor < i ? [anchor, i] : [i, anchor]
      const seg = items.slice(a, b + 1)
      const on = !checked.has(k)
      setChecked((s) => {
        const n = new Set(s)
        for (const x of seg) on ? n.add(x.key) : n.delete(x.key)
        return n
      })
      setCheckedMap((m) => {
        const n = new Map(m)
        for (const x of seg) on ? n.set(x.key, x) : n.delete(x.key)
        return n
      })
      setAnchor(i)
      return
    }
    setChecked((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n })
    setCheckedMap((m) => {
      const n = new Map(m); n.has(k) ? n.delete(k) : n.set(k, q); return n
    })
    setAnchor(i)
  }
  const exitSelect = () => {
    setSelectMode(false); setChecked(new Set()); setCheckedMap(new Map()); setAnchor(null)
  }
  /** 「全选本页」：`checked` 和 `checkedMap` **必须一起改**。
   *
   *  批量操作（加入卷子/讲义、删除选中）读的是 `checkedMap`（要题对象，
   *  而且得支持跨页），表头显示的是 `checked`。以前 ListHeader 只 `setChecked`，
   *  于是「已选 100 道 → 加入卷子」实际只加进去上一次单独勾的那 1 道，
   *  导出自然只有 1 题（用户实测报的 bug，2026-11-02）。 */
  const checkAll = (qs: Q[]) => {
    setChecked(new Set(qs.map((x) => x.key)))
    setCheckedMap(new Map(qs.map((x) => [x.key, x])))
  }
  /** 「清空」勾选：两个集合一起清。只清一个的话，隐藏的旧勾选还会被批量操作读走。 */
  const clearChecked = () => {
    setChecked(new Set()); setCheckedMap(new Map()); setAnchor(null)
  }
  const enterSelect = () => setSelectMode(true)

  /** 「筛了几项」的**唯一算法**。
   *
   *  以前这个数在界面里被就地加了三遍（`activeFilters + missing.length + points.length`），
   *  `activeFilters` 里本来就含 points，于是标出来的数字大于实际项数——
   *  用户点「清除全部（7）」却发现只有 5 项。现在只在这里算，界面只读。 */
  const activeFilters =
    has.length + missing.length + points.length + diffs.length + years.length
    + sources.length + scopes.length + paperStates.length + starStates.length
    + qualities.length + (type ? 1 : 0) + (kind ? 1 : 0)
    + (pointSource ? 1 : 0) + answerSources.length + (reviewed ? 1 : 0)

  /** 当前选中的这批考点，是不是**正好等于**某一章／某一节？
   *
   *  是的话表头就报那一章的名字（「章 · 四、导数」），而不是干巴巴的
   *  「考点 · 19 个」——用户点的是章节，就该看到章节名。 */
  const scopeName = useMemo(() => {
    if (!points.length || !facets?.points) return ''
    const cur = new Set(points)
    const groups = groupTree(facets.points || [])
    for (const g of groups) {
      const ids = g.sections.flatMap((x) => x.points.map((p: any) => p.value))
      if (ids.length === cur.size && ids.every((i) => cur.has(i))) return `章 · ${g.topic}`
    }
    for (const g of groups) {
      for (const sec of g.sections) {
        const ids = sec.points.map((p: any) => p.value)
        if (ids.length === cur.size && ids.every((i) => cur.has(i)))
          return `节 · ${sec.section}`
      }
    }
    return ''
  }, [points, facets])

  /** **只有最后一次请求算数**（乱序防护）。
   *
   *  打开题库时那条"全库"请求是最慢的（要扫 2 万道、还要渲染 100 条块 IR），
   *  而搜索请求只回 1 条、几十毫秒就回来了。用户开页就打字，于是：
   *  搜索的响应先落地（表头 1 道、列表是那道题），全库的响应后落地，
   *  把 `items`/`total` 又改回全库——表头明明挂着「搜「断臂」」，
   *  数字却是两万量级、列表也退回没筛的样子。用户截图里那个数就是这么来的。
   *  `my !== seq.current` 的响应一律丢弃，连 `loading` 都不许它关。 */
  const seq = useRef(0)

  /** 关键词**防抖**：输入框即时回显，参与请求的值等停手 160ms。
   *  中文输入法一个字会连发三次请求——每次都全库扫一遍，且乱序落地。 */
  const qApplied = useDebounced(q, 160)

  /** 当前筛选条件的**唯一一份**——列表、导出、组卷都从这里取。
   *
   *  以前 App.tsx 里手抄了一份传给导出，抄漏了 `missing`/`source`，后来列表
   *  新增的「地区/完整度/星级/质检」四个维度也没跟上：**列表里筛到的**和
   *  **组卷用的池子**不是同一批题，用户筛了星级、卷子却出别的题。
   *  现在只有这一处组装，谁要筛条件都拿它。 */
  const filters = useMemo(() => ({
    q: qApplied, type, kind,
    point: points.join(','), difficulty: diffs.join(','),
    year: years.join(','), has: has.join(','), missing: missing.join(','),
    source: sources.join(','),
    region_scope: scopes.join(','), paper_state: paperStates.join(','),
    star_state: starStates.join(','), quality: qualities.join(','),
    point_source: pointSource, answer_source: answerSources.join(','),
    reviewed,
  }), [qApplied, type, kind, points, diffs, years, has, missing,
       sources, scopes, paperStates, starStates, qualities, pointSource,
       answerSources, reviewed])

  /** 一次请求的**全部输入**压成一个键。
   *
   *  好处有二：effect 的依赖只剩这一个（不会再漏项），以及"筛选变了"
   *  有了**单一判定**——下面「回第一页」就靠它，不再靠十四条依赖各写一遍。 */
  const fetchKey = useMemo(() => JSON.stringify([filters, sort, pageSize]),
    [filters, sort, pageSize])

  /** 筛选变了就回第一页。**在渲染期改，不放 effect 里**：
   *  那个 effect 排在拉取 effect 后面跑，会先按旧页码发一次、再按新页码发一次——
   *  每改一次筛选打两次全库扫描，而其中一次的结果注定是垃圾。 */
  const [seenKey, setSeenKey] = useState(fetchKey)
  if (seenKey !== fetchKey) { setSeenKey(fetchKey); setPage(1) }

  /** 换页/换筛选后，Shift 连选的锚点作废。
   *
   *  `anchor` 记的是**当前这一页**的下标。翻到第 2 页还留着第 1 页的下标，
   *  按住 Shift 点一下会从错误的位置开始圈选（而且跨页连选本来就没有意义）。
   *  失效了就重新从这一下开始，别让用户莫名其妙选中一片。 */
  useEffect(() => { setAnchor(null) }, [page, fetchKey])

  /** **静默刷新**：删除后本地已经把行去掉了，再悄悄校正一次列表/计数——
   *  不闪「加载中」、不弹详情顶部的「正在刷新列表…」。
   *  一次删除动作从用户视角看就是「点删除 → 行没了」，不是再等一轮刷新。 */
  const silentNext = useRef(false)

  useEffect(() => {
    const my = ++seq.current
    const silent = silentNext.current
    silentNext.current = false
    // 旧请求直接取消：它扫的是全库，回来晚了还会覆盖新结果
    const ac = new AbortController()
    // 静默刷新不点亮 loading；但如果它顶掉了一个正在显示的请求，
    // 结束时会负责把 loading 关掉（否则那条被取消的请求永远关不了）。
    if (!silent) setLoading(true)
    api.list({
      ...filters, sort,
      limit: String(pageSize), offset: String((page - 1) * pageSize),
    }, ac.signal)
      .then((d) => {
        if (my !== seq.current) return
        setItems(d.items); setTotal(d.total)
        // 删题/改筛选后当前页可能超界，拉回来
        const maxPage = Math.max(1, Math.ceil(d.total / pageSize))
        if (page > maxPage) {
          // 翻页补拉也走静默：删完最后一页时不要又闪一下刷新条
          if (silent) silentNext.current = true
          setPage(maxPage)
        }
        setSel((cur: Q | null) =>
          cur && d.items.some((x: Q) => x.key === cur.key) ? cur : (d.items[0] ?? null))
      })
      .catch((e) => {
        if (my !== seq.current) return
        // **主动取消不是故障**：改筛选、翻页、关页面都会取消一次在途请求
        if ((e as { name?: string } | null)?.name === 'AbortError') return
        reportErr(e)
      })
      .finally(() => { if (my === seq.current) setLoading(false) })
    return () => ac.abort()
    // fetchKey 已含全部筛选输入；page/reload 会单独触发重新拉取
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchKey, page, reload])

  useEffect(() => { setPageInput(String(page)) }, [page])

  useEffect(() => {
    api.facets().then(setFacets).catch(reportErr)
  }, [reload])

  // 选中的考点所在大类自动展开，否则选完就看不见自己选了什么
  useEffect(() => {
    if (!points.length || !facets) return
    const hit = new Set(facets.points.filter((p) => points.includes(p.value)).map((p) => p.topic))
    if (!hit.size) return
    setOpenTopics((s) => new Set([...s, ...hit]))
  }, [points, facets])

  /** 删除等「界面已经先本地改掉」的动作：后台校正，界面不闪刷新。 */
  const refreshSilent = () => {
    silentNext.current = true
    setReload((v) => v + 1)
  }

  /** 当前筛选的**可序列化快照**：地址栏和「我的筛选」预设共用这一份字段。
   *  数组用逗号拼，和 `filters` 完全同构。 */
  const snapshotFilters = (): UrlFilters => ({
    q: q.trim(), type, kind,
    point: points.join(','), diff: diffs.join(','), year: years.join(','),
    source: sources.join(','), has: has.join(','), missing: missing.join(','),
    scope: scopes.join(','), paper: paperStates.join(','), star: starStates.join(','),
    quality: qualities.join(','), psrc: pointSource, asrc: answerSources.join(','),
    reviewed,
  })

  /** 恢复一套筛选（预设/地址栏）；页码回到 1。 */
  const loadFilters = (f: UrlFilters, sortKey: string = 'used') => {
    setQ(f.q || ''); setType(f.type || ''); setKind(f.kind || '')
    setPoints(split(f.point)); setDiffs(split(f.diff)); setYears(split(f.year))
    setSources(split(f.source)); setHas(split(f.has)); setMissing(split(f.missing))
    setScopes(split(f.scope)); setPaperStates(split(f.paper))
    setStarStates(split(f.star)); setQualities(split(f.quality))
    setPointSource(f.psrc || ''); setAnswerSources(split(f.asrc)); setReviewed(f.reviewed || '')
    setSort((SORT_KEYS.has(sortKey) ? sortKey : 'used') as SortKey)
    setPage(1)
  }

  return {
    facets, items, setItems, total, setTotal, sel, setSel, loading, reload, setReload,
    refreshSilent,
    page, setPage, pageSize, setPageSize, pageInput, setPageInput, jumpPage, listRef,
    q, setQ, type, setType, kind, setKind,
    has, setHas, missing, setMissing, points, setPoints, diffs, setDiffs,
    sources, setSources,
    scopes, setScopes, paperStates, setPaperStates,
    starStates, setStarStates, qualities, setQualities,
    pointSource, setPointSource, answerSources, setAnswerSources, reviewed, setReviewed,
    years, setYears, sort, setSort, openTopics, setOpenTopics,
    selectMode, setSelectMode, checked, setChecked,
    checkedMap, setCheckedMap,
    filters,
    toggleYear, toggle, toggleHas, toggleMissing, togglePoint, toggleDiff,
    toggleSource: toggle(setSources),
    toggleScope: toggle(setScopes), togglePaper: toggle(setPaperStates),
    toggleStar: toggle(setStarStates), toggleQuality: toggle(setQualities),
    toggleAnswerSource: toggle(setAnswerSources),
    togglePoints, toggleTopic, toggleCheck, exitSelect, enterSelect,
    checkAll, clearChecked,
    activeFilters, scopeName,
    snapshotFilters, loadFilters,
  }
}
