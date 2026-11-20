/** 学段工作台：先回答「现在有什么、接下来做什么」。
 *
 *  这一版把旧首页的「大横幅 + 知识星云 + 四张 KPI + 三张学段卡 + 流水线 +
 *  讲义横幅 + 质量卡」压成三层：
 *    ① 一行状态与四个真实数字（不重复展示同一批统计）
 *    ② 当前卷子 / 接下来 / 最近试卷（真正会点开的东西）
 *    ③ 快速开始 / 覆盖 / 质量 + 学段对比（旁路信息，放右栏和页尾）
 *
 *  不再用随机星云和渐变文字当主视觉：这是每天要用的工作台，
 *  秩序感和「下一步」比气氛重要。
 */
import {
  ArrowRight, BookOpenText, CalendarDays, CheckCircle2, ChevronRight, CircleAlert,
  FileStack, FolderOpen, Info, Network, Plus, Search, TriangleAlert,
} from 'lucide-react'
import type { Overview, Q } from '@/lib/types'
import { STAGES, STAGE_BY_KEY, type Stage } from '@/lib/stage'
import type { PageKey } from '@/app/Shell'

function pct(n: number, d: number) {
  if (!d) return 0
  return Math.max(0, Math.min(100, Math.round((n / d) * 100)))
}

function fmt(n: number | undefined | null) {
  return Number(n || 0).toLocaleString()
}

function SectionHead({ title, hint, action }: {
  title: string
  hint?: React.ReactNode
  action?: { label: string; onClick: () => void }
}) {
  return (
    <div className="mb-2.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
      <h2 className="text-[13.5px] font-semibold tracking-[-.01em] text-ink">{title}</h2>
      {hint && <span className="text-[10.5px] text-ink-faint">{hint}</span>}
      {action && (
        <button onClick={action.onClick}
          className="press ml-auto inline-flex items-center gap-1 text-[11px] font-medium
                     text-brand-ink hover:underline">
          {action.label}<ArrowRight size={11} />
        </button>
      )}
    </div>
  )
}

function Metric({ label, value, unit, hint, tone, onClick }: {
  label: string; value: number; unit: string; hint?: string; tone: string; onClick?: () => void
}) {
  const body = (
    <>
      <div className="flex items-baseline gap-1.5">
        <span className="tnum text-[24px] font-semibold leading-none tracking-[-.03em] text-ink">
          {fmt(value)}
        </span>
        <span className="text-[10.5px] text-ink-faint">{unit}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-ink-soft">
        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: tone }} />
        <span>{label}</span>
        {hint && <span className="truncate text-[10px] text-ink-faint">{hint}</span>}
      </div>
    </>
  )
  const cls = 'rounded-[var(--radius-card)] border border-border bg-surface/90 p-3.5 ' +
    'shadow-[var(--shadow-card)] text-left'
  return onClick ? (
    <button onClick={onClick} className={`press block ${cls} hover:border-border-strong`}>{body}</button>
  ) : <div className={cls}>{body}</div>
}

function EmptyTask() {
  return (
    <div className="glass-card flex items-center gap-3 px-4 py-5">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-has-soft text-has">
        <CheckCircle2 size={16} />
      </span>
      <div>
        <div className="text-[12.5px] font-medium text-ink">这一轮没有结构性缺口</div>
        <div className="mt-0.5 text-[11px] text-ink-faint">可以继续组卷，或去题库里按考点慢慢挑。</div>
      </div>
    </div>
  )
}

