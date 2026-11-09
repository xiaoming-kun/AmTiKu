/** 已掌握：**学习者私有状态**，只存 localStorage，绝不写进知识地图。
 *
 *  以前是 Detail 里的 useState，刷新就清零——用户勾了 35 个点，一刷新全回来，
 *  「推荐学习路径」等于没用。这里做成一个小 store：
 *    · 唯一键 `amtiku.mastery`，值是点 id 的数组；
 *    · 用 useSyncExternalStore 订阅（和 theme.ts 同一套写法，不引 Context）；
 *    · 三个视图（导图 / 全景 / 先修图）和右栏共用同一份，勾一处，图上同步变。
 */
import { useSyncExternalStore } from 'react'

const KEY = 'amtiku.mastery'
let cache: Set<string> | null = null
const subs = new Set<() => void>()

function read(): Set<string> {
  if (cache) return cache
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || '[]')
    cache = new Set(Array.isArray(v) ? v.filter((x) => typeof x === 'string') : [])
  } catch {
    cache = new Set()
  }
  return cache
}

function commit(next: Set<string>) {
  cache = next
  try {
    localStorage.setItem(KEY, JSON.stringify([...next]))
  } catch { /* 隐私模式存不下：只是不记忆，不报错 */ }
  for (const f of subs) f()
}

export function isMastered(id: string): boolean {
  return read().has(id)
}

export function toggleMastered(id: string) {
  const next = new Set(read())
  if (next.has(id)) next.delete(id)
  else next.add(id)
  commit(next)
}

export function clearMastered() {
  commit(new Set())
}

/** 组件里用：返回当前已掌握集合（同一份引用，变更时整体换新）。 */
export function useMastery(): Set<string> {
  return useSyncExternalStore(
    (cb) => {
      subs.add(cb)
      return () => subs.delete(cb)
    },
    read,
    read,
  )
}
