/** 试卷库：出过的卷子 / 合集，只存题号，所以能原样还原。
 *
 *  旧界面把「试卷管理」做成导航里的一个入口，点进去却是题库栏切到卷子视图——
 *  名不副实。现在它是一页真正的档案：按时间倒序、能搜、能载入回卷子、能删。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowRight, CalendarDays, FileStack, FolderOpen, Loader2, Plus, Search,
  Share2, Trash2, Upload, X,
} from 'lucide-react'
import type { Q } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import { toast } from '@/app/Toast'

type PaperItem = {
  name: string; title: string; kind: string; mode: string
  keys: string[]; n: number; at: string; updated?: string; note?: string
}

export default function PapersPage({ onLoad, onPaper, focus }: {
  onLoad: (items: Q[]) => void
  onPaper: () => void
  /** 从题库卡片「组过 N 卷」跳过来：直接把搜索框钉在这份卷名上。 */
  focus?: string
}) {
  const [items, setItems] = useState<PaperItem[] | null>(null)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')
  const [busy, setBusy] = useState('')
  const [drop, setDrop] = useState<PaperItem | null>(null)

  const load = () => {
    api.papers()
      .then((d: { items: PaperItem[] }) => setItems(d.items || []))
      .catch((e) => { reportErr(e); setItems([]) })
  }
  useEffect(load, [])

  // 从别的页面带着卷名跳进来：搜索框直接筛到那一份，不用再让人翻几百条。
  // 只认**卷名**，不认标题——列表里显示的是 title，用户看到的就是它。
  useEffect(() => {
    if (focus) setQ(focus)
  }, [focus])

  const filtered = useMemo(() => {
    const k = q.trim().toLowerCase()
    return (items || []).filter((x) => {
      if (kind && (x.kind || '试卷') !== kind) return false
      if (!k) return true
      return [x.title, x.name, x.kind, x.note].some((v) =>
        String(v || '').toLowerCase().includes(k))
    })
  }, [items, q, kind])

  const loadOne = async (p: PaperItem) => {
    if (!p.keys?.length) { toast('这份存档没有题号', { tone: 'warn' }); return }
    if (p.keys.length > 1000) { toast('存档超过 1000 道，暂不支持一次载入', { tone: 'warn' }); return }
    setBusy(p.name)
    try {
      const d: any = await api.list({ keys: p.keys.join(','), limit: '1000', lite: '1' })
      onLoad((d.items || []) as Q[])
      toast(`已载入「${p.title}」 · ${p.n} 道`, {
        action: { label: '去组卷', run: onPaper },
      })
    } catch (e) { reportErr(e) } finally { setBusy('') }
  }

  const remove = async (p: PaperItem) => {
    try {
      await api.paperDelete(p.name)
      setDrop(null)
      setItems((xs) => (xs || []).filter((x) => x.name !== p.name))
      toast(`已删除「${p.title}」`, { tone: 'warn' })
    } catch (e) { reportErr(e) }
  }

  const fileRef = useRef<HTMLInputElement>(null)

  /** 分享包：只打包题块 + 图片，不复制整库；下载走 Blob。 */
  const share = async (p: PaperItem) => {
    if (!p.keys?.length) { toast('这份存档没有题号', { tone: 'warn' }); return }
    setBusy('share:' + p.name)
    try {
      const blob = await api.shareExport(p.keys, p.title || p.name)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${(p.title || p.name).replace(/[\\/:*?"<>|]/g, '_')}.amti-pack.zip`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      toast(`已导出分享包 · ${p.keys.length} 道`)
    } catch (e) { reportErr(e) } finally { setBusy('') }
  }

  const importPack = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setBusy('import')
    try {
      const r: any = await api.shareImport(f)
      if (!r?.ok) {
        toast((r?.errors || ['导入失败']).slice(0, 3).join('；'), { tone: 'warn' })
      } else {
        toast(`导入 ${r.imported} 道，跳过 ${r.skipped?.length || 0} 道`
          + (r.images?.length ? `，图片 ${r.images.length} 张` : ''))
      }
    } catch (err) { reportErr(err) } finally {
      setBusy('')
      e.target.value = ''
    }
  }

  return (
    <div className="b-scroll h-full overflow-y-auto">
      <div className="b-page">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜卷名 / 备注"
              className="b-input h-8 w-[220px] pl-7 pr-7 text-[11.5px]" />
            {q && <button onClick={() => setQ('')} className="icon-btn absolute right-1 top-1/2 h-5 w-5 -translate-y-1/2"><X size={11} /></button>}
          </div>
          {['', '试卷', '测试卷', '合集', '讲义'].map((k) => (
            <button key={k || 'all'} onClick={() => setKind(k)}
              className={`b-chip ${kind === k ? 'b-chip-on' : ''}`}>{k || '全部'}</button>
          ))}
          <span className="tnum text-[10.5px] text-ink-faint">
            {items === null ? '读取中…' : `${filtered.length} / ${items.length} 份`}
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <input ref={fileRef} type="file" accept=".zip,.amti-pack.zip"
              onChange={importPack} className="hidden" />
            <button onClick={() => fileRef.current?.click()} disabled={busy === 'import'}
              className="b-btn b-btn-secondary">
              {busy === 'import'
                ? <><Loader2 size={14} className="animate-spin" />导入中</>
                : <><Upload size={14} />导入分享包</>}
            </button>
            <button onClick={onPaper} className="b-btn b-btn-primary">
              <Plus size={14} />新建组卷
            </button>
          </div>
        </div>
        <div className="mb-3 mt-2 text-[10.5px] text-ink-faint">
          每次导出都会自动存档；载入后回到组卷工作区，可以继续换题、改版式、重导。
        </div>

        <div className="mt-3 b-card overflow-hidden">
          {items === null ? (
            <div className="flex items-center justify-center gap-2 py-16 text-[11.5px] text-ink-faint">
              <Loader2 size={14} className="animate-spin" />正在读试卷存档…
            </div>
          ) : filtered.length === 0 ? (
            <div className="b-empty m-5 border-0 bg-surface-2">
              <FolderOpen size={26} className="text-border-strong" />
              <div className="text-[13px] font-medium text-ink-soft">
                {items.length ? '没有匹配的卷子' : '还没有出过卷子'}
              </div>
              <div className="text-[11px]">
                {items.length ? '换个关键词或类型' : '去题库挑几道题，导出后就会自动出现在这里'}
              </div>
              {!items.length && <button onClick={onPaper} className="b-btn b-btn-primary mt-1">去组卷</button>}
            </div>
          ) : (
            <div className="overflow-x-auto">
            <table className="b-table">
              <thead>
                <tr>
                  <th>卷名</th>
                  <th className="hidden w-[90px] md:table-cell">类型</th>
                  <th className="hidden w-[70px] sm:table-cell">题量</th>
                  <th className="hidden w-[150px] md:table-cell">时间</th>
                  <th className="w-[150px] text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => (
                  <tr key={p.name}>
                    <td>
                      <div className="flex items-center gap-2">
                        <FileStack size={14} className="shrink-0 text-ink-faint" />
                        <div className="min-w-0">
                          <div className="truncate text-[12.5px] font-medium text-ink">{p.title}</div>
                          <div className="truncate text-[10px] text-ink-faint">{p.name}</div>
                          <div className="mt-0.5 text-[10px] text-ink-faint sm:hidden">
                            {p.kind || '试卷'} · {p.n} 道
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="hidden whitespace-nowrap md:table-cell">
                      <span className={`whitespace-nowrap rounded-full px-1.5 py-[1px] text-[10px] font-medium
                        ${p.kind === '合集' ? 'bg-[#f5f3ff] text-[#6d28d9]' : 'bg-muted text-ink-soft'}`}>
                        {p.kind || '试卷'}
                      </span>
                    </td>
                    <td className="tnum hidden whitespace-nowrap text-[11.5px] text-ink-soft sm:table-cell">{p.n} 道</td>
                    <td className="tnum hidden text-[10.5px] text-ink-faint md:table-cell">
                      <span className="inline-flex items-center gap-1">
                        <CalendarDays size={10} />{(p.updated || p.at || '').slice(0, 16)}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => loadOne(p)} disabled={busy === p.name}
                          className="b-btn b-btn-soft b-btn-sm">
                          {busy === p.name
                            ? <><Loader2 size={12} className="animate-spin" />载入中</>
                            : <><ArrowRight size={12} />载入</>}
                        </button>
                        <button onClick={() => share(p)} disabled={!!busy}
                          title="导出分享包（题目 + 图片）"
                          className="icon-btn h-7 w-7 text-ink-faint hover:text-brand-ink disabled:opacity-40">
                          {busy === 'share:' + p.name
                            ? <Loader2 size={13} className="animate-spin" />
                            : <Share2 size={13} />}
                        </button>
                        <button onClick={() => setDrop(p)} title="删除存档"
                          className="icon-btn h-7 w-7 text-ink-faint hover:text-warn">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </div>

        <p className="mt-3 text-[10px] leading-relaxed text-ink-faint">
          存档只记题号（key），不复制题目正文；所以题库里的题改了，重新载入就是新的。
          删除存档不会删题。
        </p>
      </div>

      {drop && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim p-5">
          <div className="b-sheet w-[400px] p-5">
            <div className="text-[14px] font-semibold">删除这份试卷存档？</div>
            <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-faint">
              「{drop.title}」的存档记录会删除，题目本身不受影响。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setDrop(null)} className="b-btn b-btn-secondary">取消</button>
              <button onClick={() => remove(drop)} className="b-btn b-btn-primary" style={{ background: 'var(--color-danger)' }}>
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
