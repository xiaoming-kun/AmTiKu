// ══════════════════════════════════════════════════════════════
//  题目 LaTeX 转换（**必须与后端 amti/slidev_handout.py 保持一致**）
//
//  为什么需要：题库是 LaTeX + newtxmath，有些东西 KaTeX 不认，
//  直接渲染会显示成源码。而且「预览」与「导出 PDF」必须一致 ——
//  否则老师看到的和生成的不一样（这个 bug 我犯过一次）。
//
//  ⚠️ 改这里时必须同步改后端，反之亦然。对应关系：
//      MACRO_FIXES      ↔ MACRO_FIXES
//      normalizeDelims  ↔ normalize_delims
//      stripAnswers     ↔ strip_answers
//      showAnswers      ↔ show_answers
//      convertTabular   ↔ convert_tabular  (+ _extract_tabular / _match_brace)
//      convertEnumerate ↔ convert_enumerate（栈式，支持嵌套）
//      tightenMath      ↔ tighten_math
// ══════════════════════════════════════════════════════════════

/** KaTeX 不认识的宏 → 等价写法（顺序：先长后短） */
const MACRO_FIXES: [RegExp, string][] = [
  [/\\symbfit\s*\{([^}]*)\}/g, '\\boldsymbol{$1}'],
  [/\\symbfit\s+([A-Za-z])/g, '\\boldsymbol{$1}'],
  [/\\symbfit/g, '\\boldsymbol'],
  [/\\symbf\s*\{([^}]*)\}/g, '\\mathbf{$1}'],
  [/\\symbf\s+([A-Za-z])/g, '\\mathbf{$1}'],
  [/\\symbf/g, '\\mathbf'],
  [/\\bm\s*\{([^}]*)\}/g, '\\boldsymbol{$1}'],
  [/\\bm\s+([A-Za-z])/g, '\\boldsymbol{$1}'],
  [/\\R\b/g, '\\mathbb{R}'], [/\\N\b/g, '\\mathbb{N}'],
  [/\\Z\b/g, '\\mathbb{Z}'], [/\\Q\b/g, '\\mathbb{Q}'],
  [/\\C\b/g, '\\mathbb{C}'], [/\\up\b/g, ''],
]

/** LaTeX 传统定界符 → Slidev 定界符 */
function normalizeDelims(t: string): string {
  return t
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, x) => `$$${String(x).trim()}$$`)
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, x) => `$${String(x).trim()}$`)
}

/** 答案宏 → 卷面空位（学生版） */
function stripAnswers(t: string): string {
  let s = t
    .replace(/\\paren\s*\[[^\]]*\]/g, '（　　）')
    .replace(/\\fillin\s*\[[^\]]*\]/g, '＿＿＿＿')
    // ⚠️ 花括号变体必须一起吃掉，否则留下孤立 {}（后端实测 708 道题受影响）
    .replace(/\\fillin\s*\{[^}]*\}/g, '＿＿＿＿')
    .replace(/\\fillin\b/g, '＿＿＿＿')
  // 兜底：紧跟在空位后面的孤立 {} （数据自带的多余花括号）
  return s.replace(/＿＿＿＿\s*\{\}/g, '＿＿＿＿')
}

/** 答案宏 → 显示答案（教师版） */
function showAnswers(t: string): string {
  return t
    .replace(/\\paren\s*\[([^\]]*)\]/g, (_, a) => `（ ${a} ）`)
    .replace(/\\fillin\s*\[([^\]]*)\]/g, '$1')
    .replace(/\\fillin\s*\{\}/g, '＿＿＿＿')
    .replace(/\\fillin\s*\{([^}]*)\}/g, '$1')
    .replace(/\\fillin\b/g, '＿＿＿＿')
}

// ── 配对花括号扫描 ───────────────────────────────────────────

/** 从 text[start]=='{' 开始，返回配对 '}' 的下标；失败返回 -1 */
function matchBrace(text: string, start: number): number {
  if (text[start] !== '{') return -1
  let depth = 0
  let i = start
  while (i < text.length) {
    const c = text[i]
    if (c === '\\') { i += 2; continue }
    if (c === '{') depth++
    else if (c === '}') { depth--; if (depth === 0) return i }
    i++
  }
  return -1
}

