/** 应用外壳：AmMath · K12 数学工作站
 *
 *  交互上的四条硬约定：
 *  ① **学段是全局视角**，不是页面里的一个筛选项。切换后停留在当前工作区，
 *     不把人弹回首页。
 *  ② 主导航只放「去哪里工作」，并且按任务收成 7 个入口：
 *     工作台 / 题库 / 组卷 / 内容 / 录入 / 质量 / 档案。
 *     原来的 11 项平铺，老师每次都要在「试卷库 / 体检 / 审阅 / 回收站 / 变更记录」
 *     里重找一遍；现在同一类工作收进一个工作区，用二级标签切换。
 *  ③ 顶栏只回答三件事：我在哪、要搜什么、下一步做什么。
 *     不再把「录题」当成全局主按钮 —— 组卷才是这个工作站的出口。
 *  ④ 视觉沿用 BoardUI：蓝白卡片、20px 圆角和柔和层次；数学题是主角。
 */
import { useEffect, useRef, useState } from 'react'
import {
  Activity, Archive, ArrowRight, BookOpenText, Check, ChevronDown, ChevronRight, CircleHelp, Command as CommandIcon,
  ExternalLink,
  FilePlus2, FileStack, FileText, LayoutDashboard, LibraryBig, Monitor, Moon,
  Palette, PanelLeftClose, PanelLeftOpen, Search, Sun, X,
} from 'lucide-react'
import type { Overview } from '@/lib/types'
import { ACCENTS, setAccent, setMode, useTheme, type Mode } from '@/lib/theme'
import { STAGES, STAGE_BY_KEY, type Stage } from '@/lib/stage'

export type PageKey =
  | 'overview' | 'map' | 'lectures' | 'bank' | 'sets' | 'ingest' | 'paper'
  | 'papers' | 'health' | 'review' | 'trash' | 'changes'

export const PAGE_META: Record<PageKey, { title: string; desc: string }> = {
  overview: { title: '工作台', desc: '这个学段的进度、待办与下一步' },
  map: { title: '知识图谱', desc: '教材顺序、先修关系与诊断入口' },
  lectures: { title: '讲义', desc: '一个知识点一份：讲、错、练' },
  bank: { title: '题库', desc: '搜题、筛题、加入当前卷子' },
  sets: { title: '套卷', desc: '整份原卷：按题号排好，一键进卷子' },
  ingest: { title: '录入', desc: '独立页：手工 / DeepSeek 录题，以及已有题的整理 / 校对' },
  paper: { title: '组卷', desc: '编排当前卷子、检查并导出' },
  papers: { title: '试卷库', desc: '出过的卷子与合集，可原样重现' },
  health: { title: '题库体检', desc: '覆盖、缺口与待补队列' },
  review: { title: '审阅', desc: '风险队列、分层抽样与复核账本' },
  trash: { title: '回收站', desc: '删除的题都在这里，可恢复' },
  changes: { title: '变更记录', desc: '每次批量改动的账本' },
}

type WorkspaceKey = 'overview' | 'bank' | 'paper' | 'content' | 'ingest' | 'quality' | 'archive'

type Workspace = {
  key: WorkspaceKey
  label: string
  desc: string
  pages: PageKey[]
  icon: React.ComponentType<{ size?: number | string; strokeWidth?: number; className?: string }>
  /** 这个入口不在当前页替换，而是在新标签页打开。 */
  newTab?: boolean
}

/** 七个工作区。顺序就是老师一天里的动线：先看状态，再找题，再组卷；
 *  备课内容与录入是旁支；质量与档案是低频但必须找得到的管理面。 */
const WORKSPACES: Workspace[] = [
  { key: 'overview', label: '工作台', desc: '进度与下一步', pages: ['overview'], icon: LayoutDashboard },
  { key: 'bank', label: '题库', desc: '找题、筛题、加入卷子', pages: ['bank', 'sets'], icon: LibraryBig },
  { key: 'paper', label: '组卷', desc: '编排与导出', pages: ['paper'], icon: FileStack },
  { key: 'content', label: '内容', desc: '知识图谱与讲义', pages: ['map', 'lectures'], icon: BookOpenText },
  { key: 'ingest', label: '录入', desc: 'LaTeX 或整份资料（新标签页）', pages: ['ingest'], icon: FilePlus2, newTab: true },
  { key: 'quality', label: '质量', desc: '体检、审阅与复核', pages: ['health', 'review'], icon: Activity },
  { key: 'archive', label: '档案', desc: '试卷、回收站、变更', pages: ['papers', 'trash', 'changes'], icon: Archive },
]

