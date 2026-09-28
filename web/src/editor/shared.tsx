/** 讲义编辑器的共享件：类型、常量、渲染组件。
 *
 *  从 App.tsx 抽出来的（代码审查 CPLX-1 / REACT-4：编辑器相关代码
 *  挤在一个文件里，App.tsx 一度 4700 行）。
 *  这里都是**纯展示 / 纯函数**，不带状态 —— 状态在 CanvasEditor 里。
 */
import { useMemo, useState } from 'react'
import { ChevronDown, Plus } from 'lucide-react'
import katex from 'katex'
import { transformStem, transformOption } from '@/lib/qlatex'
import { renderBlocks } from '@/lib/render'
import type { Block } from '@/lib/render'
import type { Q } from '@/lib/types'

/** 轻量 LaTeX 渲染：把 $行内$ 与 $$独立$$ 转成 KaTeX。 */
/** 常见数学记号 → 看得懂的文字（左栏列表专用）。
 *
 *  不映射就会**丢掉**：`$x\\in(-1,1)$` 变成 `x(-1,1)`、`$\\paren[D]$` 变成 `[D]`，
 *  老师没法拿它认题。这里只求「读得通」，不追求排版正确。 */
const PLAIN_SYM: Record<string, string> = {
  in: '∈', notin: '∉', cup: '∪', cap: '∩', subset: '⊂', subseteq: '⊆',
  le: '≤', leq: '≤', ge: '≥', geq: '≥', ne: '≠', neq: '≠', equiv: '≡',
  pm: '±', mp: '∓', times: '×', div: '÷', cdot: '·', ast: '∗',
  alpha: 'α', beta: 'β', gamma: 'γ', theta: 'θ', lambda: 'λ', mu: 'μ',
  pi: 'π', rho: 'ρ', sigma: 'σ', phi: 'φ', varphi: 'φ', omega: 'ω', Delta: 'Δ',
  infty: '∞', angle: '∠', triangle: '△', perp: '⊥', parallel: '∥',
  forall: '∀', exists: '∃', to: '→', rightarrow: '→', Rightarrow: '⇒',
  leftrightarrow: '⇔', int: '∫', sum: '∑', prod: '∏', sqrt: '√', circ: '°',
  cdots: '⋯', dots: '…', ldots: '…', qquad: ' ', quad: ' ',
  // 函数名：原样留着，别让 `g(x)=\cos x` 变成 `g(x)= x`
  sin: 'sin', cos: 'cos', tan: 'tan', cot: 'cot', sec: 'sec', csc: 'csc',
  arcsin: 'arcsin', arccos: 'arccos', arctan: 'arctan', ln: 'ln', log: 'log',
  lg: 'lg', exp: 'exp', lim: 'lim', max: 'max', min: 'min', det: 'det',
}

/** 题干 → 纯文字（左栏列表用）。
 *
 *  列表里显示 LaTeX 源码（`$PA\\perp$ 底面`）很难读，
 *  去掉命令、图片标签、$ 定界符，只留文字。
 *
 *  ⚠️ 这里**只服务「认题」**，不做也不该做真正的 LaTeX 解析
 *  （题目的事实来源是 `amti/latex_ir.py`）。所以**不截断** ——
 *  截多少由卡片的 CSS 决定，展开时才看得到完整的题。
 */
