/** 新建讲义：从高中知识点里挑一个还没有讲义的考点，生成可编辑的 TeX 骨架。 */
import { useEffect, useMemo, useState } from 'react'
import { BookOpen, Loader2, Plus, Search, X } from 'lucide-react'
import { api, reportErr } from '@/lib/api'

type Point = { value: string; title: string; topic: string; section: string; stars: number; n: number }

export default function NewLectureDialog({ existing, onClose, onCreated }: {
  existing: Set<string>
  onClose: () => void
  onCreated: (id: string) => void
}) {
  const [points, setPoints] = useState<Point[] | null>(null)
  const [kw, setKw] = useState('')
  const [title, setTitle] = useState('')
  const [pick, setPick] = useState<Point | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.facets('senior')
      .then((d: { points?: Point[] }) => setPoints(d.points || []))
      .catch((e) => { reportErr(e); setPoints([]) })
  }, [])

  const avail = useMemo(() => {
    const k = kw.trim().toLowerCase()
    return (points || [])
      .filter((p) => !k || [p.value, p.title, p.topic, p.section].some((x) => String(x || '').toLowerCase().includes(k)))
  }, [points, kw])

  const create = async () => {
    if (!pick && !title.trim()) return
    setBusy(true); setErr('')
    try {
      const d = await api.topicNew(pick?.value || '', title.trim())
      onCreated(d.id)
    } catch (e) {
      setErr(String((e as Error)?.message || e))
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      onClick={() => !busy && onClose()}>
      <div className="pop flex max-h-[82vh] w-full max-w-[720px] flex-col overflow-hidden rounded-[22px]
                      border border-border bg-surface shadow-[var(--shadow-pop)]"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-border px-5 py-3">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-soft text-brand">
            <BookOpen size={16} />
          </span>
          <div>
            <div className="text-[14px] font-semibold">新建讲义</div>
            <div className="text-[10.5px] text-ink-faint">从高中考点生成可编辑的讲义骨架</div>
          </div>
          <button onClick={onClose} disabled={busy} className="icon-btn ml-auto h-7 w-7"><X size={15} /></button>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-0 sm:grid-cols-[1fr_280px]">
          <div className="flex min-h-0 flex-col border-b border-border sm:border-b-0 sm:border-r">
            <div className="p-3">
              <div className="relative">
                <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
                <input value={kw} onChange={(e) => setKw(e.target.value)}
                  placeholder="搜考点 / 章 / 编号"
                  className="h-8 w-full rounded-lg border border-border bg-surface-2 pl-8 pr-2 text-[11.5px] outline-none
                             focus:border-brand-line" />
              </div>
              <div className="mt-1.5 text-[10px] text-ink-faint">
                {points === null ? '正在读考点…' : `${avail.length} 个考点可选 · 可关联也可自建`}
              </div>
            </div>
            <div className="b-scroll min-h-0 flex-1 overflow-y-auto px-2 pb-3">
              <button onClick={() => { setPick(null); setTitle('') }}
                className={`mb-0.5 flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left
                            ${!pick ? 'bg-brand-soft text-brand-ink' : 'text-ink-soft hover:bg-muted'}`}>
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-surface text-[10px] text-ink-faint">+</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[11.5px] font-medium">不绑定考点</span>
                  <span className="block text-[9.5px] text-ink-faint">建一份独立讲义（如复习专题 / 章节补充）</span>
                </span>
              </button>
              {avail.map((p) => {
                const on = pick?.value === p.value
                return (
                  <button key={p.value} onClick={() => { setPick(p); if (!title) setTitle(p.title) }}
                    className={`mb-0.5 flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left
                                ${on ? 'bg-brand-soft text-brand-ink' : 'text-ink-soft hover:bg-muted'}`}>
                    <span className="tnum w-10 shrink-0 text-[10px] text-ink-faint">{p.value}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[11.5px] font-medium">{p.title}</span>
                      <span className="block truncate text-[9.5px] text-ink-faint">{p.topic} · {p.section}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      {existing.has(p.value) && <span className="block text-[9px] text-ink-faint">已有</span>}
                      <span className="tnum block text-[9.5px] text-ink-faint">{p.n} 题</span>
                    </span>
                  </button>
                )
              })}
              {points !== null && !avail.length && (
                <div className="px-3 py-10 text-center text-[11.5px] text-ink-faint">
                  这个条件下没有可新建的知识点
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-col p-4">
            <div className="text-[10.5px] font-semibold tracking-wide text-ink-faint">讲义标题</div>
            <input value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder={pick?.title || '选一个考点'}
              className="mt-1.5 h-9 w-full rounded-lg border border-border bg-surface-2 px-2.5 text-[12px]
                         outline-none focus:border-brand-line" />
            <div className="mt-3 rounded-lg bg-surface-2 p-2.5 text-[10.5px] leading-relaxed text-ink-faint">
              {pick ? (
                <>将生成关联 <b className="font-medium text-ink-soft">{pick.value}</b> 的讲义骨架：
                  导言区 + 内容提要 + 本节 + 小结。保存后可在阅读器里点击段落直接改。</>
              ) : '不绑定考点也可以建；适合复习专题、章节补充或临时讲义。'}
            </div>
            {err && <div className="mt-2 rounded-lg bg-danger-soft px-2.5 py-2 text-[10.5px] text-danger">{err}</div>}
            <span className="flex-1" />
            <button onClick={create} disabled={(!pick && !title.trim()) || busy}
              className="press mt-3 flex h-9 items-center justify-center gap-1.5 rounded-lg bg-brand
                         text-[12px] font-medium text-white shadow-[var(--shadow-brand)] disabled:opacity-40">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
              {busy ? '正在生成…' : '生成讲义'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