const WORKSPACE_OF: Record<PageKey, Workspace> = Object.fromEntries(
  WORKSPACES.flatMap((w) => w.pages.map((p) => [p, w])),
) as Record<PageKey, Workspace>

const WORKSPACE_GROUPS: { label: string; keys: WorkspaceKey[] }[] = [
  { label: '日常工作', keys: ['overview', 'bank', 'paper', 'content', 'ingest'] },
  { label: '资料与质量', keys: ['quality', 'archive'] },
]

function NavRow({ item, active, collapsed, badge, onClick }: {
  item: Workspace; active: boolean; collapsed: boolean; badge?: number; onClick: () => void
}) {
  const Icon = item.icon
  return (
    <button
      onClick={onClick}
      title={item.newTab ? `${item.label} · 在新标签页打开` : (collapsed ? `${item.label} · ${item.desc}` : item.desc)}
      aria-current={active ? 'page' : undefined}
      data-on={active ? '1' : '0'}
      className={`b-nav ${collapsed ? 'justify-center px-0' : ''} ${active ? 'b-nav-on' : ''}`}
    >
      <Icon size={collapsed ? 18 : 16} strokeWidth={active ? 2.2 : 1.8}
        className={`shrink-0 ${active ? 'text-brand' : 'text-ink-faint'}`} />
      {!collapsed && (
        <>
          <span className="min-w-0 flex-1 truncate text-left">{item.label}</span>
          {item.newTab && <ExternalLink size={11} className="shrink-0 text-ink-faint" />}
          {!!badge && (
            <span className={`tnum shrink-0 text-[10.5px] ${
              active ? 'text-brand-ink' : 'text-ink-faint'}`}>
              {badge > 9999 ? `${Math.floor(badge / 1000)}k` : badge}
            </span>
          )}
        </>
      )}
      {collapsed && !!badge && (
        <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-brand" />
      )}
    </button>
  )
}

