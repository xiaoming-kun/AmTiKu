/** 学段总览：把「图谱 → 讲义 → 题库 → 组卷」四段流水线摊在一屏。
 *
 *  这是新的首页。旧版一打开就是两万道题的列表，老师得先想「我今天要干嘛」；
 *  现在先看到这个学段的进度和缺口，再点进具体工作区。
 *  小学/初中题库还在建，总览也会如实显示「0 题 + 诊断题 N 道」，
 *  而不是给一块空白让人以为坏了。
 */
import {
  Activity, ArrowRight, BookOpenText, CalendarDays, ChevronRight, CircleAlert,
  FileStack, FolderOpen, LibraryBig, Network, Plus, Sparkles, TriangleAlert,
} from 'lucide-react'
import type { Overview } from '@/lib/types'
import { STAGES, STAGE_BY_KEY, type Stage } from '@/lib/stage'
import { effectiveDark, useTheme } from '@/lib/theme'
import type { PageKey } from '@/app/Shell'
import SpotlightCard from '@/app/reactbits/SpotlightCard'

function pct(n: number, d: number) {
  if (!d) return 0
  return Math.max(0, Math.min(100, Math.round((n / d) * 100)))
}

function StageCard({ s, active, data, onClick }: {
  s: (typeof STAGES)[number]; active: boolean
  data: Overview | null; onClick: () => void
}) {
  const row = data?.stages.find((x) => x.key === s.key)
  const bank = row?.bank || 0
  const diag = row?.diagnostics || 0
  const lec = row?.lectures || 0
  const pts = row?.points || 0
  return (
    <button onClick={onClick}
      className={`glass-card group relative overflow-hidden p-4 text-left transition-all duration-300
        hover:-translate-y-0.5 ${active ? 'ring-1 ring-brand/40 shadow-[var(--glow-cyan)]' : ''}`}>
      <i className="absolute inset-x-0 top-0 h-[2px] opacity-90"
        style={{ background: `linear-gradient(90deg, transparent, ${s.color}, transparent)` }} />
      <div className="absolute -right-10 -top-10 h-28 w-28 rounded-full opacity-40 blur-2xl"
        style={{ background: s.color }} />
      <div className="relative flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ background: s.color, boxShadow: `0 0 12px ${s.color}` }} />
        <span className="text-[13.5px] font-semibold">{s.name}</span>
        <span className="text-[10.5px] text-ink-faint">{s.grades}</span>
        {active && (
          <span className="ml-auto rounded-full border border-brand-line bg-brand-soft px-2 py-[1px]
                           text-[10px] font-semibold text-brand-ink">当前</span>
        )}
      </div>
      <div className="relative mt-4 grid grid-cols-3 gap-2">
        {[
          [pts, '知识点'], [bank || diag, bank ? '题库' : '诊断题'],
          [lec, '讲义'],
        ].map(([n, label]) => (
          <div key={String(label)}>
            <div className="text-[22px] font-semibold leading-none tracking-tight tnum">{Number(n).toLocaleString()}</div>
            <div className="mt-1 text-[10px] tracking-wide text-ink-faint">{label}</div>
          </div>
        ))}
      </div>
      <div className="relative mt-3 text-[10.5px] leading-relaxed text-ink-faint">{s.blurb}</div>
    </button>
  )
}

