/** AI 录题的「来源」面板：先连接、再配对资料、再明确点开始。
 *
 *  旧流程是「选文件即上传」，没配 Key 也会先开始、答案册还靠 confirm 追问，
 *  读取中只有一行进度。这里把 AI 读取拆成四步可见的动作：
 *    1 连接 DeepSeek（状态、测试、高级设置）
 *    2 配对试题 / 答案（暂存，不自动计费）
 *    3 明确点「开始读取」（按页计费，可取消）
 *    4 读取报告（页数 / 通过核对 / 待补 / 费用 / 覆盖）
 *
 *  真正的读取、取消、轮询仍在 useIngest；这里只负责把顺序和状态说清楚。
 */
import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, Check, CheckCircle2, FileText, KeyRound, Loader2,
  History, Play, RefreshCw, Sparkles, Upload, X,
} from 'lucide-react'
import { useIngestCtx } from './IngestContext'
import { FIELD, LABEL, MINI } from './shared'
import { api } from '@/lib/api'

function fmtSize(n: number): string {
  if (!n) return ''
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(n / 1024))} KB`
}

function looksLikeAnswerName(name: string): boolean {
  // 「试卷+答案」合订本仍归试题；只有明确的答案/解析册才自动移到答案栏。
  if (/试卷|试题|题目/.test(name)) return false
  return /(^|[_\-—\s（(])(参考)?答案[^/]*\.(pdf|png|jpe?g|webp|bmp)$/i.test(name)
    || /(^|[_\-—\s（(])解析[^/]*\.(pdf|png|jpe?g|webp|bmp)$/i.test(name)
    || /(^|[_\-—\s（(])(answer|solution)[^/]*\.(pdf|png|jpe?g|webp|bmp)$/i.test(name)
}

function stageOf(msg: string, done: boolean): number {
  if (done) return 3
  if (msg.includes('核对')) return 2
  if (msg.includes('转录') || msg.includes('答案册') || msg.includes('补读')) return 1
  return 0
}

const STEPS = ['上传 / 拆页', '转录', '对照答案', '生成题卡']

export default function AiIngestPanel() {
  const bag = useIngestCtx()
  const {
    aiBusy, aiProg, aiErr, setAiErr, aiNote, setAiNote, aiCfg, aiSetup, setAiSetup,
    aiKey, setAiKey, aiSaveKey, aiTesting, aiClearKey, aiModel, setAiModel,
    aiBase, setAiBase,
    aiAns, setAiAns, aiRunFiles, loadAiHistory, aiCancel, aiJobId, aiCancelling,
    aiReport, setAiReport, text, pv, changeText, selected,
  } = bag

  const [pending, setPending] = useState<File[]>([])
  const [drag, setDrag] = useState(false)
  const [hint, setHint] = useState('')
  const [answerDrag, setAnswerDrag] = useState(false)
  const [fillSolutions, setFillSolutions] = useState(false)
  const [hist, setHist] = useState<any[]>([])
  const [histOpen, setHistOpen] = useState(false)
  const [histLoading, setHistLoading] = useState(false)
  const answerInput = useRef<HTMLInputElement>(null)

  const configured = aiCfg?.configured === true
  const showSetup = !configured || aiSetup
  const done = !!aiReport
  const blocked = ((pv as any)?.items || []).filter((it: any) =>
    Array.isArray(it?.blocking) && it.blocking.length > 0)
  const msg = aiProg?.msg || ''
  const activeStep = done ? 4 : stageOf(msg, false)
  const pct = aiProg?.total
    ? Math.max(3, Math.min(100, Math.round(aiProg.done / aiProg.total * 100)))
    : null

  useEffect(() => {
    if (aiBusy) return
    let alive = true
    setHistLoading(true)
    api.aiHistory()
      .then((d: any) => { if (alive) setHist(Array.isArray(d?.items) ? d.items : []) })
      .catch(() => { /* 历史读不到不影响录题 */ })
      .finally(() => { if (alive) setHistLoading(false) })
    return () => { alive = false }
  }, [aiReport, aiBusy])

  const addSources = (fs: FileList | File[]) => {
    if (aiBusy) return
    const list = Array.from(fs || [])
    if (!list.length) return
    const existing = new Set(aiAns.map((a) => a.name))
    const answerLike = list.filter((f) => looksLikeAnswerName(f.name) && !existing.has(f.name))
    const sourceList = list.filter((f) => !answerLike.includes(f))
    if (answerLike.length) {
      readAnswers(answerLike,
        `检测到 ${answerLike.length} 份答案/解析文件，已自动放到「答案 / 解析」栏；`
        + '如果放错了，请从答案栏移除后重新选。选文件仍不会自动开始。')
    }
    if (!sourceList.length) {
      if (answerLike.length) setAiErr('')
      return
    }
    const good: File[] = []
    for (const f of sourceList) {
      const isPdf = /\.pdf$/i.test(f.name) || f.type === 'application/pdf'
      const isImg = f.type.startsWith('image/')
      if (!isPdf && !isImg) {
        setAiErr(`「${f.name}」不是 PDF / 图片；Word 请先另存为 PDF。`)
        continue
      }
      if (f.size > 200 * 1024 * 1024) {
        setAiErr(`「${f.name}」超过 200 MB，请先拆分或压缩。`)
        continue
      }
      good.push(f)
    }
    if (!good.length) return
    const first = pending.length === 0
    setPending((old) => [...old, ...good])
    setAiErr(''); setAiNote('')
    if (!answerLike.length) setHint(first ? '' : hint)
    if (first && aiAns.length && !answerLike.length) {
      setHint('答案文件会继续沿用；如果换了另一份卷子，请先移除旧答案，避免按题号抄错。')
    }
    if (first && text.trim()) {
      changeText('')
      setAiReport(null)
    }
  }

  const readAnswers = (fs: FileList | File[], note = '') => {
    if (aiBusy) return
    const list = Array.from(fs || []).filter((f) => {
      const isPdf = /\.pdf$/i.test(f.name) || f.type === 'application/pdf'
      const isImg = f.type.startsWith('image/')
      if (!isPdf && !isImg) setAiErr(`「${f.name}」不是 PDF / 图片；答案只收这两种。`)
      return isPdf || isImg
    })
    if (!list.length) return
    const read = (f: File) => new Promise<{ name: string; b64: string }>((resolve, reject) => {
      const rd = new FileReader()
      rd.onload = () => resolve({
        name: f.name, b64: String(rd.result || '').split(',')[1] || '',
      })
      rd.onerror = () => reject(new Error(`读不出「${f.name}」`))
      rd.readAsDataURL(f)
    })
    Promise.all(list.map(read))
      .then((got) => {
        setAiAns((old) => [...old, ...got])
        setAiErr(''); setHint(note)
      })
      .catch((e) => setAiErr(String((e as any)?.message || e)))
  }

  const start = () => {
    if (aiBusy) return
    if (!configured) {
      setAiSetup(true)
      setAiErr('先把 DeepSeek 连接好，再开始读取。')
      return
    }
    if (!pending.length) {
      setAiErr('先选至少一份试题 PDF / 图片。')
      return
    }
    setAiErr(''); setAiNote(''); setHint('')
    aiRunFiles(pending, fillSolutions)
  }

  const goReview = () => {
    window.dispatchEvent(new CustomEvent('ammath:ingest-review'))
  }

  const sourceBytes = pending.reduce((n, f) => n + f.size, 0)

  return (
    <section className="order-1 shrink-0 space-y-3 rounded-[var(--radius-card)] border border-brand-line
                        bg-brand-soft/25 p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#f5f3ff] text-[#6d28d9]">
          <Sparkles size={16} />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 text-[13px] font-semibold text-ink">
            DeepSeek 读取
            <span className="rounded-full border border-brand-line bg-surface px-1.5 py-[1px]
                             text-[9.5px] font-medium text-brand-ink">DeepSeek</span>
            <span className="rounded-full border border-border bg-surface px-1.5 py-[1px]
                             text-[9.5px] text-ink-faint"
              title="系统提示来自《试卷扫描标准化规范》§14.1；本地程序只追加 JSON schema">规范 §14.1</span>
          </div>
          <div className="mt-0.5 text-[10.5px] text-ink-faint">
            试题和答案分开选，读完自动对照；只读不写库
          </div>
        </div>
      </div>

      {aiCfg === null ? (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-2
                        text-[11px] text-ink-faint">
          <Loader2 size={12} className="animate-spin" />正在读取 DeepSeek 配置…
        </div>
      ) : showSetup ? (
        <div className="rounded-lg border border-brand-line bg-surface p-2.5">
          <div className="flex items-center gap-1.5 text-[12px] font-semibold text-ink">
            <KeyRound size={13} className="text-brand" />
            {configured ? 'DeepSeek 连接设置' : '连接 DeepSeek'}
          </div>
          {!configured && (
            <ol className="mt-1.5 space-y-0.5 text-[10.5px] leading-relaxed text-ink-soft">
              <li>1. 打开 platform.deepseek.com → API keys → 创建 API key</li>
              <li>2. 粘贴 Key → 保存并测试；之后不用再填</li>
            </ol>
          )}
          <div className="mt-2 flex items-center gap-1.5">
            <input type="password" value={aiKey} spellCheck={false}
              onChange={(e) => setAiKey(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && (aiKey.trim() || configured)) void aiSaveKey() }}
              placeholder={configured ? '留空 = 不更换 Key' : 'sk-…（只存这台电脑）'}
              className={`${FIELD} min-w-0 flex-1 font-mono`} />
            <button onClick={() => void aiSaveKey()}
              disabled={aiTesting || (!aiKey.trim() && !configured)}
              className="press inline-flex h-[32px] shrink-0 items-center gap-1 rounded-lg
                         bg-brand px-2.5 text-[11.5px] font-semibold text-white disabled:opacity-40">
              {aiTesting ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              保存并测试
            </button>
            {configured && (
              <button onClick={() => setAiSetup(false)} className={MINI}>收起</button>
            )}
          </div>
          <details className="mt-2 text-[10.5px] text-ink-faint">
            <summary className="cursor-pointer select-none">高级设置（模型 / 地址）</summary>
            <div className="mt-1.5 grid grid-cols-2 gap-1.5">
              <label className="col-span-2">
                <span className="mb-0.5 block">模型</span>
                <input value={aiModel} spellCheck={false} onChange={(e) => setAiModel(e.target.value)}
                  placeholder="deepseek-flash" className={`${FIELD} h-[28px] w-full font-mono`} />
              </label>
              <label className="col-span-2">
                <span className="mb-0.5 block">接口地址</span>
                <input value={aiBase} spellCheck={false} onChange={(e) => setAiBase(e.target.value)}
                  placeholder="https://api.deepseek.com" className={`${FIELD} h-[28px] w-full font-mono`} />
              </label>
            </div>
            <div className="mt-1">网络慢或接口不通时才需要改地址；改完点「保存并测试」。</div>
          </details>
          {configured && (
            <div className="mt-1.5 flex items-center gap-2 text-[10.5px] text-ink-faint">
              <span>当前 {aiCfg.model}{aiCfg.key_hint}</span>
              <button onClick={() => void aiClearKey()} className="underline hover:text-warn">清掉 Key</button>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-has-line
                        bg-has-soft/50 px-2.5 py-2 text-[10.5px] text-has">
          <CheckCircle2 size={13} />
          <span>DeepSeek 已连接 · {aiCfg.model}{aiCfg.key_hint}</span>
          <button onClick={() => void aiSaveKey()} disabled={aiTesting}
            className="ml-auto inline-flex items-center gap-1 rounded border border-has-line bg-surface
                       px-1.5 py-[2px] text-[10px] text-has disabled:opacity-40">
            {aiTesting ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
            {aiTesting ? '测试中' : '测试连接'}
          </button>
          <button onClick={() => { setAiSetup(true); setAiErr('') }}
            className="text-[10px] underline hover:text-ink">设置</button>
        </div>
      )}

      {aiBusy ? (
        <div className="rounded-lg border border-brand-line bg-surface p-3">
          <div className="flex items-center gap-2">
            <Loader2 size={14} className="shrink-0 animate-spin text-brand" />
            <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-ink">
              {msg || '正在上传…'}
            </span>
            <span className="tnum shrink-0 text-[10px] text-ink-faint">
              {aiProg?.sec ? `${aiProg.sec}s` : ''}
            </span>
            <button onClick={() => void aiCancel()} disabled={!aiJobId || aiCancelling}
              className="shrink-0 text-[10.5px] underline text-ink-faint hover:text-warn disabled:opacity-40">
              {aiCancelling ? '取消中…' : '取消'}
            </button>
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            {STEPS.map((s, i) => (
              <span key={s} className="flex min-w-0 flex-1 items-center gap-1">
                <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full
                  text-[9px] font-semibold ${i < activeStep ? 'bg-has-soft text-has'
                    : i === activeStep ? 'bg-brand text-white' : 'bg-muted text-ink-faint'}`}>
                  {i < activeStep ? <Check size={9} /> : i + 1}
                </span>
                <span className={`truncate text-[9.5px] ${i === activeStep ? 'font-medium text-ink' : 'text-ink-faint'}`}>
                  {s}
                </span>
              </span>
            ))}
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-brand transition-[width] duration-300"
              style={{ width: `${pct ?? 12}%` }} />
          </div>
          <div className="mt-1 flex items-center text-[9.5px] text-ink-faint">
            <span>{aiProg?.total ? `已读 ${aiProg.done} / ${aiProg.total} 页` : '正在准备页数…'}</span>
            <span className="ml-auto">可取消；已发出的请求仍会计费</span>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-1.5">
            <button onClick={() => setHistOpen((v) => !v)}
              className="press inline-flex h-6 items-center gap-1 rounded-md border border-border
                         bg-surface px-2 text-[10px] text-ink-soft hover:border-brand-line hover:text-brand-ink">
              <History size={11} />历史读取{hist.length ? ' (' + hist.length + ')' : ''}
              {histLoading ? <Loader2 size={10} className="animate-spin" /> : null}
            </button>
            <span className="text-[10px] text-ink-faint">不用重新上传；打开上次结果</span>
          </div>
          {histOpen && (
            <div className="max-h-36 space-y-1 overflow-y-auto rounded-lg border border-border bg-bg p-1.5">
              {hist.length === 0 ? (
                <div className="px-2 py-2 text-[10px] text-ink-faint">还没有历史读取</div>
              ) : hist.map((h) => (
                <button key={h.id} disabled={!h.has_result || aiBusy}
                  onClick={() => { setHistOpen(false); void loadAiHistory(h.id) }}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left
                             text-[10px] text-ink-soft hover:bg-surface disabled:cursor-not-allowed
                             disabled:opacity-45">
                  <FileText size={11} className="shrink-0 text-ink-faint" />
                  <span className="min-w-0 flex-1 truncate">
                    <b className="font-medium text-ink">{String(h.title || h.name || h.id).replace(/\\_/g, '_')}</b>
                    <span className="ml-1 text-ink-faint">
                      {String(h.created_at || '').slice(5, 16)} · {h.questions || 0} 道
                      {h.has_result ? ' · ¥' + Number(h.cost_cny || 0).toFixed(3) : ' · 未完成'}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <span className={LABEL}>资料配对</span>
            <span className="text-[10px] text-ink-faint">试题/答案分开放；答案 PDF 会自动移到答案栏，选文件不会自动开始</span>
          </div>

          <label
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); addSources(e.dataTransfer.files) }}
            className={`flex min-h-[92px] cursor-pointer items-center gap-3 rounded-xl border-2
                        border-dashed bg-surface p-3 transition-colors ${drag
                          ? 'border-brand bg-brand-soft/60'
                          : pending.length ? 'border-has-line' : 'border-border hover:border-brand-line'}`}>
            <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${
              pending.length ? 'bg-has-soft text-has' : 'bg-brand-soft text-brand'}`}>
              {pending.length ? <CheckCircle2 size={18} /> : <FileText size={18} />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[11.5px] font-semibold text-ink">
                试题 / 试卷 <span className="font-normal text-warn">必选</span>
                <span className="ml-1 font-normal text-ink-faint">可多选</span>
              </span>
              <span className="mt-0.5 block text-[10.5px] text-ink-faint">
                {pending.length
                  ? `已选 ${pending.length} 个文件 · ${fmtSize(sourceBytes)}；尚未开始`
                  : 'PDF 或图片；可以一次选多份，按选择顺序合并'}
              </span>
            </span>
            {pending.length > 0 ? (
              <button onClick={(e) => {
                e.preventDefault(); e.stopPropagation(); setPending([])
                setHint('已清空试题；如果换卷，请同时移除旧答案。')
              }} title="清空所有试题文件" className="icon-btn h-7 w-7 shrink-0">
                <X size={14} />
              </button>
            ) : <Upload size={15} className="shrink-0 text-ink-faint" />}
            <input type="file" accept=".pdf,image/*" multiple className="hidden"
              onChange={(e) => { addSources(e.target.files || []); e.currentTarget.value = '' }} />
          </label>

          {pending.length > 0 && (
            <div className="space-y-1">
              {pending.map((f, i) => (
                <div key={`${f.name}-${i}`}
                  className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1
                             text-[10px] text-ink-soft">
                  <FileText size={11} className="shrink-0 text-has" />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  <span className="tnum shrink-0 text-ink-faint">{fmtSize(f.size)}</span>
                  <button onClick={() => setPending((old) => old.filter((_, j) => j !== i))}
                    title="移除这份" className="icon-btn h-5 w-5 shrink-0"><X size={11} /></button>
                </div>
              ))}
            </div>
          )}

          <div
            onDragOver={(e) => { e.preventDefault(); setAnswerDrag(true) }}
            onDragLeave={() => setAnswerDrag(false)}
            onDrop={(e) => { e.preventDefault(); setAnswerDrag(false); readAnswers(e.dataTransfer.files) }}
            className={`rounded-lg border bg-surface px-2.5 py-2 ${
              answerDrag ? 'border-brand' : aiAns.length ? 'border-has-line' : 'border-border'}`}>
            <div className="flex items-center gap-2">
              <FileText size={13} className={`shrink-0 ${aiAns.length ? 'text-has' : 'text-ink-faint'}`} />
              <span className="shrink-0 text-[10.5px] font-medium text-ink-soft">答案 / 解析</span>
              <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-faint">
                {aiAns.length ? `已选 ${aiAns.length} 个文件` : '可选；可以多份，和试题分开'}
              </span>
              <button onClick={() => answerInput.current?.click()}
                className="press inline-flex h-[24px] shrink-0 items-center gap-1 rounded-md border
                           border-border bg-surface px-1.5 text-[10.5px] text-ink-soft
                           hover:border-brand-line hover:text-brand-ink">
                <Upload size={10} />添加文件
              </button>
            </div>
            {aiAns.length > 0 && (
              <div className="mt-1.5 space-y-1">
                {aiAns.map((f, i) => (
                  <div key={`${f.name}-${i}`}
                    className="flex items-center gap-1.5 rounded-md border border-border bg-bg px-2 py-1
                               text-[10px] text-ink-soft">
                    <FileText size={10} className="shrink-0 text-has" />
                    <span className="min-w-0 flex-1 truncate">{f.name}</span>
                    <button onClick={() => setAiAns((old) => old.filter((_, j) => j !== i))}
                      title="移除这份答案" className="icon-btn h-5 w-5 shrink-0"><X size={11} /></button>
                  </div>
                ))}
              </div>
            )}
            <input ref={answerInput} type="file" accept=".pdf,image/*" multiple className="hidden"
              onChange={(e) => { readAnswers(e.target.files || []); e.currentTarget.value = '' }} />
          </div>

          {hint && (
            <div className="rounded-md border border-warn-line bg-warn-soft px-2 py-1.5 text-[10px] text-warn">
              {hint}
            </div>
          )}
          {!aiAns.length && (
            <div className="text-[10px] text-ink-faint">
              没选答案：缺答案 / 解析的题会在核对时被拦下，不会静默入库。
            </div>
          )}

          <label className="flex items-start gap-2 rounded-lg border border-border bg-surface
                            px-2.5 py-2 text-[10.5px] leading-relaxed text-ink-soft">
            <input type="checkbox" checked={fillSolutions}
              onChange={(e) => setFillSolutions(e.target.checked)}
              className="mt-[2px] accent-[var(--color-brand)]" />
            <span>
              缺解析的题，让 DeepSeek 补写解析
              <span className="ml-1 text-ink-faint">
                （默认不补；会额外计费，生成的是模型解析，入库前仍需逐题核对）
              </span>
            </span>
          </label>

          <div className="rounded-lg border border-danger/25 bg-danger-soft px-2.5 py-2
                          text-[10px] leading-relaxed text-danger">
            <b>计费提醒</b>：选文件只暂存，不会自动上传；点「确认开始读取」才按页计费。
            取消或失败时，已经发出的请求仍可能收费。
          </div>

          <div className="flex flex-wrap items-center gap-2 border-t border-brand-line/60 pt-2.5">
            <span className="min-w-0 flex-1 text-[10px] leading-relaxed text-ink-faint">
              本次实际花费会在读取报告里用红字大字显示。
            </span>
            <button onClick={start} disabled={!pending.length || !configured || aiTesting}
              title={!configured ? '先连接 DeepSeek' : !pending.length ? '先选试题' : '确认开始读取'}
              className="press b-btn b-btn-primary h-8 shrink-0">
              <Play size={13} />{aiReport ? '重新读取' : aiErr ? '确认重试' : '确认开始读取'}
            </button>
          </div>
        </>
      )}

      {aiErr && (
        <div className="flex items-start gap-1.5 rounded-lg border border-warn-line
                        bg-warn-soft px-2.5 py-2 text-[11px] leading-relaxed text-warn">
          <AlertTriangle size={13} className="mt-[1px] shrink-0" />
          <span className="min-w-0 flex-1 break-words">{aiErr}</span>
          <button onClick={() => setAiErr('')} className="shrink-0 underline">知道了</button>
        </div>
      )}

      {aiNote && !aiBusy && !aiReport && (
        <div className="flex items-start gap-1.5 rounded-lg border border-has-line
                        bg-has-soft px-2.5 py-2 text-[11px] leading-relaxed text-has">
          <Check size={13} className="mt-[1px] shrink-0" />
          <span className="min-w-0 break-words">{aiNote}</span>
        </div>
      )}

      {aiReport && !aiBusy && (
        <div className="rounded-lg border border-has-line bg-surface p-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <CheckCircle2 size={13} className="text-has" />
            <span className="text-[11.5px] font-semibold text-ink">本次 DeepSeek 读取报告</span>
            <span className="ml-auto text-[10px] text-ink-faint">
              {aiReport.stats?.pages || 0} 页 · {aiReport.stats?.seconds || 0}s
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-end justify-between gap-2 rounded-xl
                          border-2 border-danger/35 bg-danger-soft px-3 py-2.5">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-danger">
                本次实际花费
              </div>
              <div className="mt-0.5 text-[9.5px] text-danger/75">
                按页计费 · 取消后已发出的请求也计入
              </div>
            </div>
            <div className="tnum text-[28px] font-bold leading-none text-danger">
              ¥{Number(aiReport.stats?.cost_cny || 0).toFixed(3)}
            </div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-3">
            {[
              ['通过核对', `${aiReport.stats?.ok || 0} 道`],
              ['待复核/待补', `${(aiReport.stats?.pending || 0) + blocked.length} 道`],
              ['答案册', aiReport.stats?.answer_pages ? `${aiReport.stats.answer_pages} 页` : '未提供'],
            ].map(([k, v]) => (
              <div key={k} className="rounded-md bg-bg px-2 py-1.5">
                <div className="text-[9.5px] text-ink-faint">{k}</div>
                <div className="text-[11px] font-semibold text-ink">{v}</div>
              </div>
            ))}
          </div>
          {aiReport.coverage?.expected ? (
            <div className="mt-1.5 text-[9.5px] leading-relaxed text-ink-faint">
              答案册覆盖 {aiReport.coverage.transcribed || 0}/{aiReport.coverage.expected}
              {aiReport.coverage.flawed?.length ? ` · 标错 ${aiReport.coverage.flawed.length} 道` : ''}
              {aiReport.coverage.missing?.length ? ` · 缺转录 ${aiReport.coverage.missing.length} 道` : ''}
              {aiReport.coverage.uncertain?.length ? ` · 核对未过 ${aiReport.coverage.uncertain.length} 道` : ''}
            </div>
          ) : null}
          {aiReport.pending?.length > 0 && (
            <div className="mt-1.5 rounded-md border border-warn-line bg-warn-soft px-2 py-1.5
                            text-[9.5px] leading-relaxed text-warn">
              还有 {aiReport.pending.length} 道未识别/待复核：
              {aiReport.pending.slice(0, 3).map((p: any) =>
                `第 ${p.no} 题 ${p.reason}`).join('；')}
              {aiReport.pending.length > 3 ? '…' : ''}
            </div>
          )}
          {(blocked.length > 0 || aiReport.pending?.length > 0) && (
            <div className="mt-2 rounded-lg border border-warn-line bg-warn-soft/45 px-2.5 py-2">
              <div className="flex flex-wrap items-center gap-1.5 text-[10.5px] font-semibold text-warn">
                <AlertTriangle size={11} />
                隔离/待补（全部保留，可查看，不会消失）
                <span className="font-normal text-ink-faint">
                  已识别 {blocked.length} 道在题卡里标红
                  {aiReport.pending?.length ? ` · 另有 ${aiReport.pending.length} 条未识别/待复核` : ''}
                </span>
              </div>
              <div className="mt-1.5 max-h-28 space-y-1 overflow-y-auto text-[10px] leading-relaxed text-ink-soft">
                {aiReport.pending?.map((p: any, i: number) => (
                  <div key={`p-${p.no || i}-${i}`} className="flex gap-1.5">
                    <span className="shrink-0 text-warn">未识别/待补</span>
                    <span className="min-w-0 flex-1">
                      第 {p.no || '?'} 题：{p.reason || '未交付'}
                      {p.page ? `（第 ${p.page} 页）` : ''}
                    </span>
                  </div>
                ))}
                {blocked.map((it: any) => (
                  <div key={`b-${it.block}-${it.key}`} className="flex gap-1.5">
                    <span className="shrink-0 text-warn">题卡</span>
                    <span className="min-w-0 flex-1">
                      第 {it.source_no || it.block + 1} 题：{(it.blocking || []).join('；')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {aiReport.source_label && (
            <div className="mt-1.5 rounded-md border border-brand-line bg-brand-soft/50 px-2 py-1.5
                            text-[9.5px] leading-relaxed text-ink-soft">
              已填入出处：<b className="font-medium text-ink">{aiReport.source_label}</b>
              {aiReport.source_region ? ` · ${aiReport.source_region}` : ''}
            </div>
          )}
          {(aiReport.stats?.generated_solutions || 0) > 0 && (
            <div className="mt-1.5 rounded-md border border-warn-line bg-warn-soft px-2 py-1.5
                            text-[9.5px] leading-relaxed text-warn">
              {aiReport.stats.generated_solutions} 道解析由 DeepSeek 补写，题卡上已标「解析补写」；
              请逐题核对后再入库。
            </div>
          )}
          {aiReport.warnings?.length ? (
            <div className="mt-1.5 line-clamp-2 text-[9.5px] leading-relaxed text-warn">
              {aiReport.warnings.filter((w: string) => !w.includes('DeepSeek 补写')).slice(0, 3).join('；')}
            </div>
          ) : null}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <button onClick={goReview} disabled={!pv}
              className="press b-btn b-btn-primary h-7 text-[11px]">
              查看题卡
            </button>
            <button onClick={() => document.getElementById('ingest-source-material')
              ?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              className="b-btn b-btn-secondary h-7 text-[11px]">看识别源码</button>
            <span className="text-[9.5px] text-ink-faint">
              {pv ? `${selected.length} 道已勾选` : '正在生成题卡…'}
            </span>
          </div>
        </div>
      )}
    </section>
  )
}