function CurrentPaper({ paper, score, answered, onPaper, onBank }: {
  paper: Q[]; score: number; answered: number
  onPaper: () => void; onBank: () => void
}) {
  if (!paper.length) {
    return (
      <section className="glass-card p-4 md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[11px] font-medium text-ink-faint">当前卷子</div>
            <h3 className="mt-1 text-[18px] font-semibold tracking-[-.02em]">还没有开始组卷</h3>
            <p className="mt-1.5 max-w-[440px] text-[12px] leading-5 text-ink-soft">
              先去题库挑题；挑中的题会进入卷子，随时可以回来排顺序、补解析、导出。
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-2 border-t border-border pt-3 text-[11px] text-ink-faint sm:grid-cols-3">
          {[
            ['01', '找题', '按考点、来源、难度筛出要用的题'],
            ['02', '编排', '按题型分节，检查解析和分值'],
            ['03', '导出', '生成 PDF / Word，或先存档'],
          ].map(([n, t, d]) => (
            <div key={n} className="flex items-baseline gap-2">
              <span className="tnum text-[10px] text-brand-ink">{n}</span>
              <span className="font-medium text-ink-soft">{t}</span>
              <span className="min-w-0 truncate">{d}</span>
            </div>
          ))}
        </div>
      </section>
    )
  }

  const typeRows = Object.entries(
    paper.reduce<Record<string, number>>((acc, q) => {
      const key = q.type_label || q.type
      acc[key] = (acc[key] || 0) + 1
      return acc
    }, {}),
  ).slice(0, 4)
  const missing = paper.length - answered

  return (
    <section className="glass-card p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10.5px] text-ink-faint">
            <span className="live-dot" />当前卷子
            <span className="text-border-strong">/</span>
            <span className="tnum">{paper.length} 道 · {score} 分</span>
          </div>
          <h3 className="mt-1 text-[18px] font-semibold tracking-[-.02em]">
            继续把这份卷子收尾
          </h3>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[11px]">
            {typeRows.map(([label, n]) => (
              <span key={label} className="text-ink-soft">
                {label} <b className="tnum font-semibold text-ink">{n}</b>
              </span>
            ))}
            <span className={`rounded px-1.5 py-[1px] text-[10.5px] ${
              missing ? 'bg-warn-soft text-warn' : 'bg-has-soft text-has'}`}>
              {missing ? `${missing} 道缺解析` : '解析齐全'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onBank} className="b-btn b-btn-secondary h-8">
            <Plus size={13} />继续挑题
          </button>
          <button onClick={onPaper} className="b-btn b-btn-primary h-8">
            打开卷子<ArrowRight size={12} />
          </button>
        </div>
      </div>
    </section>
  )
}

function QuickStart({ onPage, onIngest }: {
  onPage: (p: PageKey) => void; onIngest: () => void
}) {
  const items: { icon: typeof Search; title: string; desc: string; onClick: () => void }[] = [
    { icon: BookOpenText, title: '读讲义', desc: '讲 · 错 · 练同页', onClick: () => onPage('lectures') },
    { icon: Network, title: '知识图谱', desc: '教材顺序与先修', onClick: () => onPage('map') },
    { icon: Plus, title: '录入题目', desc: 'LaTeX 或整份资料', onClick: onIngest },
    { icon: FolderOpen, title: '试卷档案', desc: '找回出过的卷子', onClick: () => onPage('papers') },
  ]
  return (
    <section>
      <SectionHead title="常用入口" />
      <div className="glass-card divide-y divide-border overflow-hidden">
        {items.map(({ icon: Icon, title, desc, onClick }) => (
          <button key={title} onClick={onClick}
            className="group flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-bg/60">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-brand-soft/70 text-brand
                             transition-colors group-hover:bg-brand-soft group-hover:text-brand-ink">
              <Icon size={14} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[12px] font-medium text-ink">{title}</span>
              <span className="block text-[10px] text-ink-faint">{desc}</span>
            </span>
            <ChevronRight size={12} className="text-ink-faint transition-transform group-hover:translate-x-0.5" />
          </button>
        ))}
      </div>
    </section>
  )
}