function Pipeline({ data, onPage, onPaper }: {
  data: Overview | null; onPage: (p: PageKey) => void; onPaper: () => void
}) {
  const { mode } = useTheme()
  const dark = effectiveDark(mode)
  if (!data) {
    return (
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="b-card h-[190px] animate-pulse bg-muted/40" />)}
      </div>
    )
  }
  const c = data.coverage
  const lecTotal = data.lectures.total || 0
  const cols: {
    key: string; title: string; icon: React.ComponentType<{ size?: number; className?: string }>
    value: number; unit: string; percent: number; lines: string[]
    action: string; go: () => void; tone: string
  }[] = [
    {
      key: 'map', title: '知识图谱', icon: Network, value: c.points, unit: '个知识点',
      percent: 100,
      lines: [`${data.stage.books} 册 · ${data.stage.chapters} 章`, `${data.stage.edges} 条先修/顺序关系`],
      action: '打开图谱', go: () => onPage('map'), tone: '#22d3ee',
    },
    {
      key: 'lecture', title: '讲义', icon: BookOpenText, value: lecTotal,
      unit: '份',
      percent: pct(c.lectures, c.points),
      lines: [`覆盖 ${c.lectures}/${c.points} 个知识点`,
        data.stage.key === 'senior' ? '讲 · 错 · 练在同一页' : '讲 · 错 · 结，与高中同一套模板'],
      action: '打开讲义', go: () => onPage('lectures'), tone: '#a78bfa',
    },
    {
      key: 'bank', title: '题库', icon: LibraryBig, value: data.bank.total, unit: '道',
      percent: pct(c.bank, c.points),
      lines: data.bank.total
        ? [`覆盖 ${c.bank}/${c.points} 个知识点`, data.bank.types.slice(0, 3).map((x) => `${x.label} ${x.n}`).join(' · ')]
        : [`诊断题 ${data.diagnostics.total} 道`, `覆盖 ${c.diagnostics}/${c.points} 个知识点`],
      action: data.bank.total ? '打开题库' : '去录题', go: () => onPage(data.bank.total ? 'bank' : 'ingest'), tone: '#f472b6',
    },
    {
      key: 'paper', title: '组卷与输出', icon: FileStack, value: data.papers.total, unit: '份存档',
      percent: data.papers.total ? 100 : 0,
      lines: data.papers.recent[0]
        ? [`最近：${data.papers.recent[0].title}`, `${data.papers.recent[0].n} 道 · ${data.papers.recent[0].at?.slice(0, 10) || ''}`]
        : ['还没有出过卷子', '组好卷子后可存进试卷库'],
      action: '去组卷', go: onPaper, tone: '#34d399',
    },
  ]
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cols.map((x) => {
        const Icon = x.icon
        return (
          <SpotlightCard
            key={x.key}
            theme={dark ? 'dark' : 'light'}
            spotlightColor={x.tone}
            intensity={dark ? 0.16 : 0.36}
            spotlightSize={220}
            softness={0.8}
            borderGlow={0.35}
            proximity={0}
            smoothing={0.35}
            flare={false}
            grain={0}
            ambient={false}
            className="glass-card group flex flex-col p-4"
          >
            <div className="flex items-center gap-2.5">
              <span className="grid h-9 w-9 place-items-center rounded-[11px]"
                style={{ background: `color-mix(in srgb, ${x.tone} 13%, var(--color-surface))`, color: x.tone }}>
                <Icon size={16} />
              </span>
              <span className="text-[12.5px] font-semibold">{x.title}</span>
              <span className="ml-auto rounded-full border border-border bg-white/[.03] px-2 py-[1px]
                               text-[9.5px] text-ink-faint">
                {x.key === 'paper' ? '存档' : `${x.percent}%`}
              </span>
            </div>
            <div className="mt-4 flex items-baseline gap-1.5">
              <span className="stat-num">{x.value.toLocaleString()}</span>
              <span className="text-[11px] text-ink-faint">{x.unit}</span>
            </div>
            <div className="mt-3 space-y-1 text-[10.5px] leading-relaxed text-ink-faint">
              {x.lines.filter(Boolean).map((l, i) => <div key={i} className="truncate">{l}</div>)}
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[.06]">
              <i className="grad-bar block h-full rounded-full transition-all duration-700"
                style={{ width: `${x.percent}%` }} />
            </div>
            <div className="mt-2 flex items-center justify-between text-[10px] text-ink-faint">
              <span>{x.key === 'map' ? '教材结构已完整'
                : x.key === 'paper' ? '存档可原样重现'
                : `覆盖 ${x.percent}%`}</span>
              <button onClick={x.go} className="font-medium text-brand-ink transition-colors hover:text-ink">
                {x.action} →
              </button>
            </div>
          </SpotlightCard>
        )
      })}
    </div>
  )
}

