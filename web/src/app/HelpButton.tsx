/** 快捷键表。
 *
 *  入口放在顶栏和命令面板里，不再在右下角常驻一颗浮球 ——
 *  页面越忙，那颗浮球越像内容的一部分。快捷键表本身是模态的，
 *  打开后盖住页面，按 Esc 或点遮罩关闭。
 */
import { useEffect, useRef, useState } from 'react'
import { CloseBtn } from '@/app/ui'

/** 键位分组。**顺序按使用的先后**：先找题，再组卷，最后是通用。 */
const GROUPS: { title: string; rows: [string, string][] }[] = [
  {
    title: '导航',
    rows: [
      ['O', '工作台 · 进度与待办'],
      ['B', '题库 · 找题与挑题'],
      ['P', '组卷 · 当前卷子与导出'],
      ['G', '知识图谱 · 教材顺序与先修关系'],
      ['T', '讲义 · 讲 · 错 · 练'],
      ['I', '录入 · 独立页（手工 / DeepSeek / 整理 / 校对）'],
      ['Q', '题库体检 · 覆盖与缺口'],
      ['A', '试卷库 · 存档与合集'],
      ['R', '回收站'],
      ['C', '变更记录'],
    ],
  },
  {
    title: '找题与组卷',
    rows: [
      ['⌘ K', '命令面板：什么都能干（推荐先记这个）'],
      ['/', '聚焦顶栏搜索框'],
      ['↑ ↓', '在题目列表里上下移动'],
      ['Enter', '打开当前这道题的详情'],
      ['空格', '勾选 / 取消勾选当前这道（Shift 连选）'],
      ['⌘ ↵', '把当前这道题加进卷子'],
      ['Z', '专注模式：收起侧栏，宽度全给题目与详情'],
    ],
  },
  {
    title: '通用',
    rows: [
      ['Esc', '关闭弹层'],
      ['?', '打开这张表'],
    ],
  },
]

export default function HelpButton() {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  // 命令面板里那条「查看键盘快捷键」要能把它打开。
  // 用自定义事件解耦：CommandPalette 不必知道 HelpButton 的存在。
  useEffect(() => {
    const open = () => setOpen(true)
    window.addEventListener('amtiku:help', open)
    return () => window.removeEventListener('amtiku:help', open)
  }, [])

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      // 问号要按 Shift 才出得来，所以这里不做大小写限制
      if (e.key === '?' && !e.metaKey && !e.ctrlKey) {
        const el = document.activeElement as HTMLElement | null
        const tag = el?.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || el?.isContentEditable) return
        e.preventDefault(); setOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  // 打开时先一步吃掉 Escape：否则同一个按键会继续冒泡到 App，
  // 把底下的题目详情也一起关掉。
  useEffect(() => {
    if (!open) return
    const esc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopImmediatePropagation()
      setOpen(false)
    }
    window.addEventListener('keydown', esc, true)
    return () => window.removeEventListener('keydown', esc, true)
  }, [open])

  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-[70] grid place-items-center bg-scrim p-4"
      onClick={() => setOpen(false)}>
      <div ref={box} onClick={(e) => e.stopPropagation()}
        role="dialog" aria-modal="true" aria-label="键盘快捷键"
        className="pop-c max-h-[86vh] w-[360px] max-w-full overflow-y-auto rounded-[var(--radius-pop)]
                   border border-border bg-surface p-4 shadow-[var(--shadow-pop)]">
        <div className="mb-3 flex items-center gap-2">
          <span className="text-[13.5px] font-semibold">键盘快捷键</span>
          <CloseBtn onClick={() => setOpen(false)} className="ml-auto" />
        </div>
        <div className="space-y-3.5">
          {GROUPS.map((g) => (
            <div key={g.title}>
              <div className="mb-1.5 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint">
                {g.title}
              </div>
              <div className="space-y-[3px]">
                {g.rows.map(([k, desc]) => (
                  <div key={k + desc} className="flex items-center gap-2.5 text-[12px]">
                    <kbd className="min-w-[38px] shrink-0 rounded-md border border-border bg-surface-2
                                    px-1.5 text-center text-[11px] font-medium leading-[19px] text-ink-soft">
                      {k}
                    </kbd>
                    <span className="min-w-0 flex-1 truncate text-ink-soft">{desc}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3.5 border-t border-border pt-2.5 text-[10.5px] leading-relaxed text-ink-faint">
          单键只在<b className="font-medium text-ink-soft">没有停在输入框里</b>时生效（打中文时不会误触）。
          <div className="mt-1.5 font-mono">AmMath v{__APP_VERSION__}</div>
        </div>
      </div>
    </div>
  )

}