function Coverage({ data, onPage }: { data: Overview | null; onPage: (p: PageKey) => void }) {
  const c = data?.coverage
  const lec = c?.lectures || 0
  const points = c?.points || 0
  const bank = c?.bank || 0
  const rows = [
    { label: '题库覆盖', n: bank, d: points, onClick: () => onPage('bank') },
    { label: '讲义覆盖', n: lec, d: points, onClick: () => onPage('lectures') },
  ]
  return (
    <section>
      <SectionHead title="内容覆盖" hint={data ? `${points} 个知识点` : ''} />
      <div className="glass-card p-3.5">
        <div className="space-y-3">
          {rows.map((r) => {
            const p = pct(r.n, r.d)
            return (
              <button key={r.label} onClick={r.onClick} className="group block w-full text-left">
                <div className="flex items-baseline gap-2">
                  <span className="text-[11.5px] text-ink-soft group-hover:text-ink">{r.label}</span>
                  <span className="tnum ml-auto text-[10.5px] text-ink-faint">{r.n}/{r.d}</span>
                  <span className="tnum w-8 text-right text-[10.5px] font-medium text-ink-soft">{p}%</span>
                </div>
                <div className="mt-1.5 h-[3px] overflow-hidden rounded-full bg-muted">
                  <i className="block h-full rounded-full bg-brand/75 transition-all duration-500"
                    style={{ width: `${p}%` }} />
                </div>
              </button>
            )
          })}
        </div>
        <button onClick={() => onPage('map')}
          className="mt-3 flex w-full items-center gap-2 border-t border-border pt-2.5 text-left
                     text-[10.5px] text-ink-faint transition-colors hover:text-ink">
          <Network size={12} />
          <span>{data?.stage.books || 0} 册 · {data?.stage.chapters || 0} 章 · {data?.stage.edges || 0} 条先修关系</span>
          <ChevronRight size={11} className="ml-auto" />
        </button>
        {!bank && (
          <div className="mt-2 text-[10.5px] leading-relaxed text-warn">
            正式题库还是空的：这个学段先以诊断题和讲义为主。
          </div>
        )}
      </div>
    </section>
  )
}

function Quality({ data, onTask, onReview }: {
  data: Overview | null
  onTask: (page: PageKey, filters: Record<string, string>) => void
  onReview: () => void
}) {
  const b = data?.bank
  const items = [
    { label: '缺解析', n: b?.missing?.['解析'] || 0, onClick: () => onTask('bank', { missing: '解析' }) },
    { label: '没有考点', n: b?.missing?.['标签'] || 0, onClick: () => onTask('bank', { missing: '标签' }) },
    { label: '考点来源未登记', n: b?.untagged_source || 0, onClick: () => onTask('bank', { psrc: '无' }) },
    { label: '待复核', n: b?.unreviewed || 0, onClick: onReview },
  ]
  return (
    <section>
      <SectionHead title="题库质量" hint="只显示需要处理的数量" />
      <div className="glass-card grid grid-cols-2 overflow-hidden">
        {items.map((x, i) => (
          <button key={x.label} onClick={x.onClick}
            className={`press p-3 text-left transition-colors hover:bg-bg/60
              ${i % 2 === 0 ? 'border-r border-border' : ''} ${i < 2 ? 'border-b border-border' : ''}`}>
            <div className={`tnum text-[18px] font-semibold leading-none ${
              x.n ? 'text-ink' : 'text-ink-faint'}`}>{fmt(x.n)}</div>
            <div className="mt-1.5 text-[10.5px] leading-tight text-ink-faint">{x.label}</div>
          </button>
        ))}
      </div>
    </section>
  )
}