function StageMenu({ stage, stages, data, onStage }: {
  stage: Stage
  stages: typeof STAGES
  data: Overview | null
  onStage: (s: Stage) => void
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])
  const meta = STAGE_BY_KEY[stage]
  return (
    <div ref={box} className="relative shrink-0">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="menu"
        aria-label="切换学段" title="切换学段"
        className="press inline-flex h-6 items-center gap-1 rounded-[5px] border border-border
                   bg-bg px-1.5 text-[10px] text-ink-soft hover:border-brand-line hover:text-ink">
        <i className="h-1.5 w-1.5 rounded-full" style={{ background: meta.color }} />
        <span className="hidden sm:inline">{meta.name}</span>
        <span className="sm:hidden">{meta.short}</span>
        <ChevronDown size={10} className={`text-ink-faint transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute left-0 top-[calc(100%+6px)] z-50 w-[190px] rounded-[var(--radius-pop)]
                        border border-border bg-surface p-1 shadow-[var(--shadow-pop)]">
          {stages.map((s) => {
            const on = s.key === stage
            const st = data?.stages.find((x) => x.key === s.key)
            return (
              <button key={s.key} onClick={() => { onStage(s.key); setOpen(false) }}
                className={`press flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left
                            ${on ? 'bg-brand-soft' : 'hover:bg-muted'}`}>
                <i className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: s.color }} />
                <span className="min-w-0 flex-1">
                  <span className={`block text-[11.5px] ${on ? 'font-semibold text-brand-ink' : 'text-ink'}`}>
                    {s.name}
                  </span>
                  <span className="block text-[9.5px] text-ink-faint">{s.grades} · {st?.points ?? '—'} 点</span>
                </span>
                {on && <Check size={12} className="text-brand-ink" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function ThemeControl({ collapsed }: { collapsed: boolean }) {
  const { mode, accent } = useTheme()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])
  const MODES: { id: Mode; icon: typeof Sun; label: string }[] = [
    { id: 'light', icon: Sun, label: '浅色' },
    { id: 'dark', icon: Moon, label: '深色' },
    { id: 'system', icon: Monitor, label: '系统' },
  ]
  if (collapsed) {
    const Icon = mode === 'dark' ? Sun : Moon
    return (
      <button onClick={() => setMode(mode === 'dark' ? 'light' : 'dark')}
        title={mode === 'dark' ? '切到浅色' : '切到深色'}
        className="icon-btn mx-auto grid h-8 w-8 place-items-center">
        <Icon size={16} />
      </button>
    )
  }
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="press flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-[11.5px]
                   text-ink-faint transition-colors hover:bg-muted hover:text-ink">
        <Palette size={14} />
        <span>外观</span>
        <span className="ml-auto flex items-center gap-1">
          {MODES.map(({ id, icon: Icon }) => mode === id
            ? <Icon key={id} size={12} className="text-ink-soft" />
            : null)}
          <ChevronRight size={12} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
        </span>
      </button>
      {open && (
        <div className="pop absolute bottom-[calc(100%+6px)] left-0 right-0 z-50 rounded-[var(--radius-pop)]
                        border border-border bg-surface p-3 shadow-[var(--shadow-pop)]">
          <div className="mb-1.5 text-[10.5px] font-semibold tracking-wide text-ink-faint">明暗</div>
          <div className="flex gap-1 rounded-lg bg-muted p-0.5">
            {MODES.map(({ id, icon: Icon, label }) => (
              <button key={id} onClick={() => setMode(id)} aria-pressed={mode === id} title={label}
                className={`press flex flex-1 items-center justify-center gap-1 rounded-md py-1.5
                            text-[11px] transition-colors ${mode === id
                              ? 'bg-surface text-ink shadow-[var(--shadow-card)]'
                              : 'text-ink-soft hover:text-ink'}`}>
                <Icon size={12} />{label}
              </button>
            ))}
          </div>
          <div className="mb-1.5 mt-3 text-[10.5px] font-semibold tracking-wide text-ink-faint">强调色</div>
          <div className="grid grid-cols-7 gap-1">
            {ACCENTS.map((a) => {
              const on = accent === a.id
              return (
                <button key={a.id} onClick={() => setAccent(a.id)} title={a.label}
                  aria-label={`强调色：${a.label}`} aria-pressed={on}
                  className={`press grid h-7 place-items-center rounded-md ${on ? 'bg-muted' : 'hover:bg-muted/70'}`}>
                  <span className="grid h-3.5 w-3.5 place-items-center rounded-full"
                    style={{
                      background: a.dot,
                      boxShadow: on ? `0 0 0 2px var(--color-surface), 0 0 0 3.5px ${a.dot}` : 'none',
                    }}>
                    {on && <Check size={8} strokeWidth={3.6} className="text-white" />}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

const SEARCH_HISTORY_KEY = 'amtiku.search.history.v1'

export default function Shell({
  stage, onStage, page, onPage, data, paperCount,
  query, onQuery, onPalette, onPaper, onOpenIngest, onHelp, searchRef, zen, onZen, detailOpen,
  children,
}: {
  stage: Stage
  onStage: (s: Stage) => void
  page: PageKey
  onPage: (p: PageKey) => void
  data: Overview | null
  paperCount: number
  query: string
  onQuery: (v: string) => void
  onPalette: () => void
  onPaper: () => void
  /** 录入：开新标签页，不替换当前页面。 */
  onOpenIngest: () => void
  onHelp: () => void
  searchRef?: React.RefObject<HTMLInputElement | null>
  /** 专注模式：收起侧栏，把宽度让给题目与详情 */
  zen?: boolean
  onZen?: () => void
  /** 详情抽屉打开时，手机底栏让位，避免盖住题目详情 */
  detailOpen?: boolean
  children: React.ReactNode
}) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const saved = localStorage.getItem('amtiku.nav.shut')
      if (saved !== null) return saved === '1'
    } catch { /* ignore */ }
    return typeof window !== 'undefined' && window.innerWidth < 1280
  })
  const shut = (v: boolean) => {
    setCollapsed(v)
    try { localStorage.setItem('amtiku.nav.shut', v ? '1' : '0') } catch { /* ignore */ }
  }

  const [histOpen, setHistOpen] = useState(false)
  const [hist, setHist] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(SEARCH_HISTORY_KEY)
      const v = raw ? JSON.parse(raw) : []
      return Array.isArray(v)
        ? v.filter((x): x is string => typeof x === 'string').slice(0, 8)
        : []
    } catch { return [] }
  })
  const rememberSearch = (v: string) => {
    const s = v.trim()
    if (!s) return
    setHist((cur) => {
      const next = [s, ...cur.filter((x) => x !== s)].slice(0, 8)
      try { localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
  }
  const clearSearchHist = () => {
    setHist([])
    try { localStorage.removeItem(SEARCH_HISTORY_KEY) } catch { /* ignore */ }
  }

  // 新标签页里至少能从标签标题分清「录入」和原工作台。
  useEffect(() => {
    document.title = `${PAGE_META[page].title} · AmMath`
  }, [page])

  const allowed = data?.stages?.map((s) => s.key) || []
  const shownStages = allowed.length ? STAGES.filter((s) => allowed.includes(s.key)) : STAGES
  const stageMeta = STAGE_BY_KEY[stage]
  const activeWs = WORKSPACE_OF[page]
  const title = PAGE_META[page]
  // 专注是「题库」的工作模式，不是全局导航状态：切走时侧栏必须回来。
  const focus = !!zen && page === 'bank'
  const isGlobal = activeWs.key === 'archive'
  const badges: Partial<Record<WorkspaceKey, number>> = {
    bank: data?.bank.total,
    paper: paperCount || undefined,
  }
  const pages = activeWs.pages

  // 录入是独立工作区：没有侧栏、没有全局搜索/顶栏、没有手机底栏。
  // 它有自己的「来源 → 核对 → 入库」顶栏；原工作台在另一个标签页里。
  if (page === 'ingest') {
    return <main id="main-content" className="flex h-full min-h-0 flex-col bg-bg">{children}</main>
  }

  return (
    <div className="relative flex h-full flex-col">
      <a href="#main-content"
        className="sr-only rounded-md bg-surface px-3 py-2 text-[12px] font-medium shadow-[var(--shadow-pop)]
                   focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[80] focus:outline-none
                   focus-visible:ring-2 focus-visible:ring-brand">
        跳到主要内容
      </a>
      <div className="flex min-h-0 flex-1">
        {/* ── 侧栏 ── */}
        <aside className={`app-chrome relative z-30 flex shrink-0 flex-col border-r border-border/70
                           bg-[color-mix(in_srgb,var(--color-surface)_60%,transparent)]
                           backdrop-blur-2xl transition-[width] duration-200
                           ${focus ? 'hidden' : collapsed ? 'w-[64px]' : 'w-[248px]'} max-md:hidden`}>
          <div className={`flex h-[64px] shrink-0 items-center gap-2.5 ${collapsed ? 'justify-center' : 'px-3.5'}`}>
            <button onClick={() => onPage('overview')} title="回到工作台"
              className={`flex min-w-0 items-center gap-2.5 text-left ${collapsed ? '' : 'flex-1'}`}>
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[11px]
                               grad-primary text-[16px] font-bold leading-none text-white
                               shadow-[var(--shadow-brand)]" aria-hidden>A</span>
              {!collapsed && (
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-semibold leading-tight tracking-[-.02em]">AmMath</span>
                  <span className="block truncate text-[10px] leading-tight text-ink-faint">K12 数学工作站</span>
                </span>
              )}
            </button>
            {!collapsed && (
              <button onClick={() => shut(true)} title="收起侧栏" className="icon-btn h-7 w-7">
                <PanelLeftClose size={15} />
              </button>
            )}
          </div>
          {collapsed && (
            <button onClick={() => shut(false)} title="展开侧栏" className="icon-btn mx-auto mb-1 h-8 w-8">
              <PanelLeftOpen size={16} />
            </button>
          )}

          {/* 学段：全局口径，三段切换。收起时竖排。 */}
          {!collapsed ? (
            <div className="px-3 pb-3">
              <div className="mb-1.5 flex items-center justify-between px-0.5">
                <span className="text-[10px] font-semibold tracking-[0.08em] text-ink-faint">当前学段</span>
                <span className="text-[10px] text-ink-faint">{stageMeta.grades}</span>
              </div>
              <div className="flex gap-0.5 rounded-[10px] border border-border bg-bg p-0.5">
                {shownStages.map((s) => {
                  const on = s.key === stage
                  const st = data?.stages.find((x) => x.key === s.key)
                  return (
                    <button key={s.key} onClick={() => onStage(s.key)}
                      title={`${s.name} · ${st?.points ?? '—'} 个知识点`}
                      aria-pressed={on}
                      className={`press flex flex-1 items-center justify-center gap-1 rounded-[8px] py-[5px]
                                  text-[11.5px] transition-colors ${on
                                    ? 'bg-surface font-semibold text-ink shadow-[var(--shadow-card)]'
                                    : 'text-ink-faint hover:text-ink'}`}>
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full"
                        style={{ background: s.color, opacity: on ? 1 : .5 }} />
                      {s.name}
                    </button>
                  )
                })}
              </div>
            </div>
          ) : (
            <div className="mx-auto mb-2 flex w-10 flex-col items-center gap-0.5 rounded-[10px] border
                            border-border bg-bg p-0.5">
              {shownStages.map((s) => (
                <button key={s.key} onClick={() => onStage(s.key)}
                  title={`${s.name} · ${data?.stages.find((x) => x.key === s.key)?.points ?? ''} 点`}
                  aria-label={`切换到${s.name}`}
                  className={`grid h-8 w-8 place-items-center rounded-[7px] text-[10.5px] font-semibold
                    transition-colors ${s.key === stage
                      ? 'bg-surface text-brand-ink shadow-[var(--shadow-card)]'
                      : 'text-ink-faint hover:bg-surface hover:text-ink'}`}>
                  {s.short}
                </button>
              ))}
            </div>
          )}

          <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-2" aria-label="主导航">
            {WORKSPACE_GROUPS.map((g, gi) => (
              <div key={g.label} className={gi ? 'mt-4' : ''}>
                {!collapsed && (
                  <div className="px-2 pb-1 text-[10px] font-semibold tracking-[0.08em] text-ink-faint">
                    {g.label}
                  </div>
                )}
                {collapsed && gi > 0 && <div className="mx-auto my-2 h-px w-7 bg-border" />}
                <div className="space-y-0.5">
                  {g.keys.map((key) => {
                    const item = WORKSPACES.find((x) => x.key === key)!
                    return (
                      <NavRow key={key} item={item} active={activeWs.key === key}
                        collapsed={collapsed} badge={badges[key]}
                        onClick={() => {
                          if (item.newTab) {
                            onOpenIngest()
                            return
                          }
                          onPage(activeWs.key === key ? page : item.pages[0])
                        }} />
                    )
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* 当前卷子 + 外观 */}
          <div className="shrink-0 border-t border-border p-2">
            {!collapsed ? (
              <button onClick={onPaper}
                className="press mb-1.5 flex w-full items-center gap-2 rounded-lg border border-border
                           bg-bg/60 px-2.5 py-2 text-left transition-colors hover:border-brand-line hover:bg-brand-soft/40">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-brand-soft text-brand">
                  <FileText size={14} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[11.5px] font-medium text-ink">当前卷子</span>
                  <span className="tnum block text-[10.5px] text-ink-faint">
                    {paperCount ? `${paperCount} 道 · 继续编排` : '还没有题 · 去题库挑'}
                  </span>
                </span>
                <ChevronRight size={13} className="shrink-0 text-ink-faint" />
              </button>
            ) : (
              <button onClick={onPaper} title="当前卷子"
                className="relative mx-auto mb-1 grid h-8 w-8 place-items-center rounded-lg text-ink-faint hover:bg-muted">
                <FileText size={16} />
                {paperCount > 0 && (
                  <span className="tnum absolute -right-0.5 -top-0.5 rounded-full bg-brand px-1
                                   text-[9px] font-semibold leading-[14px] text-white">
                    {paperCount > 99 ? '99+' : paperCount}
                  </span>
                )}
              </button>
            )}
            <ThemeControl collapsed={collapsed} />
            {!collapsed && (
              <button onClick={onHelp}
                className="mt-0.5 flex w-full items-center gap-2 rounded-lg px-2 py-1.5
                           text-[11.5px] text-ink-faint hover:bg-muted hover:text-ink">
                <CircleHelp size={14} />快捷键与帮助
                <kbd className="ml-auto rounded border border-border bg-surface-2 px-1
                                text-[9.5px] leading-[15px]">?</kbd>
              </button>
            )}
          </div>
        </aside>

        {/* ── 右半：顶栏 + 内容 ── */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="app-chrome app-chrome-top relative z-20 flex h-[60px] shrink-0 items-center gap-2
                             border-b border-border/70 bg-[color-mix(in_srgb,var(--color-surface)_42%,transparent)]
                             px-3 backdrop-blur-2xl md:gap-4 md:px-5">
            <div className="flex min-w-0 items-center gap-2.5 xl:w-[248px]">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-[8px] grad-primary
                               text-[13px] font-bold leading-none text-white md:hidden"
                aria-hidden>A</span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="truncate text-[16px] font-semibold tracking-[-.02em] md:text-[17px]">
                    {title.title}
                  </h1>
                  {isGlobal ? (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded-[5px] border
                                     border-border bg-bg px-1.5 py-[1px] text-[10px] text-ink-soft">
                      <i className="h-1.5 w-1.5 rounded-full bg-ink-faint" />全学段
                    </span>
                  ) : (
                    <StageMenu stage={stage} stages={shownStages} data={data} onStage={onStage} />
                  )}
                </div>
                <div className="hidden truncate text-[10.5px] text-ink-faint lg:block">{title.desc}</div>
              </div>
            </div>

            <div className="relative min-w-0 flex-1 md:max-w-[520px]">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
              <input
                ref={searchRef}
                value={query}
                onChange={(e) => onQuery(e.target.value)}
                onFocus={() => setHistOpen(true)}
                onBlur={() => {
                  window.setTimeout(() => setHistOpen(false), 140)
                  if (query.trim()) rememberSearch(query)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                    rememberSearch(query); setHistOpen(false)
                    ;(e.currentTarget as HTMLInputElement).blur()
                  } else if (e.key === 'Escape') {
                    onQuery(''); setHistOpen(false)
                  }
                }}
                aria-label="搜索题库"
                placeholder="搜索题目、考点、出处…"
                title="公式：cosB、3/4、x^2；字段：考点:三角 年份:2024 类型:多选 难度:中档 出处:…；-词 排除"
                className="h-10 w-full rounded-full border border-border/80 bg-surface-2/60 pl-10 pr-16
                           text-[12.5px] text-ink outline-none backdrop-blur-xl transition-all
                           placeholder:text-ink-faint focus:border-brand-line focus:bg-surface
                           focus:ring-4 focus:ring-brand-soft/50"
              />
              {query ? (
                <button onClick={() => onQuery('')} title="清空"
                  className="icon-btn absolute right-1.5 top-1/2 h-6 w-6 -translate-y-1/2">
                  <X size={13} />
                </button>
              ) : (
                <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2
                                rounded border border-border bg-surface px-1.5 text-[10px]
                                leading-[17px] text-ink-faint sm:block">/</kbd>
              )}
              {histOpen && hist.length > 0 && (
                <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-50 overflow-hidden
                                rounded-[var(--radius-card)] border border-border bg-surface py-1
                                shadow-[var(--shadow-pop)]">
                  <div className="flex items-center px-3 py-1.5 text-[10.5px] text-ink-faint">
                    <span>最近搜索</span>
                    <button onMouseDown={(e) => e.preventDefault()} onClick={clearSearchHist}
                      className="ml-auto text-ink-faint transition-colors hover:text-ink">清空</button>
                  </div>
                  {hist.map((h) => (
                    <button key={h} onMouseDown={(e) => e.preventDefault()}
                      onClick={() => { onQuery(h); rememberSearch(h); setHistOpen(false) }}
                      className="block w-full truncate px-3 py-1.5 text-left text-[12px] text-ink-soft
                                 transition-colors hover:bg-brand-soft/50 hover:text-brand-ink">
                      {h}
                    </button>
                  ))}
                  <div className="mt-1 border-t border-border/60 px-3 py-1.5 text-[10.5px]
                                  leading-relaxed text-ink-faint">
                    语法：考点:三角 · 年份:2024 · 类型:多选 · 难度:中档 · -词 排除
                  </div>
                </div>
              )}
            </div>

            <div className="ml-auto flex shrink-0 items-center gap-1.5">
              {focus && onZen && (
                <button onClick={onZen} title="退出专注模式（Z）"
                  className="press flex h-8 items-center gap-1.5 rounded-[8px] border
                             border-brand-line bg-brand-soft px-2.5 text-[11.5px] font-medium
                             text-brand-ink">
                  <PanelLeftOpen size={13} />
                  <span className="hidden sm:inline">退出专注</span>
                </button>
              )}
              <button onClick={onHelp} title="快捷键与帮助"
                className="icon-btn mobile-hide hidden h-8 w-8 border border-border md:inline-flex">
                <CircleHelp size={15} />
              </button>
              <button onClick={onPalette} title="命令面板（⌘K）"
                className="icon-btn mobile-hide hidden h-8 w-8 border border-border sm:inline-flex">
                <CommandIcon size={14} />
              </button>
              {paperCount > 0 && (
                <button onClick={onPaper}
                  className="press b-btn grad-primary mobile-hide h-8 rounded-[10px] px-3 text-[12px] text-white">
                  继续组卷
                  <span className="tnum rounded bg-white/15 px-1 text-[10px] leading-[16px]">{paperCount}</span>
                  <ArrowRight size={12} />
                </button>
              )}
            </div>
          </header>

          {/* 同组页面用二级标签切换；不占侧栏，也不新增一层弹窗。 */}
          {pages.length > 1 && (
            <div className="flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b border-border
                            bg-surface px-3 md:px-5" role="tablist" aria-label={`${activeWs.label}子页面`}>
              {activeWs.label !== PAGE_META[pages[0]].title && (
                <span className="mr-2 hidden text-[10px] font-semibold tracking-[0.08em] text-ink-faint sm:inline">
                  {activeWs.label}
                </span>
              )}
              {pages.map((p) => {
                const on = p === page
                return (
                  <button key={p} role="tab" aria-selected={on}
                    onClick={() => onPage(p)}
                    className={`press relative flex h-10 shrink-0 items-center px-2 text-[12px]
                                transition-colors ${on
                                  ? 'font-semibold text-ink'
                                  : 'text-ink-faint hover:text-ink'}`}>
                    {PAGE_META[p].title}
                    {on && <span className="absolute inset-x-2 bottom-0 h-[2px] rounded-t bg-brand" />}
                  </button>
                )
              })}
            </div>
          )}

          <main id="main-content" className="min-h-0 flex-1 overflow-hidden max-md:pb-[calc(56px+env(safe-area-inset-bottom))]">
            <div key={page} className="anim-fade-in h-full">
              {children}
            </div>
          </main>
        </div>
      </div>

      {/* 手机底栏：五个最高频入口；其余走「更多」命令面板。 */}
      {!detailOpen && <nav aria-label="手机导航"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
        className="app-chrome fixed inset-x-0 bottom-0 z-40 flex h-[56px] items-stretch border-t
                   border-border/70 bg-[color-mix(in_srgb,var(--color-surface)_88%,transparent)]
                   px-2 backdrop-blur-2xl md:hidden">
        {([
          { key: 'overview', label: '工作台', icon: LayoutDashboard },
          { key: 'bank', label: '题库', icon: LibraryBig },
          { key: 'paper', label: '组卷', icon: FileStack },
          { key: 'map', label: '内容', icon: BookOpenText },
        ] as { key: PageKey; label: string; icon: typeof LayoutDashboard }[]).map(({ key, label, icon: Icon }) => {
          const on = activeWs.key === WORKSPACE_OF[key].key
          return (
            <button key={key}
              onClick={() => onPage(activeWs.key === WORKSPACE_OF[key].key ? page : key)}
              aria-current={on ? 'page' : undefined}
              className={`relative flex flex-1 flex-col items-center justify-center gap-0.5
                          text-[9.5px] font-medium transition-colors ${on ? 'text-brand-ink' : 'text-ink-faint'}`}>
              <Icon size={18} strokeWidth={on ? 2.2 : 1.8} />
              {label}
              {on && <span className="absolute bottom-1 h-1 w-1 rounded-full bg-brand" />}
            </button>
          )
        })}
        <button onClick={onPalette} aria-label="更多页面（命令面板）"
          className={`relative flex flex-1 flex-col items-center justify-center gap-0.5
                     text-[9.5px] font-medium transition-colors ${
                       ['quality', 'archive', 'ingest'].includes(activeWs.key)
                         ? 'text-brand-ink' : 'text-ink-faint hover:text-ink'}`}>
          <CommandIcon size={18} strokeWidth={['quality', 'archive', 'ingest'].includes(activeWs.key) ? 2.2 : 1.8} />
          更多
          {['quality', 'archive', 'ingest'].includes(activeWs.key) && (
            <span className="absolute bottom-1 h-1 w-1 rounded-full bg-brand" />
          )}
        </button>
      </nav>}
    </div>
  )
}
