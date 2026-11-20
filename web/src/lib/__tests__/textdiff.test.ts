/** 讲义「保存前预览」的行级 diff。锁三件事：行号从 1 起、
 *  未变的行不会退化成删+加（否则预览满屏红绿）、超大文本走整体替换兜底。 */
import { describe, expect, it } from 'vitest'
import { diffCount, diffLines } from '@/lib/textdiff'

describe('diffLines', () => {
  it('完全相同：全是 same，行号 a/b 都从 1 起', () => {
    expect(diffLines('a\nb\nc', 'a\nb\nc')).toEqual([
      { kind: 'same', text: 'a', a: 1, b: 1 },
      { kind: 'same', text: 'b', a: 2, b: 2 },
      { kind: 'same', text: 'c', a: 3, b: 3 },
    ])
  })

  it('CRLF 与 LF 视为同一份内容（Word/Windows 另存的讲义不该整篇报改动）', () => {
    expect(diffLines('第一行\r\n第二行', '第一行\n第二行')).toEqual([
      { kind: 'same', text: '第一行', a: 1, b: 1 },
      { kind: 'same', text: '第二行', a: 2, b: 2 },
    ])
  })

  it('删掉中间一行：只标那一行 del，后面的行仍是 same 而不是删+加', () => {
    expect(diffLines('a\nb\nc', 'a\nc')).toEqual([
      { kind: 'same', text: 'a', a: 1, b: 1 },
      { kind: 'del', text: 'b', a: 2 },
      { kind: 'same', text: 'c', a: 3, b: 2 },
    ])
  })

  it('插入一行：只标 add，行号 b 顺延', () => {
    expect(diffLines('a\nb', 'a\nx\nb')).toEqual([
      { kind: 'same', text: 'a', a: 1, b: 1 },
      { kind: 'add', text: 'x', b: 2 },
      { kind: 'same', text: 'b', a: 2, b: 3 },
    ])
  })

  it('空串也是「一行空行」——两空串比出 1 行 same，不是空数组', () => {
    expect(diffLines('', '')).toEqual([{ kind: 'same', text: '', a: 1, b: 1 }])
  })

  it('从空到有内容：空行 del + 新行 add', () => {
    expect(diffLines('', 'x')).toEqual([
      { kind: 'del', text: '', a: 1 },
      { kind: 'add', text: 'x', b: 1 },
    ])
  })

  it('最后一行被改：del 旧行 + add 新行，前面的 same 保留', () => {
    expect(diffLines('标题\n旧结论', '标题\n新结论')).toEqual([
      { kind: 'same', text: '标题', a: 1, b: 1 },
      { kind: 'del', text: '旧结论', a: 2 },
      { kind: 'add', text: '新结论', b: 2 },
    ])
  })

  it('中文逐行对比不受编码/长度影响', () => {
    const before = '（1）求 $x$ 的值。\n（2）证明：$a>0$。'
    const after = '（1）求 $x$ 的值。\n（2）证明：$a\\ge 0$。'
    const rows = diffLines(before, after)
    expect(rows.filter((r) => r.kind === 'same')).toHaveLength(1)
    expect(rows).toContainEqual({ kind: 'del', text: '（2）证明：$a>0$。', a: 2 })
    expect(rows).toContainEqual({ kind: 'add', text: '（2）证明：$a\\ge 0$。', b: 2 })
  })

  it('超大输入不跑 LCS：整体先删后加（行数 = 两边之和）', () => {
    const big = 'x\n'.repeat(400)               // 401 行
    const other = 'y\n'.repeat(400)             // 401 行 → 401*401 > 160_000
    const rows = diffLines(big, other)
    expect(rows).toHaveLength(802)
    expect(rows.slice(0, 401).every((r, i) => r.kind === 'del' && r.a === i + 1)).toBe(true)
    expect(rows.slice(401).every((r, i) => r.kind === 'add' && r.b === i + 1)).toBe(true)
  })
})

describe('diffCount', () => {
  it('分别数增删行，same 不计入', () => {
    const add = { kind: 'add' as const, text: 'n', b: 1 }
    const del = { kind: 'del' as const, text: 'o', a: 1 }
    const same = { kind: 'same' as const, text: 's', a: 1, b: 1 }
    expect(diffCount([same, del, add, add])).toEqual({ add: 2, del: 1 })
    expect(diffCount([])).toEqual({ add: 0, del: 0 })
  })
})
