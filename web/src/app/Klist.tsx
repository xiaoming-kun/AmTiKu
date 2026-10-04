/** 「知识清单」页：按考点翻讲解，右边同时看到这个考点的题库画像。
 *
 *  为什么把三样放一屏：备一个考点，本来要「书里看讲解 → 回工作台筛题 →
 *  再挑哪几道」。这一屏把 **书（讲解）↔ 考纲（考点）↔ 题库（题）** 对齐到
 *  同一个考点 id 上。对应关系是后端人工核定的那份 `知识清单映射.json`，
 *  前端不自己猜、也不再第二遍解析 LaTeX。
 *
 *  渲染全部走 `lib/render.tsx::renderBlocks`——讲解与题目共用同一个渲染器，
 *  公式/表格/图都认，避免「预览一个样、导出另一个样」那类老坑。
 */
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, BookOpen, Check, ChevronRight, Loader2, Search } from 'lucide-react'
import { renderBlocks } from '@/lib/render'
import { reportErr } from '@/lib/api'
import { SHORT_NAME } from '@/lib/paper'
import { klistApi } from '@/lib/klist'
import type { KPointRow, KPointTopic, KPointView } from '@/lib/klist'

const DIFFS = ['简单题', '中档题', '难题']

export default function Klist({ onFindPoint }: {
  /** 跳到工作台并按这个考点筛题（和「知识链路」页同一个动作） */
  onFindPoint: (pid: string, title: string) => void
}) {
  const [tree, setTree] = useState<KPointTopic[]>([])
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [fold, setFold] = useState<Record<string, boolean>>({})
  const [pid, setPid] = useState('')
  const [v, setV] = useState<KPointView | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    klistApi.points()
      .then((d) => {
        setTree(d.tree || [])
        if (!pid && d.tree?.length) setPid(d.tree[0].sections[0].points[0]?.id || '')
      })
      .catch((e) => { setErr(String(e?.message || e)); reportErr(e) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!pid) return
    setBusy(true)
    klistApi.point(pid).then(setV).catch((e) => {
      setErr(String(e?.message || e)); reportErr(e)
    }).finally(() => setBusy(false))
  }, [pid])

  /* 搜索是**本地过滤**：整棵树 152 行，一次拿完再筛，比每敲一个字打一次接口干净。 */
  const shown = useMemo(() => {
    const w = q.trim().toLowerCase()
    if (!w) return tree
    return tree
      .map((t) => ({
        ...t,
        sections: t.sections
          .map((s) => ({
            ...s,
            points: s.points.filter((p) =>
              (p.title + ' ' + p.id).toLowerCase().includes(w)),
          }))
          .filter((s) => s.points.length),
      }))
      .filter((t) => t.sections.length)
  }, [tree, q])

  const cur = useMemo(() => {
    for (const t of tree) for (const s of t.sections)
      for (const p of s.points) if (p.id === pid) return p
    return null
  }, [tree, pid])

  return (
    <div className="flex min-h-0 flex-1">
      {/* ── 左：考点树 ─────────────────────────────────── */}
      <aside className="flex w-[262px] shrink-0 flex-col border-r border-border bg-surface">
        <div className="border-b border-border px-3 py-2.5">
          <div className="mb-2 flex items-center gap-1.5 text-[12.5px] font-semibold">
            <BookOpen size={13} className="text-brand-ink" /> 按考点看讲义
          </div>
          <div className="flex items-center gap-1.5 rounded-md border border-border bg-bg px-2">
            <Search size={12} className="shrink-0 text-ink-faint" />
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="搜考点，如 导数 / 5.2"
              className="w-full bg-transparent py-1.5 text-[12.5px] outline-none" />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-1.5 py-1.5">
          {err && <div className="px-2 py-1.5 text-[11.5px] text-danger">{err}</div>}
          {shown.map((t) => (
            <TreeTopic key={t.title} t={t} fold={fold} onFold={setFold}
              active={pid} onPick={setPid} />
          ))}
          {!shown.length && !err && (
            <div className="px-2 py-3 text-[11.5px] text-ink-faint">没有匹配的考点</div>
          )}
        </div>
        <div className="border-t border-border px-3 py-2 text-[11px] text-ink-faint">
          共 <span className="tnum">{tree.reduce((a, t) =>
            a + t.sections.reduce((b, s) => b + s.points.length, 0), 0)}</span> 个考点
        </div>
      </aside>

      {/* ── 中：讲解正文 ───────────────────────────────── */}
      <main className="min-w-0 flex-1 overflow-y-auto">
        {busy && <div className="flex h-24 items-center justify-center">
          <Loader2 size={16} className="animate-spin text-ink-faint" />
        </div>}
        {!busy && v && <Reading v={v} />}
      </main>

      {/* ── 右：这个考点在题库里长什么样 ───────────────── */}
      {!busy && v && cur && <Sidebar v={v} row={cur} onFindPoint={onFindPoint} />}
    </div>
  )
}

