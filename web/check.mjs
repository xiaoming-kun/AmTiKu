/**
 * AmTiKu · 前端渲染端到端检查
 *
 * 把**接口真实下发的**块级 IR 走一遍前端的渲染路径，验证：
 *   1. 每个数学节点 KaTeX 都能渲染（用与 App 完全相同的参数）
 *   2. 正文里没有漏出来的 LaTeX 块级语法（\begin / \end / \item）
 *   3. 每个图片节点在 /api/figure 都能取到实体文件
 *
 * 这三条正好覆盖已发生过的三类线上问题：公式画不出来、列表拍平漏语法、碎图。
 * 需要后端在跑：python3 -m amti.web.server --port 8899
 *
 *     cd web && node check.mjs
 */
import katex from 'katex'

const BASE = process.env.AMTIKU_BASE || 'http://127.0.0.1:8899'

// 与 src/lib/render.tsx 里的 MACROS 保持一致
const MACROS = {
  '\\symbfit': '\\boldsymbol',
  '\\symbf': '\\mathbf',
  '\\mbox': '\\text',
  '\\i': '\\mathrm{i}',
  '\\eu': '\\mathrm{e}',
  '\\uppi': '\\pi',
  '\\R': '\\mathbb{R}',
  '\\Z': '\\mathbb{Z}',
  '\\N': '\\mathbb{N}',
}

const LEAK = /\\(?:begin|end)\{[a-zA-Z*]+\}|\\item(?![a-zA-Z])/

async function fetchAll() {
  const r = await fetch(`${BASE}/api/questions?limit=100000`)
  if (!r.ok) throw new Error(`接口返回 ${r.status}——后端在跑吗？`)
  return r.json()
}

/** 遍历块级 IR，回调每一个数学 / 文本 / 图片节点。 */
function walk(blocks, on) {
  for (const b of blocks || []) {
    // ⚠️ 必须和 src/lib/render.tsx 的 renderBlocks **走同一套结构**。
    // 表格单元格有两种形态：普通格 `{in}`，嵌套表格的格 `{blocks}`。
    // 少认一种这里就会崩，或者更糟——**静默漏检**。
    if (b.t === 'p') (b.in || []).forEach(on.inline)
    else if (b.t === 'math') on.math(b.tex, true)
    else if (b.t === 'list') (b.items || []).forEach((it) => walk(it, on))
    else if (b.t === 'table') (b.rows || []).forEach((r) => r.forEach((c) => {
      if (c.blocks) walk(c.blocks, on)
      else (c.in || []).forEach(on.inline)
    }))
    else if (b.t === 'box') walk(b.blocks, on)
    else if (b.t === 'fig') on.fig(b.id)
    else if (b.t === 'raw') on.raw(b)
  }
}

const { total, items } = await fetchAll()
const fail = { katex: [], leak: [], fig: [] }
let nMath = 0
let nFig = 0
const figIds = new Set()

for (const q of items) {
  const groups = [
    ['stem', q.blocks?.stem],
    ['answer', q.blocks?.answer],
    ['solution', q.blocks?.solution],
    ...(q.blocks?.options || []).map((b, i) => [`opt${i}`, b]),
  ]
  for (const [field, blocks] of groups) {
    walk(blocks, {
      math: (tex, display) => {
        nMath++
        try {
          katex.renderToString(tex, {
            displayMode: !!display, throwOnError: true, strict: false,
            trust: true, macros: MACROS,
          })
        } catch (e) {
          fail.katex.push({ key: q.key, field, tex: tex.slice(0, 100), msg: String(e.message || e).slice(0, 90) })
        }
      },
      inline: (n) => {
        if (n.t === 'm') {
          nMath++
          try {
            katex.renderToString(n.s, {
              displayMode: !!n.display, throwOnError: true, strict: false,
              trust: true, macros: MACROS,
            })
          } catch (e) {
            fail.katex.push({ key: q.key, field, tex: n.s.slice(0, 100), msg: String(e.message || e).slice(0, 90) })
          }
        } else if ((n.t === 's' || n.t === 'raw') && LEAK.test(n.s || '')) {
          fail.leak.push({ key: q.key, field, s: (n.s || '').slice(0, 80) })
        } else if (n.t === 'fig') {
          nFig++
          figIds.add(n.id)
        }
      },
      fig: (id) => {
        nFig++
        figIds.add(id)
      },
      raw: () => {},
    })
  }
}

// 图片：并发 HEAD 一下，确认 /api/figure 真能取到
const ids = [...figIds]
const results = await Promise.all(ids.map(async (id) => {
  try {
    const r = await fetch(`${BASE}/api/figure?path=${encodeURIComponent(id)}`, { method: 'GET' })
    return r.ok ? null : { id, status: r.status }
  } catch (e) {
    return { id, status: String(e) }
  }
}))
fail.fig = results.filter(Boolean)

console.log(`题目 ${total} 道   数学节点 ${nMath}   图片引用 ${nFig}（去重 ${ids.length}）`)
const report = [
  ['KaTeX 渲染', fail.katex],
  ['LaTeX 泄漏', fail.leak],
  ['图片可取', fail.fig],
]
let bad = 0
for (const [name, list] of report) {
  if (!list.length) {
    console.log(`  ✓ ${name}`)
    continue
  }
  bad += list.length
  console.log(`  ✗ ${name}：${list.length} 处`)
  for (const x of list.slice(0, 8)) console.log(`      ${JSON.stringify(x).slice(0, 150)}`)
  if (list.length > 8) console.log(`      … 其余 ${list.length - 8} 处`)
}
console.log(bad ? `\n未通过（${bad} 处问题）` : '\n全部通过')
process.exit(bad ? 1 : 0)
