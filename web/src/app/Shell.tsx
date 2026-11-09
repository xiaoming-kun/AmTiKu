/** 应用外壳：学段切换 + 侧栏 + 顶栏。
 *
 *  交互上的三条硬约定：
 *  ① **学段是全局视角**，不是页面里的一个筛选项。切换后停留在当前工具
 *     （在知识图谱就换图谱的学段，在题库就换题库的学段），不把人弹回首页。
 *  ② 侧栏只放「去哪个工作区」，不放具体动作；动作在页面里、在顶栏右侧。
 *     旧版把录入、导出、主题、范围全塞进侧栏，一列 11 项，扫不清。
 *  ③ 顶栏搜索是**全局入口**：在任何页面输入都直接进题库/诊断题库并带上关键词，
 *     不需要先切到题库页。
 */
import { useEffect, useRef, useState } from 'react'
import {
  Activity, BookOpenText, ChevronRight, CircleHelp, ClipboardCheck, Command as CommandIcon,
  FilePlus2, FileStack, FileText, FolderOpen, History, LayoutDashboard,
  LibraryBig, Minimize2, Monitor, Moon, Network, PanelLeftClose, PanelLeftOpen,
  Plus, Search, Sun, Trash2, X,
} from 'lucide-react'
import type { Overview } from '@/lib/types'
import { ACCENTS, setAccent, setMode, useTheme, type Mode } from '@/lib/theme'
import { STAGES, STAGE_BY_KEY, type Stage } from '@/lib/stage'

export type PageKey =
  | 'overview' | 'map' | 'lectures' | 'bank' | 'ingest' | 'paper'
  | 'papers' | 'health' | 'review' | 'trash' | 'changes'

type NavItem = {
  key: PageKey
  label: string
  desc: string
  icon: React.ComponentType<{ size?: number | string; strokeWidth?: number; className?: string }>
  badge?: number
}

export const PAGE_META: Record<PageKey, { title: string; desc: string }> = {
  overview: { title: '总览', desc: '学段进度、待办与最近动作' },
  map: { title: '知识图谱', desc: '教材顺序、先修关系与诊断入口' },
  lectures: { title: '讲义', desc: '一个知识点一份：讲、错、练' },
  bank: { title: '题库', desc: '找题、挑题、加入卷子' },
  ingest: { title: '录题', desc: '粘贴 LaTeX 或让 AI 读整份资料' },
  paper: { title: '组卷', desc: '当前卷子、智能组卷与导出' },
  papers: { title: '试卷库', desc: '出过的卷子与合集，可原样重现' },
  health: { title: '题库体检', desc: '覆盖、缺口与待补队列' },
  review: { title: '审阅', desc: '风险队列、分层抽样与复核账本' },
  trash: { title: '回收站', desc: '删除的题都在这里，可恢复' },
  changes: { title: '变更记录', desc: '每次批量改动的账本' },
}

