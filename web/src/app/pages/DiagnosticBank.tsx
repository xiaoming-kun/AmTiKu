/** 小学/初中诊断题库。
 *
 *  高中走完整的题库工作台；小初现阶段题库还没有正式题，但知识地图里
 *  已经挂了近两千道诊断题（题干/选项/答案/解析齐全）。这就是小初
 *  「找题」的入口：按教材位置筛，点开看答案，确认是这节该会的就进图谱。
 *
 *  交互取舍：
 *  · 左表 + 右详情，而不是卡片瀑布——诊断题短，一屏扫十几道更合适；
 *  · 答案默认遮住，点「显示答案」才开（老师投屏/家长在旁边时很重要）；
 *  · 不提供「加入组卷」：这些题还不在正式题库里，强行加进去会让导出
 *    按 key 找不到题。给的是「去录题」——把它升级成正式题。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  BookMarked, ChevronLeft, ChevronRight, Download, Eye, EyeOff,
  Filter, Lightbulb, Network, Plus, Search, X,
} from 'lucide-react'
import { api, reportErr } from '@/lib/api'
import { useDebounced } from '@/lib/useDebounced'
import { STAGE_BY_KEY, type Stage } from '@/lib/stage'

type DItem = {
  key: string; stage: string; stage_name: string
  book: string; chapter: string; grade: number
  point: string; point_title: string
  type: string; level: string
  prompt: string; answer: string
  choices: [string, string][]
  explanation: string
}
type DFacets = {
  books: { value: string; n: number }[]
  chapters: { value: string; n: number }[]
  levels: { value: string; n: number }[]
  points: { value: string; title: string; n: number }[]
}
type DData = { total: number; items: DItem[]; facets: DFacets }

const LEVEL: Record<string, string> = { basic: '基础', standard: '标准', challenge: '挑战' }
const LEVEL_CLS: Record<string, string> = {
  basic: 'bg-has-soft text-has',
  standard: 'bg-brand-soft text-brand-ink',
  challenge: 'bg-warn-soft text-warn',
}
const PAGE_SIZE = 40

export default function DiagnosticBank({
  stage, point = '', search = '', onSearch, onClearPoint, onOpenPoint, onIngest, onBank,
}: {
  stage: Stage
  /** 从知识图谱点进来的知识点：只显示这个点的诊断题。 */
  point?: string
  /** 顶栏全局搜索：同步到这一页的搜索框。 */
  search?: string
  onSearch?: (v: string) => void
  onClearPoint?: () => void
  onOpenPoint: (id: string) => void
  onIngest: () => void
  onBank: () => void
}) {
  const [q, setQ] = useState(search)
  useEffect(() => { setQ(search) }, [search])
  const setQLocal = (v: string) => { setQ(v); onSearch?.(v) }
  const qApplied = useDebounced(q, 180)
  const [book, setBook] = useState('')
  const [chapter, setChapter] = useState('')
  const [level, setLevel] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<DData | null>(null)
  const [loading, setLoading] = useState(false)
  const [sel, setSel] = useState<DItem | null>(null)
  const [reveal, setReveal] = useState(false)
  const [exp, setExp] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => { setPage(1); setSel(null) }, [qApplied, book, chapter, level, stage, point])
  useEffect(() => {
    let alive = true
    setLoading(true)
    api.diagnostics({
      stage, q: qApplied, book, chapter, level, point,
      limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE),
    })
      .then((d: DData) => { if (alive) setData(d) })
      .catch((e) => { if (alive) reportErr(e) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [stage, qApplied, book, chapter, level, page, point])

  const total = data?.total || 0
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const facets = data?.facets
  const meta = STAGE_BY_KEY[stage]

  const chapters = useMemo(() => {
    const all = facets?.chapters || []
    if (!book) return all
    // 章的 facets 是跨册汇总的；没有「章属于哪册」的信息时，只保留当前册下
    // 题目里出现过的章——后端按 book 过滤后 facets 会自然收窄。
    return all
  }, [facets, book])

  const doExport = async (answers: boolean) => {
    if (exp) return
    setExp(true)
    try {
      const d: any = await api.diagnosticsExport({
        stage, q: qApplied, book, chapter, point, level,
        limit: 20, answers, title: `${meta.name}数学诊断卷`,
      })
      if (!d?.ok) throw new Error(String(d?.error || d?.detail || '导出失败'))
      const rel = d.pdf_rel ? encodeURIComponent(d.pdf_rel) : ''
      if (rel) window.open(`/api/pdf?path=${rel}`, '_blank')
    } catch (e) { reportErr(e) } finally { setExp(false) }
  }

  if (stage === 'senior') {
    return (
      <div className="b-page">
        <div className="b-empty">
          <BookMarked size={28} className="text-border-strong" />
          <div className="text-[13px] font-medium text-ink-soft">高中题库走完整工作台</div>
          <div className="text-[11px]">诊断题库只覆盖小学和初中</div>
          <button onClick={onBank} className="b-btn b-btn-primary mt-1">打开高中题库</button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* toolbar */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-[15px] font-semibold">诊断题库</h2>
            <span className="tnum rounded-full bg-muted px-2 py-[1px] text-[10.5px] text-ink-soft">
              {loading ? '…' : total.toLocaleString()} 道
            </span>
            <span className="inline-flex items-center gap-1 rounded-full border border-border
                             bg-surface-2 px-1.5 py-[1px] text-[10px] text-ink-faint">
              <i className="h-1.5 w-1.5 rounded-full" style={{ background: meta.color }} />
              {meta.name}
            </span>
          </div>
          <div className="mt-0.5 text-[10.5px] text-ink-faint">
            按教材位置筛，点一行看答案；这些题在知识图谱里也挂着
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input value={q} onChange={(e) => setQLocal(e.target.value)}
              placeholder="搜题干 / 知识点"
              className="b-input h-8 w-[220px] pl-7 pr-7 text-[11.5px]" />
            {q && <button onClick={() => setQLocal('')} className="icon-btn absolute right-1 top-1/2 h-5 w-5 -translate-y-1/2"><X size={11} /></button>}
          </div>
          <button onClick={() => doExport(false)} disabled={exp || total === 0}
            className="b-btn b-btn-secondary h-8 px-2.5 text-[11.5px]" title="按当前筛选导出前 20 道">
            <Download size={13} />{exp ? '生成中…' : '学生卷'}
          </button>
          <button onClick={() => doExport(true)} disabled={exp || total === 0}
            className="b-btn b-btn-secondary h-8 px-2.5 text-[11.5px]" title="含答案与解析">
            <Download size={13} />教师版
          </button>
          <button onClick={onIngest} className="b-btn b-btn-primary h-8 px-2.5 text-[11.5px]">
            <Plus size={13} />录题
          </button>
        </div>
      </div>

      {/* filters */}
      <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-border bg-surface-2/60 px-4 py-2">
        <Filter size={12} className="text-ink-faint" />
        <select value={book} onChange={(e) => { setBook(e.target.value); setChapter('') }}
          className="h-7 rounded-md border border-border bg-surface px-2 text-[11px] text-ink-soft outline-none">
          <option value="">全部教材</option>
          {(facets?.books || []).map((b) => <option key={b.value} value={b.value}>{b.value}（{b.n}）</option>)}
        </select>
        <select value={chapter} onChange={(e) => setChapter(e.target.value)}
          className="h-7 max-w-[240px] rounded-md border border-border bg-surface px-2 text-[11px] text-ink-soft outline-none">
          <option value="">全部章节</option>
          {chapters.map((c) => <option key={c.value} value={c.value}>{c.value}（{c.n}）</option>)}
        </select>
        <div className="ml-1 flex items-center gap-1">
          {[{ v: '', label: '全部难度' }, ...Object.entries(LEVEL).map(([v, label]) => ({ v, label }))].map((x) => (
            <button key={x.v || 'all'} onClick={() => setLevel(x.v)}
              className={`b-chip ${level === x.v ? 'b-chip-on' : ''}`}>{x.label}</button>
          ))}
        </div>
        {point && (
          <span className="inline-flex items-center gap-1 rounded-full border border-brand-line
                           bg-brand-soft px-2 py-[2px] text-[10.5px] text-brand-ink">
            知识点：{data?.items.find((x) => x.point === point)?.point_title || point}
            <button onClick={() => onClearPoint?.()} title="去掉知识点筛选" className="ml-0.5"><X size={10} /></button>
          </span>
        )}
        {(book || chapter || level || q || point) && (
          <button onClick={() => { setBook(''); setChapter(''); setLevel(''); setQ(''); onClearPoint?.() }}
            className="ml-auto flex items-center gap-1 text-[10.5px] text-ink-faint hover:text-warn">
            <X size={11} />清除筛选
          </button>
        )}
      </div>

      <div className="flex min-h-0 flex-1">
        {/* list */}
        <div ref={listRef} className="b-scroll min-w-0 flex-1 overflow-y-auto">
          {loading && !data && (
            <div className="space-y-2 p-4">
              {[0, 1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-14 rounded-lg" />)}
            </div>
          )}
          {!loading && total === 0 && (
            <div className="b-empty m-6">
              <Search size={24} className="text-border-strong" />
              <div className="text-[13px] font-medium text-ink-soft">这个条件下没有诊断题</div>
              <div className="text-[11px]">换一个教材位置，或清掉关键词</div>
            </div>
          )}
          {!!data?.items.length && (
            <table className="b-table">
              <thead className="sticky top-0 z-10">
                <tr>
                  <th className="w-[52%]">题目</th>
                  <th>知识点</th>
                  <th className="hidden lg:table-cell">教材位置</th>
                  <th>难度</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((it) => {
                  const on = sel?.key === it.key
                  return (
                    <tr key={it.key} onClick={() => { setSel(it); setReveal(false) }}
                      className={`cursor-pointer ${on ? 'bg-brand-soft/50' : ''}`}>
                      <td>
                        <div className="line-clamp-2 text-[12.5px] leading-relaxed text-ink">{it.prompt}</div>
                      </td>
                      <td>
                        <button onClick={(e) => { e.stopPropagation(); onOpenPoint(it.point) }}
                          className="max-w-[180px] truncate text-left text-[11.5px] text-brand-ink hover:underline"
                          title={it.point_title}>
                          {it.point_title}
                        </button>
                      </td>
                      <td className="hidden max-w-[200px] lg:table-cell">
                        <div className="truncate text-[10.5px] text-ink-faint">{it.book}</div>
                        <div className="truncate text-[10.5px] text-ink-faint">{it.chapter}</div>
                      </td>
                      <td>
                        <span className={`rounded-full px-1.5 py-[1px] text-[10px] font-medium ${LEVEL_CLS[it.level] || 'bg-muted text-ink-faint'}`}>
                          {LEVEL[it.level] || it.level}
                        </span>
                      </td>
                      <td><ChevronRight size={13} className={on ? 'text-brand' : 'text-ink-faint'} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-center gap-2 border-t border-border bg-surface py-2 text-[11px] text-ink-faint">
              <button disabled={page <= 1} onClick={() => { setPage((p) => p - 1); listRef.current?.scrollTo(0, 0) }}
                className="b-btn b-btn-secondary b-btn-sm disabled:opacity-40"><ChevronLeft size={12} />上一页</button>
              <span className="tnum">第 {page} / {maxPage} 页</span>
              <button disabled={page >= maxPage} onClick={() => { setPage((p) => p + 1); listRef.current?.scrollTo(0, 0) }}
                className="b-btn b-btn-secondary b-btn-sm disabled:opacity-40">下一页<ChevronRight size={12} /></button>
            </div>
          )}
        </div>

        {/* detail */}
        <aside className={`shrink-0 border-l border-border bg-surface ${
          sel ? 'w-[380px] max-lg:hidden' : 'hidden'}`}>
          {sel && (
            <div className="flex h-full flex-col">
              <div className="flex items-start gap-2 border-b border-border px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className={`rounded-full px-1.5 py-[1px] text-[10px] font-medium ${LEVEL_CLS[sel.level] || 'bg-muted text-ink-faint'}`}>
                      {LEVEL[sel.level] || sel.level}
                    </span>
                    <span className="text-[10px] text-ink-faint">{sel.type === 'choice' ? '选择题' : sel.type === 'numeric' ? '填空题' : sel.type}</span>
                  </div>
                  <button onClick={() => onOpenPoint(sel.point)}
                    className="mt-1 block max-w-full truncate text-left text-[13px] font-semibold text-ink hover:text-brand-ink"
                    title={sel.point_title}>
                    {sel.point_title}
                  </button>
                  <div className="mt-0.5 truncate text-[10.5px] text-ink-faint">{sel.book} · {sel.chapter}</div>
                </div>
                <button onClick={() => setSel(null)} className="icon-btn h-7 w-7 shrink-0"><X size={14} /></button>
              </div>

              <div className="b-scroll min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
                <div className="text-[14px] leading-relaxed text-ink">{sel.prompt}</div>
                {sel.choices.length > 0 && (
                  <div className="space-y-1.5">
                    {sel.choices.map(([k, t]) => (
                      <div key={k} className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 text-[12px]
                        ${reveal && sel.answer === k ? 'border-has-line bg-has-soft text-has' : 'border-border text-ink-soft'}`}>
                        <span className="font-semibold">{k}</span><span>{t}</span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="rounded-xl border border-border bg-surface-2 p-3">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] font-semibold text-ink-soft">答案</span>
                    <button onClick={() => setReveal((v) => !v)}
                      className="ml-auto flex items-center gap-1 text-[10.5px] font-medium text-brand-ink hover:underline">
                      {reveal ? <EyeOff size={11} /> : <Eye size={11} />}
                      {reveal ? '遮住' : '显示答案'}
                    </button>
                  </div>
                  <div className={`mt-1.5 text-[13px] font-semibold ${reveal ? 'text-has' : 'select-none blur-[5px] text-ink-faint'}`}>
                    {reveal ? sel.answer : '点显示答案'}
                  </div>
                </div>

                {sel.explanation && (
                  <div>
                    <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold text-ink-soft">
                      <Lightbulb size={12} />解析
                    </div>
                    <div className={`text-[11.5px] leading-relaxed text-ink-soft ${reveal ? '' : 'select-none blur-[4px]'}`}>
                      {reveal ? sel.explanation : '先自己想一想，再显示答案'}
                    </div>
                  </div>
                )}
              </div>

              <div className="shrink-0 space-y-2 border-t border-border p-3">
                <button onClick={() => onOpenPoint(sel.point)} className="b-btn b-btn-secondary w-full">
                  <Network size={13} />在知识图谱中查看
                </button>
                <button onClick={onIngest} className="b-btn b-btn-primary w-full">
                  <Plus size={13} />录成正式题
                </button>
                <p className="text-center text-[10px] leading-relaxed text-ink-faint">
                  诊断题暂不进组卷；录成正式题后会出现在{meta.name}题库里
                </p>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
