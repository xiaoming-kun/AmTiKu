/** 知识清单（讲义讲解内容源）的前端类型与请求。
 *
 *  ⚠️ 这里**不解析 LaTeX**。书里 500 多种自己的宏与环境由后端
 *  `amti/klist.py` 展开成块级 IR，前端只画切好的块 —— 与题库题目
 *  共用同一个渲染器（`lib/render.tsx`），所以不再有第二份解析。
 *
 *  数据只在必要时拉：目录树不带正文（全量 1MB），点开哪个节点才拉哪个。
 */
import type { Block } from '@/lib/render'
import { request } from '@/lib/api'

/** 目录项 / 搜索结果里的节点（**不带正文**） */
export type KNodeMeta = {
  id: string
  title: string
  level: string        // file|chapter|section|subsection|subsubsection
  file: string         // 书的哪个分文件（20 个）
  line: number
  chars: number
  n_fig: number
  n_table: number
}

export type KTreeNode = KNodeMeta & { kids: KTreeNode[] }
export type KHit = KNodeMeta & { hit: string }        // 命中的正文片段
export type KNode = KNodeMeta & { blocks: Block[] }   // 完整节点

export type KStats = {
  ok?: boolean
  error?: string
  stats: { nodes: number; files: number; chars: number; figs: number
           figs_pending: number; tables: number; unknown_macros: number }
  built_at: string
  book_dir: string
  files: string[]
  stale: boolean        // 书比生成物新（要重新生成）
  map: { points_total: number; points_mapped: number; nodes_used: number
         nodes_total: number; points_missing: string[] }
}

const enc = encodeURIComponent

export const klistApi = {
  stats: () => request<KStats>('/api/klist/stats'),
  tree: () => request<{ tree: KTreeNode[]; stats: KStats['stats'] }>('/api/klist/tree'),
  search: (q: string, limit = 60) =>
    request<{ items: KHit[] }>(`/api/klist/search?q=${enc(q)}&limit=${limit}`),
  node: (id: string) => request<KNode>('/api/klist/node/' + enc(id)),
}
