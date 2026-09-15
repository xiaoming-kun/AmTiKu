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
import { useMemo } from 'react'
import katex from 'katex'
import type { ReactNode } from 'react'

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

function Img({ id, width }: { id: string; width: string }) {
  return (
    <img
      className="q-img"
      src={`/api/figure?path=${encodeURIComponent(id)}`}
      alt="题图"
      style={{ width }}
      loading="lazy"
    />
  )
}

function Inlines({ nodes }: { nodes: Inline[] }) {
  return (
    <>
      {nodes.map((n, i) => {
        switch (n.t) {
          case 's':
            return <span key={i}>{n.s}</span>
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

function BlockView({ b }: { b: Block }) {
  switch (b.t) {
    case 'p':
      return (
        <div className="q-p">
          <Inlines nodes={b.in} />
        </div>
      )

    case 'math':
      return (
        <div className="q-math">
          <Math tex={b.tex} display />
        </div>
      )

    case 'list': {
      const items = b.items.map((it, i) => <li key={i}>{renderBlocks(it)}</li>)
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
                      {c.blocks ? renderBlocks(c.blocks)
                                : <Inlines nodes={c.in || []} />}
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
          {renderBlocks(b.blocks)}
        </div>
      )

    case 'fig':
      return (
        <div className="q-fig">
          <Img id={b.id} width={b.width} />
        </div>
      )

    case 'raw':
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
export function renderBlocks(blocks?: Block[] | null): ReactNode {
  if (!blocks || blocks.length === 0) return null
  return <>{blocks.map((b, i) => <BlockView key={i} b={b} />)}</>
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
