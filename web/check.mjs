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

/**
 * 取全库。
 *
 * ⚠️ 两个约束（后端审查后新增）：
 *   1. `limit` 上限是 **1000**（防一次请求打爆服务）→ 必须**分页**；
 *   2. 列表默认**瘦身**（只带题干块 IR）→ 必须显式 `lite=0`，
 *      否则答案/解析的块 IR 缺失，这个脚本就会**静默漏检**——
 *      而它下面的 walk() 正是要逐个校验 answer/solution 里的公式。
 */
async function fetchAll() {
  const PAGE = 500
  const items = []
  let total = 0
  for (let offset = 0; ; offset += PAGE) {
    const r = await fetch(
      `${BASE}/api/questions?lite=0&limit=${PAGE}&offset=${offset}`)
    if (!r.ok) throw new Error(`接口返回 ${r.status}——后端在跑吗？`)
    const d = await r.json()
    total = d.total
    items.push(...d.items)
    if (items.length >= total || d.items.length === 0) break
  }
  return { total, items }
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

// 图片：确认 /api/figure 真能取到。
//
// ⚠️ 原来是 `Promise.all(ids.map(fetch))` —— **3491 个并发 GET**，
//    而且把每张图**整个下载**下来。后端每张图都要过一遍透明处理
//    （PIL，跑在线程池，默认 40 个 worker），并发一上来就有一两个连接
//    被 reset，检查于是报"图片取不到"，而后端其实是好的（curl 一把就 200）。
//    现在：并发上限 6 + 拿到响应头就 cancel 掉 body + 失败重试一次。
const ids = [...figIds]
const CONCURRENCY = 6
const results = []
let cursor = 0

async function probeOnce(id) {
  const ac = new AbortController()
  try {
    const r = await fetch(`${BASE}/api/figure?path=${encodeURIComponent(id)}`,
                          { signal: ac.signal })
    try { await r.body?.cancel() } catch { /* 某些实现没有 body.cancel */ }
    return r.ok ? null : { id, status: r.status }
  } catch (e) {
    return { id, status: String(e.message || e) }
  }
}

async function worker() {
  for (;;) {
    const i = cursor++
    if (i >= ids.length) return
    const id = ids[i]
    let bad = await probeOnce(id)
    if (bad) bad = await probeOnce(id)          // 抖动，重试一次
    if (bad) results.push({ id, status: bad.status })
  }
}
await Promise.all(Array.from({ length: CONCURRENCY }, worker))
fail.fig = results

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
  const DETAIL = process.env.DETAIL === '1'
  for (const x of (DETAIL ? list : list.slice(0, 8)))
    console.log(`      ${JSON.stringify(DETAIL ? x : JSON.stringify(x).slice(0, 150))}`)
  if (!DETAIL && list.length > 8) console.log(`      … 其余 ${list.length - 8} 处`)
}
console.log(bad ? `\n未通过（${bad} 处问题）` : '\n全部通过')
process.exit(bad ? 1 : 0)