/** 找出最外层 tabular 块 [start, end, body] */
function extractTabular(text: string): [number, number, string][] {
  const BEGIN = '\\begin{tabular}'
  const END = '\\end{tabular}'
  const all: [number, number, string][] = []
  const stack: number[] = []
  const bodies: number[] = []
  let pos = 0
  while (pos < text.length) {
    const ib = text.indexOf(BEGIN, pos)
    const ie = text.indexOf(END, pos)
    if (ib < 0 && ie < 0) break
    if (ib >= 0 && (ie < 0 || ib < ie)) {
      let j = ib + BEGIN.length
      while (j < text.length && (text[j] === ' ' || text[j] === '\t')) j++
      if (text[j] === '[') {                       // 可选 [位置]
        const k = text.indexOf(']', j)
        if (k > 0 && k - j < 60) j = k + 1
      }
      if (text[j] === '{') {                       // 列格式（配对花括号）
        const k = matchBrace(text, j)
        if (k > 0) j = k + 1
      }
      stack.push(ib); bodies.push(j); pos = j
    } else {
      if (stack.length) {
        const bi = stack.pop() as number
        const bs = bodies.pop() as number
        all.push([bi, ie + END.length, text.slice(bs, ie)])
      }
      pos = ie + END.length
    }
  }
  // 只保留最外层：嵌套的交给孩子递归处理
  all.sort((a, b) => a[0] - b[0] || b[1] - a[1])
  const outer: [number, number, string][] = []
  let lastEnd = -1
  for (const blk of all) {
    if (blk[0] >= lastEnd) { outer.push(blk); lastEnd = blk[1] }
  }
  return outer
}

/** LaTeX 表格 → markdown 表格（支持嵌套，用占位符） */
function convertTabular(input: string): string {
  let text = input
    // 去 center / minipage 外壳（表格本身居中）
    .replace(/\\begin\{center\}([\s\S]*?)\\end\{center\}/g, '$1')
    .replace(/\\begin\{minipage\}(\[[^\]]*\])?\{[^}]*\}/g, '')
    .replace(/\\end\{minipage\}/g, '')

  const cache = new Map<string, string>()

  const toMd = (body: string): string => {
    const rows: string[][] = []
    for (let line of body.split('\\\\')) {
      line = line.trim()
      if (!line) continue
      line = line.replace(/\\hline/g, '').trim()
      if (!line) continue
      const cells = line.split('&').map((c) => c.trim())
      if (cells.some((c) => c)) rows.push(cells)
    }
    if (!rows.length) return '\n'
    const ncol = Math.max(...rows.map((r) => r.length))
    const padded = rows.map((r) => [...r, ...Array(ncol - r.length).fill('')])
    const out = ['', '| ' + padded[0].join(' | ') + ' |', '|' + '---|'.repeat(ncol)]
    for (let i = 1; i < padded.length; i++) out.push('| ' + padded[i].join(' | ') + ' |')
    out.push('')
    return out.join('\n')
  }

  /**
   * ⚠️ 顺序很重要：
   *   ① 先把 body 里嵌套的 tabular 换成占位符
   *   ② 再按 \\ 和 & 解析外层（此时 body 是单行安全的）
   *   ③ 最后还原占位符
   * 反过来做会让内层 markdown 的换行破坏外层行结构（后端踩过这个坑）。
   */
  const stash = (body: string): string => {
    for (const [k, v] of Array.from(cache.entries())) body = body.split(k).join(v)
    const inner = extractTabular(body)
    for (let i = inner.length - 1; i >= 0; i--) {
      const [st, en, b] = inner[i]
      const ph = stash(b)
      body = body.slice(0, st) + ph + body.slice(en)
    }
    let md = toMd(body)
    for (let round = 0; round < 8; round++) {
      let hit = false
      for (const k of Array.from(cache.keys())) {
        if (md.includes(k)) { md = md.split(k).join(cache.get(k) as string); cache.delete(k); hit = true }
      }
      if (!hit) break
    }
    return md
  }

  const blocks = extractTabular(text).sort((a, b) => b[0] - a[0])
  for (const [st, en, body] of blocks) {
    text = text.slice(0, st) + stash(body) + text.slice(en)
  }
  return text
}

/**
 * enumerate → （1）（2）…
 *
 * ⚠️ 用**栈式解析**处理嵌套，不用正则 ——
 * 题库里有嵌套 enumerate（大题的小问下还有小问），正则数不了括号，
 * 无论贪婪还是非贪婪都会错配 \end（后端实测 242 道题受影响）。
 */
