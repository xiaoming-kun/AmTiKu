/**
 * AmTiKu · 块级 IR → React
 *
 * **这里不解析 LaTeX。** 解析在 Python 那边（`amti/latex_blocks.py`），
 * 前端只把已经切好的块画出来，公式交给 KaTeX。分工定死：
 *
 *     Python 解析一次 → 块级 IR → 前端只负责画
 *
 * 为什么改成这样
 * --------------
 * 这里原本自己写了一份 LaTeX→HTML 解析器，实测至少错四处，全是真实报障：
 *   1. 环境结束位置少算一个字符   → 答案末尾漏出孤零零的 `}`
 *   2. 不跳过 `tabular` 的列格式  → 表格第一行变成 `{|c|cccccccccc|}`
 *   3. `\item` 无脑切分，不认嵌套 → 内层列表被拍平、`\end{enumerate}` 漏到页面
 *   4. `center`/`minipage` 没处理 → `\begin{center}` 当正文显示
 *
 * 全量库 20706 题里 25.1% 带列表、2.3% 带表格。在前端打补丁是追不平的，
 * 所以语法解析整体收回 Python，前端不再碰。
 */
import { useMemo, useState } from 'react'
import katex from 'katex'
import type { ReactNode } from 'react'
import { send } from '@/lib/api'

/* ══ IR 类型（对应 amti/latex_blocks.py 的输出） ═══════════ */

export type Inline =
  | { t: 's'; s: string }
  | { t: 'm'; s: string; display?: boolean }
  | { t: 'fig'; id: string; width: string }
  | { t: 'blank' }
  | { t: 'paren' }
  | { t: 'br' }
  | { t: 'sp' }
  | { t: 'raw'; s: string }

export type Cell = { in?: Inline[]; blocks?: Block[]; span: number }

export type Block =
  | { t: 'p'; in: Inline[] }
  | { t: 'math'; tex: string; display: boolean }
  | { t: 'list'; ordered: boolean; items: Block[][] }
  | { t: 'table'; rows: Cell[][]; env: string }
  | { t: 'box'; kind: string; width?: string | null; blocks: Block[] }
  | { t: 'fig'; id: string; width: string }
  | { t: 'raw'; env?: string; tex: string }

/* ══ 公式 ═════════════════════════════════════════════════ */

/** 旧项目踩过的坑：这些宏 KaTeX 不认，会在页面上显示成红字源码。 */
const MACROS: Record<string, string> = {
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

function Math({ tex, display }: { tex: string; display: boolean }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(tex, {
        displayMode: display,
        throwOnError: false,
        strict: false,
        trust: true,
        macros: MACROS,
      })
    } catch {
      return null
    }
  }, [tex, display])

  if (html == null) return <code className="latex-err">{tex}</code>
  // KaTeX 的输出由本地库生成，内容来自题库，不经过用户输入
  return <span dangerouslySetInnerHTML={{ __html: html }} />
}

/* ══ 行内 ═════════════════════════════════════════════════ */

/** TikZ 在 HTML 里画不了：点一下交给后端渲成 PNG，再审图。 */
function TikzRaw({ tex }: { tex: string }) {
  const [src, setSrc] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const load = async () => {
    if (busy || !tex.trim()) return
    setBusy(true); setErr('')
    try {
      const r: any = await send('/api/tikz/render', 'POST', { tex })
      setSrc(`/api/figure?path=${encodeURIComponent(r.path)}`)
    } catch (e) {
      setErr(String((e as any)?.message || e))
    } finally { setBusy(false) }
  }
  return (
    <div className="q-raw">
      <span className="q-raw-tag">TikZ 图形</span>
      {src ? (
        <img className="q-img" src={src} alt="TikZ" style={{ maxWidth: '100%' }} />
      ) : (
        <button onClick={load} disabled={busy}
          className="press rounded-md border border-border bg-surface px-2 py-[3px]
                     text-[11px] text-ink-soft hover:border-brand-line disabled:opacity-50">
          {busy ? '渲染中…' : '显示 TikZ 图'}
        </button>
      )}
      {err && <div className="mt-1 text-[10.5px] text-warn">{err}</div>}
    </div>
  )
}

function Img({ id, width }: { id: string; width: string }) {
  const [missing, setMissing] = useState(false)
  if (missing) {
    return <span className="text-[10px] text-warn">图片缺失（见卡片下方预览）</span>
  }
  return (
    <img
      className="q-img"
      src={`/api/figure?path=${encodeURIComponent(id)}`}
      alt="题图"
      style={{ width }}
      loading="lazy"
      onError={() => setMissing(true)}
    />
  )
}

/** 搜索命中高亮：大小写不敏感，只包命中的片段。
 *
 *  只对**纯文本**做（题干里的公式是 KaTeX 渲染的，不拆）；出处、考点名、
 *  题干文字都能用。`kw` 为空原样返回，别为没搜索的列表加一层节点。 */
