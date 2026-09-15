/** 录入抽屉：粘贴 LaTeX 源码 → 预览 → 入库。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1）。
 */
import { useState } from 'react'
import { renderBlocks } from '@/lib/render'
import { api } from '@/lib/api'
import { Flags, Report, INGEST_SAMPLE } from '@/app/ui'

export default function IngestDrawer({ onClose, onDone, facets }: {
  onClose: () => void; onDone: () => void; facets: any
}) {
  const [text, setText] = useState('')
  const [book, setBook] = useState('手工录入')
  const [label, setLabel] = useState('')
  const [year, setYear] = useState('')
  const [no, setNo] = useState('')       // 原卷题号，单题录入时填
  // **难度与考点在界面上直接选**。不填也能录（之后靠 LLM 自动打标），
  // 但手工录入时人就在旁边，顺手指一下比事后回头补准得多——
  // 而且**手动标的不会被自动打标覆盖**（`point_source: manual`）。
  const [diff, setDiff] = useState('')
  const [pts, setPts] = useState<string[]>([])
  // 库里已有的题：手里这份更全就**升级**（默认开）。
  // 「连已有解析也覆盖」默认关——残缺的重录不该冲掉库里好的解析。
  const [updateExisting, setUpdateExisting] = useState(true)
  const [updateForce, setUpdateForce] = useState(false)
  // 「并入这道」：{新题的 key: 库内那道题的 key}。
  // 判重是算出来的，算不准——最终由人拍板。
  const [mergeInto, setMergeInto] = useState<Record<string, string>>({})
  const [ptKw, setPtKw] = useState('')
  const [pv, setPv] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)

  /** 拖进来或选一个 `.tex` / `.txt` 文件，读进文本框。
   *  比复制粘贴省事，尤其是几百行的整卷。 */
  const readFile = (f: File) => {
    const r = new FileReader()
    r.onload = () => { setText(String(r.result || '')); setPv(null); setMsg('')
                       setErr('') }
    r.readAsText(f, 'utf-8')
  }
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const body = () => ({
    text, book, label,
    year: year ? Number(year) : null,
    source_no: no,
    difficulty: diff,
    points: pts.join(','),
    update_existing: updateExisting,
    update_force: updateForce,
    merge_into: mergeInto,
  })

  const dryRun = () => {
    if (!text.trim()) { setErr('先粘贴题目 LaTeX'); return }
    setBusy(true); setErr(''); setMsg('')
    api.ingestPreview(body())
      .then((d) => { if (d.detail) setErr(String(d.detail)); else setPv(d) })
      .catch((e) => setErr(String(e))).finally(() => setBusy(false))
  }

  /** **一键更新**：把手里这份并到库里那道题上，升级完直接落盘。
   *
   *  走的就是「干跑 → 确认导入」同一条后端链路（`commit` 的
   *  `merge_into` + `update_existing`），只是省掉中间两次点击。
   *  敢做成一键，是因为升级规则是**只升不降**：补空的解析、并考点、
   *  改答案，任何一个字段都不会因为这次操作变空。
   */
  const updateInto = (newKey: string, targetKey: string) => {
    setBusy(true); setErr(''); setMsg('')
    api.ingestCommit({ ...body(), merge_into: { ...mergeInto, [newKey]: targetKey },
                       update_existing: true })
      .then((d) => {
        if (d.detail || !d.ok) { setErr(String(d.detail || d.error)); return }
        const up = (d.upgraded || []).find((u: any) => u.key === targetKey)
        const label = (f: string) => ({ solution: '解析', answer: '答案',
          points: '考点', difficulty: '难度' } as any)[f] || f
        setMsg(up ? `✓ 已更新 ${targetKey.split('/').pop()}：${up.fields.map(label).join('、')}`
                  : `✓ ${targetKey.split('/').pop()} 已是最新，无需改动`)
        setPv(null); setText(''); setMergeInto({}); onDone()
      })
      .catch((e) => setErr(String(e))).finally(() => setBusy(false))
  }

  const doCommit = () => {
    if (!pv) { setErr('先干跑一次'); return }
    if (pv.missing_images?.length) {
      setErr(`有 ${pv.missing_images.length} 张图缺失，先补图再导入`); return
    }
    setBusy(true); setErr('')
    api.ingestCommit(body())
      .then((d) => {
        if (d.detail || !d.ok) { setErr(String(d.detail || d.error)); return }
        setMsg(`已导入 ${d.added_count} 道` +
          (d.upgraded?.length ? `，升级 ${d.upgraded.length} 道` : '') +
          (d.skipped?.length ? `，跳过 ${d.skipped.length} 道` : ''))
        setPv(null); setText(''); onDone()
      })
      .catch((e) => setErr(String(e))).finally(() => setBusy(false))
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg" onClick={onClose}>
      <div className="flex min-h-0 flex-1 flex-col" onClick={(e) => e.stopPropagation()}>
        <header className="relative flex items-center gap-3 border-b border-border bg-surface px-4 py-2.5">
          <span className="text-[14px] font-semibold">录入题目</span>
          <span className="text-[11.5px] text-ink-faint">
            先干跑看清楚，再确认导入 —— 干跑什么都不写
          </span>
          <button onClick={onClose}
            className="ml-auto text-[18px] leading-none text-ink-faint hover:text-ink">×</button>
        </header>

        <div className="flex min-h-0 flex-1">
          {/* 左：源材料 */}
          <div className="flex min-w-0 flex-1 flex-col border-r border-border">
            <div className="flex flex-wrap items-end gap-3 border-b border-border px-4 py-3">
              {([['来源', book, setBook, '手工录入'], ['出处', label, setLabel, '如 第14套武汉三调'],
                 ['年份', year, setYear, '2024'], ['题号', no, setNo, '7']] as const).map(([name, val, set, ph]) => (
                <div key={name}>
                  <div className="mb-1 text-[11px] font-semibold text-ink-faint">{name}</div>
                  <input value={val} onChange={(e) => (set as any)(e.target.value)} placeholder={ph}
                    className="w-[150px] rounded-lg border border-border bg-bg px-2.5 py-1.5 text-[12.5px]
                               outline-none placeholder:text-ink-faint focus:border-brand/40 focus:bg-surface" />
                </div>
              ))}
              <button onClick={() => setText(INGEST_SAMPLE)}
                className="rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[12px] hover:bg-muted">
                填入示例
              </button>
              {/* 选文件：和拖拽一个效果 */}
              <label className="cursor-pointer rounded-lg border border-border bg-surface
                                px-2.5 py-1.5 text-[12px] hover:bg-muted">
                选文件…
                <input type="file" accept=".tex,.txt" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) readFile(f) }} />
              </label>
            </div>

            {/* ── 难度 / 考点 ──
                留空也能录（之后靠自动打标补），但人就在旁边时顺手指一下，
                比事后回头对 17554 道题找哪道没标要准得多。
                手动标了会记成 `point_source: manual`，自动打标不再覆盖。 */}
            <div className="flex flex-wrap items-start gap-4 border-b border-border bg-muted/30 px-4 py-2.5">
              <div>
                <div className="mb-1 text-[11px] font-semibold text-ink-faint">
                  难度 <span className="font-normal">（可留空，按主考点派生）</span>
                </div>
                <div className="flex gap-1">
                  {([['简单题', 1], ['中档题', 2], ['难题', 3]] as const).map(([d, k]) => (
                    <button key={d} onClick={() => setDiff(diff === d ? '' : d)}
                      className={`rounded-md border px-2 py-1 text-[11.5px] transition-colors ${
                        diff === d ? 'border-brand/40 bg-brand-soft font-medium text-brand-ink'
                                   : 'border-border bg-bg text-ink-soft hover:bg-muted'}`}>
                      <span className="tracking-tight">{'★'.repeat(k)}</span>
                      <span className="ml-1 text-[11px]">{d.replace('题', '')}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="min-w-[280px] flex-1">
                <div className="mb-1 text-[11px] font-semibold text-ink-faint">
                  考点 <span className="font-normal">（第一条为主考点，可留空）</span>
                </div>
                {/* 已选：按选中顺序排，第一个就是主考点 */}
                {pts.length > 0 && (
                  <div className="mb-1.5 flex flex-wrap gap-1">
                    {pts.map((p, i) => {
                      const t = (facets?.points || []).find((x: any) => x.value === p)
                      return (
                        <span key={p}
                          className="inline-flex items-center gap-1 rounded-md border border-brand/30
                                     bg-brand-soft px-1.5 py-[2px] text-[11px] text-brand-ink">
                          {i === 0 && <b title="主考点">主</b>}
                          {t?.title || p}
                          <button onClick={() => setPts((xs) => xs.filter((x) => x !== p))}
                            className="text-ink-faint hover:text-warn">✕</button>
                        </span>
                      )
                    })}
                  </div>
                )}
                <input value={ptKw} onChange={(e) => setPtKw(e.target.value)}
                  placeholder="搜索考点…"
                  className="w-full rounded-lg border border-border bg-bg px-2.5 py-1.5 text-[12.5px]
                             outline-none placeholder:text-ink-faint focus:border-brand/40 focus:bg-surface" />
                {ptKw.trim() && (
                  <div className="mt-1 max-h-[132px] overflow-y-auto rounded-lg border border-border bg-surface">
                    {(facets?.points || [])
                      .filter((p: any) => !pts.includes(p.value) &&
                        (p.title.includes(ptKw.trim()) || p.value.includes(ptKw.trim())))
                      .slice(0, 20)
                      .map((p: any) => (
                        <button key={p.value}
                          onClick={() => { setPts((xs) => [...xs, p.value]); setPtKw('') }}
                          className="flex w-full items-baseline gap-2 px-2.5 py-1 text-left
                                     text-[12px] hover:bg-muted">
                          <span className="font-mono text-[10.5px] text-ink-faint">{p.value}</span>
                          <span className="min-w-0 flex-1 truncate">{p.title}</span>
                        </button>
                      ))}
                  </div>
                )}
              </div>
            </div>
            <div className="relative min-h-0 flex-1"
              onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault(); setDrag(false)
                const f = e.dataTransfer.files?.[0]
                if (f) readFile(f)
              }}>
              <textarea value={text}
                onChange={(e) => { setText(e.target.value); setPv(null); setMsg('') }}
                spellCheck={false}
                placeholder={'粘贴 exam-zh 格式的题目，或把 .tex 文件拖进来：\n\n\\begin{question}\n…\n\\end{question}\n\\begin{solution}\n…\n\\end{solution}'}
                className="h-full w-full resize-none bg-bg px-4 py-3 font-mono text-[12.5px]
                           leading-relaxed outline-none placeholder:text-ink-faint" />
              {drag && (
                <div className="pointer-events-none absolute inset-2 flex items-center justify-center
                                rounded-xl border-2 border-dashed border-brand/50 bg-brand-soft/60
                                text-[13px] font-medium text-brand-ink">
                  松手就导入这个文件
                </div>
              )}
            </div>
          </div>

          {/* 右：干跑报告 */}
          <div className="flex w-[420px] shrink-0 flex-col">
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
              {!pv && !busy && (
                <div className="flex h-full items-center justify-center text-[12.5px] text-ink-faint">
                  点「干跑」看解析结果、图片、查重、影响面
                </div>
              )}
              {busy && (
                <div className="anim-fade-in space-y-2">
                  <div className="flex items-center gap-2 text-[12.5px] text-ink-soft">
                    <span className="inline-block h-3.5 w-3.5 rounded-full border-2
                                     border-brand-soft border-t-brand"
                      style={{ animation: 'spin .8s linear infinite' }} />
                    正在解析 · 规范化 · 查重 · 查图…
                  </div>
                  <div className="progress-track" />
                  {/* 骨架屏：先给出「报告大概长这样」，比空白等着好 */}
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="rounded-lg border border-border p-2.5">
                      <div className="skeleton mb-2 h-3 w-24" />
                      <div className="skeleton h-2.5 w-full" />
                      <div className="skeleton mt-1.5 h-2.5 w-3/5" />
                    </div>
                  ))}
                </div>
              )}
              {pv && (<>
                {/* 规范：**验证 → 修改 → 复核**。这是录入流程的第一步，
                    最该让人看见——「改之前哪里不合规、规范器改了什么、
                    复核过没过」三件事一目了然。
                    复核不过就不许导入（后端也会拒）。 */}
                {pv.spec && (
                  <Report n="①" title="规范：验证 → 修改 → 复核">
                    <div className="space-y-1 text-[11.5px]">
                      <div className="flex items-baseline gap-1.5">
                        <span className="w-14 shrink-0 text-ink-faint">改之前</span>
                        {pv.spec.before?.length
                          ? <span className="text-warn">✗ {pv.spec.before.length} 处不合规</span>
                          : <span className="text-has">✓ 本来就合规</span>}
                      </div>
                      {!!pv.spec.before?.length && (
                        <div className="ml-[3.75rem] space-y-0.5 text-[10.5px] text-ink-faint">
                          {pv.spec.before.slice(0, 5).map((b: any, i: number) => (
                            <div key={i} className="truncate">
                              <span className="font-mono">{b.key.split('/').pop()}</span>
                              {' '}[{b.check}] {b.why}
                            </div>
                          ))}
                          {pv.spec.before.length > 5 &&
                            <div>… 其余 {pv.spec.before.length - 5} 处</div>}
                        </div>
                      )}
                      <div className="flex items-baseline gap-1.5">
                        <span className="w-14 shrink-0 text-ink-faint">规范器</span>
                        {pv.spec.fixed?.length
                          ? <span className="text-ink-soft">
                              {pv.spec.fixed.map((f: any) => `${f.name} ${f.hits} 道`).join(' · ')}
                            </span>
                          : <span className="text-ink-faint">无需改动</span>}
                      </div>
                      <div className="flex items-baseline gap-1.5">
                        <span className="w-14 shrink-0 text-ink-faint">复核后</span>
                        {pv.spec.ok
                          ? <span className="font-medium text-has">✓ 全部规范，可以导入</span>
                          : <span className="font-medium text-warn">
                              ✗ 仍有 {pv.spec.after.length} 处 —— 先改题目，不许导入
                            </span>}
                      </div>
                    </div>
                  </Report>
                )}

                <Report n="②" title={`解析结果：${pv.count} 道`}>
                  {pv.errors?.length > 0 && (
                    <div className="mb-1 text-warn">⚠ {pv.errors.length} 个解析问题</div>
                  )}
                  {pv.items.map((it: any, i: number) => (
                    <div key={i} className="mb-1.5 rounded-lg border border-border bg-bg px-2.5 py-1.5">
                      <div className="mb-0.5 flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
                        <span className="rounded bg-muted px-1.5 py-[1px]">{it.type_label}</span>
                        {/* 难度：星号 + 名称。**没标就明说「难度未定」**，
                            不要留空——留空看不出是"没标"还是"界面漏了"。 */}
                        {it.stars
                          ? <span className="rounded bg-brand-soft px-1.5 py-[1px] text-brand-ink"
                              title={it.difficulty}>
                              {'★'.repeat(it.stars)} {it.difficulty}
                            </span>
                          : <span className="rounded border border-dashed border-border px-1.5 py-[1px]">
                              难度未定
                            </span>}
                        <Flags flags={it.flags} />
                        <span className="ml-auto font-mono">{it.key.split('/').pop()}</span>
                      </div>
                      <div className="q-stem line-clamp-2 text-[12px]">{renderBlocks(it.blocks?.stem)}</div>
                      {/* 考点：全名。没有就说明"这批题还没打标签"。 */}
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        {it.point_titles?.length
                          ? it.point_titles.map((t: string, k: number) => (
                              <span key={k} title={it.points?.[k] || ''}
                                className={`rounded px-1.5 py-[1px] text-[10.5px] font-semibold ${
                                  k === 0 ? 'bg-brand-soft text-brand-ink'
                                          : 'bg-muted text-ink-soft'}`}>
                                {k === 0 && <span className="mr-0.5 text-[9px] font-normal opacity-70">主</span>}
                                {t}
                              </span>
                            ))
                          : <span className="text-[10.5px] text-ink-faint">
                              未标考点（导入后可在详情页补）
                            </span>}
                      </div>
                    </div>
                  ))}
                </Report>

                <Report n="③" title={`图片检查：${Object.keys(pv.images || {}).length} 张`}>
                  {Object.keys(pv.images || {}).length === 0
                    ? <div className="text-[11.5px] text-ink-faint">没有引用图片</div>
                    : Object.entries(pv.images).map(([k, v]: any) => (
                      <div key={k} className="flex items-center gap-2 text-[11.5px]">
                        <span className="min-w-0 flex-1 truncate font-mono text-[10.5px]">{k}</span>
                        <span className={v.status === 'missing' ? 'text-warn' : 'text-has'}>{v.note}</span>
                      </div>
                    ))}
                </Report>

                <Report n="④" title={`查重：新建 ${pv.dup.new} · 并入 ${pv.dup.merge} · 疑似 ${pv.dup.suspect}`
                  + (pv.dup.upgrade ? ` · 升级 ${pv.dup.upgrade}` : '')}>
                  {/* **升级**：题库里已经有这道题，但手里这份更全（带解析／考点更多）
                      ——不新写一份，而是**改库里那一份**。干跑就要讲清楚，
                      否则点完「确认导入」才发现白录了。 */}
                  {pv.dup.upgrade > 0 && (
                    <div className="mb-2 rounded-lg border border-brand/30 bg-brand-soft/60 px-2 py-1.5">
                      <div className="text-[11.5px] font-medium text-brand-ink">
                        ↑ {pv.dup.upgrade} 道已在库、但这份更全，导入时会升级（不会新增一份）
                      </div>
                      {pv.items.filter((it: any) => it.update_fields?.length).map((it: any) => (
                        <div key={it.key} className="mt-1 text-[11px] text-ink-soft">
                          <span className="font-mono">{it.key.split('/').pop()}</span>
                          {' '}更新：{it.update_fields.map((f: string) =>
                            ({ solution: '解析', answer: '答案', points: '考点',
                               difficulty: '难度' } as any)[f] || f).join('、')}
                        </div>
                      ))}
                    </div>
                  )}
                  {pv.items.filter((it: any) => it.dups?.length).map((it: any) => (
                    <div key={it.key} className="mb-1 text-[11.5px]">
                      <div className="truncate text-ink-soft">{it.key}</div>
                      {it.update_fields?.length > 0 && (
                        <div className="ml-2 text-[11px] text-brand-ink">
                          ↑ 手里这份更全 → 更新 {it.update_fields.join('、')}
                        </div>
                      )}
                      {it.dups.map((d: any) => (
                        <div key={d.key} className="ml-2 rounded-md border border-border
                                                   bg-bg px-2 py-1.5">
                          <div className="flex items-center gap-1.5">
                            <span className={d.verdict === '并入' ? 'text-warn' : 'text-ink-faint'}>
                              [{d.verdict}]
                            </span>
                            <span className="min-w-0 flex-1 truncate font-mono text-[10.5px]">{d.key}</span>
                            <span className="text-ink-faint">{d.score.toFixed(3)}</span>
                          </div>
                          {/* **把库内那道题的原文摆出来**——只给题号和分数，
                              人判断不了是不是同一道，等于没提示 */}
                          {d.stem && (
                            <div className="mt-0.5 line-clamp-2 text-[11px] text-ink-soft">{d.stem}</div>
                          )}
                          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10.5px] text-ink-faint">
                            <span>{d.type_label}</span>
                            <span className={d.has_solution ? 'text-has' : 'text-gap'}>
                              {d.has_solution ? '✓解析' : '✗解析'}
                            </span>
                            <span className={d.has_answer ? 'text-has' : 'text-gap'}>
                              {d.has_answer ? '✓答案' : '✗答案'}
                            </span>
                            {d.point_titles?.length > 0 && <span>{d.point_titles[0]}</span>}
                            {/* 拍板：这其实就是同一道题 → 并入它（走升级那条路） */}
                            <span className="ml-auto inline-flex gap-1">
                              {mergeInto[it.key] === d.key ? (
                                <button onClick={() => { const m = { ...mergeInto }
                                    delete m[it.key]; setMergeInto(m); setPv(null) }}
                                  className="rounded border border-warn/40 bg-warn-soft
                                             px-1.5 py-[1px] text-warn">
                                  撤销并入
                                </button>
                              ) : (
                                <button onClick={() => { setMergeInto({ ...mergeInto, [it.key]: d.key })
                                                          setPv(null) }}
                                  className="rounded border border-border bg-surface px-1.5 py-[1px]
                                             text-ink-soft hover:border-brand/40 hover:text-brand-ink">
                                  并入这道
                                </button>
                              )}
                              {/* **一键更新**：并进去 + 升级 + 落盘，一步到位 */}
                              <button disabled={busy} onClick={() => updateInto(it.key, d.key)}
                                title="把手里这份并入这道题并升级：补解析、并考点、改答案，然后落盘"
                                className="rounded border border-brand/40 bg-brand-soft px-1.5 py-[1px]
                                           font-medium text-brand-ink hover:bg-brand-soft/70
                                           disabled:opacity-40">
                                用这份更新
                              </button>
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                  {!pv.items.some((it: any) => it.dups?.length) && !pv.dup.upgrade &&
                    <div className="text-[11.5px] text-has">✓ 库中没有相似题</div>}
                  {/* 两个开关。允许升级默认开；「连已有解析也覆盖」默认关——
                      重录一份残缺的解析，不该把库里那份好的冲掉。 */}
                  <label className="mt-2 flex items-center gap-2 text-[11.5px] text-ink-soft">
                    <input type="checkbox" checked={updateExisting}
                      onChange={(e) => { setUpdateExisting(e.target.checked); setPv(null) }}
                      className="accent-[var(--color-brand)]" />
                    库里已有这道题时，手里这份更全就升级（补解析 · 并考点 · 改答案）
                  </label>
                  {updateExisting && (
                    <label className="mt-1 flex items-center gap-2 text-[11.5px] text-ink-soft">
                      <input type="checkbox" checked={updateForce}
                        onChange={(e) => { setUpdateForce(e.target.checked); setPv(null) }}
                        className="accent-[var(--color-brand)]" />
                      连已有的解析也覆盖（默认只补空的，不动已有的）
                    </label>
                  )}
                </Report>

                <Report n="⑤" title="类型与字段校验">
                  <div className="mb-1 text-[11.5px]">
                    {pv.types.map((t: any) => `${t.label} ${t.n}`).join(' · ') || '—'}
                  </div>
                  {pv.problems?.length
                    ? <div className="text-[11.5px] text-warn">⚠ {pv.problems.length} 道有字段问题</div>
                    : <div className="text-[11.5px] text-has">✓ 全部通过</div>}
                </Report>

                <Report n="⑥" title="影响面">
                  <div className={`text-[12px] font-medium ${
                    pv.impact.existing_questions ? 'text-warn' : 'text-has'}`}>
                    存量题目影响：{pv.impact.existing_questions} 道
                  </div>
                  <div className="mt-0.5 text-[11px] text-ink-faint">{pv.impact.note}</div>
                </Report>
              </>)}
            </div>

            <div className="space-y-2 border-t border-border px-4 py-3">
              {err && <div className="rounded-lg border border-warn/30 bg-warn-soft p-2 text-[11.5px] text-warn">✗ {err}</div>}
              {msg && <div className="rounded-lg border border-has/30 bg-has-soft p-2 text-[11.5px] text-has">✓ {msg}</div>}
              <div className="flex gap-2">
                <button onClick={dryRun} disabled={busy}
                  className="rounded-lg border border-border bg-surface px-3 py-1.5 text-[12.5px] hover:bg-muted disabled:opacity-50">
                  干跑
                </button>
                <button onClick={doCommit}
                  disabled={busy || !pv || pv.count === 0 || pv.spec?.ok === false
                            || (pv.missing_images?.length ?? 0) > 0}
                  title={pv?.spec?.ok === false ? '规范复核没过，先改题目'
                         : (pv?.missing_images?.length ? '有缺图，先补图' : '')}
                  className="ml-auto rounded-lg bg-brand px-4 py-1.5 text-[12.5px] font-medium text-white
                             hover:opacity-90 disabled:opacity-40">
                  确认导入 {pv?.count ? `(${pv.count} 道)` : ''}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
