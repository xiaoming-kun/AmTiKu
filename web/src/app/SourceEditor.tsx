/** 改源码弹窗：**直接改 LaTeX 正文 → 检查 → 保存**。
 *
 *  为什么要有它：详情页只能改答案/解析；题干里的公式写坏了、选项串行了，
 *  以前只能去改 `题目/*.tex`。现在在页面上就能改，而且改完立刻看到渲染。
 *
 *  **不设口令**（用户明确说没必要）：打开就直接读源码、进编辑器。
 *  安全性由下面三道兜住，而不是靠多输一次密码：
 *    ① **只改正文**：`%% @q` 元数据行不进来，key/出处/考点不会被手改坏；
 *    ② **检查与保存同一套后端逻辑**：规范化 + 规范审查 + 结构校验，
 *       预览看到的就是真要写进去的那份；
 *    ③ 保存带内容指纹 + 全库写锁 + 原子写盘，不会覆盖别人的并发改动。
 *
 *  弹窗用 portal 挂到 body：详情抽屉有 transform 动画，`fixed` 留在里面
 *  会以抽屉为参照，弹窗就跑偏了。
 */
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertTriangle, Check, Code2, Loader2, Save, Search, X,
} from 'lucide-react'
import type { Q, SavedHandler } from '@/lib/types'
import { api } from '@/lib/api'
import { renderBlocks } from '@/lib/render'
import { CloseBtn, Report } from '@/app/ui'

/** 后端 `POST /api/questions/{key}/source` 的返回。 */
type SourceReport = Q & {
  ok: boolean
  saved?: boolean
  unchanged?: boolean
  tex?: string
  fixed?: string[]
  after?: { check: string; why: string; field?: string }[]
  /** 与录入页「干跑」同一套分块报告（`spec`/`images`/`impact`） */
  spec?: {
    before: { check: string; why: string; field?: string }[]
    fixed: string[]
    after: { check: string; why: string; field?: string }[]
    ok: boolean
  }
  images?: Record<string, { status: string; note: string }>
  impact?: { existing_questions: number; note: string }
  /** 后端详情里本来就有 problems；这里显式声明，免得和 Q 的定义打架 */
  problems?: string[]
}

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
const LABEL = 'text-[11px] font-semibold tracking-[0.08em] text-ink-faint'
const BTN =
  'press inline-flex h-[32px] items-center gap-1.5 rounded-lg border border-border ' +
  'bg-surface px-3 text-[12.5px] text-ink-soft transition-colors ' +
  'hover:border-border-strong hover:text-ink disabled:opacity-40'
const BTN_PRIMARY =
  'press inline-flex h-[32px] items-center gap-1.5 rounded-lg bg-brand px-3 text-[12.5px] ' +
  'font-medium text-white shadow-[var(--shadow-brand)] transition-[filter] ' +
  'hover:brightness-105 disabled:opacity-40'