export default function OverviewPage({
  stage, data, loading, onStage, onPage, onTask, onPaper, onIngest, onReview,
  onOpenPaper, paper, score, answered,
}: {
  stage: Stage
  data: Overview | null
  loading: boolean
  onStage: (s: Stage) => void
  onPage: (p: PageKey) => void
  onTask: (page: PageKey, filters: Record<string, string>) => void
  onPaper: () => void
  onIngest: () => void
  onReview?: () => void
  onOpenPaper: (name: string) => void
  paper: Q[]
  score: number
  answered: number
}) {
  const meta = STAGE_BY_KEY[stage]
  const tasks = (data?.tasks || []).slice(0, 4)
  const allowedStages = new Set((data?.stages || []).map((x) => x.key))
  const shownStages = allowedStages.size ? STAGES.filter((s) => allowedStages.has(s.key)) : STAGES
  const bankTotal = data ? (data.bank.total || data.diagnostics.total) : 0
  const bankLabel = data?.bank.total ? '题库' : '诊断题'

  return (
    <div className="b-scroll h-full overflow-y-auto">
      <div className="b-page max-w-[1180px]">
        {/* ── 页头：一个轻薄的工作台横幅，不重复统计 ── */}
        <section className="hero-panel p-5 md:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <span className="aurora-pill">
                <span className="live-dot" />K12 · {meta.name} · 学段工作台
              </span>
              <h1 className="mt-3 text-[30px] font-semibold leading-[1.15] tracking-[-.035em] md:text-[34px]">
                {meta.name} 工作台
              </h1>
              <p className="mt-2 max-w-[660px] text-[12px] leading-5 text-ink-soft">
                先把题找齐，再组卷、导出。{data?.stage.key === 'senior'
                  ? `知识图谱、讲义和题库已经连成一条线；今天从待办或当前卷子继续。`
                  : `这个学段以诊断题和章节讲义起步，正式题录进来后会自动接入组卷。`}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10.5px] text-ink-faint">
                <span>{data?.edition || '人教版教材顺序'}</span>
                <span className="text-border-strong">·</span>
                <span>全库 {fmt(data?.stages?.reduce((n, s) => n + s.points, 0))} 个知识点</span>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button onClick={() => onPage('bank')} className="b-btn b-btn-secondary h-9">
                <Search size={14} />找题
              </button>
              {paper.length === 0 && (
                <button onClick={onPaper} className="b-btn b-btn-primary h-9">
                  <FileStack size={14} />开始组卷
                </button>
              )}
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label={bankLabel} value={bankTotal} unit="道" tone="#0071e3"
              hint={data?.bank.total ? '正式入库' : '按教材位置'}
              onClick={() => onPage('bank')} />
            <Metric label="讲义" value={data?.lectures.total || 0} unit="份" tone="#af52de"
              hint={stage === 'senior' ? '讲 · 错 · 练' : '讲 · 错 · 结'}
              onClick={() => onPage('lectures')} />
            <Metric label="知识点" value={data?.coverage.points || 0} unit="个" tone="#00a3c4"
              hint={`${data?.stage.books || 0} 册 · ${data?.stage.chapters || 0} 章`}
              onClick={() => onPage('map')} />
            <Metric label="试卷档案" value={data?.papers.total || 0} unit="份" tone="#db2777"
              hint="可原样还原"
              onClick={() => onPage('papers')} />
          </div>
        </section>

        <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_292px]">
          <div className="min-w-0 space-y-6">
            <CurrentPaper paper={paper} score={score} answered={answered}
              onPaper={onPaper} onBank={() => onPage('bank')} />

            <section>
              <SectionHead title="接下来做这些"
                hint={loading ? '正在统计…' : tasks.length ? `${tasks.length} 项需要处理` : '没有结构性缺口'} />
              {loading && !data ? (
                <div className="space-y-2">
                  {[0, 1, 2].map((i) => <div key={i} className="h-[58px] animate-pulse rounded-[var(--radius-card)] bg-muted/50" />)}
                </div>
              ) : tasks.length === 0 ? <EmptyTask /> : (
                <div className="glass-card divide-y divide-border overflow-hidden">
                  {tasks.map((t) => (
                    <button key={t.id} onClick={() => onTask(t.page as PageKey, t.filters || {})}
                      className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-bg/60">
                      <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${
                        t.tone === 'warn' ? 'bg-warn-soft text-warn' : 'bg-muted text-ink-soft'}`}>
                        {t.tone === 'warn' ? <CircleAlert size={14} /> : <Info size={14} />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-baseline gap-2">
                          <span className="truncate text-[12.5px] font-medium text-ink">{t.label}</span>
                          {t.n > 0 && <span className="tnum text-[10.5px] text-ink-faint">{fmt(t.n)}</span>}
                        </span>
                        <span className="mt-0.5 block truncate text-[10.5px] text-ink-faint">{t.hint}</span>
                      </span>
                      <ChevronRight size={13} className="shrink-0 text-ink-faint transition-transform group-hover:translate-x-0.5" />
                    </button>
                  ))}
                </div>
              )}
            </section>

            <section>
              <SectionHead title="最近试卷" hint={data?.papers.total ? `共 ${fmt(data.papers.total)} 份存档` : ''}
                action={{ label: '全部', onClick: () => onPage('papers') }} />
              {data?.papers.recent?.length ? (
                <div className="glass-card divide-y divide-border overflow-hidden">
                  {data.papers.recent.slice(0, 4).map((p) => (
                    <button key={p.name} onClick={() => onOpenPaper(p.name)}
                      className="group flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-bg/60">
                      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-muted text-ink-faint
                                       transition-colors group-hover:text-brand">
                        <FileStack size={14} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12px] font-medium text-ink">{p.title}</span>
                        <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-ink-faint">
                          <CalendarDays size={10} />{p.at?.slice(0, 10) || '—'}
                          <span>·</span>{p.kind}
                          <span>·</span>{p.n} 道
                        </span>
                      </span>
                      <ChevronRight size={13} className="shrink-0 text-ink-faint" />
                    </button>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-2.5 rounded-[var(--radius-card)] border border-dashed
                                border-border-strong px-4 py-4 text-[11.5px] text-ink-faint">
                  <FolderOpen size={16} />还没有出过卷子。导出第一份卷子后，它会自动存档在这里。
                </div>
              )}
            </section>
          </div>

          <aside className="space-y-5">
            <QuickStart onPage={onPage} onIngest={onIngest} />
            <Coverage data={data} onPage={onPage} />
            <Quality data={data} onTask={onTask} onReview={() => onReview?.()} />
          </aside>
        </div>

        {/* ── 学段对比：用一张表，不再用三张会抢焦点的卡片 ── */}
        <section className="mt-7 border-t border-border pt-5">
          <SectionHead title="学段概况" hint="切换学段不会离开当前工具" />
          <div className="glass-card overflow-x-auto">
            <table className="b-table min-w-[620px]">
              <thead>
                <tr>
                  <th>学段</th>
                  <th>知识点</th>
                  <th>题库 / 诊断</th>
                  <th>讲义</th>
                  <th>状态</th>
                  <th className="w-[80px] text-right">切换</th>
                </tr>
              </thead>
              <tbody>
                {shownStages.map((s) => {
                  const row = data?.stages.find((x) => x.key === s.key)
                  const on = s.key === stage
                  return (
                    <tr key={s.key} className={on ? 'bg-brand-soft/40' : 'cursor-pointer'}
                      onClick={() => { if (!on) onStage(s.key) }}>
                      <td>
                        <div className="flex items-center gap-2">
                          <i className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                          <span className="font-medium text-ink">{s.name}</span>
                          <span className="text-[10px] text-ink-faint">{s.grades}</span>
                        </div>
                      </td>
                      <td className="tnum">{fmt(row?.points)}</td>
                      <td className="tnum">
                        {row?.bank ? fmt(row.bank) : <span className="text-ink-faint">—</span>}
                        <span className="mx-1 text-border-strong">/</span>
                        <span className="text-ink-faint">{fmt(row?.diagnostics)}</span>
                      </td>
                      <td className="tnum">{fmt(row?.lectures)}</td>
                      <td>
                        {on
                          ? <span className="rounded bg-brand-soft px-1.5 py-[1px] text-[10px] font-medium text-brand-ink">当前</span>
                          : <span className="text-[10.5px] text-ink-faint">{row?.bank ? '完整生产线' : '建设中的诊断线'}</span>}
                      </td>
                      <td className="text-right">
                        <button onClick={(e) => { e.stopPropagation(); onStage(s.key) }}
                          disabled={on}
                          className="press rounded border border-border px-2 py-1 text-[10.5px]
                                     text-ink-soft hover:border-brand-line hover:text-brand-ink
                                     disabled:opacity-35">
                          {on ? '已在此' : '切过去'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        {stage !== 'senior' && (
          <div className="mt-4 flex items-start gap-2 text-[10.5px] leading-relaxed text-ink-faint">
            <TriangleAlert size={13} className="mt-0.5 shrink-0" />
            <span>
              {meta.name}正式题库还在建设：现在以诊断题和章节讲义为主，录进来的题会自动接入题库与组卷。
            </span>
          </div>
        )}
        <div className="mt-6 flex items-center gap-1.5 text-[10px] text-ink-faint">
          <Network size={12} />知识图谱、讲义与题库共用同一套教材口径
        </div>
      </div>
    </div>
  )
}
