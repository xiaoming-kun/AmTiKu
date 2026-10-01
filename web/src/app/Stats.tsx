/** 变更记录（原来的「质量中心/统计」页已删）。

  页面上那几块（题型分布、难度分布、年份分布、考点覆盖、完整性缺口、标签来源）
  平时没人看，却占着侧边栏一格，用户要求删掉。`groupTree` 留着——
  它是考点树的分组逻辑，筛选面板和列表都在用。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1）。
 */
import { useEffect, useState } from 'react'
import { History } from 'lucide-react'
import { api, reportErr } from '@/lib/api'

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
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <History size={22} className="text-border-strong" />
        <span className="text-[12.5px] text-ink-faint">
          还没有变更记录 —— 只有 MIGRATE 级迁移（改存量数据）才会留档
        </span>
      </div>
    )
  }
  return (
    <div className="flex h-full min-h-0">
      <div className="w-[288px] shrink-0 overflow-y-auto border-r border-border bg-surface-2
                      px-3.5 py-3.5">
        <div className="mb-2.5 flex items-baseline gap-1.5 text-[11px] font-semibold
                        tracking-[0.08em] text-ink-faint">
          变更记录 <span className="tnum">{items.length}</span> 份
        </div>
        <div className="space-y-1.5">
          {items.map((x) => (
            <button key={x.name} onClick={() => open(x.name)}
              className={`press block w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                cur === x.name ? 'border-brand-line bg-brand-soft shadow-[var(--shadow-card)]'
                               : 'border-border bg-surface hover:border-border-strong'}`}>
              <div className={`truncate text-[12.5px] font-medium ${
                cur === x.name ? 'text-brand-ink' : 'text-ink-soft'}`}>{x.rule}</div>
              <div className="tnum mt-0.5 text-[11px] text-ink-faint">{x.at}</div>
            </button>
          ))}
        </div>
      </div>
      <div className="min-w-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="rounded-[var(--radius-card)] border border-border bg-surface p-4
                        shadow-[var(--shadow-card)]">
          <pre className="whitespace-pre-wrap font-sans text-[12.5px] leading-relaxed text-ink-soft">
            {text}
          </pre>
        </div>
      </div>
    </div>
  )
}
