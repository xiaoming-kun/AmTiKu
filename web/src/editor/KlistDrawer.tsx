/** 编辑器左栏的「知识清单」来源：翻书的目录，点一下把整段讲解加进画布。
 *
 *  与「题库」来源并列（同一栏切换，见 CanvasEditor 的 `head` 开关）。
 *  内容源是《高中数学知识清单》，由 `amti/klist.py` 解析成块级 IR；
 *  前端只把 IR 画出来（`lib/render.tsx` 同一个渲染器，图/表/公式都认）。
 *
 *  两条与题库左栏不同的取舍：
 *  ① **只有目录树 + 搜索，没有"按考点"**。书按教材编、题库按考纲编，两套
 *     编号不同源；考点↔节点的对应是人工核定的（`知识清单映射.json`），
 *     接口留着（`/api/klist/by-point`），但不在这一栏里做第二套浏览方式。
 *  ② **超长节点不给预览**。附录那种 2.6 万字的节点渲染出来会卡住整栏，
 *     而且这么长的东西本来也不适合"看一眼再决定"—— 只给字数，点 + 直接加。
 */
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { BookOpen, ChevronRight, Loader2, Plus, Search } from 'lucide-react'
import { renderBlocks } from '@/lib/render'
import { klistApi, type KHit, type KNode, type KTreeNode } from '@/lib/klist'
import { SEARCH_DEBOUNCE_MS } from '@/editor/shared'

/** 正文超过这么多字就不在左栏里预览（见文件头 ②）。 */
const PREVIEW_MAX = 4000

