/** 题库列表的数据与筛选状态。
 *
 *  从 App.tsx 抽出来的（审查报告 CPLX-1：App 曾是全文件最大的组件）。
 *  只管「列出哪些题」这件事：筛选项、分页、勾选、列表数据。
 *  详情页、录入、导出、组卷都不在这里。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Q, Facets } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import { groupTree } from '@/app/Stats'

export type SortKey = 'used' | 'new' | 'old' | 'solved' | 'diff' | 'diff2' | ''

export function useQuestionList() {
  const [facets, setFacets] = useState<Facets | null>(null)
  const [items, setItems] = useState<Q[]>([])
  const [total, setTotal] = useState(0)
  const [sel, setSel] = useState<Q | null>(null)
  const [loading, setLoading] = useState(false)
  const [reload, setReload] = useState(0)

  // ── 分页 ──
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [pageInput, setPageInput] = useState('1')
  const listRef = useRef<HTMLDivElement>(null)

  const jumpPage = () => {
    const max = Math.max(1, Math.ceil(total / pageSize))
    const n = Math.min(max, Math.max(1, parseInt(pageInput, 10) || 1))
    setPage(n); setPageInput(String(n))
    listRef.current?.scrollTo(0, 0)
  }

  // ── 筛选项 ──
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  const [kind, setKind] = useState('')
  const [has, setHas] = useState<string[]>([])
  // **缺什么**。后端 `missing` 是"全都缺"的语义，所以
  // `missing=答案,解析` 正好是「没解析也没答案」——最常用的一个视角：
  // 这些就是还没做的题。
  const [missing, setMissing] = useState<string[]>([])
  const [points, setPoints] = useState<string[]>([])
  const [diffs, setDiffs] = useState<string[]>([])
  const [openTopics, setOpenTopics] = useState<Set<string>>(new Set())
  // 排序：默认按**使用频次**（导出过多次的经典题排前面）。
  // `seq` 是录入先后（append 只追加，所以文件顺序就是录入顺序）。
  const [sort, setSort] = useState<SortKey>('used')
  const [years, setYears] = useState<string[]>([])
  const toggleYear = (v: string) =>
    setYears((xs) => (xs.includes(v) ? xs.filter((x) => x !== v) : [...xs, v]))

  // 选定模式**默认开启**——绝大多数操作都是「挑几道题加进卷子」，
  // 默认开着省一次点击。但不预先勾选任何题：**选什么由你决定**。
  const [selectMode, setSelectMode] = useState(true)
  const [checked, setChecked] = useState<Set<string>>(new Set())

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
  const toggleCheck = (k: string) => setChecked((s) => {
    const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n
  })
  const exitSelect = () => { setSelectMode(false); setChecked(new Set()) }
  const enterSelect = () => setSelectMode(true)

  const activeFilters =
    has.length + points.length + diffs.length + years.length + (type ? 1 : 0) + (kind ? 1 : 0)

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

  // 拉列表
  useEffect(() => {
    setLoading(true)
    api.list({
      q, type, kind, has: has.join(','), missing: missing.join(','),
      point: points.join(','), difficulty: diffs.join(','),
      year: years.join(','), sort,
      limit: String(pageSize), offset: String((page - 1) * pageSize),
    })
      .then((d) => {
        setItems(d.items); setTotal(d.total)
        // 删题/改筛选后当前页可能超界，拉回来
        const maxPage = Math.max(1, Math.ceil(d.total / pageSize))
        if (page > maxPage) setPage(maxPage)
        setSel((cur: Q | null) =>
          cur && d.items.some((x: Q) => x.key === cur.key) ? cur : (d.items[0] ?? null))
      })
      .catch(reportErr)
      .finally(() => setLoading(false))
  }, [q, type, kind, has, missing, points, diffs, years, sort, page, pageSize, reload])

  useEffect(() => { setPageInput(String(page)) }, [page])

  // 改了筛选条件就**回到第一页**——不然会停在一个空页上
  useEffect(() => { setPage(1) },
    [q, type, kind, has, missing, points, diffs, years, sort, pageSize])

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

  return {
    facets, items, setItems, total, setTotal, sel, setSel, loading, reload, setReload,
    page, setPage, pageSize, setPageSize, pageInput, setPageInput, jumpPage, listRef,
    q, setQ, type, setType, kind, setKind,
    has, setHas, missing, setMissing, points, setPoints, diffs, setDiffs,
    years, setYears, sort, setSort, openTopics, setOpenTopics,
    selectMode, setSelectMode, checked, setChecked,
    toggleYear, toggle, toggleHas, toggleMissing, togglePoint, toggleDiff,
    togglePoints, toggleTopic, toggleCheck, exitSelect, enterSelect,
    activeFilters, scopeName,
  }
}
