/** 外观控制：明暗 + 强调色。
 *
 *  放在导航栏底部，和「当前范围」并列 —— 这两件事性质一样：都是**全局口径**，
 *  改一下整个界面的样子就变了，不属于任何单个页面。MathBank 也是这个位置
 *  （它叫「明暗模式」），放在左栏底部是对的：不会和页面内的动作抢注意力。
 *
 *  两个正交的轴，所以是两组控件而不是一个：
 *  · 明暗 —— 三态（系统/浅色/深色）。三态而不是 MathBank 的两态开关：
 *    跟随系统是大多数人的默认期望，而且**不能只在首次生效**（用户随时
 *    会把系统从深改浅）。
 *  · 强调色 —— 六个圆点。只用颜色本身表达，不加文字标签：
 *    色板是"看一眼就知道选哪个"的东西，加文字反而要读。
 */
import { Sun, Moon, Monitor, Check } from 'lucide-react'
import { ACCENTS, useTheme, setMode, setAccent, type Mode } from '@/lib/theme'

const MODES: { id: Mode; label: string; Icon: typeof Sun }[] = [
  { id: 'light',  label: '浅色', Icon: Sun },
  { id: 'dark',   label: '深色', Icon: Moon },
  { id: 'system', label: '跟随系统', Icon: Monitor },
]

export default function Appearance({ collapsed = false }: { collapsed?: boolean }) {
  const { mode, accent } = useTheme()

  /* 收起成图标条时只留一个明暗按钮。
     强调色在窄条里没地方放 —— 与其塞进去一个看不清的色板，
     不如只留最高频的那个开关（MathBank 收起时也是这么做的）。 */
  if (collapsed) {
    const dark = mode === 'dark'
    const Icon = dark ? Sun : Moon
    return (
      <div className="shrink-0 border-t border-border p-2">
        <button
          onClick={() => setMode(dark ? 'light' : 'dark')}
          title={dark ? '切到浅色' : '切到深色'}
          className="icon-btn mx-auto flex h-9 w-9 items-center justify-center rounded-lg"
        >
          <Icon size={17} />
        </button>
      </div>
    )
  }

  return (
    <div className="shrink-0 border-t border-border p-2.5">
      <div className="mb-1.5 px-0.5 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint">
        外观
      </div>

      {/* ── 明暗：三段。选中态是「浮起来的白块」，和上面的范围切换同一套 ── */}
      <div className="flex gap-[3px] rounded-[9px] bg-muted p-[3px]">
        {MODES.map(({ id, label, Icon }) => {
          const on = mode === id
          return (
            <button
              key={id}
              onClick={() => setMode(id)}
              title={label}
              aria-pressed={on}
              className={`press flex flex-1 items-center justify-center gap-1 rounded-[7px] py-[5px]
                          text-[11.5px] font-medium transition-colors ${on
                            ? 'bg-surface text-ink shadow-[var(--shadow-card)]'
                            : 'text-ink-faint hover:text-ink-soft'}`}
            >
              <Icon size={12.5} strokeWidth={on ? 2.3 : 1.9} />
              <span className={id === 'system' ? 'hidden xl:inline' : ''}>
                {id === 'system' ? '系统' : label}
              </span>
            </button>
          )
        })}
      </div>

      {/* ── 强调色。圆点本身就是色卡，选中的加一圈描边 + 对勾 ──
          对勾不只为好看：灰度色（石墨）和低彩度色在暗底上光看圆点
          分不出选没选，需要一个**与颜色无关**的记号。 */}
      <div className="mt-2 flex items-center gap-[3px] px-0.5">
        {ACCENTS.map((a) => {
          const on = accent === a.id
          return (
            <button
              key={a.id}
              onClick={() => setAccent(a.id)}
              title={a.label}
              aria-label={`强调色：${a.label}`}
              aria-pressed={on}
              className={`press grid h-[26px] flex-1 place-items-center rounded-[7px]
                          transition-colors ${on ? 'bg-muted' : 'hover:bg-muted/70'}`}
            >
              <span
                className="grid h-[15px] w-[15px] place-items-center rounded-full"
                style={{
                  background: a.dot,
                  // 选中环用圆点自己的颜色，不刷品牌色 —— 否则选中「翠绿」时
                  // 环是粉的，看起来像选错了。中间垫一圈 surface 色，
                  // 让环和圆点之间留出空隙，而不是糊成一坨。
                  boxShadow: on ? `0 0 0 2px var(--color-surface), 0 0 0 4px ${a.dot}` : 'none',
                }}
              >
                {on && <Check size={9} strokeWidth={3.6} className="text-white" />}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
