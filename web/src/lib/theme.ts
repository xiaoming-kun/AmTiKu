/** 外观（明暗 + 强调色）。
 *
 *  为什么要有这个文件，而不是在 Nav 里写两行：
 *  ① 主题必须**在首屏绘制之前**就定下来。写在 React 里的话，暗色用户会
 *     先看到一帧全白的界面再"啪"地变黑（闪屏）。所以真正的落地在
 *     `web/index.html` 里那段阻塞式脚本，这里只是同一套规则的第二份
 *     实现 —— 两份必须一致，键名和取值都别各写各的。
 *  ② 暗色不是"再画一套组件"。全项目颜色早就收成语义 token，这里只负责
 *     往 `<html>` 上挂 `.dark` / `data-accent`，二十多个页面一起变。
 *
 *  与 MathBank 那版的差别：它是 二元(亮/暗) + 忽略系统偏好，
 *  这里给三态 —— **系统 / 浅色 / 深色**，默认跟随系统。
 *  用 `useSyncExternalStore` 而不是 Context：主题是全局单例，
 *  没有任何"局部覆写"的需求，Context 只会多一层 Provider 要穿。
 */
import { useSyncExternalStore } from 'react'

export type Mode = 'system' | 'light' | 'dark'
export type Accent = 'rose' | 'indigo' | 'ocean' | 'emerald' | 'violet' | 'graphite'

/** localStorage 键。**这两个字符串在 index.html 里也出现**，改名要一起改。 */
const K_MODE = 'amtiku.theme'
const K_ACCENT = 'amtiku.accent'

export const ACCENTS: { id: Accent; label: string; dot: string }[] = [
  // dot 是给选择器里那个小圆点用的实色。写死而不是读 CSS 变量：
  // 下拉要**同时**展示六种颜色，读变量只能读到当前那一种。
  { id: 'rose',     label: '玫粉',   dot: '#ce338a' },
  { id: 'indigo',   label: '靛蓝',   dot: '#4f5bd5' },
  { id: 'ocean',    label: '湖蓝',   dot: '#2b7fa8' },
  { id: 'emerald',  label: '翠绿',   dot: '#2b8355' },
  { id: 'violet',   label: '紫罗兰', dot: '#8b46c4' },
  { id: 'graphite', label: '石墨',   dot: '#6b6b74' },
]

const MODES: Mode[] = ['system', 'light', 'dark']

function readMode(): Mode {
  try {
    const v = localStorage.getItem(K_MODE)
    if (v && (MODES as string[]).includes(v)) return v as Mode
  } catch { /* 隐私模式下 localStorage 会抛，退回默认 */ }
  return 'system'
}

function readAccent(): Accent {
  try {
    const v = localStorage.getItem(K_ACCENT)
    if (v && ACCENTS.some((a) => a.id === v)) return v as Accent
  } catch { /* 同上 */ }
  return 'rose'
}

/** 系统现在是不是暗色。老 Safari 没有 matchMedia 的 change 事件，
 *  用可选链兜住 —— 监听不上只是"不会自动切"，不该让界面炸。 */
const mq = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-color-scheme: dark)')
  : null

export function systemDark(): boolean {
  return !!mq?.matches
}

/** 「系统」模式下此刻实际是亮还是暗 */
export function effectiveDark(mode: Mode): boolean {
  return mode === 'dark' || (mode === 'system' && systemDark())
}

/** 把主题写到 `<html>` 上。**只做这一件事**，不碰 DOM 其他部分。 */
function paint(mode: Mode, accent: Accent) {
  const el = document.documentElement
  el.classList.toggle('dark', effectiveDark(mode))
  el.dataset.accent = accent
}

/* ── 一个极小的外部 store ────────────────────────────────
   主题是全局单例，用订阅表比 Context 轻，也让"非 React 的地方"
   （比如首屏脚本、将来的快捷键）能直接改。 */
let state = { mode: readMode(), accent: readAccent() }
const subs = new Set<() => void>()

function emit() {
  paint(state.mode, state.accent)
  subs.forEach((f) => f())
}

function subscribe(f: () => void) {
  subs.add(f)
  return () => { subs.delete(f) }
}

/** 跟随系统：只在「系统」模式下才有意义，但一直挂着 —— 用户的偏好
 *  随时可能从深改浅，而那时他可能正停在「系统」上。 */
mq?.addEventListener?.('change', () => {
  if (state.mode === 'system') emit()
})

export function setMode(mode: Mode) {
  state = { ...state, mode }
  try { localStorage.setItem(K_MODE, mode) } catch { /* 存不下就只是不记忆 */ }
  emit()
}

export function setAccent(accent: Accent) {
  state = { ...state, accent }
  try { localStorage.setItem(K_ACCENT, accent) } catch { /* 同上 */ }
  emit()
}

/** 明暗快捷键用：在「浅色 / 深色」间翻。
 *  当前若是「系统」，就翻到**系统的反面**（用户按了键，意思很明确），
 *  而不是先跳到「浅色」——那样在暗系统上按一次会变成亮的，像按反了。 */
export function toggleDark() {
  setMode(effectiveDark(state.mode) ? 'light' : 'dark')
}

export function getTheme() { return state }

export function useTheme() {
  return useSyncExternalStore(subscribe, getTheme, getTheme)
}

/** 挂载时再 paint 一次。首屏脚本已经在 head 里画过了，
 *  这里是为了兜住「脚本被 CSP 拦掉 / 老浏览器没跑」的情况 —— 幂等，无副作用。 */
export function initTheme() {
  paint(state.mode, state.accent)
}