function convertEnumerate(input: string): string {
  const BEGIN = '\\begin{enumerate}'
  const END = '\\end{enumerate}'
  const MARKS = '①②③④⑤⑥⑦⑧⑨⑩'

  const render = (items: string[], depth: number): string => {
    const out: string[] = []
    items.forEach((it, i) => {
      const label = depth === 0 ? `（${i + 1}）`
        : depth === 1 ? (MARKS[i] || `(${i + 1})`)
        : `${String.fromCharCode(97 + i)}. `
      out.push('\n' + '　'.repeat(depth) + label + it.trim())
    })
    return out.join('') + '\n'
  }

  let text = input
  const parts: string[] = []
  const stack: { items: string[]; cur: string[] }[] = []
  let pos = 0

  while (pos < text.length) {
    const ib = text.indexOf(BEGIN, pos)
    const ie = text.indexOf(END, pos)
    if (ib < 0 && ie < 0) {
      const tail = text.slice(pos)
      if (stack.length) stack[stack.length - 1].cur.push(tail)
      else parts.push(tail)
      break
    }
    if (ib >= 0 && (ie < 0 || ib < ie)) {
      const chunk = text.slice(pos, ib)
      if (stack.length) stack[stack.length - 1].cur.push(chunk)
      else parts.push(chunk)
      let j = ib + BEGIN.length
      if (text[j] === '[') {
        const k = text.indexOf(']', j)
        if (k > 0 && k - j < 40) j = k + 1
      }
      stack.push({ items: [], cur: [] })
      pos = j
    } else {
      const chunk = text.slice(pos, ie)
      if (stack.length) stack[stack.length - 1].cur.push(chunk)
      else parts.push(chunk)
      if (!stack.length) { pos = ie + END.length; continue }
      const top = stack.pop() as { items: string[]; cur: string[] }
      const body = top.cur.join('')
      for (const piece of body.split(/\\item\b/).slice(1)) {
        if (piece.trim()) top.items.push(piece)
      }
      const rendered = render(top.items, stack.length)
      if (stack.length) stack[stack.length - 1].cur.push(rendered)
      else parts.push(rendered)
      pos = ie + END.length
    }
  }
  return parts.join('')
}

/** 数学模式内 < > → \lt \gt；\{ \} → \lbrace{} \rbrace{} */
function convertMathSafe(t: string): string {
  const s = t
    .replace(/\\left\s*\\\{/g, '\\left\\lbrace{}')
    .replace(/\\right\s*\\\}/g, '\\right\\rbrace{}')
    .replace(/\\\{/g, '\\lbrace{}')
    .replace(/\\\}/g, '\\rbrace{}')
  const parts = s.split(/(\$[^$]*\$)/)
  for (let i = 1; i < parts.length; i += 2) {
    parts[i] = parts[i].replace(/</g, '\\lt ').replace(/>/g, '\\gt ')
  }
  return parts.join('')
}

/** 修掉 markdown-it 拒绝解析的数学定界符（闭 $ 前的空格） */
function tightenMath(t: string): string {
  const blocks: string[] = []
  let text = t.replace(/\$\$[\s\S]+?\$\$/g, (m) => {
    blocks.push(m)
    return `\u0001B${blocks.length - 1}\u0001`
  })

  const out: string[] = []
  for (const line of text.split('\n')) {
    if ((line.match(/\$/g) || []).length < 2) { out.push(line); continue }
    const segs = line.split('$')
    // segs[0] 正文, segs[1] 公式, segs[2] 正文, segs[3] 公式… 正文原样（含空格）
    const rebuilt = [segs[0]]
    for (let k = 1; k < segs.length; k++) {
      if (k % 2 === 1) rebuilt.push('$' + segs[k].trim() + '$')
      else rebuilt.push(segs[k])
    }
    let line2 = rebuilt.join('')
    if (segs.length % 2 === 0) line2 = line2.slice(0, -1)   // 未闭合
    out.push(line2)
  }
  text = out.join('\n')

  blocks.forEach((b, i) => { text = text.split(`\u0001B${i}\u0001`).join(b) })
  return text
}

/** 图形环境 → 占位（老师自己画图） */
/** 图形环境处理。
 *
 *  ⚠️ \includegraphics 不能直接删掉 —— 题目写着「如图」却没图就没法看。
 *  编辑器用题库的图片接口 /api/figure 显示（后端导出时换成 /img/，因为
 *  Slidev 只认自己 public 下的文件）。两边路径不同，但都要有图。
 */
function stripGraphics(t: string): string {
  return t
    .replace(/\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}/g,
             (_, name) => `<img src="/api/figure?path=${encodeURIComponent(String(name).trim())}" />`)
    .replace(/\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}/g, '【图：请手绘】')
    .replace(/\\begin\{axis\}(\[[^\]]*\])?[\s\S]*?\\end\{axis\}/g, '【图：请手绘】')
    .replace(/\\begin\{scope\}(\[[^\]]*\])?[\s\S]*?\\end\{scope\}/g, '')
}

/** 一道题的题干 → 可渲染的 markdown（与后端 transform 一致） */
export function transformStem(stem: string, withAnswers = false): string {
  let t = stripGraphics(stem || '')
  for (const [pat, rep] of MACRO_FIXES) t = t.replace(pat, rep)
  t = withAnswers ? showAnswers(t) : stripAnswers(t)
  t = normalizeDelims(t)
  t = convertTabular(t)
  t = convertEnumerate(t)
  t = convertMathSafe(t)
  t = tightenMath(t)
  return t.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim()
}

/** 选项文字 → 可渲染 */
export function transformOption(text: string): string {
  let t = text || ''
  for (const [pat, rep] of MACRO_FIXES) t = t.replace(pat, rep)
  t = normalizeDelims(t)
  t = convertMathSafe(t)
  t = tightenMath(t)
  return t
}