const GALAXY_DOTS = Array.from({ length: 30 }, (_, i) => {
  const ring = i % 3
  const r = 36 + ring * 30
  const a = i * 2.39996 + ring * 1.7
  return {
    x: 180 + Math.cos(a) * r,
    y: 128 + Math.sin(a) * r * 0.78,
    rr: 1.7 + (i % 3) * 0.7,
    c: ['#2563eb', '#7c3aed', '#0891b2', '#db2777', '#d97706'][i % 5],
  }
})

function HeroGalaxy({ total, onMap }: { total: number; onMap: () => void }) {
  return (
    <button onClick={onMap}
      className="group relative h-[252px] w-full max-w-[372px] shrink-0 overflow-hidden rounded-[24px]
                 border border-[#d8e4ff] bg-[linear-gradient(135deg,#eef4ff,#e4ecff_48%,#f1e8ff)]
                 text-left shadow-[0_30px_70px_-38px_rgba(37,99,235,.45)]">
      <div className="absolute inset-0 bg-[radial-gradient(55%_75%_at_35%_20%,rgba(147,197,253,.55),transparent_60%),radial-gradient(55%_75%_at_80%_85%,rgba(196,181,253,.55),transparent_60%),radial-gradient(40%_50%_at_60%_50%,rgba(251,207,232,.28),transparent_60%)]" />
      <div className="absolute inset-0 opacity-60"
        style={{ backgroundImage: 'radial-gradient(rgba(15,23,42,.10) 1px, transparent 1px)', backgroundSize: '18px 18px',
                 maskImage: 'radial-gradient(ellipse 70% 65% at 50% 50%, #000 30%, transparent 78%)' }} />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-40 w-40 -translate-x-1/2
                      -translate-y-1/2 rounded-full opacity-45 blur-2xl"
        style={{ background: 'radial-gradient(circle at 32% 30%, #bfdbfe, #a5b4fc 45%, #e9d5ff 70%, transparent 76%)' }} />
      <svg viewBox="0 0 360 256" className="absolute inset-0 h-full w-full">
        <defs>
          <radialGradient id="hero-center">
            <stop offset="0%" stopColor="#dbeafe" stopOpacity=".9" />
            <stop offset="60%" stopColor="#ede9fe" stopOpacity=".5" />
            <stop offset="100%" stopColor="#fbfcff" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="hero-ring" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#60a5fa" />
            <stop offset="100%" stopColor="#c084fc" />
          </linearGradient>
          <filter id="hero-glow"><feGaussianBlur stdDeviation="2" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        {[66, 100, 132].map((r, i) => (
          <circle key={r} cx="180" cy="128" r={r} fill="none" stroke="rgba(15,23,42,.08)"
            strokeWidth={i === 1 ? 1 : .6} strokeDasharray="2 9" />
        ))}
        {GALAXY_DOTS.slice(0, 18).map((d, i) => (
          <path key={i} d={`M 180 128 Q ${(180 + d.x) / 2} ${(128 + d.y) / 2} ${d.x} ${d.y}`}
            fill="none" stroke="#2563eb" strokeOpacity=".24" strokeWidth=".75" />
        ))}
        {GALAXY_DOTS.map((d, i) => (
          <circle key={i} cx={d.x} cy={d.y} r={d.rr} fill={d.c} filter="url(#hero-glow)" opacity=".9" />
        ))}
        <circle cx="180" cy="128" r="58" fill="url(#hero-center)" />
        <circle cx="180" cy="128" r="24" fill="#ffffff" stroke="url(#hero-ring)" strokeWidth="1.2" />
        <text x="180" y="132" textAnchor="middle" fontSize="15" fontWeight="700" fill="#0f172a">{total}</text>
        <text x="180" y="145" textAnchor="middle" fontSize="7" fill="#64748b" letterSpacing=".08em">POINTS</text>
      </svg>
      <div className="absolute left-3.5 top-3 flex items-center gap-1.5">
        <span className="live-dot" />
        <span className="text-[9px] font-semibold tracking-[0.16em] text-[#475569]">KNOWLEDGE CONSTELLATION</span>
      </div>
      <div className="absolute bottom-3.5 left-3.5 rounded-xl border border-white/80
                      bg-white/85 px-3 py-2 shadow-[0_10px_24px_-18px_rgba(15,23,42,.4)] backdrop-blur-xl">
        <div className="tnum text-[17px] font-semibold leading-none text-[#0f172a]">{total.toLocaleString()}</div>
        <div className="mt-1 text-[8.5px] tracking-wide text-[#64748b]">知识点 · 实时</div>
      </div>
      <div className="absolute bottom-3.5 right-3.5 flex items-center gap-1 rounded-full
                      border border-[#e5e9f2] bg-white/85 px-2.5 py-1 text-[9px] text-[#64748b]
                      backdrop-blur-xl transition-colors group-hover:border-[#bfdbfe] group-hover:text-[#1d4ed8]">
        进入导图 <ArrowRight size={10} />
      </div>
    </button>
  )
}

export default function OverviewPage({
  stage, data, loading, onStage, onPage, onTask, onPaper, onIngest, onBankFilter, onOpenPaper, onReview,
}: {
  stage: Stage
  data: Overview | null
  loading: boolean
  onStage: (s: Stage) => void
  onPage: (p: PageKey) => void
  onTask: (page: PageKey, filters: Record<string, string>) => void
  onPaper: () => void
  onIngest: () => void
  onBankFilter: () => void
  onReview?: () => void
  onOpenPaper: (name: string) => void
}) {
  const meta = STAGE_BY_KEY[stage]
  const underConstruction = stage !== 'senior'
  const tasks = data?.tasks || []
  const missing = data?.bank.missing || {}
  const lecTotal = data?.lectures.total || 0
  // 单学段交付包里只列包内学段：三个空学段卡片会让客户以为另外两套没给。
  const allowedStages = new Set((data?.stages || []).map((x) => x.key))
  const shownStages = allowedStages.size ? STAGES.filter((s) => allowedStages.has(s.key)) : STAGES

  return (
    <div className="b-scroll h-full overflow-y-auto">
      <div className="b-page">
        {/* hero */}
        <section className="hero-panel p-6 md:p-7">
          <div className="relative z-10 flex flex-wrap items-start gap-6">
            <div className="min-w-0 flex-1">
              <span className="aurora-pill">
                <span className="live-dot" />
                K12 · {meta.name} · 学段工作台
              </span>
              <h2 className="mt-4 text-[32px] font-semibold leading-[1.08] tracking-[-.045em] md:text-[38px]">
                {meta.name} <span className="grad-text">教学工作台</span>
              </h2>
              <p className="mt-3 max-w-[680px] text-[12.5px] leading-relaxed text-ink-soft">
                {data?.edition || '人教版教材顺序'}。从知识图谱出发，把讲义、题目和卷子串成一条线。
                {underConstruction && ' 这个学段正在建设：讲义和诊断题先读起来，再把正式题目入库。'}
              </p>
              <div className="mt-5 flex flex-wrap items-center gap-2">
                <button onClick={onIngest} className="b-btn b-btn-secondary h-9 rounded-full px-4">
                  <Plus size={14} />录入题目
                </button>
                {lecTotal > 0 && (
                  <button onClick={() => onPage('lectures')} className="b-btn b-btn-secondary h-9 rounded-full px-4">
                    <BookOpenText size={14} />读讲义
                  </button>
                )}
                <button onClick={onPaper} className="b-btn grad-primary h-9 rounded-full px-4 text-white
                                                   shadow-[var(--shadow-brand)] hover:brightness-110">
                  <Sparkles size={14} />新建组卷
                </button>
                {data?.tasks[0] && (
                  <button onClick={() => onTask(data.tasks[0].page as PageKey, data.tasks[0].filters || {})}
                    className="group ml-1 flex items-center gap-2 rounded-full border border-border/70
                               bg-white/[.02] px-3 py-1.5 text-[10.5px] text-ink-faint
                               transition-colors hover:border-brand-line hover:text-ink">
                    <span className="live-dot" />
                    下一步：{data.tasks[0].label}
                    {data.tasks[0].n > 0 && <span className="tnum text-ink-soft">{data.tasks[0].n.toLocaleString()}</span>}
                    <ArrowRight size={11} className="transition-transform group-hover:translate-x-0.5" />
                  </button>
                )}
              </div>
            </div>

            <HeroGalaxy total={data?.coverage.points || 0} onMap={() => onPage('map')} />
          </div>
        </section>

        {/* 关键数字 */}
        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            { label: '题目', value: data ? (data.bank.total || data.diagnostics.total) : 0,
              hint: data?.bank.total ? '正式入库' : '诊断题', c: '#2563eb' },
            { label: '讲义', value: lecTotal,
              hint: data?.stage.key === 'senior' ? '讲 · 错 · 练' : '讲 · 错 · 结', c: '#7c3aed' },
            { label: '知识点', value: data?.coverage.points || 0,
              hint: `${data?.stage.books || 0} 册教材`, c: '#0891b2' },
            { label: '组卷', value: data?.papers.total || 0, hint: '份存档', c: '#db2777' },
          ].map((x) => (
            <div key={x.label} className="glass-card relative overflow-hidden p-4">
              <span className="absolute -right-6 -top-6 h-20 w-20 rounded-full opacity-[.08] blur-xl"
                style={{ background: x.c }} />
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: x.c }} />
                <span className="text-[10px] font-medium tracking-wide text-ink-faint">{x.label}</span>
              </div>
              <div className="mt-3 stat-num text-[30px]">{x.value.toLocaleString()}</div>
              <div className="mt-1 text-[10px] text-ink-faint">{x.hint}</div>
            </div>
          ))}
        </div>

        {/* 学段对比 */}
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {shownStages.map((s) => (
            <StageCard key={s.key} s={s} active={s.key === stage} data={data}
              onClick={() => onStage(s.key)} />
          ))}
        </div>

        {lecTotal > 0 && (
          <button onClick={() => onPage('lectures')}
            className="glass-card group mt-4 flex w-full flex-wrap items-center gap-3 p-4 text-left
                       transition-all hover:-translate-y-0.5">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
              <BookOpenText size={19} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[12.5px] font-semibold">
                讲义已接入 {lecTotal} 份
              </span>
              <span className="mt-0.5 block text-[10.5px] text-ink-faint">
                按人教版教材的册 / 章归位；开源内容已保留作者与许可。
              </span>
            </span>
            <span className="ml-auto inline-flex items-center gap-1 text-[10.5px] font-medium text-brand-ink">
              去阅读 <ArrowRight size={12} className="transition-transform group-hover:translate-x-0.5" />
            </span>
          </button>
        )}

        {/* 流水线 */}
        <div className="mt-6 flex items-end justify-between">
          <div>
            <h3 className="text-[14px] font-semibold">内容生产线</h3>
            <p className="mt-0.5 text-[11px] text-ink-faint">学生看到的一道题，背后要经过这四步</p>
          </div>
          {loading && <span className="text-[10.5px] text-ink-faint">正在统计…</span>}
        </div>
        <div className="mt-2.5">
          <Pipeline data={data} onPage={onPage} onPaper={onPaper} />
        </div>

        {/* 待办 + 最近 */}
        <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-[1.15fr_.85fr]">
          <section className="glass-card overflow-hidden">
            <div className="flex items-center gap-2.5 border-b border-border/70 px-4 py-3">
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-warn-soft text-warn">
                <CircleAlert size={15} />
              </span>
              <h3 className="text-[13px] font-semibold">接下来做这些</h3>
              <span className="ml-auto rounded-full border border-border bg-white/[.03] px-2 py-[1px]
                               text-[10px] text-ink-faint">
                {tasks.length ? `${tasks.length} 项` : '暂无待办'}
              </span>
            </div>
            {tasks.length === 0 ? (
              <div className="b-empty m-4 border-0 bg-surface-2">
                <div className="text-[13px] font-medium text-ink-soft">这个学段状态很好</div>
                <div className="text-[11px]">没有发现结构性的缺口</div>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {tasks.map((t) => (
                  <button key={t.id}
                    onClick={() => onTask(t.page as PageKey, t.filters || {})}
                    className="group flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[.035]">
                    <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${t.tone === 'warn' ? 'bg-warn' : 'bg-brand'}`}
                      style={{ boxShadow: t.tone === 'warn' ? '0 0 10px #fbbf24' : '0 0 10px #22d3ee' }} />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline gap-2">
                        <span className="text-[12.5px] font-medium text-ink">{t.label}</span>
                        {t.n > 0 && <span className="tnum text-[11px] text-ink-faint">{t.n.toLocaleString()}</span>}
                      </span>
                      <span className="mt-0.5 block text-[10.5px] leading-relaxed text-ink-faint">{t.hint}</span>
                    </span>
                    <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full
                                     border border-border text-ink-faint transition-all
                                     group-hover:border-brand-line group-hover:text-brand-ink
                                     group-hover:shadow-[var(--glow-cyan)]">
                      <ArrowRight size={12} />
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="glass-card overflow-hidden">
            <div className="flex items-center gap-2.5 border-b border-border/70 px-4 py-3">
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand-soft text-brand">
                <FolderOpen size={15} />
              </span>
              <h3 className="text-[13px] font-semibold">最近组卷</h3>
              <button onClick={() => onPage('papers')}
                className="ml-auto text-[10.5px] font-medium text-brand-ink hover:underline">
                全部 {data?.papers.total || 0} 份
              </button>
            </div>
            {(data?.papers.recent || []).length === 0 ? (
              <div className="px-4 py-6 text-center text-[11.5px] text-ink-faint">还没有出过卷子</div>
            ) : (
              <div className="divide-y divide-border">
                {data!.papers.recent.map((p) => (
                  <button key={p.name} onClick={() => onOpenPaper(p.name)}
                    className="group flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-white/[.035]">
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-white/[.04]
                                     text-ink-faint transition-colors group-hover:text-brand-ink">
                      <FileStack size={14} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12px] text-ink">{p.title}</span>
                      <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-ink-faint">
                        <CalendarDays size={10} />{p.at?.slice(0, 16) || ''}
                        <span>·</span>{p.kind}
                        <span>·</span>{p.n} 道
                      </span>
                    </span>
                    <ChevronRight size={13} className="shrink-0 text-ink-faint" />
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* 质量快照 */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: '缺解析', v: missing['解析'] || 0, tone: 'warn' },
            { label: '没有考点', v: missing['标签'] || 0, tone: 'warn' },
            { label: '考点来源未登记', v: data?.bank.untagged_source || 0, tone: 'ink' },
            { label: '待审', v: data?.bank.unreviewed || 0, tone: 'ink', go: 'review' },
          ].map((x) => (
            <button key={x.label} onClick={() => (x.go === 'review' ? onReview?.() : onBankFilter())}
              className="glass-card sheen flex items-center gap-3 px-3.5 py-3 text-left
                         transition-transform hover:-translate-y-0.5">
              <span className={`grid h-8 w-8 place-items-center rounded-lg ${
                x.tone === 'warn' && x.v ? 'bg-warn-soft text-warn' : 'bg-white/[.04] text-ink-faint'}`}>
                <Activity size={15} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="stat-num block text-[20px]">{x.v.toLocaleString()}</span>
                <span className="block text-[10px] tracking-wide text-ink-faint">{x.label}</span>
              </span>
              <ChevronRight size={13} className="text-ink-faint" />
            </button>
          ))}
        </div>

        {underConstruction && (
          <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-brand-line
                          bg-brand-soft/60 px-4 py-3 text-[11.5px] leading-relaxed text-brand-ink">
            <TriangleAlert size={15} className="mt-0.5 shrink-0" />
            <span>
              <b>{meta.name}题库正在建设。</b>目前以知识图谱和诊断题为主；
              录进来的题会自动归到{meta.name}，录完就能在题库和组卷里用。
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
