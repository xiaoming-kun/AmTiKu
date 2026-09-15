/** 左栏「按考点选题」的状态与数据。
 *
 *  从 CanvasEditor 抽出来的（审查报告 CPLX-1：一个组件管 8 件事）。
 *  只管三件事：考点树、搜索、某个考点下的题（懒加载 + 缓存）。
 */
import { useEffect, useState } from 'react'
import type { Q } from '@/lib/types'
import { request, reportErr } from '@/lib/api'
import { SEARCH_DEBOUNCE_MS, POINT_PAGE, POINT_MAX } from '@/editor/shared'

export type TopicGroup = { name: string; count: number; points: any[] }

export function useDrawer() {
  const [q, setQ] = useState('')                       // 搜索词
  const [searchResults, setSearchResults] = useState<Q[] | null>(null)
  const [topics, setTopics] = useState<TopicGroup[]>([])
  const [openTopic, setOpenTopic] = useState('')
  const [openPoint, setOpenPoint] = useState('')
  const [pointQs, setPointQs] = useState<Record<string, Q[]>>({})
  const [loadingPt, setLoadingPt] = useState('')

  // 考点树：/api/facets 给 153 个考点，按「章」分组
  useEffect(() => {
    request('/api/facets').then((d) => {
      const m = new Map<string, TopicGroup>()
      for (const p of (d.points || []) as any[]) {
        const k = p.topic || '其他'
        const t = m.get(k)
        if (t) { t.count += p.n || 0; t.points.push(p) }
        else m.set(k, { name: k, count: p.n || 0, points: [p] })
      }
      setTopics([...m.values()])
    }).catch(reportErr)
  }, [])

  // 搜索：走后端全文检索（覆盖全部题目），带防抖与取消
  useEffect(() => {
    const kw = q.trim()
    if (!kw) { setSearchResults(null); return }
    // AbortController：慢响应不能覆盖新结果（审查报告 I-2）
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      request(`/api/questions?q=${encodeURIComponent(kw)}&limit=50`, { signal: ctrl.signal })
        .then((d) => setSearchResults(d.items || d.questions || []))
        .catch((e) => {
          if (e?.name === 'AbortError') return      // 主动取消，不算错误
          setSearchResults([]); reportErr(e)
        })
    }, SEARCH_DEBOUNCE_MS)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [q])

  /** 展开/收起一个考点：首次展开时懒加载该考点的**完整**题列表。
   *
   *  为什么不一次全拉：17k 道太多；点开才取，取过就缓存。
   *  limit 给 5000 足够覆盖最大考点（实测最大 717 道）。
   */
  const togglePoint = (pv: string) => {
    if (openPoint === pv) { setOpenPoint(''); return }
    setOpenPoint(pv)
    if (!pointQs[pv]) {
      setLoadingPt(pv)
      // 后端 limit 上限是 1000（审查报告 Important #1），所以**分页取全**：
      // 一页 1000，直到取完或达到 POINT_MAX 为止。
      const load = async (): Promise<Q[]> => {
        const acc: Q[] = []
        let offset = 0
        for (;;) {
          const d = await request(
            `/api/questions?point=${encodeURIComponent(pv)}` +
            `&limit=${POINT_PAGE}&offset=${offset}`)
          const page: Q[] = d.items || d.questions || []
          acc.push(...page)
          offset += page.length
          if (page.length < POINT_PAGE) break        // 取完了
          if (acc.length >= POINT_MAX) break         // 到上限，别把浏览器拖垮
        }
        return acc
      }
      load()
        .then((qs) => setPointQs((m) => ({ ...m, [pv]: qs })))
        .catch(reportErr)
        .finally(() => setLoadingPt(''))
    }
  }

  return {
    q, setQ, searchResults, topics, openTopic, setOpenTopic,
    openPoint, pointQs, loadingPt, togglePoint,
  }
}
