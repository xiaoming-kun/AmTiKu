/** 录题工作台。
 *
 *  旧版是一个右侧抽屉，从导航栏点进来直接就是一大片输入框——小白客户
 *  第一眼不知道「我可以粘贴，也可以把整份 PDF 交给 AI」。
 *  现在先给几个入口卡片，再说清四步流程；真正的编辑器仍然是同一个抽屉
 *  （核对/勾选/入库那套代码一份都不重复）。
 */
import { useEffect, useMemo, useState } from 'react'
import {
  ArrowRight, CheckCircle2, FileText, FolderOpen, ScanLine, ShieldCheck, Sparkles,
  UploadCloud, Wand2,
} from 'lucide-react'
import { STAGE_BY_KEY, type Stage } from '@/lib/stage'
import { api } from '@/lib/api'
import type { IngestMode } from '@/app/ingest/IngestWorkspace'

const DRAFT_KEY = 'amtiku.ingest.draft.v1'

function readDraft(): { text: string; book: string; n: number } | null {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || '{}')
    const text = String(d?.text || '')
    if (!text.trim()) return null
    return { text, book: String(d?.book || ''), n: text.split('\\begin{question}').length - 1 }
  } catch { return null }
}

export default function IngestHome({ stage, onOpen, onBank }: {
  stage: Stage
  onOpen: (mode: IngestMode) => void
  onBank: () => void
}) {
  const draft = useMemo(readDraft, [])
  const meta = STAGE_BY_KEY[stage]
  const [usage, setUsage] = useState<any>(null)
  const [usageErr, setUsageErr] = useState(false)
  useEffect(() => {
    let alive = true
    const load = () => {
      api.aiUsage()
        .then((d: any) => { if (alive) { setUsage(d); setUsageErr(false) } })
        .catch(() => { if (alive && !usage) setUsageErr(true) })
    }
    load()
    const t = window.setInterval(load, 30000)
    window.addEventListener('focus', load)
    return () => { alive = false; window.clearInterval(t); window.removeEventListener('focus', load) }
  }, [])   // eslint-disable-line
  const today = usage?.today || { cost_cny: 0, tokens: 0, calls: 0 }
  const total = usage?.total || { cost_cny: 0, tokens: 0, calls: 0 }
  const steps = [
    { t: '来源', d: '粘贴 LaTeX，或选一份 PDF / 照片' },
    { t: '识别', d: 'AI 抽成题，或直接用你粘的源' },
    { t: '核对', d: '逐题看考点、答案、解析、缺图' },
    { t: '入库', d: '整批校验通过才写盘，可撤销' },
  ]
  return (
    <div className="flex h-full min-h-0 flex-col bg-bg">
      <header className="flex h-14 shrink-0 items-center gap-2.5 border-b border-border bg-surface px-4 md:px-6">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[10px] grad-primary
                         text-[14px] font-bold text-white shadow-[var(--shadow-brand)]" aria-hidden>A</span>
        <span className="text-[14px] font-semibold tracking-[-.02em]">AmMath</span>
        <span className="text-border-strong">/</span>
        <span className="text-[12.5px] font-medium text-ink-soft">录入</span>
        <span className="rounded-full border border-brand-line bg-brand-soft px-1.5 py-[1px]
                         text-[10px] font-medium text-brand-ink">独立页</span>
        <span className="ml-auto truncate text-[10.5px] text-ink-faint">
          {meta.name} · 入库后按考点归档
        </span>
      </header>
      <div className="b-scroll min-h-0 flex-1 overflow-y-auto">
      <div className="b-page max-w-[1080px]">
        <div className="border-b border-border pb-4">
          <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
            <div className="min-w-0 flex-1">
              <h1 className="text-[22px] font-semibold tracking-tight">选择录入 / 整理 / 校对方式</h1>
              <p className="mt-1 text-[12px] leading-relaxed text-ink-soft">
                先选一种工作方式，进入独立工作区。录入只解析、不写库；整理和校对只给建议，确认后才写回。
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5 text-[10.5px] text-ink-faint">
              <CheckCircle2 size={12} />没有答案或解析的题不入库
            </div>
          </div>
          <div className="mt-2 text-[10.5px] text-ink-faint">
            完成或关闭本页，不会影响原工作台；入库后回原工作台刷新即可看到新题。
          </div>
          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div className="flex items-center gap-3 rounded-[var(--radius-card)] border-2
                            border-danger/30 bg-danger-soft px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="text-[9.5px] font-semibold uppercase tracking-[0.08em] text-danger">
                  今日 DeepSeek 花费
                </div>
                <div className="mt-0.5 tnum text-[24px] font-bold leading-none text-danger">
                  ¥{Number(today.cost_cny || 0).toFixed(3)}
                </div>
              </div>
              <div className="shrink-0 text-right text-[9.5px] leading-relaxed text-danger/75">
                {Number(today.tokens || 0).toLocaleString()} tokens
                <br />{today.calls || 0} 次调用
              </div>
            </div>
            <div className="flex items-center gap-3 rounded-[var(--radius-card)] border
                            border-border bg-surface px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="text-[9.5px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
                  累计 DeepSeek 花费
                </div>
                <div className="mt-0.5 tnum text-[24px] font-bold leading-none text-ink">
                  ¥{Number(total.cost_cny || 0).toFixed(3)}
                </div>
              </div>
              <div className="shrink-0 text-right text-[9.5px] leading-relaxed text-ink-faint">
                {Number(total.tokens || 0).toLocaleString()} tokens
                <br />{total.calls || 0} 次调用
              </div>
            </div>
          </div>
          {usageErr && (
            <div className="mt-1 text-[9.5px] text-warn">AI 用量流水暂时读不到；不影响录题。</div>
          )}
          {usage?.note && (
            <div className="mt-1 text-[9px] text-ink-faint">{usage.note}</div>
          )}
        </div>

        {draft && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-warn-line
                          bg-warn-soft px-4 py-3">
            <FileText size={16} className="text-warn" />
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] font-medium text-warn">上次录到一半</div>
              <div className="mt-0.5 truncate text-[10.5px] text-warn/80">
                {draft.book || '未填出处'} · 约 {draft.n || 1} 道 · 草稿还在本机
              </div>
            </div>
            <button onClick={() => onOpen('latex')} className="b-btn b-btn-secondary h-8 px-3 text-[11.5px]">
              继续上次
            </button>
          </div>
        )}

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          <button onClick={() => onOpen('latex')}
            className="b-card b-card-hover group flex flex-col p-4 text-left">
            <div className="flex items-center gap-2.5">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-soft text-brand">
                <FileText size={19} />
              </span>
              <div>
                <div className="text-[14px] font-semibold">手工录题</div>
                <div className="text-[10.5px] text-ink-faint">粘贴 LaTeX · 一道或一整批</div>
              </div>
              <ArrowRight size={16} className="ml-auto text-ink-faint transition-transform group-hover:translate-x-0.5" />
            </div>
            <p className="mt-3 text-[11.5px] leading-relaxed text-ink-faint">
              按项目格式粘贴 <code className="rounded bg-muted px-1 text-[10.5px]">\begin&#123;question&#125;</code>，
              解析器先做规范检查、查重、缺图预检，全部通过才允许入库。
            </p>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {['15 项规范检查', '查重', '缺图预检', '整批校验'].map((x) => (
                <span key={x} className="b-chip">{x}</span>
              ))}
            </div>
            <div className="mt-auto flex items-center gap-1 pt-4 text-[11.5px] font-medium text-brand-ink">
              开始手工录题 <ArrowRight size={12} />
            </div>
          </button>

          <button onClick={() => onOpen('ai')}
            className="b-card b-card-hover group flex flex-col p-4 text-left">
            <div className="flex items-center gap-2.5">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#f5f3ff] text-[#6d28d9]">
                <Sparkles size={19} />
              </span>
              <div>
                <div className="text-[14px] font-semibold">DeepSeek 录题</div>
                <div className="text-[10.5px] text-ink-faint">PDF / 图片 · 逐题核对</div>
              </div>
              <ArrowRight size={16} className="ml-auto text-ink-faint transition-transform group-hover:translate-x-0.5" />
            </div>
            <p className="mt-3 text-[11.5px] leading-relaxed text-ink-faint">
              整份试卷/答案交给 DeepSeek：先切题转录，再对照答案页核对。识别结果进同一个核对界面，
              <b className="font-semibold text-ink-soft">仍然只读不写库</b>，你确认后才入库。
              Word 请先另存为 PDF；这里只收 PDF / 图片。
            </p>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {['PDF / 图片', '自动切题', '两遍核对', '可补解析'].map((x) => (
                <span key={x} className="b-chip">{x}</span>
              ))}
            </div>
            <div className="mt-auto flex items-center gap-1 pt-4 text-[11.5px] font-medium text-[#6d28d9]">
              打开 DeepSeek 录题 <ArrowRight size={12} />
            </div>
          </button>

          <button onClick={() => onOpen('proof')}
            className="b-card b-card-hover group flex flex-col p-4 text-left">
            <div className="flex items-center gap-2.5">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#fff7ed] text-[#c2410c]">
                <ShieldCheck size={19} />
              </span>
              <div>
                <div className="text-[14px] font-semibold">AI 整理 / 校对</div>
                <div className="text-[10.5px] text-ink-faint">已有题 · 补缺项 · 答案 / 解析 / 配图</div>
              </div>
              <ArrowRight size={16} className="ml-auto text-ink-faint transition-transform group-hover:translate-x-0.5" />
            </div>
            <p className="mt-3 text-[11.5px] leading-relaxed text-ink-faint">
              从题库筛选已有题：DeepSeek 独立做一遍，校对答案、解析步骤和配图；
              缺考点/难度/答案/解析时也能补齐。逐条确认后写回，TikZ 在源码里核对。
            </p>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {['筛选整理', '校对答案/解析', '补考点/难度', '补 TikZ'].map((x) => (
                <span key={x} className="b-chip">{x}</span>
              ))}
            </div>
            <div className="mt-auto flex items-center gap-1 pt-4 text-[11.5px] font-medium text-[#c2410c]">
              打开整理 / 校对 <ArrowRight size={12} />
            </div>
          </button>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_.8fr]">
          <section className="b-card p-5">
            <div className="flex items-center gap-2">
              <Wand2 size={15} className="text-brand" />
              <h3 className="text-[13px] font-semibold">四步走完，题才真正进库</h3>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-4">
              {steps.map((s, i) => (
                <div key={s.t} className="relative rounded-xl border border-border bg-surface-2 p-3">
                  <div className="flex items-center gap-1.5">
                    <span className="grid h-5 w-5 place-items-center rounded-full bg-brand-soft
                                     text-[10px] font-semibold text-brand-ink">{i + 1}</span>
                    <span className="text-[11.5px] font-semibold">{s.t}</span>
                  </div>
                  <div className="mt-1.5 text-[10.5px] leading-relaxed text-ink-faint">{s.d}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-start gap-2 rounded-lg bg-brand-soft/60 px-3 py-2.5 text-[11px] leading-relaxed text-brand-ink">
              <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
              <span>没有答案或解析的题一律不许入库；解答题答案栏写「见解析」。宁缺勿错。</span>
            </div>
          </section>

          <section className="b-card p-5">
            <div className="flex items-center gap-2">
              <ScanLine size={15} className="text-ink-faint" />
              <h3 className="text-[13px] font-semibold">录完去哪</h3>
            </div>
            <div className="mt-3 space-y-2">
              <button onClick={onBank} className="b-btn b-btn-secondary w-full justify-between">
                <span className="flex items-center gap-2"><FolderOpen size={13} />去题库看刚录的题</span>
                <ArrowRight size={13} />
              </button>
              <div className="rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[10.5px] leading-relaxed text-ink-faint">
                新题默认按录入顺序排在题库末尾；在题库里按「新录入」排序就能看到。
                考点选对之后，知识图谱和讲义也会自动带上它。
              </div>
            </div>
            <div className="mt-4 text-[10.5px] leading-relaxed text-ink-faint">
              <div className="mb-1 font-semibold text-ink-soft">图片题</div>
              拖入或粘贴图片时，图片会按内容寻址命名存进 <code className="rounded bg-muted px-1">图片/</code>，
              不会因为改名断引用。
            </div>
          </section>
        </div>

        <div className="mt-4 flex items-center gap-2 text-[10.5px] text-ink-faint">
          <UploadCloud size={13} />
          所有数据只在本机；录题不会上传到任何外部服务器（AI 模式除外，调用的是你配置的模型）。
        </div>
      </div>
      </div>
    </div>
  )
}