export function plainStem(stem: string): string {
  return String(stem || '')
    .replace(/<img[^>]*>/g, '［图］')
    .replace(/\\includegraphics\s*(?:\[[^\]]*\])?\s*\{[^}]+\}/g, '［图］')
    // TikZ 图：整段收成「［图］」，别把源码摊在列表里
    .replace(/\\begin\{(tikzpicture|axis|scope)\}(\[[^\]]*\])?[\s\S]*?\\end\{\1\}/g, '［图］')
    .replace(/\\(?:d|t)?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, '$1/$2')
    // 填空处 `\paren[D]`：括号里那个字母是答案，列表只留空括号
    .replace(/\\paren\s*\[[^\]]*\]/g, '（　）')
    .replace(/\\([a-zA-Z]+)(\s*)/g, (_m, name: string, sp: string) => (PLAIN_SYM[name] ?? '') + sp)
    .replace(/\$\$?/g, '')
    .replace(/[{}]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** 把 markdown 表格切成「文本段 + 表格段」，其余原样。 */
export function splitTables(text: string): { type: 'text' | 'table' | 'image'; rows?: string[][]; body?: string }[] {
  const lines = String(text || '').split('\n')
  const out: { type: 'text' | 'table' | 'image'; rows?: string[][]; body?: string }[] = []
  let buf: string[] = []
  let i = 0
  const isRow = (l: string) => /^\s*\|.*\|\s*$/.test(l)
  const isSep = (l: string) => /^\s*\|[\s:|-]+\|\s*$/.test(l)
  const isImg = (l: string) => {
    const t = l.trim()
    return /^<img\s/i.test(t) || /^!\[[^\]]*\]\([^)]+\)$/.test(t)
  }

  const flush = () => {
    if (buf.length) { out.push({ type: 'text', body: buf.join('\n') }); buf = [] }
  }

  while (i < lines.length) {
    // 图片行：单独成段并居中
    if (isImg(lines[i])) {
      flush()
      out.push({ type: 'image', body: lines[i].trim() })
      i++
      continue
    }
    // 表格 = 行 | 分隔行 | 若干行
    if (isRow(lines[i]) && i + 1 < lines.length && isSep(lines[i + 1])) {
      flush()
      const rows: string[][] = []
      const cells = (l: string) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
      rows.push(cells(lines[i]))
      i += 2
      while (i < lines.length && isRow(lines[i])) { rows.push(cells(lines[i])); i++ }
      out.push({ type: 'table', rows })
      continue
    }
    buf.push(lines[i])
    i++
  }
  flush()
  return out
}

/** 渲染题干：markdown 表格 → 真表格；其余 → KaTeX。
 *
 *  为什么需要：RichText 只做 KaTeX，不解析 markdown。
 *  后端导出走 Slidev 的 markdown 解析器（表格正常），
 *  编辑器没有解析器，表格会显示成 `| a | b |` 纯文本（用户实测发现）。
 */
