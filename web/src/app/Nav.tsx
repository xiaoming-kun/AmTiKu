/** 全局导航栏（最左那条）。
 *
 *  为什么要有它：旧界面把「找题 / 组卷 / 录题 / 统计 / 回收站」全塞进
 *  主区顶上一行标签，于是**主区的第一行永远在解释自己在哪**，
 *  而且标签一多就换行。搬到左侧以后，主区从第一像素开始就是内容。
 *
 *  三条设计约定：
 *  ① 分组只分两组：**工作流**（往里进数据）和**组卷输出**（往外出成品）。
 *     这两组之间才是真正的分界，其余都是同组内的并列项。
 *  ② 每项右边挂一个**单键快捷键**（和设计文档 §键盘优先 对齐）。
 *     单键只在不在输入框里时生效，见 App.tsx 的 keydown 处理。
 *  ③ 可以收成图标条（60px）。收起来时靠 `title` 兜底，不靠猜。
 */
import { useEffect } from 'react'
import {
  LayoutGrid, ScanLine, FolderTree, Sparkles,
  ClipboardList, Trash2, History,
  PanelLeftClose, PanelLeft, Check,
} from 'lucide-react'

export type NavKey =
  | 'workbench' | 'ingest' | 'points'
  | 'export' | 'paper' | 'trash' | 'changes'

type Item = {
  key: NavKey
  label: string
  hint: string          // 单键快捷键
  icon: React.ComponentType<{ size?: number | string; strokeWidth?: number; className?: string }>
  /** 收成图标条时 title 里补一句，说明这项是干什么的 */
  desc: string
}

export const NAV_GROUPS: { label: string; items: Item[] }[] = [
  {
    label: '工作流',
    items: [
      { key: 'workbench', label: '工作台', hint: 'W', icon: LayoutGrid, desc: '找题、挑题、组卷' },
      { key: 'ingest', label: '录题', hint: 'I', icon: ScanLine, desc: '把 LaTeX 粘进来入库' },
      { key: 'points', label: '知识点', hint: 'K', icon: FolderTree, desc: '按章节考点筛题' },
    ],
  },
  {
    label: '组卷输出',
    items: [
      { key: 'export', label: '智能组卷', hint: 'B', icon: Sparkles, desc: '随机组卷、考点覆盖卷、导出 PDF' },
      { key: 'paper', label: '试卷管理', hint: 'P', icon: ClipboardList, desc: '当前卷子与已存试卷' },
      { key: 'trash', label: '回收站', hint: 'R', icon: Trash2, desc: '删除的题都在这儿，可恢复' },
      { key: 'changes', label: '变更记录', hint: 'C', icon: History, desc: '每次批量改动的账本' },
    ],
  },
]

/** 快捷键 → 导航项。App.tsx 单键监听用这张表。 */
export const NAV_BY_HINT: Record<string, NavKey> = Object.fromEntries(
  NAV_GROUPS.flatMap((g) => g.items.map((i) => [i.hint.toLowerCase(), i.key])),
)

const W_OPEN = 208
const W_SHUT = 60