export function Highlight({ text, kw }: { text: string; kw?: string }): ReactNode {
  const k = (kw || '').trim()
  if (!text || !k) return text
  const low = text.toLowerCase()
  const kl = k.toLowerCase()
  if (!low.includes(kl)) return text
  const out: ReactNode[] = []
  let i = 0
  let n = 0
  while (i < text.length) {
    const j = low.indexOf(kl, i)
    if (j < 0) { out.push(text.slice(i)); break }
    if (j > i) out.push(text.slice(i, j))
    out.push(
      <mark key={n++} className="rounded-[3px] bg-warn-soft px-0.5 text-inherit">
        {text.slice(j, j + k.length)}
      </mark>,
    )
    i = j + k.length
  }
  return <>{out}</>
}

function Inlines({ nodes, kw }: { nodes: Inline[]; kw?: string }) {
  return (
    <>
      {nodes.map((n, i) => {
        switch (n.t) {
          case 's':
            return <span key={i}><Highlight text={n.s} kw={kw} /></span>
          case 'm':
            return <Math key={i} tex={n.s} display={!!n.display} />
          case 'fig':
            return <Img key={i} id={n.id} width={n.width} />
          case 'blank':
            return <span key={i} className="blank" />
          case 'paren':
            return <span key={i} className="q-paren">{'（\u3000\u3000）'}</span>
          case 'br':
            return <br key={i} />
          case 'sp':
            return <span key={i} className="q-sp" />
          case 'raw':
            // 没处理的宏：显式标出来，不静默吞掉
            return <code key={i} className="latex-unknown" title="这个宏还没处理">{n.s}</code>
          default:
            return null
        }
      })}
    </>
  )
}

/* ══ 块 ═══════════════════════════════════════════════════ */

const RAW_LABEL: Record<string, string> = {
  tikzpicture: 'TikZ 图形',
  pgfpicture: 'PGF 图形',
  circuitikz: '电路图',
  axis: '坐标图',
}

function BlockView({ b, kw }: { b: Block; kw?: string }) {
  switch (b.t) {
    case 'p':
      return (
        <div className="q-p">
          <Inlines nodes={b.in} kw={kw} />
        </div>
      )

    case 'math':
      return (
        <div className="q-math">
          <Math tex={b.tex} display />
        </div>
      )

    case 'list': {
      const items = b.items.map((it, i) => <li key={i}>{renderBlocks(it, kw)}</li>)
      return b.ordered
        ? <ol className="q-list">{items}</ol>
        : <ul className="q-list">{items}</ul>
    }

    case 'table':
      return (
        <div className="q-table-wrap">
          <table className="q-table">
            <tbody>
              {b.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((c, j) => (
                    <td key={j} colSpan={c.span > 1 ? c.span : undefined}>
                      {/* 单元格里可能是**嵌套的表格**（老卷子常用 tabular 套 tabular
                          做排版），那种情况整格按块渲染，画出来就是表里套表。 */}
                      {c.blocks ? renderBlocks(c.blocks, kw)
                                : <Inlines nodes={c.in || []} kw={kw} />}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )

    case 'box':
      return (
        <div className={`q-box q-${b.kind}`} style={b.width ? { maxWidth: '100%' } : undefined}>
          {renderBlocks(b.blocks, kw)}
        </div>
      )

    case 'fig':
      return (
        <div className="q-fig">
          <Img id={b.id} width={b.width} />
        </div>
      )

    case 'raw':
      if (b.env === 'tikzpicture' && b.tex) {
        return <TikzRaw tex={b.tex} />
      }
      return (
        <div className="q-raw">
          <span className="q-raw-tag">{RAW_LABEL[b.env || ''] || b.env || '原样内容'}</span>
          <span className="q-raw-note">HTML 画不了，导出 PDF 可见</span>
        </div>
      )

    default:
      return null
  }
}

/** 渲染一段块级 IR。`blocks` 为空时返回 null。 */
export function renderBlocks(blocks?: Block[] | null, kw?: string): ReactNode {
  if (!blocks || blocks.length === 0) return null
  return <>{blocks.map((b, i) => <BlockView key={i} b={b} kw={kw} />)}</>
}

/** 块级 IR → 纯文本（搜索摘要、剪贴板用）。 */
export function blocksText(blocks?: Block[] | null): string {
  if (!blocks) return ''
  const out: string[] = []
  const walkIn = (ns: Inline[]) => {
    for (const n of ns) {
      if (n.t === 's' || n.t === 'raw') out.push(n.s)
      else if (n.t === 'm') out.push(n.s)
      else if (n.t === 'blank') out.push('____')
      else if (n.t === 'paren') out.push('（  ）')
    }
  }
  const walk = (bs: Block[]) => {
    for (const b of bs) {
      if (b.t === 'p') walkIn(b.in)
      else if (b.t === 'math') out.push(b.tex)
      else if (b.t === 'list') b.items.forEach(walk)
      else if (b.t === 'table') b.rows.forEach((r) => r.forEach(
        (c) => (c.blocks ? walk(c.blocks) : walkIn(c.in || []))))
      else if (b.t === 'box') walk(b.blocks)
    }
  }
  walk(blocks)
  return out.join(' ').replace(/\s+/g, ' ').trim()
}
