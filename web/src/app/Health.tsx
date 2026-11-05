/** 题库体检：把后端已经算好的统计变成能点的页面。
 *
 *  数据全部来自 `GET /api/stats/detail`（一次请求，不读第二遍题库）。
 *  这里只做展示和“跳到工作台按这个范围筛题”，不碰任何题目数据。
 */
import { useEffect, useState } from 'react'
import {
  Activity, ArrowRight, BookOpen, CircleAlert, FileText, Image as ImageIcon,
  RefreshCw, Tags, TriangleAlert,
} from 'lucide-react'
import { api, reportErr } from '@/lib/api'

type Diff = '简单题' | '中档题' | '难题'
type Point = {
  value: string; title: string; n: number; topic: string; section: string
  stars: number; difficulty: string; by_diff?: Record<Diff, number>
}
type Data = {
  total: number
  points_covered: number
  points_total: number
  all_points: Point[]
  by_type: { value: string; label: string; n: number }[]
  by_difficulty: { value: string; n: number }[]
  by_year: { value: string; n: number }[]
  by_topic: { value: string; n: number; total: number; covered: number }[]
  by_point_source: { value: string; n: number }[]
  by_source: { value: string; n: number }[]
  missing: { value: string; n: number }[]
  figures: { files: number; bytes: number }
  reviewed?: number
  unreviewed?: number
}

export type Scope = {
  points?: string[]; missing?: string[]; years?: string[]
  q?: string; note?: string
  /** 考点标注来源：'无' = 没记来源（「无标签来源」卡片/队列点进来用）。 */
  pointSource?: string
  reviewed?: string
}

const DIFF: Diff[] = ['简单题', '中档题', '难题']
const DIFF_TONE: Record<Diff, string> = {
  简单题: 'bg-has', 中档题: 'bg-brand', 难题: 'bg-danger',
}

function Panel({ title, hint, children, className = '' }: {
  title: string; hint?: React.ReactNode; children: React.ReactNode; className?: string
}) {
  return (
    <section className={`rounded-[var(--radius-card)] border border-border bg-surface
                        p-4 shadow-[var(--shadow-card)] ${className}`}>
      <div className="mb-3 flex items-baseline gap-2">
        <h2 className="text-[13.5px] font-semibold tracking-tight">{title}</h2>
        {hint && <span className="text-[11px] text-ink-faint">{hint}</span>}
      </div>
      {children}
    </section>
  )
}

function Kpi({ label, value, sub, tone = 'ink', onClick }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode
  tone?: 'ink' | 'warn' | 'danger' | 'has'; onClick?: () => void
}) {
  const color = { ink: 'text-ink', warn: 'text-warn', danger: 'text-danger', has: 'text-has' }[tone]
  const Comp: any = onClick ? 'button' : 'div'
  return (
    <Comp onClick={onClick}
      className={`rounded-[var(--radius-card)] border border-border bg-surface p-3.5 text-left
                  shadow-[var(--shadow-card)] ${onClick ? 'press hover:border-brand-line' : ''}`}>
      <div className="text-[11px] font-medium text-ink-faint">{label}</div>
      <div className={`tnum mt-1 text-[24px] font-semibold leading-none tracking-tight ${color}`}>
        {value}
      </div>
      {sub && <div className="mt-1.5 text-[11px] text-ink-faint">{sub}</div>}
    </Comp>
  )
}

function Bar({ n, max, tone = 'bg-brand' }: { n: number; max: number; tone?: string }) {
  return (
    <div className="h-[6px] w-full overflow-hidden rounded-full bg-muted">
      <div className={`h-full rounded-full ${tone}`}
        style={{ width: `${Math.max(2, (n / Math.max(1, max)) * 100)}%` }} />
    </div>
  )
}

function pct(n: number, d: number) {
  return d ? Math.round((n / d) * 100) : 0
}

