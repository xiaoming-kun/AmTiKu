/** 讲义编辑器的共享件：类型、常量、渲染组件。
 *
 *  从 App.tsx 抽出来的（代码审查 CPLX-1 / REACT-4：编辑器相关代码
 *  挤在一个文件里，App.tsx 一度 4700 行）。
 *  这里都是**纯展示 / 纯函数**，不带状态 —— 状态在 CanvasEditor 里。
 */
import { useMemo } from 'react'
import katex from 'katex'
import { transformStem, transformOption } from '@/lib/qlatex'
import type { Q } from '@/lib/types'

/** 轻量 LaTeX 渲染：把 $行内$ 与 $$独立$$ 转成 KaTeX。 */
/** 题干 → 纯文字（侧边栏列表用）。
 *
 *  列表里显示 LaTeX 源码（`$PA\\perp$ 底面`）很难读，
 *  去掉命令、图片标签、$ 定界符，只留文字。
 */
export function plainStem(stem: string): string {
  return String(stem || '')
    .replace(/<img[^>]*>/g, '［图］')
    .replace(/\\includegraphics\s*(?:\[[^\]]*\])?\s*\{[^}]+\}/g, '［图］')
    .replace(/\$\$?/g, '')
    .replace(/\\[a-zA-Z]+\s*/g, '')
    .replace(/[{}]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80)
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
  type: string        // chapter|section|point|text|formula|question|blank
  text?: string
  key?: string
  x: number; y: number; w: number; h: number
  z?: number
  fontSize?: number
  lineHeight?: number  // 行距倍数，空=默认 DEFAULT_LH
  headers?: string[]   // 表格：表头
  rows?: string[][]    // 表格：数据行
}

/* ══ 调参常量 ══════════════════════════════════════
   审查报告 RDY-3：这些数字原来散落在代码里、没有名字，
   改的时候要靠搜索猜含义。集中到这里。 */
export const SEARCH_DEBOUNCE_MS = 350      // 搜索防抖（输入停顿多久才发请求）
export const POINT_LIMIT = 5000            // 单个考点一次拉多少（最大考点 717 道）
export const MEASURE_DELAY_MS = 120        // 内容测量延迟（等 DOM 稳定）
export const FIT_MIN = 0.4                 // 自动缩放下限（再小就没法看了）
export const FIT_MARGIN = 0.015            // 适配时页底保留的空白比例
export const RESIZE_SLACK_PCT = 0.6        // 缩放下限余量（%），防正好卡住文字
export const DEFAULT_Q_W = 92              // 题目块默认宽（%）
export const DEFAULT_Q_X = 4               // 题目块默认左边距（%）

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
  '16:9': { w: 16, h: 9 },
  a4: { w: 210, h: 297 },
  '4:3': { w: 4, h: 3 },
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

export function QuestionRow({ q, onAdd }: { q: Q; onAdd: () => void }) {
  const label = useMemo(() => {
    const k = q.key || ''
    const hit = stemCache.get(k)
    if (hit) return hit
    const txt = plainStem(q.stem || k)
    if (stemCache.size > 3000) stemCache.clear()      // 简单上限，防无限增长
    stemCache.set(k, txt)
    return txt
  }, [q.key, q.stem])

  return (
    <div onClick={onAdd} title="点击加入画布"
      className="mb-1 cursor-pointer rounded-lg border border-border bg-bg px-2 py-1.5
                 text-[11px] hover:border-brand/40 hover:bg-surface">
      <div className="line-clamp-2 text-ink-soft">{label}</div>
    </div>
  )
}

export function CBlockView({ b, qmap, fs }:
  { b: CBlock; qmap: Map<string, Q>; fs: number }) {
  const lh = b.lineHeight ?? DEFAULT_LH
  const q = b.type === 'question' ? qmap.get(b.key || '') : undefined

  // 转换结果记忆化：LaTeX→markdown 是几十条正则的流水线，
  // 原来**每次渲染都重算**（画布每块 + 离屏探针各一遍，审查报告 PERF-1）
  const stemText = useMemo(() => (q ? transformStem(q.stem || '') : ''), [q])
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
    return (
      <div className="p-ex" style={{ margin: 0, fontSize: fs, lineHeight: lh }}>
        <MarkdownBody text={stemText} />
        {!!opts.length && (
          // 选项不换行：拉宽块时字号自动变大，一行能放下
          <div className="mt-1 flex flex-nowrap gap-x-3" style={{ fontSize: fs * 0.92 }}>
            {opts.map((o, oi) => (
              <span key={o.label}>
                <span>({o.label})</span>
                <RichText text={optTexts[oi] || ''} />
              </span>
            ))}
          </div>
        )}
      </div>
    )
  }
  return <div className="p-t" style={{ margin: 0, fontSize: fs, lineHeight: lh }}>
    <RichText text={b.text || '正文'} /></div>
}
