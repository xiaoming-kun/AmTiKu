/** 录入工作区 · 手工录题：粘贴 LaTeX、出处、可选批量标注。
 *  手工模式**不接受文件**；AI/文件读取在 DeepSeek 录题模式里。
 *  状态来自 useIngest，本组件只负责这一栏的渲染。 */
import { Check, Loader2, Play, Sparkles, X } from 'lucide-react'
import { useIngestCtx } from './IngestContext'
import AiIngestPanel from './AiIngestPanel'
import { DEFAULT_BOOK, DEFAULT_LABEL, DEFAULT_YEAR, FIELD, LABEL, MINI } from './shared'

export default function SourceStage() {
  const bag = useIngestCtx()
  const {
    ai, msg, aiClean, book, setBook, label, setLabel, region, setRegion,
    year, setYear, facets, srcDir, setSrcDir, keyNeedsSanitize, yearBad, pv, showHint,
    fillHint, backfill, setBackfill, resetReview, setMsg, nearThreshold, setNearThreshold,
    autoTag, setAutoTag, selected, specAfter, llmStatus, unloadLlm, refreshLlm, restored,
    clearDraft, changeText, busy, text, err, dryRun,
  } = bag
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto px-5 pt-4 pb-0">


            {ai && <AiIngestPanel />}

            <section id="ingest-source-material"
              className={`order-3 flex min-h-[240px] flex-1 flex-col ${aiClean ? 'hidden' : ''}`}>
              {restored && (
                <div className="mb-2 flex items-center gap-2 rounded-md border border-border
                                bg-surface-2 px-2 py-1 text-[10.5px] text-ink-faint">
                  已恢复上次未提交的草稿
                  <button onClick={clearDraft} className="underline hover:text-ink-soft">清空重来</button>
                </div>
              )}
              <div className="mb-2 flex shrink-0 flex-wrap items-center gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">1</span>
                <span className={`${LABEL} shrink-0 whitespace-nowrap`}>
                  {ai ? '识别出的 LaTeX（可校对）' : '粘贴 LaTeX'}
                </span>
                <span className="ml-auto text-[10px] text-ink-faint">
                  {ai ? 'AI 识别结果，可直接校对' : '直接粘贴，不读文件'}
                </span>
                {/[▲●○■□]/.test(text) && (
                  <button onClick={() => {
                    const next = text
                      .replace(/[\(（]\s*[▲●○■□]\s*[\)）]/g, '')
                      .replace(/[▲●○■□]/g, '')
                      .replace(/[\(（]\s*[\)）]\s*(?=\\paren\[)/g, '')
                    changeText(next)
                    setMsg('已清理 ▲ / ● / ○ / □ 答题占位符；请重新解析')
                  }} className="text-[10px] text-brand-ink underline underline-offset-2">
                    清理答题占位符
                  </button>
                )}
              </div>
              <div className="relative min-h-0 flex-1 overflow-hidden rounded-[var(--radius-card)]
                              border border-border bg-surface-2
                              focus-within:border-brand-line
                              focus-within:shadow-[0_0_0_3px_var(--color-brand-soft)]">
                <textarea value={text}
                  onChange={(e) => changeText(e.target.value)}
                  spellCheck={false}
                  placeholder={ai
                    ? 'AI 识别出的 LaTeX 会出现在这里；可以直接校对、补答案/解析，再点「重新解析」。'
                    : '在这里粘贴项目格式的 LaTeX；\n支持一道题，也支持一整份试卷。\n\n\\title{2025年长沙市高三调研}\n\\begin{question}\n…\n\\end{question}\n\\begin{solution}\n…\n\\end{solution}'}
                  className="h-full w-full resize-none bg-transparent px-4 py-3.5 font-mono
                             text-[12.5px] leading-relaxed outline-none placeholder:text-ink-faint" />
              </div>

            </section>

            <section className={`order-4 shrink-0 ${aiClean ? 'hidden' : ''}`}>
              <div className="mb-2 flex items-baseline gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">2</span>
                <span className={LABEL}>出处</span>
                <span className="text-[11px] text-ink-faint">
                  默认「{DEFAULT_BOOK} / {DEFAULT_LABEL} / {DEFAULT_YEAR}」；有
                  <code className="font-mono text-[10.5px]"> \title&#123;…&#125; </code>
                  时可点「填入出处」采用
                </span>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                {([['来源', book, setBook, '手工录入', 'ingest-books'],
                   ['出处', label, setLabel, '如 2025年长沙市高三调研', 'ingest-sources'],
                   ['地区', region, setRegion, '如 新高考I卷 / 武汉', 'ingest-regions'],
                   ['年份', year, setYear, '2025', '']] as const).map(([name, val, set, ph, list]) => (
                  <div key={name}>
                    <div className={`mb-1.5 ${LABEL}`}>{name}</div>
                    <input value={val} onChange={(e) => (set as any)(e.target.value)} placeholder={ph}
                      list={list || undefined}
                      inputMode={name === '年份' ? 'numeric' : undefined}
                      className={`${name === '出处' ? 'w-[230px]' : 'w-[160px]'} ${FIELD}`} />
                  </div>
                ))}
              </div>
              <datalist id="ingest-books">
                {(facets?.books || []).map((x: any) => <option key={x.value} value={x.value} />)}
              </datalist>
              <datalist id="ingest-sources">
                {(facets?.sources || []).slice(0, 400).map((x: any) => <option key={x.value} value={x.value} />)}
              </datalist>
              <datalist id="ingest-regions">
                {(facets?.regions || []).map((x: any) => <option key={x.value} value={x.value} />)}
              </datalist>
              <div className="mt-2">
                <div className={`mb-1.5 ${LABEL}`}>
                  图片来源目录 <span className="font-normal tracking-normal text-ink-faint/80">（可选；带 \includegraphics 时填）</span>
                </div>
                <input value={srcDir} onChange={(e) => setSrcDir(e.target.value)}
                  placeholder="例如 /Users/…/待录入图片（服务器本地路径；留空用默认目录）"
                  className={`w-full ${FIELD}`} />
              </div>
              {keyNeedsSanitize && (
                <div className="mt-2 text-[10.5px] text-ink-faint">
                  提示：来源/出处里的 “/” 或 “#” 只影响内部 key，后端会自动换成全角；
                  显示出处保持原文。
                </div>
              )}
              {yearBad && (
                <div className="mt-2 text-[10.5px] text-warn">
                  年份请填 4 位数字，如 2026。
                </div>
              )}
              {pv?.source_hint?.title && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
                  <Sparkles size={11} className="shrink-0 text-brand" />
                  标题识别：{pv.source_hint.title}
                  {pv.source_hint.year ? ` · ${pv.source_hint.year}` : ''}
                  {showHint && (
                    <button onClick={fillHint} className={MINI}>填入出处</button>
                  )}
                </div>
              )}
              <label className="mt-3 flex items-start gap-2 rounded-md border border-border
                                bg-bg px-2 py-1.5 text-[11px] text-ink-soft">
                <input type="checkbox" checked={backfill}
                  onChange={(ev) => {
                    const on = ev.target.checked
                    setBackfill(on)
                    resetReview()
                    setMsg(on
                      ? '补旧题模式：只给库里已有题补空考点/难度；请重新解析'
                      : '已切回普通录入；请重新解析')
                  }}
                  className="mt-[1px] accent-[var(--color-brand)]" />
                <span>
                  <b className="font-medium text-ink">补旧题模式</b>
                  <span className="text-ink-faint">
                    ：只更新库里**已有题**的空考点/空难度，不新增、不改答案/解析/已有考点
                  </span>
                </span>
              </label>
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
                <span>整题相似阈值</span>
                <input type="number" min={80} max={100} value={nearThreshold}
                  onChange={(ev) => {
                    const n = Number(ev.target.value)
                    setNearThreshold(Number.isFinite(n) ? Math.min(100, Math.max(80, n)) : 95)
                  }}
                  className="h-[24px] w-[62px] rounded-md border border-border bg-surface px-1.5
                             text-[11px] text-ink-soft outline-none focus:border-brand-line" />
                <span>%</span>
                <span>· 超过这个值按规则不录入；改动后请重新解析</span>
              </div>
            </section>

            {/* 批量：AI 只补空标签；逐题在右栏改。
                **大模型录题模式下整块不显示** —— 那边的考点/难度是 DeepSeek 读出来的，
                再去勾一个「解析后用 qwen3.5 自动标」只会让小白以为还得装个本地模型。 */}
            <section className={`order-5 shrink-0 ${ai ? 'hidden' : ''}`}>
              <div className="mb-2 flex items-baseline gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">3</span>
                <span className={LABEL}>批量</span>
                <span className="text-[11px] text-ink-faint">qwen3.5 只做粗标，人最后拍板</span>
              </div>
              <label className="flex items-start gap-2 text-[11.5px] text-ink-soft">
                <input type="checkbox" checked={autoTag}
                  onChange={(e) => setAutoTag(e.target.checked)}
                  className="mt-[1px] accent-[var(--color-brand)]" />
                <span>解析后用 <b className="font-medium text-ink">qwen3.5</b> 自动标考点/难度
                  <span className="text-ink-faint">
                    （默认关闭：不勾就不会启动模型；勾选后解析完才加载 9B。
                    不勾可点顶栏「AI 标注空缺」手动标）
                  </span></span>
              </label>
              {pv && (
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-ink-faint">
                  <span>已选 <b className="text-ink-soft">{selected.length}</b> / {pv.count} 道</span>
                  <span className="text-border">·</span>
                  <span>{pv.spec?.ok ? '规范复核通过' : `${specAfter} 处规范复核未过`}</span>
                </div>
              )}
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] text-ink-faint">
                <span>qwen3.5 标注模型：</span>
                {(() => {
                  const loaded: any[] = llmStatus?.loaded || []
                  const tagModel = String(llmStatus?.tag_model || 'qwen3.5-9b-mlx')
                  const tagRow = loaded.find((r) => r.identifier === tagModel
                    || r.model_key === tagModel
                    || String(r.identifier || '').includes(tagModel))
                  return tagRow ? (
                    <span className="inline-flex items-center gap-1 rounded bg-brand-soft px-1.5
                                     py-[1px] text-brand-ink">
                      已加载
                      <button onClick={() => void unloadLlm(tagRow.identifier, '9B 标注模型')}
                        className="underline">卸载</button>
                    </span>
                  ) : <span className="rounded bg-muted px-1.5 py-[1px]">未加载</span>
                })()}
                <button onClick={() => void refreshLlm()} className="underline">刷新</button>
              </div>
            </section>

            {/* 题目：输入框有边框；文件名/读图按钮跟着它。 */}
              <div className={`order-6 sticky bottom-0 z-10 -mx-5 mt-3 flex shrink-0 flex-col gap-2
                              border-t border-border bg-surface/95 px-5 py-2.5 backdrop-blur ${
                                ai && !text.trim() ? 'hidden' : ''}`}>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-ink-faint">
                  <span>{text.trim() ? `${text.trim().length.toLocaleString()} 字符` : '还没有材料'}</span>
                  <span className="text-border-strong">·</span>
                  <span className="truncate">{label || '未填出处'}{year ? ` · ${year}` : ''}</span>
                  <span className="text-border-strong">·</span>
                  <span>只解析、不入库</span>
                </div>
                {err && !pv && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-warn-line
                                  bg-warn-soft px-2.5 py-2 text-[11.5px] text-warn">
                    <X size={13} className="mt-[1px] shrink-0" />{err}
                  </div>
                )}
                {msg && !pv && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-has-line
                                  bg-has-soft px-2.5 py-2 text-[11.5px] text-has">
                    <Check size={13} className="mt-[1px] shrink-0" />{msg}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="hidden text-[11px] text-ink-faint sm:inline">
                    脚本会先验证、再规范化、最后复核；不合规的不让入库
                  </span>
                  <span className="text-[10.5px] text-ink-faint sm:hidden">只解析，不写库</span>
                  <button onClick={() => void dryRun()} disabled={busy || !text.trim()}
                    className="press ml-auto inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 rounded-lg border
                               border-brand-line bg-brand-soft px-4 py-2 text-[13px] font-semibold
                               text-brand-ink transition-colors hover:bg-brand hover:text-white
                               disabled:opacity-40 disabled:hover:bg-brand-soft
                               disabled:hover:text-brand-ink">
                    {busy ? <Loader2 size={13} className="shrink-0 animate-spin" />
                          : <Play size={13} className="shrink-0" />}
                    {pv ? '重新解析' : '解析成题'}
                  </button>
                </div>
                {busy && <div className="progress-track" />}
              </div>
    </div>
  )
}
