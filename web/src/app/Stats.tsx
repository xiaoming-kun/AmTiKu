/** 统计 / 变更记录。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1）。
 */
import { useEffect, useState } from 'react'
import { api, reportErr } from '@/lib/api'
import { Panel } from '@/app/ui'

/** 考点按「大类 → 小类」两级分组，保持知识点库的原始顺序 */
export function groupTree<T extends { topic: string; section: string }>(pts: T[]) {
  const out: { topic: string; sections: { section: string; points: T[] }[] }[] = []
  for (const p of pts) {
    let t = out.find((x) => x.topic === p.topic)
    if (!t) { t = { topic: p.topic, sections: [] }; out.push(t) }
    let sec = t.sections.find((x) => x.section === p.section)
    if (!sec) { sec = { section: p.section, points: [] }; t.sections.push(sec) }
    sec.points.push(p)
  }
  return out
}

/** **变更记录**：每次 MIGRATE 级迁移留下的报告。
 *
 *  顶层设计要求「规则改存量数据」必须可追溯——这里就是那本账。
 *  左边列表，点开看全文。 */
export function Changes() {
  const [items, setItems] = useState<any[]>([])
  const [cur, setCur] = useState('')
  const [text, setText] = useState('')

  const open = (name: string) => {
    setCur(name)
    api.changeText(name).then((d) => setText(d.text || '')).catch(reportErr)
  }
  useEffect(() => {
    api.changes().then((d) => {
      setItems(d.items || [])
      if (d.items?.[0]) open(d.items[0].name)
    }).catch(reportErr)
  }, [])

  if (!items.length) {
    return (
      <div className="flex h-full items-center justify-center text-[12.5px] text-ink-faint">
        还没有变更记录 —— 只有 MIGRATE 级迁移（改存量数据）才会留档
      </div>
    )
  }
  return (
    <div className="flex h-full min-h-0">
      <div className="w-[280px] shrink-0 overflow-y-auto border-r border-border px-3 py-3">
        <div className="mb-2 text-[11px] font-semibold tracking-wide text-ink-faint">
          变更记录 {items.length} 份
        </div>
        {items.map((x) => (
          <button key={x.name} onClick={() => open(x.name)}
            className={`mb-1 block w-full rounded-lg border px-2.5 py-1.5 text-left transition-colors ${
              cur === x.name ? 'border-brand/40 bg-brand-soft'
                             : 'border-border bg-surface hover:bg-muted'}`}>
            <div className="truncate text-[12px] font-medium text-ink-soft">{x.rule}</div>
            <div className="text-[10.5px] text-ink-faint">{x.at}</div>
          </button>
        ))}
      </div>
      <div className="min-w-0 flex-1 overflow-y-auto px-5 py-4">
        <pre className="whitespace-pre-wrap font-sans text-[12.5px] leading-relaxed text-ink-soft">
          {text}
        </pre>
      </div>
    </div>
  )
}