function TreeTopic({ t, fold, onFold, active, onPick }: {
  t: KPointTopic; fold: Record<string, boolean>
  onFold: (m: Record<string, boolean>) => void
  active: string; onPick: (id: string) => void
}) {
  const open = fold[t.title] !== false          // 默认全展开，搜的时候才收
  return (
    <div className="mb-0.5">
      <button onClick={() => onFold({ ...fold, [t.title]: !open })}
        className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-left
                   text-[12px] font-semibold hover:bg-muted">
        <ChevronRight size={11} className={open ? 'rotate-90 transition' : 'transition'} />
        <span className="truncate">{t.title}</span>
      </button>
      {open && t.sections.map((s) => (
        <div key={s.title} className="ml-3">
          <div className="px-1.5 pt-1 text-[11px] text-ink-faint">{s.title}</div>
          {s.points.map((p) => <PointRow key={p.id} p={p} on={active === p.id} onClick={onPick} />)}
        </div>
      ))}
    </div>
  )
}

function PointRow({ p, on, onClick }: { p: KPointRow; on: boolean; onClick: (id: string) => void }) {
  return (
    <button onClick={() => onClick(p.id)}
      className={'flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-[12px] '
        + (on ? 'bg-brand-soft text-brand-ink' : 'hover:bg-muted')}>
      <span className="tnum shrink-0 text-[10.5px] text-ink-faint">{p.id}</span>
      <span className="min-w-0 flex-1 truncate">{p.title.replace(/^\S+\s/, '')}</span>
      {p.short > 0 && (
        <span className="tnum shrink-0 rounded bg-warn-soft px-1 text-[10px] text-warn"
          title={`配额 100 道，库存只够 ${p.given} 道，缺 ${p.short}`}>
          缺{p.short}
        </span>
      )}
      <span className="tnum shrink-0 text-[10.5px] text-ink-faint">{p.pool}</span>
    </button>
  )
}