export default function SourceEditor({ q, onClose, onSaved }: {
  q: Q
  onClose: () => void
  onSaved: SavedHandler
}) {
  const [orig, setOrig] = useState('')      // 打开时的源码，用于「还原」
  const [draft, setDraft] = useState('')
  const [hash, setHash] = useState(q.hash)  // 打开时的内容指纹（乐观并发）
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState('')
  const [loadNonce, setLoadNonce] = useState(0)
  const [busy, setBusy] = useState<'' | 'check' | 'save'>('')
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const [rep, setRep] = useState<SourceReport | null>(null)
  const [pv, setPv] = useState<Q | null>(null)
  // **通过检查的那份文本**。保存只认它 —— 与录入页同一条规矩：
  // 干跑通过才能确认导入，改完源码（哪怕改回原样）都得重新检查。
  const [checkedTex, setCheckedTex] = useState('')

  // 打开就直接取源码。**不验口令**，所以没有 auth 阶段。
  useEffect(() => {
    let alive = true
    setLoading(true); setLoadErr('')
    api.source(q.key, {})
      .then((d: { tex?: string; hash?: string }) => {
        if (!alive) return
        const tex = d.tex || ''
        setOrig(tex); setDraft(tex)
        setHash(d.hash || q.hash)
      })
      .catch((e) => { if (alive) setLoadErr(msg(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [q.key, loadNonce])

  // Esc 关闭（正在检查/保存时不让关，避免半途丢状态）
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [busy, onClose])

  const check = () => {
    if (!draft.trim()) { setErr('源码是空的'); return }
    setBusy('check'); setErr(''); setNote('')
    api.source(q.key, { tex: draft, expect_hash: hash })
      .then((d: SourceReport) => {
        setRep(d); setPv(d)
        // **检查通过才同步规范器改过的文本**：没通过时保留用户原稿，
        // 否则一按检查，验证器的中间产物会盖掉他正在改的内容。
        if (d.ok) {
          const fixedTex = d.tex || draft
          if (fixedTex !== draft) {
            setDraft(fixedTex)
            setNote(d.fixed?.length
              ? `规范器改动了 ${d.fixed.join('、')}，已同步到左侧`
              : '已同步规范器整理后的源码')
          }
          setCheckedTex(fixedTex)
        } else {
          setCheckedTex('')
        }
      })
      .catch((e) => setErr(msg(e)))
      .finally(() => setBusy(''))
  }

  const save = () => {
    if (!draft.trim()) { setErr('源码是空的'); return }
    // 与录入页同一条规矩：**没干跑过、或干跑没通过、或检查后又改过**，不许保存。
    if (!rep?.ok || checkedTex !== draft) {
      setErr('先点「检查」：通过之后才能保存（检查后又改过源码的话，要重新检查）')
      return
    }
    setBusy('save'); setErr(''); setNote('')
    api.source(q.key, { tex: draft, expect_hash: hash, dry_run: false })
      .then((d: SourceReport) => {
        setRep(d); setPv(d)
        // 源码可能改了题干/解析；详情用保存结果立即更新，列表在后台静默校正，
        // **不**再闪「正在刷新列表…」（用户明确要求一步到位）。
        if (d.ok) { onSaved(d, { refreshList: true, silent: true }); onClose() }
        else setErr(d.problems?.length
          ? '还有问题，见右侧预览上方的说明'
          : '规范审查没通过，见右侧预览上方的说明')
      })
      .catch((e) => setErr(msg(e)))
      .finally(() => setBusy(''))
  }

  const dirty = !loading && !loadErr && draft !== orig
  const bad = !!rep && !rep.ok

  return createPortal(
    <div className="anim-fade-in fixed inset-0 z-[80] flex items-center justify-center bg-scrim
                    p-4 backdrop-blur-[2px]">
      <div role="dialog" aria-modal="true" aria-label="改源码"
        className={`pop-c flex flex-col overflow-hidden rounded-[var(--radius-pop)]
                    border border-border bg-surface shadow-[var(--shadow-pop)] ${
          // 读取中/失败时是个小卡片；拿到了源码才展开成编辑器
          loading || loadErr
            ? 'w-[min(520px,92vw)]'
            : 'h-[min(88vh,900px)] w-[min(1180px,96vw)]'}`}>

        {/* ── 标题栏 ── */}
        <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg
                           bg-brand-soft text-brand-ink">
            <Code2 size={15} />
          </span>
          <span className="shrink-0 text-[15px] font-semibold tracking-tight">改源码</span>
          <span className="min-w-0 truncate font-mono text-[10.5px] text-ink-faint"
            title={q.key}>{q.key}</span>
          {dirty && (
            <span className="shrink-0 rounded-full bg-warn-soft px-2 py-[2px]
                             text-[10.5px] font-medium text-warn">未保存</span>
          )}
          <span className="ml-auto" />
          <CloseBtn onClick={onClose} title="关闭（Esc）" />
        </div>

        {loading ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-10 text-center">
            <Loader2 size={26} className="animate-spin text-brand" />
            <div className="text-[13px] text-ink-soft">正在读取源码…</div>
          </div>
        ) : loadErr ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-warn-soft text-warn">
              <X size={20} />
            </span>
            <div className="text-[14px] font-semibold text-warn">读取源码失败</div>
            <div className="max-w-[380px] text-[11.5px] leading-relaxed text-ink-faint">
              {loadErr}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <button onClick={() => setLoadNonce((n) => n + 1)} className={BTN}>重试</button>
              <button onClick={onClose} className={BTN}>关闭</button>
            </div>
          </div>
        ) : (
          /* ── 编辑界面 ── */
          <>
            <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border
                            bg-surface-2 px-4 py-2">
              <span className="text-[11.5px] text-ink-faint">
                改完点「检查」看渲染和审查结果，通过后再保存。
              </span>
              <span className="ml-auto" />
              <button onClick={() => { setDraft(orig); setRep(null); setPv(null); setCheckedTex(''); setErr(''); setNote('') }}
                disabled={!dirty || !!busy}
                className={BTN}>还原</button>
              <button onClick={check} disabled={!!busy || !draft.trim()} className={BTN}>
                {busy === 'check' ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
                {busy === 'check' ? '检查中…' : '检查'}
              </button>
              <button onClick={save}
                disabled={!!busy || !draft.trim() || !rep?.ok || checkedTex !== draft}
                title={!rep?.ok ? '先点「检查」，通过后才能保存' : ''}
                className={BTN_PRIMARY}>
                {busy === 'save' ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                {busy === 'save' ? '保存中…' : '保存'}
              </button>
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
              {/* 源码 */}
              <section className="flex min-h-0 flex-col border-b border-border lg:border-b-0 lg:border-r">
                <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2">
                  <span className={LABEL}>源码</span>
                  <span className="text-[10.5px] text-ink-faint">
                    元数据行不在这里；保存时自动重新解析
                  </span>
                </div>
                <textarea
                  value={draft}
                  autoFocus
                  spellCheck={false}
                  wrap="off"
                  onChange={(e) => {
                    // 源码一改，上一次的检查结论就过期了——**不能继续挂着
                    // 「检查通过」**，否则人以为改完还是好的。重新点检查即可。
                    setDraft(e.target.value); setErr(''); setNote('')
                    setRep(null); setPv(null); setCheckedTex('')
                  }}
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); save() }
                  }}
                  className="min-h-0 flex-1 resize-none overflow-auto border-0 bg-bg p-4
                             font-mono text-[12.5px] leading-[1.7] text-ink outline-none
                             focus:bg-surface" />
                <div className="flex shrink-0 items-center gap-2 border-t border-border px-4 py-1.5
                                text-[10.5px] text-ink-faint">
                  <span className="tnum">{draft.length.toLocaleString()} 字</span>
                  <span>·</span>
                  <span className="tnum">{draft.split('\n').length} 行</span>
                  <span className="ml-auto">⌘/Ctrl + Enter 保存</span>
                </div>
              </section>

              {/* 检查结果：**与录入页「干跑」同一套分块**——
                  ① 规范（验证→修改→复核） ② 解析结果 ③ 图片 ④ 字段 ⑤ 影响面。
                  两处说法不一样，人就得学两遍；同一件事就该长同一个样子。 */}
              <section className="flex min-h-0 flex-col">
                <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2">
                  <span className={LABEL}>检查结果</span>
                  {rep?.ok ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-has">
                      <Check size={12} />通过，可以保存
                    </span>
                  ) : bad ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-warn">
                      <AlertTriangle size={12} />还有问题
                    </span>
                  ) : (
                    <span className="text-[10.5px] text-ink-faint">点「检查」后更新</span>
                  )}
                  {note && <span className="ml-auto truncate text-[10.5px] text-brand-ink" title={note}>{note}</span>}
                </div>

                <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
                  {err && (
                    <div className="flex items-start gap-1.5 rounded-lg border border-warn-line
                                    bg-warn-soft px-2.5 py-2 text-[11.5px] text-warn">
                      <X size={13} className="mt-[1px] shrink-0" />{err}
                    </div>
                  )}

                  {/* 空态**说明"会出现什么"**：跟录入页一个字都不用改口 —
                      改了源码、点了检查，得到的还是这五样东西。 */}
                  {!rep && !err && (
                    <div className="anim-fade-in flex h-full flex-col justify-center gap-3 px-1">
                      <div className="flex items-center gap-2 text-[12.5px] text-ink-soft">
                        <Search size={13} className="shrink-0 text-ink-faint" />
                        点「检查」之后，这里依次给出五样东西：
                      </div>
                      <ol className="space-y-2">
                        {([
                          ['规范：验证 → 修改 → 复核', '改之前哪里不合规、规范器改了什么、复核过没过'],
                          ['解析结果', '改完的题干与选项长什么样（渲染预览）'],
                          ['图片', '引用了几张、哪些在库里、哪些缺'],
                          ['字段校验', '单选/多选/填空/解答的字段自不自洽'],
                          ['影响面', '这次会动到几道存量题'],
                        ] as const).map(([tt, dd], i) => (
                          <li key={tt} className="flex gap-2.5 rounded-[var(--radius-card)] border
                                                 border-border bg-surface p-2.5">
                            <span className="mt-[1px] grid h-4 w-4 shrink-0 place-items-center rounded
                                             bg-muted text-[10px] font-semibold text-ink-faint">
                              {i + 1}
                            </span>
                            <span className="min-w-0">
                              <span className="block text-[12px] font-medium text-ink">{tt}</span>
                              <span className="mt-0.5 block text-[11px] leading-relaxed text-ink-faint">
                                {dd}
                              </span>
                            </span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {rep && (<>
                    <Report n="①" title="规范：验证 → 修改 → 复核">
                      <div className="space-y-2 text-[11.5px]">
                        <div className="flex items-center gap-2">
                          <span className="w-14 shrink-0 text-ink-faint">改之前</span>
                          {rep.spec?.before?.length ? (
                            <span className="inline-flex items-center gap-1 font-medium text-warn">
                              <X size={12} className="shrink-0" />{rep.spec.before.length} 处不合规
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 font-medium text-has">
                              <Check size={12} className="shrink-0" />本来就合规
                            </span>
                          )}
                        </div>
                        {!!rep.spec?.before?.length && (
                          <div className="ml-[3.75rem] space-y-0.5 text-[10.5px] text-ink-faint">
                            {rep.spec.before.slice(0, 5).map((b, i) => (
                              <div key={i} className="truncate">[{b.check}] {b.why}</div>
                            ))}
                            {rep.spec.before.length > 5 &&
                              <div>… 其余 {rep.spec.before.length - 5} 处</div>}
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <span className="w-14 shrink-0 text-ink-faint">规范器</span>
                          {rep.spec?.fixed?.length
                            ? <span className="text-ink-soft">{rep.spec.fixed.join(' · ')}</span>
                            : <span className="text-ink-faint">无需改动</span>}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="w-14 shrink-0 text-ink-faint">复核后</span>
                          {rep.spec?.ok ? (
                            <span className="inline-flex items-center gap-1 font-medium text-has">
                              <Check size={12} className="shrink-0" />全部规范，可以保存
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 font-medium text-warn">
                              <X size={12} className="shrink-0" />
                              仍有 {rep.spec?.after?.length ?? 0} 处 —— 先改源码
                            </span>
                          )}
                        </div>
                      </div>
                    </Report>

                    <Report n="②" title={`解析结果：${rep.type_label || rep.type}`}>
                      <div className="space-y-3">
                        <div>
                          <div className="q-stem text-ink">{renderBlocks(pv?.blocks?.stem)}</div>
                          {pv && pv.options?.length > 0 && (
                            <ul className="q-options mt-3 space-y-1">
                              {pv.options.map((o, i) => (
                                <li key={o.label}>
                                  <span className="lbl">{o.label}.</span>
                                  <span>{renderBlocks(pv.blocks?.options?.[i])}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                        <div>
                          <div className="mb-1 text-[11px] font-semibold tracking-[0.08em] text-danger">答案</div>
                          <div className="text-[13.5px] font-semibold leading-relaxed text-danger">
                            {pv?.answer ? renderBlocks(pv.blocks?.answer)
                                        : <span className="text-[12px] font-normal text-ink-faint">（没有答案）</span>}
                          </div>
                        </div>
                        <div>
                          <div className={`mb-1 ${LABEL}`}>解析</div>
                          <div className="q-solution text-ink-soft">
                            {pv?.solution ? renderBlocks(pv.blocks?.solution)
                                          : <span className="text-[12px] text-ink-faint">（没有解析）</span>}
                          </div>
                        </div>
                      </div>
                    </Report>

                    <Report n="③" title={`图片检查：${Object.keys(rep.images || {}).length} 张`}>
                      {Object.keys(rep.images || {}).length === 0
                        ? <div className="text-[11.5px] text-ink-faint">没有引用图片</div>
                        : <div className="space-y-1">
                            {Object.entries(rep.images || {}).map(([k, v]) => (
                              <div key={k} className="flex items-center gap-2 text-[11.5px]">
                                <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-ink-soft">{k}</span>
                                <span className={`inline-flex shrink-0 items-center gap-1 ${
                                  v.status === 'missing' ? 'text-warn' : 'text-has'}`}>
                                  {v.status === 'missing'
                                    ? <AlertTriangle size={11} className="shrink-0" />
                                    : <Check size={11} className="shrink-0" />}
                                  {v.note}
                                </span>
                              </div>
                            ))}
                          </div>}
                    </Report>

                    <Report n="④" title="字段校验">
                      {rep.problems?.length
                        ? <div className="space-y-1 text-[11.5px] text-warn">
                            <div className="inline-flex items-center gap-1 font-medium">
                              <AlertTriangle size={12} className="shrink-0" />
                              {rep.problems.length} 个问题
                            </div>
                            {rep.problems.map((x, i) => <div key={i} className="ml-3">· {x}</div>)}
                          </div>
                        : <div className="inline-flex items-center gap-1 text-[11.5px] font-medium text-has">
                            <Check size={12} className="shrink-0" />全部通过
                          </div>}
                    </Report>

                    <Report n="⑤" title="影响面">
                      <div className={`text-[12px] font-medium ${
                        rep.impact?.existing_questions ? 'text-warn' : 'text-has'}`}>
                        存量题目影响：{rep.impact?.existing_questions ?? 0} 道
                      </div>
                      <div className="mt-1 text-[11px] leading-snug text-ink-faint">
                        {rep.impact?.note}
                      </div>
                    </Report>
                  </>)}
                </div>
              </section>
            </div>

            {/* 底部：错误 + 关闭 */}
            <div className="flex shrink-0 items-center gap-2 border-t border-border px-4 py-2.5">
              <span className="min-w-0 truncate text-[11px] text-ink-faint">
                {err ? <span className="text-warn">{err}</span>
                     : dirty ? '改动还没保存'
                     : '没有改动'}
              </span>
              <span className="ml-auto" />
              <button onClick={onClose} className={BTN}>关闭</button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  )
}