export default function Health({ onScope }: { onScope: (s: Scope) => void }) {
  const [d, setD] = useState<Data | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => {
    setBusy(true); setErr('')
    api.statsDetail()
      .then((x: Data) => setD(x))
      .catch((e) => { setErr(String((e as any)?.message || e)); reportErr(e) })
      .finally(() => setBusy(false))
  }
  useEffect(load, [])

  if (!d) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center text-[13px] text-ink-faint">
        {err ? (
          <div className="text-center">
            <div className="mb-2 text-warn">{err}</div>
            <button onClick={load} className="press rounded-lg border border-border px-3 py-1.5">
              重试
            </button>
          </div>
        ) : '正在统计题库…'}
      </div>
    )
  }

  const missingSol = d.missing.find((x) => x.value === '解析')?.n || 0
  const unlabeled = d.by_point_source.find((x) => x.value === '无')?.n || 0
  const noEasy = d.all_points.filter((p) => p.n > 0 && (p.by_diff?.['简单题'] || 0) === 0)
  const noHard = d.all_points.filter((p) => p.n > 0 && (p.by_diff?.['难题'] || 0) === 0)
  const maxTopic = Math.max(...d.by_topic.map((x) => x.n), 1)
  const maxDiff = Math.max(...d.by_difficulty.map((x) => x.n), 1)
  const years = d.by_year.slice(-12)
  const maxYear = Math.max(...years.map((x) => x.n), 1)
  const maxSource = Math.max(...d.by_source.map((x) => x.n), 1)
  const diffMap = Object.fromEntries(d.by_difficulty.map((x) => [x.value, x.n]))

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-bg">
      <div className="mx-auto w-full max-w-[1180px] space-y-4 px-6 py-5">
        <header className="flex items-end gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="flex items-center gap-2 text-[21px] font-semibold tracking-tight">
              <Activity size={19} className="text-brand" />题库体检
            </h1>
            <p className="mt-0.5 text-[12px] text-ink-faint">
              覆盖、难度、缺口和待补队列。点数字/考点直接跳到工作台筛题。
            </p>
          </div>
          <button onClick={load} disabled={busy}
            className="press flex h-[30px] shrink-0 items-center gap-1.5 rounded-lg border
                       border-border bg-surface px-2.5 text-[12px] text-ink-soft
                       hover:border-border-strong hover:text-ink disabled:opacity-50">
            <RefreshCw size={13} className={busy ? 'animate-spin' : ''} />刷新
          </button>
        </header>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Kpi label="题目总数" value={d.total.toLocaleString()} sub={`${d.by_type.length} 种题型`} />
          <Kpi label="考点覆盖" value={`${d.points_covered}/${d.points_total}`}
            tone="has" sub={`${pct(d.points_covered, d.points_total)}% 考点有题`} />
          <Kpi label="缺解析" value={missingSol.toLocaleString()} tone="warn"
            sub="点这里只看缺解析的题" onClick={() => onScope({ missing: ['解析'], note: '缺解析' })} />
          <Kpi label="无标签来源" value={unlabeled.toLocaleString()} tone="warn"
            sub={`约 ${pct(unlabeled, d.total)}%：考点标签没记是谁标的；点这里只看这些题`}
            onClick={() => onScope({ pointSource: '无', note: '无标签来源' })} />
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="章节覆盖" hint="点一章看这一章的题" className="lg:col-span-2">
            <div className="grid gap-x-8 gap-y-2.5 md:grid-cols-2">
              {d.by_topic.map((t) => (
                <button key={t.value}
                  onClick={() => onScope({
                    points: d.all_points.filter((p) => p.topic === t.value).map((p) => p.value),
                    note: `章 · ${t.value}`,
                  })}
                  className="press group text-left">
                  <div className="mb-1 flex items-baseline gap-2">
                    <span className="min-w-0 flex-1 truncate text-[12px] text-ink group-hover:text-brand-ink">
                      {t.value}
                    </span>
                    <span className="tnum text-[10.5px] text-ink-faint">
                      {t.covered}/{t.total} 考点
                    </span>
                    <span className="tnum w-14 text-right text-[10.5px] text-ink-faint">
                      {t.n.toLocaleString()} 题
                    </span>
                  </div>
                  <Bar n={t.n} max={maxTopic} tone="bg-brand" />
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="难度结构" hint="人工 / 模型推定 / 考点代理">
            <div className="space-y-2.5">
              {DIFF.map((k) => (
                <div key={k}>
                  <div className="mb-1 flex items-baseline gap-2 text-[11.5px]">
                    <span className="w-16 text-ink-soft">{k}</span>
                    <span className="tnum text-ink">{diffMap[k]?.toLocaleString() || 0}</span>
                    <span className="tnum text-ink-faint">
                      {pct(diffMap[k] || 0, d.total)}%
                    </span>
                  </div>
                  <Bar n={diffMap[k] || 0} max={maxDiff} tone={DIFF_TONE[k]} />
                </div>
              ))}
            </div>
            <div className="mt-3 border-t border-border pt-2 text-[10.5px] leading-relaxed text-ink-faint">
              高考卷常见目标约 <b className="text-ink-soft">易 3 : 中 5 : 难 2</b>；
              当前结构偏中难。难度口径：人工 3,687 道 · 模型推定 20,105 道 ·
              其余按主考点代理——**模型推定不是实测**，与人工标签交叉验证一致率约 74%。
            </div>
          </Panel>

          <Panel title="质量队列" hint="有缺口不等于坏题">
            <div className="space-y-2">
              <button onClick={() => onScope({ missing: ['解析'], note: '缺解析' })}
                className="press flex w-full items-center gap-2 rounded-lg border border-border
                           bg-bg px-2.5 py-2 text-left hover:border-brand-line">
                <CircleAlert size={14} className="shrink-0 text-warn" />
                <span className="min-w-0 flex-1 text-[12px]">缺解析</span>
                <span className="tnum text-[12px] font-medium text-warn">{missingSol}</span>
                <ArrowRight size={12} className="shrink-0 text-ink-faint" />
              </button>
              <button onClick={() => onScope({ pointSource: '无', note: '无标签来源' })}
                className="press flex w-full items-center gap-2 rounded-lg border border-border
                           bg-bg px-2.5 py-2 text-left hover:border-brand-line">
                <Tags size={14} className="shrink-0 text-warn" />
                <span className="min-w-0 flex-1 text-[12px]">无标签来源</span>
                <span className="tnum text-[12px] font-medium text-warn">{unlabeled}</span>
                <ArrowRight size={12} className="shrink-0 text-ink-faint" />
              </button>
              <button onClick={() => onScope({ reviewed: 'no', note: '未复核' })}
                className="press flex w-full items-center gap-2 rounded-lg border border-border
                           bg-bg px-2.5 py-2 text-left hover:border-brand-line">
                <CircleAlert size={14} className="shrink-0 text-warn" />
                <span className="min-w-0 flex-1 text-[12px]">未复核</span>
                <span className="tnum text-[12px] font-medium text-warn">
                  {(d.unreviewed ?? 0).toLocaleString()}
                </span>
                <ArrowRight size={12} className="shrink-0 text-ink-faint" />
              </button>
              <div className="flex items-center gap-2 rounded-lg border border-border bg-bg px-2.5 py-2">
                <ImageIcon size={14} className="shrink-0 text-ink-faint" />
                <span className="min-w-0 flex-1 text-[12px]">图片文件</span>
                <span className="tnum text-[12px] text-ink-soft">
                  {d.figures.files.toLocaleString()}
                </span>
              </div>
            </div>
            <div className="mt-3 text-[10.5px] leading-relaxed text-ink-faint">
              无标签来源是<b className="font-medium text-ink-soft">考点标签的来源没记录</b>
              （point_source 为空），标签本身可能没错——多是早期批量录入留下的；
              点进去抽样复核即可，不必全量重打。
            </div>
          </Panel>

          <Panel title="考点缺口" hint="没有简单题 / 没有难题的考点">
            <div className="mb-2 flex items-baseline gap-3 text-[11.5px]">
              <span className="inline-flex items-center gap-1 text-warn">
                <TriangleAlert size={12} />无简单题 {noEasy.length}
              </span>
              <span className="inline-flex items-center gap-1 text-danger">
                <TriangleAlert size={12} />无难题 {noHard.length}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {noEasy.slice(0, 6).map((p) => (
                <button key={p.value} onClick={() => onScope({ points: [p.value], note: p.title })}
                  className="press rounded-full border border-warn-line bg-warn-soft px-2 py-[2px]
                             text-[11px] text-warn hover:brightness-[.98]">
                  {p.title}
                </button>
              ))}
              {noHard.slice(0, 6).map((p) => (
                <button key={p.value} onClick={() => onScope({ points: [p.value], note: p.title })}
                  className="press rounded-full border border-border bg-bg px-2 py-[2px]
                             text-[11px] text-ink-soft hover:border-danger hover:text-danger">
                  {p.title}
                </button>
              ))}
            </div>
            <div className="mt-3 text-[10.5px] text-ink-faint">
              点考点 → 只看这个考点的题；缺口不代表题不够，只代表这一档没有。
            </div>
          </Panel>

          <Panel title="年份分布" hint="近 12 年；点年份筛题" className="lg:col-span-2">
            <div className="flex h-[96px] items-end gap-1.5">
              {years.map((y) => (
                <button key={y.value} onClick={() => onScope({ years: [y.value], note: `${y.value} 年` })}
                  title={`${y.value} 年 · ${y.n} 道`}
                  className="group flex min-w-0 flex-1 flex-col items-center justify-end gap-1">
                  <span className="tnum text-[9.5px] text-ink-faint opacity-0 group-hover:opacity-100">
                    {y.n}
                  </span>
                  <span className="w-full rounded-t-[3px] bg-brand/75 transition-colors group-hover:bg-brand"
                    style={{ height: `${Math.max(3, Math.sqrt(y.n / maxYear) * 64)}px` }} />
                  <span className="tnum text-[9.5px] text-ink-faint">{y.value.slice(2)}</span>
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="来源 Top" hint="按卷别统计" className="lg:col-span-2">
            <div className="grid gap-x-8 gap-y-2 md:grid-cols-2">
              {d.by_source.slice(0, 10).map((s) => (
                <div key={s.value}>
                  <div className="mb-1 flex items-baseline gap-2 text-[11.5px]">
                    <span className="min-w-0 flex-1 truncate text-ink-soft">{s.value}</span>
                    <span className="tnum text-ink-faint">{s.n.toLocaleString()}</span>
                  </div>
                  <Bar n={s.n} max={maxSource} tone="bg-ink-faint/45" />
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <footer className="flex items-center gap-2 pb-2 text-[10.5px] text-ink-faint">
          <BookOpen size={12} />
          统计口径：考点计数按标签（一题多考点各算一次）；章节题量按题去重；难度由主考点派生。
          <span className="ml-auto inline-flex items-center gap-1">
            <FileText size={11} />数据源：GET /api/stats/detail
          </span>
        </footer>
      </div>
    </div>
  )
}