function Reading({ v }: { v: KPointView }) {
  const p = v.point
  return (
    <div className="mx-auto max-w-[780px] px-7 py-6">
      <div className="mb-1 flex flex-wrap items-baseline gap-2">
        <span className="tnum text-[12px] text-brand-ink">{p.id}</span>
        <h1 className="text-[19px] font-bold leading-tight">{p.title}</h1>
        <span className="text-[12px] text-warn">{'★'.repeat(p.stars || 0)}</span>
      </div>
      <div className="mb-5 text-[11.5px] text-ink-faint">
        {p.topic} · {p.section} · 考点难度 {p.difficulty || '未定'}
      </div>

      {Object.keys(p.fields).length > 0 && (
        <section className="mb-6">
          <H2>考点五要素</H2>
          {Object.entries(p.fields).map(([k, vals]) => (
            <div key={k} className="mb-2.5">
              <div className="mb-1 text-[12.5px] font-semibold">{k}</div>
              <ul className="ml-4 list-disc space-y-1 text-[13px] leading-relaxed">
                {/* 五要素是散文里混着 unicode 数学符号（∈ ⊆ √ aₙ₊₁）。
                    网页这边浏览器字体直接画得出来，不必像 LaTeX 那份先转 `$…$`。 */}
                {(Array.isArray(vals) ? vals : [vals]).map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      {v.commentary.map((c) => (
        <section key={c.role} className="mb-6">
          <H2>{c.role}</H2>
          {c.nodes.map((n) => (
            <div key={n.id} className="mb-4 rounded-lg border border-border bg-bg p-4">
              <div className="mb-2 text-[13.5px] font-semibold">{n.title}</div>
              {n.blocks?.length
                ? renderBlocks(n.blocks)
                : <div className="text-[12px] text-ink-faint">这一节没有正文</div>}
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-2 border-b border-border pb-1 text-[14.5px] font-bold text-brand-ink">
      {children}
    </h2>
  )
}

function Sidebar({ v, row, onFindPoint }: {
  v: KPointView; row: KPointRow
  onFindPoint: (pid: string, title: string) => void
}) {
  const b = v.bank
  return (
    <aside className="flex w-[330px] shrink-0 flex-col border-l border-border bg-surface">
      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
        <div className="mb-3">
          <div className="text-[11px] text-ink-faint">题库库存</div>
          <div className="flex items-baseline gap-1.5">
            <span className="tnum text-[21px] font-bold">{b.pool}</span>
            <span className="text-[11.5px] text-ink-faint">道（主考点口径）</span>
          </div>
        </div>

        <div className="mb-3 flex items-baseline gap-1.5 text-[11.5px]">
          <span className="text-ink-faint">讲解</span>
          <span className="tnum text-[15px] font-bold text-brand-ink">{row.n_node}</span>
          <span className="text-ink-faint">节 · 出题</span>
          <span className="tnum text-[15px] font-bold text-brand-ink">{b.given}</span>
          <span className="text-ink-faint">道</span>
        </div>

        <Block title="分层选题（目标 100 道）">
          {DIFFS.map((d) => (
            <div key={d} className="mb-1.5">
              <div className="flex items-center justify-between text-[11.5px]">
                <span>{d}</span>
                <span className="tnum text-ink-faint">
                  取 {b.taken[d] || 0} / 库存 {b.stock[d] || 0}
                </span>
              </div>
              <Bar have={b.taken[d] || 0} want={quota(d)} />
              {(b.short[d] || 0) > 0 && (
                <div className="mt-0.5 text-[10.5px] text-warn">
                  缺 {b.short[d]} 道 —— 库存不足，按「有多少出多少」处理
                </div>
              )}
            </div>
          ))}
          <div className="mt-1 text-[11px] text-ink-faint">
            本次共出 <span className="tnum font-semibold text-ink">{b.given}</span> / {b.want} 道
          </div>
        </Block>

        <Block title="题型分布">
          {Object.entries(b.by_type).map(([t, n]) => (
            <Row key={t} label={SHORT_NAME[t] || t} n={n} max={b.pool} />
          ))}
        </Block>

        <Block title="来源">
          <Row label="高考真题" n={b.by_kind['高考'] || 0} max={b.pool} />
          <Row label="模拟" n={b.by_kind['模拟'] || 0} max={b.pool} />
          {b.years.length > 0 && (
            <div className="mt-1.5 text-[11px] text-ink-faint">
              近年：{b.years.slice(0, 4).map(([y, n]) => `${y}(${n})`).join(' · ')}
            </div>
          )}
        </Block>

        <Block title="难度依据">
          {Object.entries(b.by_source).map(([s, n]) => (
            <Row key={s} label={s} n={n} max={b.pool} />
          ))}
          <div className="mt-1 text-[10.5px] leading-snug text-ink-faint">
            题库不存逐题难度：优先用题目自带的，其次按同卷位置推定，最后才用考点星级。
          </div>
        </Block>

        {DIFFS.map((d) => (v.pick[d] || []).length > 0 && (
          <Block key={d} title={`${d} · 出题 ${b.taken[d] || 0} 道，先看前 ${v.pick[d].length} 道`}>
            {v.pick[d].map((it) => (
              <button key={it.key} onClick={() => onFindPoint(v.point.id, v.point.title)}
                title={`${it.tag || it.key}｜难度依据：${it.src}`}
                className="mb-1 flex w-full items-start gap-1.5 rounded px-1.5 py-1 text-left
                           text-[11.5px] hover:bg-muted">
                <span className="tnum shrink-0 rounded bg-muted px-1 text-[10px]">
                  {SHORT_NAME[it.type] || it.type}
                </span>
                <span className="min-w-0 flex-1 truncate text-ink-faint">{it.key}</span>
                {it.has_fig && <span className="shrink-0 text-[10px] text-ink-faint">图</span>}
              </button>
            ))}
          </Block>
        ))}

        {b.broken.length > 0 && (
          <div className="mt-2 flex items-start gap-1.5 rounded-md bg-warn-soft px-2 py-1.5
                          text-[11px] leading-snug text-warn">
            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
            <span>
              另有 {b.broken.length} 道题的作答位没闭合（数据缺陷），已跳过不出——
              需要在题库里逐题订正。
            </span>
          </div>
        )}

        <button onClick={() => onFindPoint(v.point.id, v.point.title)}
          className="press mt-3 flex w-full items-center justify-center gap-1.5 rounded-md
                     bg-brand px-3 py-2 text-[12.5px] font-medium text-white">
          <Check size={13} /> 去工作台筛这个考点的题
        </button>
      </div>
    </aside>
  )
}

function quota(d: string) {
  return d === '简单题' ? 20 : 40
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-3 border-t border-border pt-2.5">
      <div className="mb-1.5 text-[11.5px] font-semibold">{title}</div>
      {children}
    </div>
  )
}

function Bar({ have, want }: { have: number; want: number }) {
  const pct = Math.min(100, Math.round((have / Math.max(1, want)) * 100))
  return (
    <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-muted">
      <div className={'h-full rounded-full ' + (pct >= 100 ? 'bg-brand' : 'bg-warn')}
        style={{ width: pct + '%' }} />
    </div>
  )
}

function Row({ label, n, max }: { label: string; n: number; max: number }) {
  return (
    <div className="mb-1 flex items-center gap-2 text-[11.5px]">
      <span className="w-[74px] shrink-0 truncate">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full bg-brand-ink/70"
          style={{ width: Math.min(100, Math.round((n / Math.max(1, max)) * 100)) + '%' }} />
      </div>
      <span className="tnum w-9 shrink-0 text-right text-ink-faint">{n}</span>
    </div>
  )
}