export function MarkdownBody({ text, className = '' }: { text: string; className?: string }) {
  const parts = useMemo(() => splitTables(text), [text])
  return (
    <div className={className}>
      {parts.map((p, i) =>
        p.type === 'image' ? (
          <div key={i} style={{ textAlign: 'center', margin: '6px 0' }}>
            {(() => {
              const raw = p.body || ''
              const m1 = raw.match(/^<img[^>]*src=["']([^"']+)["']/i)
              const m2 = raw.match(/^!\[[^\]]*\]\(([^)]+)\)$/)
              const src = m1 ? m1[1] : (m2 ? m2[1] : '')
              return src ? (
                <img src={src} alt=""
                  style={{ maxWidth: '55%', maxHeight: 210, width: 'auto',
                           height: 'auto', display: 'inline-block' }} />
              ) : null
            })()}
          </div>
        ) : p.type === 'table' ? (
          <table key={i} className="p-ex"
                 style={{ borderCollapse: 'collapse', width: '100%',
                          fontSize: '0.94em', margin: '4px 0' }}>
            <tbody>
              {(p.rows || []).map((row, ri) => (
                <tr key={ri}>
                  {row.map((c, ci) => (
                    <td key={ci}
                      style={{ border: '1px solid #555', padding: '3px 7px',
                               background: 'transparent',
                               fontWeight: ri === 0 ? 700 : undefined,
                               textAlign: ri === 0 ? 'center' : undefined,
                               borderBottom: ri === 0 ? '2px solid #555' : undefined }}>
                      <RichText text={c} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <span key={i}><RichText text={p.body || ''} /></span>
        ),
      )}
    </div>
  )
}

export function RichText({ text, className = '' }: { text: string; className?: string }) {
  const html = useMemo(() => {
    const esc = (x: string) => x.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const parts = String(text || '').split(/(\$\$[\s\S]+?\$\$)/)
    return parts.map((seg) => {
      const dm = seg.match(/^\$\$([\s\S]+?)\$\$$/)
      if (dm) {
        try { return katex.renderToString(dm[1], { displayMode: true, throwOnError: false }) }
        catch { return esc(seg) }
      }
      return seg.split(/(\$[^$]+?\$)/).map((t) => {
        const im = t.match(/^\$([^$]+?)\$$/)
        if (im) {
          try { return katex.renderToString(im[1], { displayMode: false, throwOnError: false }) }
          catch { return esc(t) }
        }
        return esc(t)
      }).join('')
    }).join('')
  }, [text])
  // ⚠️ 信任边界（代码审查 SEC-1）：这里的 __html 由**自有题库**的文本拼成 ——
  //   纯文本段经 esc() 转义 & < >，数学段来自 KaTeX（默认 trust:false，
  //   不会生成可执行标记）。**若将来题干来源外部化**（导入他人题库、
  //   OCR 录入、AI 生成），必须先接 DOMPurify 过滤再注入
  //   （dompurify 已在依赖里，可直接用）。
  return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />
}

// ══════════════════════════════════════════════════════════════
//  讲义编辑器 —— 画布式自由排版
//
//  交互：
//    · 左栏按考点展开选题目 → 点一下加入画布
//    · 画布上拖动/缩放块，右侧改字号/行距
//    · 内容超出一页时自动等比缩小（fit）
// ══════════════════════════════════════════════════════════════

export type CBlock = {
  id: string
  type: string        // chapter|section|point|text|formula|table|emoji|blank|question|klist
  text?: string
  key?: string
  x: number; y: number; w: number; h: number
  z?: number
  fontSize?: number
  lineHeight?: number  // 行距倍数，空=默认 DEFAULT_LH
  headers?: string[]   // 表格：表头
  rows?: string[][]    // 表格：数据行
  showSource?: boolean // 高考题是否标出处（不设则跟讲义级开关）
  /** 知识清单讲解块：来源节点 id，以及**块级 IR 快照**。
   *
   *  快照（而不是运行时按 id 去查）是刻意的：讲义是**成品**，不该因为
   *  书被重新生成、节点被改名就变样；导出也因此不依赖书在不在。
   *  `text` 存节点标题，属性栏显示用。 */
  nid?: string
  ir?: Block[]
}

/* ══ 调参常量 ══════════════════════════════════════
   审查报告 RDY-3：这些数字原来散落在代码里、没有名字，
   改的时候要靠搜索猜含义。集中到这里。 */
export const SEARCH_DEBOUNCE_MS = 350      // 搜索防抖（输入停顿多久才发请求）
export const POINT_PAGE = 1000              // 单次请求上限（后端 limit ≤ 1000）
export const POINT_MAX = 3000               // 一个考点最多取这么多（最大考点实测 717）
export const MEASURE_DELAY_MS = 120        // 内容测量延迟（等 DOM 稳定）
export const FIT_MIN = 0.4                 // 自动缩放下限（再小就没法看了）
export const FIT_MARGIN = 0.015            // 适配时页底保留的空白比例
export const RESIZE_SLACK_PCT = 0.6        // 缩放下限余量（%），防正好卡住文字
export const DEFAULT_Q_W = 92              // 题目块默认宽（%）
export const DEFAULT_Q_X = 4               // 题目块默认左边距（%）
export const DEFAULT_Y = 6                 // 新块的默认顶边（%，当前页还空着时）
export const GAP_PCT = 1.5                 // 自动往下排时，块与块之间留的空（%）

/** 块的本地唯一 id（只在前端用，导出时剥掉） */
export const uid = () => Math.random().toString(36).slice(2, 10)

export const CB_TYPES: { v: string; label: string; hint: string }[] = [
  { v: 'chapter', label: '一级标题', hint: '手写体 + 荧光笔' },
  { v: 'section', label: '二级标题', hint: '稍小 + 荧光笔' },
  { v: 'point', label: '知识点', hint: '红点 + 文字' },
  { v: 'text', label: '正文', hint: '讲解文字，支持 $公式$' },
  { v: 'formula', label: '公式', hint: '独立公式 $$...$$' },
  { v: 'table', label: '表格', hint: '对比表格，表头黄底' },
  { v: 'emoji', label: '表情', hint: '大号表情标记（难度/易错）' },
  { v: 'blank', label: '留白', hint: '占位空白区' },
]

/** 块类型 → 中文名（选中时显示在属性栏）。
 *
 *  `CB_TYPES` 是「工具栏上能手动加的块」；`klist`（知识清单讲解块）只能从
 *  左栏插入，放进菜单里就成了"能加一个空讲解"这种没意义的操作。
 *  但它被选中时仍要有个人话名字，所以标签在这里合一次。
 */
export const BLOCK_LABEL: Record<string, string> = {
  ...Object.fromEntries(CB_TYPES.map((k) => [k.v, k.label])),
  klist: '知识清单',
}

/** 可选字体（标题 / 正文）。
 *
 *  都是 macOS + 已安装的开源字体，导出时能正确嵌入 PDF。
 *  value 是 CSS font-family，label 是界面显示名。
 */
export const TITLE_FONTS = [
  { v: '"Source Han Sans SC", "PingFang SC", sans-serif', label: '思源黑体（印刷感，默认）' },
  { v: '"LXGW ZhenKai GB", "Xingkai SC", serif', label: '霞鹜臻楷（书法感）' },
  { v: '"Alibaba PuHuiTi 3.0", "PingFang SC", sans-serif', label: '阿里巴巴普惠体' },
  { v: '"HanziPen SC", "Xingkai SC", cursive', label: '翩翩体（手写）' },
  { v: '"PingFang SC", "Heiti SC", sans-serif', label: '苹方（系统黑体）' },
  { v: '"Songti SC", "STSong", serif', label: '宋体' },
  { v: '"Kaiti SC", "STKaiti", serif', label: '楷体' },
]

export const BODY_FONTS = [
  { v: '"LXGW WenKai GB", "LXGW WenKai", serif', label: '霞鹜文楷（默认）' },
  { v: '"Source Han Serif SC", "Songti SC", serif', label: '思源宋体' },
  { v: '"Source Han Sans SC", "PingFang SC", sans-serif', label: '思源黑体' },
  { v: '"Songti SC", "STSong", serif', label: '宋体' },
  { v: '"Kaiti SC", "STKaiti", serif', label: '楷体' },
  { v: '"PingFang SC", "Heiti SC", sans-serif', label: '苹方' },
]

export const DEFAULT_TITLE_FONT = TITLE_FONTS[0].v
export const DEFAULT_BODY_FONT = BODY_FONTS[0].v

/** 一数常用的难度/提示表情 */
export const EMOJIS = [
  ['😡', '易错'], ['🤯', '难点'], ['🤮', '恶心'], ['😭', '易丢分'],
  ['⭐', '重点'], ['🎯', '必考'], ['💡', '技巧'], ['⚠️', '注意'],
  ['✅', '正确'], ['❌', '错误'], ['📌', '记牢'], ['🔥', '高频'],
]

export const RATIO_BOX: Record<string, { w: number; h: number }> = {
  '16:9': { w: 16, h: 9 },          // 讲课、录屏
  a4: { w: 210, h: 297 },           // 打印、发学生（竖版）
  '4:3': { w: 4, h: 3 },            // iPad 12.9″/13″/10.2″ 等（也是老式投影）
  // iPad 11″ / 10.9″（Air、iPad 10/11、Pro 11）：2360×1640 ≈ 1.439
  // 16:9 投到 iPad 上上下留黑边，看着"不伦不类"——这个铺满
  ipad11: { w: 2360, h: 1640 },
}

/** 块的字号基准值（与后端 _font_size 的默认值保持一致）。
 *
 *  ⚠️ 刻意**不按块宽缩放**：拉宽文本框时字号不该变（PPT 的行为）。
 *     用户要改字号就用右侧属性面板，不要让它自己算。
 */
export const DEFAULT_FS = 16          // 默认字号（与后端 DEFAULT_FS 一致）
export const DEFAULT_LH = 2.0         // 默认行距（与后端 DEFAULT_LH 一致）

/** 块最终字号：手动设的优先，否则用默认值 */
export function blockFontSize(b: CBlock): number {
  return b.fontSize ?? DEFAULT_FS
}

/** 块在画布上的呈现（用模板类，与导出完全一致） */
/** 题目列表行 —— 「已选 / 搜索 / 考点抽屉」三处共用。
 *
 *  原来这三段 JSX 逐字重复（审查报告 DUP-1），改样式要改三遍。
 *  `plainStem` 结果按 key 缓存：展开 717 道的考点时省下大量正则。
 */
export const stemCache = new Map<string, string>()

export function QuestionRow({ q, onAdd, onOpen }: {
  q: Q; onAdd: () => void; onOpen: () => void
}) {
  // 认题要先看得见题：默认给 4 行，还想看全就点开（不点开不影响左边栏的速度）
  const [open, setOpen] = useState(false)
  const label = useMemo(() => {
    const k = q.key || ''
    const hit = stemCache.get(k)
    if (hit) return hit
    const txt = plainStem(q.stem || k)
    if (stemCache.size > 3000) stemCache.clear()      // 简单上限，防无限增长
    stemCache.set(k, txt)
    return txt
  }, [q.key, q.stem])

  // 分工：**点题干 = 看整道题**（右侧弹出详情，跟主页面同一个组件），
  // 「+」= 直接加进画布。以前整张卡都是「加入画布」，想看一眼全题没地方看。
  return (
    <div className="group flex items-start gap-1.5 rounded-lg border border-border
                    bg-surface px-3 py-2 transition-colors
                    hover:border-brand-line hover:bg-brand-soft/40">
      <button onClick={onOpen} title="点击查看整道题（题干 / 答案 / 解析）"
        className={`min-w-0 flex-1 text-left text-[12.5px] leading-[1.5] text-ink-soft
                    transition-colors group-hover:text-ink ${open ? '' : 'line-clamp-4'}`}>
        {label}
      </button>
      {/* 展开/收起：常驻会挤掉题干，只在悬停或已展开时露出来 */}
      <button onClick={() => setOpen((o) => !o)}
        title={open ? '收起题干' : '展开完整题干'}
        className={`mt-[2px] grid h-6 w-5 shrink-0 place-items-center rounded-md
                    text-ink-faint transition-opacity duration-150
                    hover:bg-muted hover:text-brand
                    ${open ? '' : 'opacity-0 group-hover:opacity-100'}`}>
        <ChevronDown size={13}
          className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      {/* 加进画布 —— 这是这张卡片的**主操作**，所以常驻 + 实心品牌色圆钮：
          以前 12px、只有悬停才淡出来，既小又找不着（用户：「这个加号要大一点」
          「重点突出一下」） */}
      <button onClick={onAdd} title="加入画布"
        className="press mt-[1px] grid h-[26px] w-[26px] shrink-0 place-items-center
                   rounded-full bg-brand text-white shadow-[var(--shadow-brand)]
                   hover:brightness-110">
        <Plus size={16} strokeWidth={2.8} />
      </button>
    </div>
  )
}

/** 模拟题出处名的脏数据过滤器（与后端 `_LABEL_JUNK` 必须一致）。
 *  老数据的 `meta.source_label` 常是卷头/页码（「满分：150 分…」「004」）。 */
const LABEL_JUNK = /满分|考试时间|共\s*\d+\s*页|第\s*\d+\s*页|答题卡|评分标准|参考答案|须知|^\s*\d+\s*$/

/** 把出处名洗干净：去扩展名、去 `_images` 这种录入后缀、去首尾符号 */
function cleanHead(s: any): string {
  return String(s ?? '').trim().replace(/\.(pdf|docx?)$/i, '')
    .replace(/_images/g, '').replace(/^[\s_\-—·、]+|[\s_\-—·、]+$/g, '')
}

/** 模拟题的出处名；取不到详细信息就用「精选模拟题」（与后端 `_sim_head` 一致） */
function simHead(q: Q): string {
  const key = String(q.key || '')
  if (key.startsWith('模拟题/') && key.includes('#')) {
    const head = cleanHead(key.split('/').slice(1).join('/').split('#')[0])
    if (head && !LABEL_JUNK.test(head)) return head
  }
  const meta = (q.meta || {}) as Record<string, any>
  let head = cleanHead(meta.source_label)
  if (head && !LABEL_JUNK.test(head) && head.length <= 40) return head
  head = cleanHead(key.includes('/') ? key.split('/')[0] : '')
  if (head && !LABEL_JUNK.test(head) && head.length >= 4 && head.length <= 40
      && /[\u4e00-\u9fff]/.test(head)) return head
  return '精选模拟题'
}

/** 出处标签：高考「2024新高考I卷 第1题」；模拟「卷名 第N题」/「精选模拟题 第N题」。
 *
 *  ⚠️ 与后端 `slidev_handout.source_label()` **必须保持一致** ——
 *  预览和导出不一致是本项目反复踩的坑（`测试/讲义测试.py` 会逐题比对）。
 */
export function sourceLabel(q: Q | undefined): string {
  if (!q) return ''
  const key = String(q.key || '')
  const no = key.includes('#') ? key.split('#').pop()!.trim() : ''
  if (q.kind === '高考') {
    const meta = (q.meta || {}) as Record<string, any>
    let region = String(meta.region || '').trim()
    if (!region && key.includes('/')) {
      const parts = key.split('/')
      if (parts.length >= 3) region = parts[parts.length - 1].split('#')[0].trim()
    }
    const year = String(meta.year || '').trim()
    const head = `${year}${region}`
    if (!head && !no) return ''
    return no ? `${head} 第${no}题` : head
  }
  if (q.kind === '模拟') {
    const head = simHead(q)
    return no ? `${head} 第${no}题` : head
  }
  return ''
}

/** 选项尺寸：**必须与后端 option_html() 一致**
 *  （后端：max-height:108px; max-width:22%）。 */
const OPT_IMG_STYLE = {
  // ⚠️ display 必须是 inline-block：Slidev 的 CSS reset 让 `img` 变 block，
  //    不加就会「预览一行、导出四行」。尺寸与后端 option_html() 保持一致。
  display: 'inline-block',
  maxHeight: 108,
  width: 'auto',
  height: 'auto',
  verticalAlign: 'middle',
} as const

/** 选项内容：文字 + 图片混排。
 *
 *  选项常常**整条就是一张图**（四个图象选项），而 RichText 只认行内公式、
 *  不认图片 —— 直接塞给它会把 `![](...)` 当文字显示出来。
 *  所以这里把 markdown 图片/`<img>` 切成片段，图片用真 `<img>` 渲染。
 */
export function OptionBody({ text }: { text: string }) {
  const parts = useMemo(() => {
    const out: { kind: 'text' | 'img'; v: string }[] = []
    // 与 transformOption 的产物对应：![alt](url)，同时兼容 <img src="...">
    const re = /!\[[^\]]*\]\(([^)]+)\)|<img[^>]*src="([^"]+)"[^>]*\/?>/g
    let last = 0
    for (let m = re.exec(text); m; m = re.exec(text)) {
      if (m.index > last) out.push({ kind: 'text', v: text.slice(last, m.index) })
      out.push({ kind: 'img', v: m[1] || m[2] || '' })
      last = m.index + m[0].length
    }
    if (last < text.length) out.push({ kind: 'text', v: text.slice(last) })
    return out
  }, [text])
  return (
    <>
      {parts.map((p, i) => p.kind === 'img'
        ? <img key={i} src={p.v} alt="" style={OPT_IMG_STYLE} />
        : <RichText key={i} text={p.v} />)}
    </>
  )
}