export default function KlistDrawer({ head, onAdd }: {
  head?: ReactNode
  onAdd: (n: { id: string; title: string; blocks: KNode['blocks'] }) => void
}) {
  const [tree, setTree] = useState<KTreeNode[]>([])
  const [sum, setSum] = useState<{ nodes: number; figs: number; tables: number } | null>(null)
  const [stale, setStale] = useState(false)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<KHit[] | null>(null)
  const [openFile, setOpenFile] = useState('')
  const [cur, setCur] = useState<KNode | null>(null)
  const [busy, setBusy] = useState('')

  useEffect(() => {
    klistApi.tree()
      .then((d) => {
        setTree(d.tree || [])
        setSum({ nodes: d.stats?.nodes || 0, figs: d.stats?.figs || 0,
                 tables: d.stats?.tables || 0 })
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
    // 书改了但没重新生成 —— 不说的话老师改完书发现界面没变，只能猜
    klistApi.stats().then((d) => setStale(!!d.stale)).catch(() => { /* 上面那条已经报错 */ })
  }, [])

  // 搜索防抖：和题库左栏一个数（输入停顿多久才发请求）
  useEffect(() => {
    const w = q.trim()
    if (!w) { setHits(null); return }
    const t = setTimeout(() => {
      klistApi.search(w).then((d) => setHits(d.items || []))
        .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [q])

  // 整本书按**分文件**分组当第一层：书的目录本身是"必修1 / 必修2 / …"
  const byFile = useMemo(() => {
    const m = new Map<string, KTreeNode[]>()
    for (const r of tree) m.set(r.file, [...(m.get(r.file) || []), r])
    return [...m]
  }, [tree])

  /** 点标题：拉这一节的正文。再点一下收起。 */
  const toggle = async (id: string) => {
    if (cur?.id === id) { setCur(null); return }
    setBusy(id)
    try { setCur(await klistApi.node(id)) }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
    finally { setBusy('') }
  }

  /** 点 +：拉正文 → 变成画布上的一整块讲解。 */
  const add = async (n: { id: string; title: string }) => {
    setBusy(n.id)
    try {
      const d = cur?.id === n.id ? cur : await klistApi.node(n.id)
      onAdd({ id: n.id, title: n.title, blocks: d.blocks })
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
    finally { setBusy('') }
  }

  const row = (n: { id: string; title: string; chars: number; n_fig: number
                    n_table: number }, depth: number, sub = '') => (
    <div key={n.id} className="group">
      <div className="flex items-center gap-1 rounded-md pr-0.5 transition-colors hover:bg-muted"
        style={{ paddingLeft: 4 + depth * 12 }}>
        <button onClick={() => toggle(n.id)} title={n.id}
          className="flex min-w-0 flex-1 items-center gap-1 py-[5px] text-left">
          <ChevronRight size={11}
            className={`shrink-0 text-ink-faint transition-transform duration-200 ${
              cur?.id === n.id ? 'rotate-90' : ''}`} />
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-soft">{n.title}</span>
          {!!(n.n_fig || n.n_table) && (
            <span className="tnum shrink-0 text-[10px] text-ink-faint">
              {n.n_fig ? `图${n.n_fig}` : ''}{n.n_fig && n.n_table ? ' ' : ''}
              {n.n_table ? `表${n.n_table}` : ''}
            </span>
          )}
        </button>
        <button onClick={() => add(n)} title="把这一节加进画布"
          className="press grid h-[22px] w-[22px] shrink-0 place-items-center rounded-md
                     text-ink-faint opacity-0 transition-opacity hover:bg-brand-soft
                     hover:text-brand-ink group-hover:opacity-100">
          {busy === n.id ? <Loader2 size={12} className="animate-spin" />
                         : <Plus size={12} />}
        </button>
      </div>
      {sub && <div className="px-1 pb-1 pl-6 text-[10.5px] text-ink-faint">{sub}</div>}
      {cur?.id === n.id && <Preview n={cur} />}
    </div>
  )

  const renderNode = (n: KTreeNode, depth: number): ReactNode => (
    <>
      {row(n, depth)}
      {n.kids.map((k) => renderNode(k, depth + 1))}
    </>
  )

  return (
    <aside data-qdrawer
      className="flex w-[254px] shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border px-3.5">
        <BookOpen size={15} className="shrink-0 text-brand" />
        {head}
      </div>

      <div className="shrink-0 border-b border-border px-3.5 py-3">
        <div className="relative">
          <Search size={13}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="搜书里那句话…"
            className="h-[32px] w-full rounded-lg border border-border bg-bg pl-7 pr-2.5 text-[12.5px]
                       outline-none transition-[border-color,box-shadow] duration-150
                       placeholder:text-ink-faint focus:border-brand-line focus:bg-surface
                       focus:shadow-[0_0_0_3px_var(--color-brand-soft)]" />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3.5">
        {err && (
          <div className="mb-3 rounded-lg border border-danger/30 bg-danger-soft px-2.5 py-2
                          text-[11px] leading-snug text-danger">
            {err}
          </div>
        )}
        {stale && (
          <div className="mb-3 rounded-lg border border-border bg-muted px-2.5 py-2
                          text-[11px] leading-snug text-ink-soft">
            书比生成物新，这里显示的还是旧的。跑一下
            <code className="mx-1 rounded bg-surface px-1">python3 -m amti.klist build</code>
            再来（新加的图还要 <code className="rounded bg-surface px-1">figs</code>）。
          </div>
        )}
        {q.trim() ? (
          <section>
            <div className="mb-2 text-[11px] font-semibold tracking-[0.08em] text-ink-faint">
              搜索结果{hits === null ? '…' : `（${hits.length}）`}
            </div>
            <div className="space-y-[3px]">
              {(hits || []).map((h) => row(h, 0, h.hit))}
              {hits?.length === 0 && (
                <div className="px-2 py-3 text-[11.5px] leading-snug text-ink-faint">
                  书里没有这句话。换个说法试试 —— 搜的是**正文原话**，
                  不是关键词（比如搜「子集个数」而不是「子集」）。
                </div>
              )}
            </div>
          </section>
        ) : (
          <section>
            <div className="mb-2 text-[11px] font-semibold tracking-[0.08em] text-ink-faint">
              翻书{sum ? `（${sum.nodes} 节 · 图 ${sum.figs} · 表 ${sum.tables}）` : ''}
            </div>
            <div className="space-y-[3px]">
              {byFile.map(([file, roots]) => {
                const on = openFile === file
                return (
                  <div key={file}>
                    <button onClick={() => setOpenFile(on ? '' : file)}
                      className={`press flex w-full items-center gap-1.5 rounded-lg px-2 py-[6px]
                                  text-left text-[12.5px] font-medium transition-colors ${
                        on ? 'bg-brand-soft text-brand-ink' : 'text-ink hover:bg-muted'}`}>
                      <ChevronRight size={13}
                        className={`shrink-0 transition-transform duration-200 ${
                          on ? 'rotate-90 text-brand' : 'text-ink-faint'}`} />
                      <span className="min-w-0 flex-1 truncate">{file}</span>
                    </button>
                    {on && (
                      <div className="anim-fade-in ml-3.5 border-l border-border pb-0.5 pl-1.5 pt-[3px]">
                        {roots.map((r) => renderNode(r, 0))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )}
      </div>
    </aside>
  )
}

/** 节点正文预览：**和画布上那一块用同一个渲染器**，所以看到什么就是加进去什么。 */
function Preview({ n }: { n: KNode }) {
  if (n.chars > PREVIEW_MAX) {
    return (
      <div className="mx-1 mb-2 rounded-lg border border-border bg-bg px-2.5 py-2
                      text-[11px] leading-snug text-ink-faint">
        这一节 {n.chars} 字{n.n_fig ? `、图 ${n.n_fig} 张` : ''}
        {n.n_table ? `、表 ${n.n_table} 张` : ''}，太长不在这里预览 ——
        点 <Plus size={10} className="inline align-middle" /> 直接加进画布看。
      </div>
    )
  }
  return (
    <div className="anim-fade-in mx-1 mb-2 max-h-[420px] overflow-y-auto rounded-lg border
                    border-border bg-bg px-2.5 py-2 text-[11.5px] leading-relaxed">
      {n.blocks.length ? renderBlocks(n.blocks)
        : <span className="text-ink-faint">这一节没有正文（可能只是标题）。</span>}
    </div>
  )
}
