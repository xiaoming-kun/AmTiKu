/** 行级 diff：只用于讲义「保存前预览」，不追求 Myers 的极限性能。 */
export type DiffRow = { kind: 'same' | 'add' | 'del'; text: string; a?: number; b?: number }

export function diffLines(before: string, after: string): DiffRow[] {
  const a = before.replace(/\r\n/g, '\n').split('\n')
  const b = after.replace(/\r\n/g, '\n').split('\n')
  // 极端大段源码就别做 LCS 了，直接整体替换预览。
  if (a.length * b.length > 160_000) {
    return [
      ...a.map((text, i) => ({ kind: 'del' as const, text, a: i + 1 })),
      ...b.map((text, i) => ({ kind: 'add' as const, text, b: i + 1 })),
    ]
  }
  const dp = Array.from({ length: a.length + 1 }, () => new Uint16Array(b.length + 1))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const rows: DiffRow[] = []
  let i = 0, j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { rows.push({ kind: 'same', text: a[i], a: i + 1, b: j + 1 }); i++; j++ }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { rows.push({ kind: 'del', text: a[i], a: i + 1 }); i++ }
    else { rows.push({ kind: 'add', text: b[j], b: j + 1 }); j++ }
  }
  while (i < a.length) { rows.push({ kind: 'del', text: a[i], a: i + 1 }); i++ }
  while (j < b.length) { rows.push({ kind: 'add', text: b[j], b: j + 1 }); j++ }
  return rows
}

export function diffCount(rows: DiffRow[]): { add: number; del: number } {
  return {
    add: rows.filter((x) => x.kind === 'add').length,
    del: rows.filter((x) => x.kind === 'del').length,
  }
}
