/**
 * AmTiKu · 赵礼显讲义暂存产物的 **KaTeX 渲染检查**
 *
 * 为什么单独写一个：`web/check.mjs` 是**走接口取全库**的（层③ 端到端渲染），
 * 只看得到已经入库的题；赵礼显讲义这一批**还没入库**（全书无答案，
 * ingest 会整批拒），所以它照不到。但"构建成功 ≠ 渲染正确"这条教训
 * 一样适用——**暂存产物也得先证明 KaTeX 画得出来**，否则等补完答案
 * 再发现几百个公式是坏的，返工成本完全不一样。
 *
 * 参数与 `web/check.mjs` / `src/lib/render.tsx` **保持一致**
 * （同一份 MACROS、同样 throwOnError）。
 *
 *     cd web && node ../脚本/赵礼显讲义KaTeX.mjs
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(HERE, '..', '数据/录题/赵礼显/out')

// `katex` 只装在 `web/node_modules` 里，而这个脚本在 `脚本/`——
// ESM 是按**脚本所在目录**找包的，直接 `import 'katex'` 会 ERR_MODULE_NOT_FOUND。
// 用 createRequire 指到 `web/package.json`，拿到的就是前端自己那份 katex。
const katex = createRequire(path.join(HERE, '..', 'web', 'package.json'))('katex')

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

// ⚠️ 这里不能照抄 `check.mjs` 的 LEAK。那条正则跑的是**渲染后的块级 IR**
// （`\begin{choices}` 那时已经被转成列表了），而这里跑的是**原始 .tex**——
// 在原始文件里 `\begin{choices}` / `\begin{enumerate}` / `\item` 全是**合法写法**，
// 照抄只会刷出一屏假阳性（第一版就是这样，265 道题里 130 道"泄漏"，
// 真正坏掉的公式反而被淹了）。这里只抓**这两个环境之外**的块级语法。
const LEAK = /\\(?:begin|end)\{(?!(?:choices|enumerate)\})[a-zA-Z*]+\}/

/**
 * 模拟前端 `stripAnswers`（`web/src/lib/qlatex.ts`）的那一步。
 *
 * ⚠️ **不做这一步，这个检查就是假的。** 前端渲染学生版卷面时，会先把
 * `\paren[…]`／`\fillin[…]` 整块换成 `（　　）`／`＿＿＿＿`，再交给 KaTeX。
 * 直接拿原始 `$…\paren[]…$` 去渲染，KaTeX 会报 "Undefined control sequence:
 * \paren"——**那是检查器自己造的错，不是产物的错**（第一版就是这么误报了
 * 5 处，其中 4 处是公式跨过 `\begin{choices}` 的假象）。
 */
function stripAnswers(t) {
  return t
    .replace(/\\(paren|fillin)(?![a-zA-Z])\s*\[[^\]]*\]/g,
             (_, cmd) => (cmd === 'paren' ? '（　　）' : '＿＿＿＿'))
    .replace(/\\fillin\s*\{[^}]*\}/g, '＿＿＿＿')
    .replace(/\\fillin(?![a-zA-Z])/g, '＿＿＿＿')
}

/** 选项/小问是列表结构，前端先转成列表再渲染——这里整块拿掉。 */
function stripEnvs(t) {
  return t
    .replace(/\\begin\{choices\}[\s\S]*?\\end\{choices\}/g, '')
    .replace(/\\begin\{enumerate\}[\s\S]*?\\end\{enumerate\}/g, '')
}

/** 从一段 LaTeX 里抠出行内 `$…$` 与行间 `\[…\]` 的公式体。 */
function mathsOf(text) {
  const out = []
  for (const m of text.matchAll(/\$([^$]+)\$/g)) out.push([m[1], false])
  for (const m of text.matchAll(/\\\[([\s\S]*?)\\\]/g)) out.push([m[1], true])
  return out
}

/** 空位落在数学模式里——**规范上就是坏的**（会产生嵌套 `$`），单独报。 */
function slotsInMath(text) {
  const bad = []
  for (const [tex] of mathsOf(text)) {
    const m = tex.match(/\\(paren|fillin)(?![a-zA-Z])/)
    if (m) bad.push(tex.slice(0, 80))
  }
  return bad
}

const files = fs.existsSync(OUT)
  ? fs.readdirSync(OUT).filter((f) => f.endsWith('.tex')).sort()
  : []
if (!files.length) {
  console.log(`没有产物：${OUT}`)
  process.exit(1)
}

let nQ = 0, nMath = 0, bad = 0
const fails = []
const inMath = []

for (const f of files) {
  const src = fs.readFileSync(path.join(OUT, f), 'utf8')
  const qs = src.split('\\begin{question}').slice(1)
  for (const raw of qs) {
    const body = raw.split('\\end{question}')[0]
    const meta = (raw.match(/%% @q (\{.*\})/) || [])[1]
    let key = f
    try { key = JSON.parse(meta).key } catch { /* 元数据坏了另算 */ }
    nQ++
    // 先按**前端同一条路**处理，再取公式
    const shown = stripAnswers(body)
    for (const s of slotsInMath(stripEnvs(body))) inMath.push([key, s])
    for (const [tex, display] of mathsOf(stripEnvs(shown))) {
      nMath++
      try {
        katex.renderToString(tex, {
          displayMode: display, throwOnError: true, strict: false,
          trust: true, macros: MACROS,
        })
      } catch (e) {
        bad++
        fails.push([key, tex.slice(0, 90), String(e.message || e).slice(0, 80)])
      }
    }
    // 泄漏检查：题干/选项正文里不该出现 choices/enumerate 之外的块级语法
    const plain = stripEnvs(shown).replace(/\$[^$]*\$/g, '')
    if (LEAK.test(plain)) {
      bad++
      fails.push([key, '正文泄漏块级语法', plain.match(LEAK)[0]])
    }
  }
}

console.log(`赵礼显讲义 KaTeX 检查：${files.length} 个文件，${nQ} 道题，${nMath} 段公式`)
for (const [key, tex, msg] of fails.slice(0, 40)) {
  console.log(`  ✗ ${key}\n      ${JSON.stringify(tex)}\n      ${msg}`)
}
if (fails.length > 40) console.log(`  … 其余 ${fails.length - 40} 处`)
console.log(bad === 0 ? '✓ 全部渲染通过' : `✗ ${bad} 处渲染失败`)

// 空位在数学模式里：KaTeX 这一层**看不出来**（`\paren` 已经被换成 `（　　）`），
// 但规范上就是坏的，单独列出来交给 `verify` 处理。
if (inMath.length) {
  console.log(`\n⚠️ 空位落在数学模式里 ${inMath.length} 处（规范 §2.2 不允许）：`)
  for (const [key, s] of inMath.slice(0, 20)) console.log(`  ${key}  ${JSON.stringify(s)}`)
  if (inMath.length > 20) console.log(`  … 其余 ${inMath.length - 20} 处`)
}
process.exit(bad === 0 && inMath.length === 0 ? 0 : 1)