export default function Nav({
  active, onPick, collapsed, onCollapsed, kind, onKind, kinds, total, pointsCovered, pointsTotal,
}: {
  active: NavKey
  onPick: (k: NavKey) => void
  collapsed: boolean
  onCollapsed: (v: boolean) => void
  kind: string
  onKind: (k: string) => void
  kinds: { value: string; n: number }[]
  total: number
  pointsCovered: number
  pointsTotal: number
}) {
  // 记忆折叠状态：老师习惯固定一种宽度，不要每次打开都变
  useEffect(() => {
    const v = localStorage.getItem('amtiku.nav.collapsed')
    if (v === '1') onCollapsed(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const set = (v: boolean) => { onCollapsed(v); localStorage.setItem('amtiku.nav.collapsed', v ? '1' : '0') }

  return (
    <aside
      style={{ width: collapsed ? W_SHUT : W_OPEN }}
      className="relative z-20 flex shrink-0 flex-col border-r border-border bg-surface
                 transition-[width] duration-200 ease-[cubic-bezier(.22,.61,.36,1)]"
    >
      {/* ── 品牌 ── */}
      <div className={`flex h-[56px] shrink-0 items-center gap-2.5 border-b border-border
                       ${collapsed ? 'justify-center px-0' : 'px-3.5'}`}>
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[9px]
                         bg-gradient-to-br from-brand to-brand-deep text-[15px] font-bold
                         text-white shadow-[var(--shadow-brand)]">
          A
        </span>
        {!collapsed && (
          <div className="anim-fade-in min-w-0 flex-1">
            <div className="truncate text-[13.5px] font-semibold leading-tight tracking-tight">AmTiKu</div>
            <div className="truncate text-[11px] leading-tight text-ink-faint">高中数学题库与组卷</div>
          </div>
        )}
        {!collapsed && (
          <button onClick={() => set(true)} title="收起导航栏"
            className="icon-btn h-6 w-6 shrink-0">
            <PanelLeftClose size={15} />
          </button>
        )}
      </div>

      {collapsed && (
        <button onClick={() => set(false)} title="展开导航栏"
          className="icon-btn mx-auto mt-2 h-8 w-8">
          <PanelLeft size={16} />
        </button>
      )}

      {/* ── 分组导航 ── */}
      <nav className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-2 py-2">
        {NAV_GROUPS.map((g, gi) => (
          <div key={g.label} className={gi ? 'mt-4' : ''}>
            {!collapsed ? (
              <div className="px-2 pb-1 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint">
                {g.label}
              </div>
            ) : (
              gi > 0 && <div className="mx-2 mb-2 border-t border-border" />
            )}
            <div className="space-y-[2px]">
              {g.items.map((it) => {
                const on = active === it.key
                const Icon = it.icon
                return (
                  <button
                    key={it.key}
                    data-on={on ? '1' : '0'}
                    onClick={() => onPick(it.key)}
                    title={collapsed ? `${it.label} · ${it.desc}` : it.desc}
                    className={`nav-item press group flex w-full items-center gap-2.5 rounded-lg
                                ${collapsed ? 'h-10 justify-center px-0' : 'px-2.5 py-[7px]'}
                                ${on ? 'bg-brand-soft text-brand-ink'
                                     : 'text-ink-soft hover:bg-muted hover:text-ink'}`}
                  >
                    <Icon size={collapsed ? 18 : 16} strokeWidth={on ? 2.2 : 1.9}
                      className={`shrink-0 ${on ? 'text-brand' : 'text-ink-faint group-hover:text-ink-soft'}`} />
                    {!collapsed && (
                      <>
                        <span className={`min-w-0 flex-1 truncate text-left text-[13px]
                                          ${on ? 'font-semibold' : 'font-medium'}`}>{it.label}</span>
                        <kbd className={`shrink-0 rounded border px-1 text-[10px] font-medium leading-[15px]
                                         ${on ? 'border-brand-line bg-surface/70 text-brand-ink'
                                              : 'border-border bg-surface-2 text-ink-faint'}`}>
                          {it.hint}
                        </kbd>
                      </>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* ── 当前范围 ──
          原来「类别」（高考/模拟）藏在中栏的筛选弹层里，而它是个
          **全局视角**：换一下，整个题库的口径就变了。放在导航栏底部，
          和左侧那些入口的性质才一致。 */}
      <div className="shrink-0 border-t border-border p-2.5">
        {!collapsed ? (
          <>
            <div className="mb-1.5 px-0.5 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint">
              当前范围
            </div>
            <div className="flex gap-[3px] rounded-[9px] bg-muted p-[3px]">
              {[{ value: '', n: total }, ...kinds].map((k) => {
                const on = kind === k.value
                return (
                  <button key={k.value || 'all'}
                    onClick={() => onKind(on && k.value ? '' : k.value)}
                    title={k.value ? `只看${k.value}题` : '全部题目'}
                    className={`press relative flex-1 rounded-[7px] py-[5px] text-[12px] font-medium
                                transition-colors ${on
                                  ? 'bg-surface text-ink shadow-[var(--shadow-card)]'
                                  : 'text-ink-faint hover:text-ink-soft'}`}>
                    {k.value || '全部'}
                  </button>
                )
              })}
            </div>
            <div className="mt-2 flex items-center gap-1.5 px-0.5 text-[10.5px] text-ink-faint">
              <span className="tnum font-semibold text-ink-soft">{total.toLocaleString()}</span>
              <span>道题</span>
              <span className="text-border-strong">·</span>
              <span className="tnum">考点 {pointsCovered}/{pointsTotal}</span>
            </div>
          </>
        ) : (
          <div className="text-center text-[10px] leading-tight text-ink-faint">
            <div className="tnum font-semibold text-ink-soft">{kinds.length + 1}</div>
            <div>范围</div>
          </div>
        )}
      </div>

      {/* 收起状态下也留一个「已选范围」的记号，不然不知道当前口径 */}
      {collapsed && kind && (
        <div className="flex items-center justify-center gap-0.5 border-t border-border py-1.5
                        text-[10px] text-brand-ink" title={`当前只看${kind}题`}>
          <Check size={11} strokeWidth={2.6} />{kind}
        </div>
      )}
    </aside>
  )
}