export function CBlockView({ b, qmap, fs, withAnswers = false }:
  { b: CBlock; qmap: Map<string, Q>; fs: number; withAnswers?: boolean }) {
  const lh = b.lineHeight ?? DEFAULT_LH
  const q = b.type === 'question' ? qmap.get(b.key || '') : undefined

  // 转换结果记忆化：LaTeX→markdown 是几十条正则的流水线，
  // 原来**每次渲染都重算**（画布每块 + 离屏探针各一遍，审查报告 PERF-1）
  /** 「显示答案」**必须传进 `transformStem` 的第二参**，不能事后补。
   *
   *  `transformStem(stem, withAnswers=false)` 内部就是
   *  `withAnswers ? showAnswers(t) : stripAnswers(t)`——**默认那一支会把答案剥掉**。
   *  所以先 `transformStem(…)`（答案已经没了）再 `showAnswers(…)` 是白搭：
   *  宏早被吃掉，后面找不到任何东西。这就是「勾了没反应」的真正原因。 */
  const stemText = useMemo(
    () => (q ? transformStem(q.stem || '', withAnswers) : ''), [q, withAnswers])
  const optTexts = useMemo(
    () => (q?.options || []).map((o) => transformOption(o.text || '')),
    [q])

  if (b.type === 'chapter') {
    return <div className="p-hand" style={{ margin: 0, fontSize: fs, lineHeight: lh }}>
      <span className="p-hl">{b.text || '一级标题'}</span></div>
  }
  if (b.type === 'section') {
    return <div className="p-sec" style={{ margin: 0, fontSize: fs, lineHeight: lh }}>
      <span className="p-hl">{b.text || '二级标题'}</span></div>
  }
  if (b.type === 'point') {
    return <div className="p-tag" style={{ margin: 0, fontSize: fs, lineHeight: lh }}>
      {b.text || '知识点'}</div>
  }
  if (b.type === 'formula') {
    return <div className="p-t" style={{ margin: 0, fontSize: fs, lineHeight: lh }}>
      <RichText text={b.text || '$$公式$$'} /></div>
  }
  if (b.type === 'table') {
    const hs = b.headers || []
    const rs = b.rows || []
    return (
      <table className="p-ex"
             style={{ borderCollapse: 'collapse', width: '100%',
                      fontSize: fs, lineHeight: 1.6 }}>
        {!!hs.length && (
          <tr>
            {hs.map((h, i) => (
              <th key={i} style={{ padding: '4px 8px' }}>
                <RichText text={transformOption(h || '')} /></th>
            ))}
          </tr>
        )}
        {rs.map((row, ri) => (
          <tr key={ri}>
            {row.map((v, ci) => (
              <td key={ci} style={{ padding: '4px 8px' }}>
                <RichText text={transformOption(v || '')} /></td>
            ))}
          </tr>
        ))}
      </table>
    )
  }
  if (b.type === 'emoji') {
    return <div style={{ fontSize: fs * 4, lineHeight: 1.1,
                         textAlign: 'center' }}>{b.text || '😡'}</div>
  }
  if (b.type === 'blank') {
    return <div className="h-full w-full rounded border border-dashed border-black/10" />
  }
  if (b.type === 'question') {
    if (!q) return <div className="text-[11px] text-ink-faint">题目（{b.key}）</div>
    const opts = (q.options || []) as any[]
    // 关键：必须走 transformStem/transformOption —— 题库是 LaTeX + newtxmath，
    // 原始题干里的 \paren[A]、\symbfit、enumerate 等 KaTeX 不认，
    // 直接渲染会显示成源码（前端包必须重新构建才生效）
    // 出处**一律标**（用户：所有题目都有出处，这个没有关掉的必要）
    const lab = sourceLabel(q)
    // 出处**并进题干同一行**（用户要求：括号 + 与题目同排）。
    // ⚠️ 必须是纯文本，不能用 <span>：MarkdownBody 不解析 HTML，
    //    用 span 会变成"预览有、导出没有"（本项目最忌讳的不一致）。
    const text = lab ? `（${lab}）${stemText}` : stemText
    return (
      <div className="p-ex" style={{ margin: 0, fontSize: fs, lineHeight: lh }}>
        <MarkdownBody text={text} />
        {!!opts.length && (
          // 选项不换行：拉宽块时字号自动变大，一行能放下
          // 选项走**普通内联流**（不用 flex）：flex 容器里 markdown 段落会变成
          // 被压窄的 flex item，图片选项会小到 13px 且各占一行（用户报的 bug）。
          <div className="mt-1" style={{ fontSize: fs * 0.92 }}>
            {opts.map((o, oi) => (
              <span key={o.label} className="mr-5 whitespace-nowrap">
                <span>({o.label})</span>
                <OptionBody text={optTexts[oi] || ''} />
              </span>
            ))}
          </div>
        )}
      </div>
    )
  }
  if (b.type === 'klist') {
    // 知识清单讲解块：**整段讲解一个块**（图/表/公式一起搬过来）。
    // 渲染直接交给题库题目用的同一个 IR 渲染器 —— 前端没有第二套解析。
    // `kl-body`：把书里那种"文字表"的排版口径拉回与导出一致，见 index.css。
    return (
      <div className="kl-body" style={{ margin: 0, fontSize: fs * 0.92, lineHeight: lh }}>
        {b.ir?.length
          ? renderBlocks(b.ir)
          : <span className="text-[11px] text-ink-faint">
              讲解「{b.nid || '?'}」没有正文
            </span>}
      </div>
    )
  }
  return <div className="p-t" style={{ margin: 0, fontSize: fs, lineHeight: lh }}>
    <RichText text={b.text || '正文'} /></div>
}