function NavRow({ item, active, collapsed, onClick }: {
  item: NavItem; active: boolean; collapsed: boolean; onClick: () => void
}) {
  const Icon = item.icon
  return (
    <button
      onClick={onClick}
      title={collapsed ? `${item.label} · ${item.desc}` : item.desc}
      data-on={active ? '1' : '0'}
      className={`b-nav ${collapsed ? 'justify-center px-0' : ''} ${active ? 'b-nav-on' : ''}`}
    >
      <Icon size={collapsed ? 18 : 16} strokeWidth={active ? 2.2 : 1.8}
        className={`shrink-0 ${active ? 'text-brand' : 'text-ink-faint'}`} />
      {!collapsed && (
        <>
          <span className="min-w-0 flex-1 truncate text-left">{item.label}</span>
          {!!item.badge && (
            <span className={`tnum shrink-0 rounded-full px-1.5 text-[10.5px] leading-[17px]
              ${active ? 'bg-brand-soft text-brand-ink' : 'bg-muted text-ink-faint'}`}>
              {item.badge > 9999 ? `${Math.floor(item.badge / 1000)}k` : item.badge}
            </span>
          )}
        </>
      )}
      {collapsed && !!item.badge && (
        <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-brand" />
      )}
    </button>
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
    { id: 'system', icon: Monitor, label: '跟随系统' },
  ]
  if (collapsed) {
    const dark = mode === 'dark'
    const Icon = dark ? Sun : Moon
    return (
      <button onClick={() => setMode(dark ? 'light' : 'dark')}
        title={dark ? '切到浅色' : '切到深色'} className="b-nav justify-center px-0">
        <Icon size={17} />
      </button>
    )
  }
  return (
    <div ref={box} className="relative">
      <div className="flex items-center gap-1">
        <div className="flex flex-1 gap-0.5 rounded-[8px] bg-muted p-0.5">
          {MODES.map(({ id, icon: Icon, label }) => (
            <button key={id} onClick={() => setMode(id)} title={label}
              aria-pressed={mode === id}
              className={`grid h-7 flex-1 place-items-center rounded-[6px] transition-colors
                ${mode === id ? 'bg-surface text-ink shadow-[var(--shadow-card)]' : 'text-ink-faint hover:text-ink'}`}>
              <Icon size={13} />
            </button>
          ))}
        </div>
        <button onClick={() => setOpen((v) => !v)} title="强调色"
          className="grid h-8 w-8 place-items-center rounded-[8px] border border-border bg-surface">
          <span className="h-3.5 w-3.5 rounded-full"
            style={{ background: ACCENTS.find((a) => a.id === accent)?.dot || '#2563eb' }} />
        </button>
      </div>
      {open && (
        <div className="pop absolute bottom-[calc(100%+8px)] right-0 z-50 w-[168px]
                        rounded-xl border border-border bg-surface p-2 shadow-[var(--shadow-pop)]">
          <div className="px-1 pb-1.5 text-[10.5px] font-semibold tracking-wide text-ink-faint">
            强调色
          </div>
          <div className="grid grid-cols-6 gap-1">
            {ACCENTS.map((a) => (
              <button key={a.id} onClick={() => setAccent(a.id)} title={a.label}
                className={`grid h-6 place-items-center rounded-md ${a.id === accent ? 'bg-muted' : 'hover:bg-muted'}`}>
                <span className="h-3 w-3 rounded-full" style={{
                  background: a.dot,
                  boxShadow: a.id === accent ? `0 0 0 2px var(--color-surface), 0 0 0 3.5px ${a.dot}` : 'none',
                }} />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Shell({
  stage, onStage, page, onPage, data, paperCount,
  query, onQuery, onPalette, onPaper, onIngest, onHelp, searchRef, zen, onZen, detailOpen,
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
  onIngest: () => void
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
    // 1280 以下默认收起：三栏（侧栏 + 列表 + 详情）会把题目栏挤到
    // 只剩 400px，卡片元信息整行换行。先让内容有呼吸，用户仍可展开。
    return typeof window !== 'undefined' && window.innerWidth < 1280
  })
  const shut = (v: boolean) => {
    setCollapsed(v)
    try { localStorage.setItem('amtiku.nav.shut', v ? '1' : '0') } catch { /* ignore */ }
  }

  const count = data?.stages.find((s) => s.key === stage)
  // 单学段交付包（只带一个学段的知识地图）里，overview.stages 只有那一个；
  // 其余学段按钮不该出现——客户看到三个空学段会以为包坏了。
  const allowed = data?.stages?.map((s) => s.key) || []
  const shownStages = allowed.length ? STAGES.filter((s) => allowed.includes(s.key)) : STAGES
  const nav: { label: string; items: NavItem[] }[] = [
    { label: '教学', items: [
      { key: 'overview', label: '总览', desc: '进度与待办', icon: LayoutDashboard },
      { key: 'map', label: '知识图谱', desc: '教材顺序与先修', icon: Network, badge: count?.points },
      { key: 'lectures', label: '讲义', desc: stage === 'senior' ? '讲、错、练' : '讲、错、结', icon: BookOpenText, badge: data?.lectures.total },
      { key: 'bank', label: '题库', desc: '找题与挑题', icon: LibraryBig, badge: data?.bank.total },
    ] },
    { label: '生产', items: [
      { key: 'ingest', label: '录题', desc: 'LaTeX / AI 读资料', icon: FilePlus2 },
      { key: 'paper', label: '组卷', desc: '组卷与导出', icon: FileStack, badge: paperCount || undefined },
    ] },
    { label: '管理', items: [
      { key: 'papers', label: '试卷库', desc: '存档与合集', icon: FolderOpen, badge: data?.papers.total },
      { key: 'health', label: '题库体检', desc: '覆盖与缺口', icon: Activity },
      { key: 'review', label: '审阅', desc: '风险队列与抽样', icon: ClipboardCheck },
      { key: 'trash', label: '回收站', desc: '可恢复', icon: Trash2 },
      { key: 'changes', label: '变更记录', desc: '批量改动账本', icon: History },
    ] },
  ]

  const title = PAGE_META[page]
  const pageDesc = page === 'lectures' && stage !== 'senior'
    ? '一个章节一份：讲 · 错 · 结' : title.desc
  const stageMeta = STAGE_BY_KEY[stage]
  // 专注是「题库」的工作模式，不是全局导航状态：切到总览/图谱/组卷时
  // 侧栏必须回来，否则用户会像刚才一样找不到导航（而且总览页没有专注入口）。
  const focus = !!zen && page === 'bank'
  // 试卷库 / 回收站 / 变更记录是**全学段共用**的，不该挂当前学段徽章。
  const globalPage = page === 'papers' || page === 'trash' || page === 'changes'

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        {/* ── 侧栏 ── */}
        <aside className={`app-chrome relative z-30 flex shrink-0 flex-col border-r border-border/70
                           bg-[color-mix(in_srgb,var(--color-surface)_60%,transparent)]
                           backdrop-blur-2xl transition-[width] duration-200
                           ${focus ? 'hidden' : collapsed ? 'w-[64px]' : 'w-[248px]'} max-md:hidden`}>
          <div className={`flex h-[60px] shrink-0 items-center gap-2.5 ${collapsed ? 'justify-center' : 'px-4'}`}>
            <span className="relative grid h-9 w-9 shrink-0 place-items-center rounded-[11px]
                             grad-primary text-[10px] font-bold tracking-tight text-white
                             shadow-[var(--shadow-brand)]">
              K12
              <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-[#22d3ee]
                               shadow-[0_0_10px_#22d3ee]" />
            </span>
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13.5px] font-semibold leading-tight">K12 数学题库</div>
                <div className="truncate text-[10.5px] leading-tight text-ink-faint">AmTiKu · 学段工作台</div>
              </div>
            )}
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

          {/* 学段切换：整个软件的口径 */}
          {!collapsed ? (
            <div className="glass-2 mx-3 mb-3 rounded-2xl p-1.5">
              <div className="px-1 pb-1 text-[10px] font-semibold tracking-[0.08em] text-ink-faint">
                当前学段
              </div>
              {shownStages.map((s) => {
                const on = s.key === stage
                const st = data?.stages.find((x) => x.key === s.key)
                return (
                  <button key={s.key} onClick={() => onStage(s.key)}
                    className={`relative flex w-full items-center gap-2 overflow-hidden rounded-xl px-2 py-[8px]
                      text-left transition-all ${on
                        ? 'bg-brand-soft ring-1 ring-brand-line shadow-[var(--shadow-card)]'
                        : 'hover:bg-muted'}`}>
                    <span className="relative h-2 w-2 shrink-0 rounded-full"
                      style={{ background: s.color }} />
                    <span className={`text-[12.5px] ${on ? 'font-semibold text-ink' : 'text-ink-soft'}`}>
                      {s.name}
                    </span>
                    <span className="tnum ml-auto text-[10px] text-ink-faint">
                      {st ? `${st.points} 点` : s.grades}
                    </span>
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="glass-2 mx-auto mb-2 flex w-10 flex-col items-center gap-0.5 rounded-xl border
                            border-border/70 bg-surface-2/60 p-0.5">
              {shownStages.map((s) => (
                <button key={s.key} onClick={() => onStage(s.key)}
                  title={`${s.name} · ${data?.stages.find((x) => x.key === s.key)?.points ?? s.grades} 点`}
                  aria-label={`切换到${s.name}`}
                  className={`relative grid h-8 w-8 place-items-center rounded-[9px] text-[10.5px] font-semibold
                    transition-colors ${s.key === stage
                      ? 'bg-brand-soft text-brand-ink ring-1 ring-brand-line'
                      : 'text-ink-faint hover:bg-muted hover:text-ink'}`}>
                  {s.short}
                  <span className="absolute right-1 top-1 h-1 w-1 rounded-full"
                    style={{ background: s.color }} />
                </button>
              ))}
            </div>
          )}

          <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {nav.map((g, gi) => (
              <div key={g.label} className={gi ? 'mt-4' : ''}>
                {!collapsed && (
                  <div className="px-2 pb-1 text-[10px] font-semibold tracking-[0.08em] text-ink-faint">
                    {g.label}
                  </div>
                )}
                <div className="space-y-0.5">
                  {g.items.map((it) => (
                    <NavRow key={it.key} item={it} active={page === it.key}
                      collapsed={collapsed} onClick={() => onPage(it.key)} />
                  ))}
                </div>
              </div>
            ))}
          </nav>

          {/* 当前卷子 + 外观 */}
          <div className="shrink-0 border-t border-border p-2.5">
            {!collapsed ? (
              <button onClick={onPaper}
                className="glass-2 mb-2 flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left
                           transition-colors hover:border-brand-line hover:bg-brand-soft/30">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
                  <FileText size={14} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[11.5px] font-medium text-ink">当前卷子</span>
                  <span className="tnum block text-[10.5px] text-ink-faint">
                    {paperCount ? `${paperCount} 道 · 去组卷` : '还没有题'}
                  </span>
                </span>
                <ChevronRight size={13} className="shrink-0 text-ink-faint" />
              </button>
            ) : (
              <button onClick={onPaper} title="当前卷子"
                className="relative mx-auto mb-2 grid h-8 w-8 place-items-center rounded-lg text-ink-faint hover:bg-muted">
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
                className="mt-1.5 flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5
                           text-[11px] text-ink-faint hover:bg-muted hover:text-ink">
                <CircleHelp size={13} />快捷键与帮助
                <kbd className="ml-auto rounded border border-border bg-surface-2 px-1
                                text-[9.5px] leading-[15px]">?</kbd>
              </button>
            )}
          </div>
        </aside>

        {/* ── 右半：顶栏 + 内容 ── */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="app-chrome app-chrome-top relative z-20 flex h-[64px] shrink-0 items-center gap-2
                             border-b border-border/70 px-3 md:gap-3 md:px-6 bg-[color-mix(in_srgb,var(--color-surface)_42%,transparent)]
                             backdrop-blur-2xl">
            <div className="flex min-w-0 items-center gap-2.5 xl:min-w-[250px]">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="truncate text-[15px] font-semibold tracking-tight sm:text-[17px]">{title.title}</h1>
                  {globalPage ? (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded-full border
                                     border-border bg-surface-2 px-1.5 py-[1px] text-[10.5px] text-ink-soft">
                      <i className="h-1.5 w-1.5 rounded-full bg-ink-faint" />
                      全局
                    </span>
                  ) : (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded-full border
                                     border-border bg-surface-2 px-1.5 py-[1px] text-[10.5px] text-ink-soft">
                      <i className="h-1.5 w-1.5 rounded-full" style={{ background: stageMeta.color }} />
                      {stageMeta.name}
                    </span>
                  )}
                </div>
                <div className="hidden truncate text-[10.5px] text-ink-faint sm:block">{pageDesc}</div>
              </div>
            </div>

            <div className="relative mx-auto min-w-0 flex-1 max-w-[560px]">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
              <input
                ref={searchRef}
                value={query}
                onChange={(e) => onQuery(e.target.value)}
                placeholder="搜索题目、答案、考点、出处、公式…"
                title="公式可以直接写：cosB、cosB=3/4、3/4、x^2"
                className="h-10 w-full rounded-full border border-border/80 bg-surface-2/60 pl-10 pr-16
                           text-[12.5px] text-ink outline-none backdrop-blur-xl transition-all
                           placeholder:text-ink-faint focus:border-brand-line focus:bg-surface
                           focus:ring-4 focus:ring-brand-soft/50"
              />
              {query ? (
                <button onClick={() => onQuery('')} title="清空"
                  className="icon-btn absolute right-2 top-1/2 h-6 w-6 -translate-y-1/2">
                  <X size={13} />
                </button>
              ) : (
                <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2
                                rounded border border-border bg-surface px-1.5 text-[10px]
                                leading-[17px] text-ink-faint sm:block">/</kbd>
              )}
            </div>

            <div className="ml-auto flex shrink-0 items-center gap-1.5">
              {focus && onZen && (
                <button onClick={onZen} title="退出专注模式（Z）"
                  className="press flex h-8 items-center gap-1.5 rounded-[10px] border
                             border-brand-line bg-brand-soft px-2.5 text-[12px] font-medium
                             text-brand-ink">
                  <Minimize2 size={13} />
                  <span className="hidden sm:inline">退出专注</span>
                </button>
              )}
              <button onClick={onPalette} title="命令面板（⌘K）"
                className="icon-btn mobile-hide hidden h-8 w-8 border border-border sm:inline-flex">
                <CommandIcon size={14} />
              </button>
              <button onClick={onPaper}
                className="press hidden h-8 items-center gap-1.5 rounded-[10px] border border-border sm:flex
                           bg-surface px-2.5 text-[12px] text-ink-soft hover:border-border-strong">
                <FileText size={13} />
                <span className="tnum hidden sm:inline">{paperCount}</span>
                <span className="hidden md:inline">卷子</span>
              </button>
              <button onClick={onIngest}
                aria-label="录题" title="录题"
                className="b-btn grad-primary h-9 rounded-full px-3 text-[12px] text-white sm:px-4
                           shadow-[var(--shadow-brand)] hover:brightness-110">
                <Plus size={14} /><span className="hidden sm:inline">录题</span>
              </button>
            </div>
          </header>

          <main className="min-h-0 flex-1 overflow-hidden max-md:pb-[calc(58px+env(safe-area-inset-bottom))]">
            <div key={page} className="anim-fade-up h-full">
              {children}
            </div>
          </main>
        </div>
      </div>

      {/* 手机底栏：侧栏在 <md 隐藏，导航不能跟着消失。
          五个入口覆盖最常用的「看总览 / 找题 / 组卷 / 录题」，更多走命令面板。 */}
      {!detailOpen && <nav aria-label="手机导航"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
        className="app-chrome fixed inset-x-0 bottom-0 z-40 flex h-[58px] items-stretch border-t
                   border-border/70 bg-[color-mix(in_srgb,var(--color-surface)_88%,transparent)]
                   px-2 backdrop-blur-2xl md:hidden">
        {([
          { key: 'overview', label: '总览', icon: LayoutDashboard },
          { key: 'bank', label: '题库', icon: LibraryBig },
          { key: 'paper', label: '组卷', icon: FileStack },
          { key: 'ingest', label: '录题', icon: FilePlus2 },
        ] as { key: PageKey; label: string; icon: typeof LayoutDashboard }[]).map(({ key, label, icon: Icon }) => {
          const on = page === key
          return (
            <button key={key} onClick={() => onPage(key)}
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
                       !['overview', 'bank', 'paper', 'ingest'].includes(page)
                         ? 'text-brand-ink' : 'text-ink-faint hover:text-ink'}`}>
          <CommandIcon size={18} strokeWidth={!['overview', 'bank', 'paper', 'ingest'].includes(page) ? 2.2 : 1.8} />
          更多
          {!['overview', 'bank', 'paper', 'ingest'].includes(page) && (
            <span className="absolute bottom-1 h-1 w-1 rounded-full bg-brand" />
          )}
        </button>
      </nav>}
    </div>
  )
}