export function Stats() {
  const [d, setD] = useState<any>(null)
  useEffect(() => { api.statsDetail().then(setD).catch(reportErr) }, [reportErr])
  if (!d) return <div className="flex h-full items-center justify-center text-[12.5px] text-ink-faint">加载中…</div>

  const Bar = ({ items, total }: any) => (
    <div className="space-y-1">
      {items.map((x: any) => (
        <div key={x.value} className="flex items-center gap-2 text-[11.5px]">
          <span className="w-[86px] shrink-0 truncate text-ink-soft" title={x.title || x.value}>
            {x.title || x.value}
          </span>
          <span className="h-[7px] flex-1 overflow-hidden rounded-full bg-muted">
            <span className="block h-full rounded-full bg-brand/60"
              style={{ width: `${Math.max(2, (x.n / total) * 100)}%` }} />
          </span>
          <span className="w-7 shrink-0 text-right text-ink-faint">{x.n}</span>
        </div>
      ))}
    </div>
  )

  return (
    <div className="h-full overflow-y-auto px-5 py-4">
      <div className="mb-4 grid grid-cols-4 gap-3">
        {[['题目总数', d.total, ''], ['覆盖考点', `${d.points_covered}/${d.points_total}`, ''],
          ['图片', d.figures.files, `${(d.figures.bytes / 1024 / 1024).toFixed(1)} MB`],
          ['待补', d.missing.reduce((s: number, m: any) => s + m.n, 0), '']].map(([k, v, sub]: any) => (
          <div key={k} className="rounded-xl border border-border bg-surface px-3 py-2.5">
            <div className="text-[11px] text-ink-faint">{k}</div>
            <div className="mt-0.5 text-[19px] font-semibold leading-tight">{v}</div>
            {sub && <div className="text-[10.5px] text-ink-faint">{sub}</div>}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Panel title="题型分布"><Bar items={d.by_type} total={d.total} /></Panel>
        <Panel title="难度分布（主考点派生）"><Bar items={d.by_difficulty} total={d.total} /></Panel>
        <Panel title="各章考点覆盖">
          <div className="space-y-1">
            {d.by_topic.map((t: any) => (
              <div key={t.value} className="flex items-center gap-2 text-[11.5px]">
                <span className="w-[110px] shrink-0 truncate text-ink-soft" title={t.value}>{t.value}</span>
                <span className="h-[7px] flex-1 overflow-hidden rounded-full bg-muted">
                  <span className="block h-full rounded-full bg-brand/60"
                    style={{ width: `${(t.covered / t.total) * 100}%` }} />
                </span>
                <span className="w-[46px] shrink-0 text-right text-ink-faint">
                  {t.covered}/{t.total}
                </span>
                <span className="w-8 shrink-0 text-right text-ink-faint">{t.n} 题</span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="标签来源"><Bar items={d.by_point_source} total={d.total} /></Panel>
        <Panel title="年份分布">
          <Bar items={d.by_year} total={Math.max(...d.by_year.map((x: any) => x.n), 1)} />
        </Panel>
        <Panel title="完整性缺口">
          {d.missing.length === 0
            ? <div className="text-[12px] text-has">✓ 没有缺口</div>
            : <Bar items={d.missing} total={d.total} />}
        </Panel>
      </div>

      {/* 全部考点：空考点也列出来，那正是要补的 */}
      <div className="mt-4 rounded-xl border border-border bg-surface p-3.5">
        <div className="mb-2 flex items-baseline gap-2">
          <span className="text-[11.5px] font-semibold text-ink-soft">全部考点</span>
          <span className="text-[11px] text-ink-faint">
            已覆盖 {d.points_covered}/{d.points_total}
            {d.points_covered < d.points_total &&
              ` · 还有 ${d.points_total - d.points_covered} 个没有题目`}
          </span>
        </div>
        <div className="space-y-3">
          {groupTree(d.all_points).map(({ topic, sections }: any) => {
            const all = sections.flatMap((s: any) => s.points)
            const cov = all.filter((p: any) => p.n > 0).length
            return (
              <div key={topic}>
                <div className="mb-1 flex items-baseline gap-2 border-b border-border pb-1">
                  <span className="text-[11.5px] font-semibold text-ink-soft">{topic}</span>
                  <span className={`text-[10.5px] ${cov < all.length ? 'text-warn' : 'text-ink-faint'}`}>
                    {cov}/{all.length}
                  </span>
                </div>
                {sections.map(({ section, points: list }: any) => (
                  <div key={section} className="mb-1.5">
                    {list.length > 1 && (
                      <div className="mb-0.5 text-[10.5px] text-ink-faint">{section}</div>
                    )}
                    <div className="flex flex-wrap gap-1">
                      {list.map((p: any) => (
                        <span key={p.value}
                          title={`${p.value}${p.n ? ` · ${p.n} 道` : ' · 暂无题目'}`}
                          className={`rounded px-1.5 py-[2px] text-[10.5px] ${
                            p.n ? 'bg-brand-soft text-brand-ink' : 'bg-muted text-ink-faint/60'}`}>
                          {p.title}{p.n ? ` ${p.n}` : ''}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
