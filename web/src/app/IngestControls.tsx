import { useMemo, useState } from 'react'
import { X } from 'lucide-react'

const DIFFS: [string, number][] = [['简单题', 1], ['中档题', 2], ['难题', 3]]

/** 考点选择器：已选按顺序排（第一条是主考点）；＋ 打开搜索。 */
export function PointPicker({ value, onChange, points }: {
  value: string[]; onChange: (v: string[]) => void
  points: any[]
}) {
  const [kw, setKw] = useState('')
  const [open, setOpen] = useState(false)
  const filtered = useMemo(() => {
    const q = kw.trim()
    const hit = q
      ? points.filter((p) => !value.includes(p.value)
          && (p.title.includes(q) || p.value.includes(q)))
      : points.filter((p) => !value.includes(p.value))
    return hit.slice(0, 24)
  }, [kw, points, value])

  const add = (pid: string) => {
    if (!value.includes(pid)) onChange([...value, pid])
    setKw('')
    setOpen(false)
  }

  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-1">
        {value.map((p, i) => {
          const t = points.find((x) => x.value === p)
          return (
            <span key={p}
              className="inline-flex items-center gap-1 rounded-md border border-brand-line
                         bg-brand-soft px-1.5 py-[2px] text-[11px] text-brand-ink">
              {i === 0 && <b title="主考点">主</b>}
              <span className="max-w-[230px] truncate">{t?.title || p}</span>
              <button onClick={() => onChange(value.filter((x) => x !== p))}
                title="移除考点"
                className="ml-0.5 grid h-3.5 w-3.5 place-items-center rounded text-brand-ink/60
                           hover:bg-brand-line/50 hover:text-brand-ink">
                <X size={10} />
              </button>
            </span>
          )
        })}
        <button onClick={() => setOpen((v) => !v)}
          className="press inline-flex items-center gap-0.5 rounded-md border border-dashed
                     border-border px-1.5 py-[2px] text-[10.5px] text-ink-faint
                     hover:border-brand-line hover:text-brand-ink">
          ＋考点
        </button>
      </div>
      {open && (
        <div className="mt-1 overflow-hidden rounded-lg border border-border bg-surface
                        shadow-[var(--shadow-card)]">
          <input autoFocus value={kw} onChange={(e) => setKw(e.target.value)}
            placeholder="搜考点名 / 编号…"
            className="h-[28px] w-full border-b border-border bg-transparent px-2
                       text-[11.5px] outline-none placeholder:text-ink-faint" />
          <div className="max-h-[168px] overflow-y-auto">
            {filtered.map((p) => (
              <button key={p.value} onClick={() => add(p.value)}
                className="flex w-full items-baseline gap-2 px-2 py-1.5 text-left text-[11.5px]
                           transition-colors hover:bg-muted">
                <span className="font-mono text-[10px] text-ink-faint">{p.value}</span>
                <span className="min-w-0 flex-1 truncate text-ink-soft">{p.title}</span>
              </button>
            ))}
            {!filtered.length && (
              <div className="px-2 py-2 text-[11px] text-ink-faint">没有匹配的考点</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/** 难度三联。显式选的亮；没选时把派生难度用浅色底标出来。 */
export function DiffPills({ value, derived, onChange }
: {
  value: string; derived: string; onChange: (v: string) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {DIFFS.map(([d, k]) => {
        const on = value === d
        const soft = !value && derived === d
        return (
          <button key={d} onClick={() => onChange(on ? '' : d)}
            title={on ? '再点一下：改回按主考点派生' : ''}
            className={`press inline-flex items-center gap-0.5 rounded-full border px-1.5 py-[2px]
                        text-[10.5px] font-medium transition-colors ${
              on ? 'border-brand bg-brand text-white'
                 : soft ? 'border-brand-line bg-brand-soft/60 text-brand-ink'
                        : 'border-border bg-surface text-ink-soft hover:border-brand-line'}`}>
            <span>{'★'.repeat(k)}</span>
            <span>{d.replace('题', '')}</span>
          </button>
        )
      })}
      {!value && derived && (
        <span className="text-[10px] text-ink-faint" title="难度由主考点派生；点上面可改">
          按考点
        </span>
      )}
    </div>
  )
}

