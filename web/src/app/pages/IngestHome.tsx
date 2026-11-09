/** 录题工作台。
 *
 *  旧版是一个右侧抽屉，从导航栏点进来直接就是一大片输入框——小白客户
 *  第一眼不知道「我可以粘贴，也可以把整份 PDF 交给 AI」。
 *  现在先给两个入口卡片，再说清四步流程；真正的编辑器仍然是同一个抽屉
 *  （核对/勾选/入库那套代码一份都不重复）。
 */
import { useMemo } from 'react'
import {
  ArrowRight, CheckCircle2, FileText, FolderOpen, ScanLine, Sparkles,
  UploadCloud, Wand2,
} from 'lucide-react'
import { STAGE_BY_KEY, type Stage } from '@/lib/stage'

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
  onOpen: (ai: boolean) => void
  onBank: () => void
}) {
  const draft = useMemo(readDraft, [])
  const meta = STAGE_BY_KEY[stage]
  const steps = [
    { t: '来源', d: '粘贴 LaTeX，或选一份 PDF / 照片' },
    { t: '识别', d: 'AI 抽成题，或直接用你粘的源' },
    { t: '核对', d: '逐题看考点、答案、解析、缺图' },
    { t: '入库', d: '整批校验通过才写盘，可撤销' },
  ]
  return (
    <div className="b-scroll h-full overflow-y-auto">
      <div className="b-page max-w-[1080px]">
        <span className="aurora-pill"><span className="live-dot" />录题工作台</span>
        <h2 className="mt-3 text-[30px] font-semibold leading-[1.1] tracking-[-.04em] md:text-[34px]">
          把一道题 <span className="grad-text">收进题库</span>
        </h2>
        <p className="mt-1 max-w-[640px] text-[12px] leading-relaxed text-ink-faint">
          当前学段：<span className="font-medium text-ink-soft">{meta.name}</span>。
          录进来的题会按考点自动归到对应学段；小学/初中的题只要考点选对，
          以后题库、图谱和组卷都会自动带上它。
        </p>

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
            <button onClick={() => onOpen(false)} className="b-btn b-btn-secondary h-8 px-3 text-[11.5px]">
              继续上次
            </button>
          </div>
        )}

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
          <button onClick={() => onOpen(false)}
            className="b-card b-card-hover group flex flex-col p-5 text-left">
            <div className="flex items-center gap-2.5">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-soft text-brand">
                <FileText size={19} />
              </span>
              <div>
                <div className="text-[14px] font-semibold">粘贴 LaTeX</div>
                <div className="text-[10.5px] text-ink-faint">最可控 · 一道或一整批</div>
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
            <div className="mt-4 flex items-center gap-1 text-[11.5px] font-medium text-brand-ink">
              开始录入 <ArrowRight size={12} />
            </div>
          </button>

          <button onClick={() => onOpen(true)}
            className="b-card b-card-hover group flex flex-col p-5 text-left">
            <div className="flex items-center gap-2.5">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#f5f3ff] text-[#6d28d9]">
                <Sparkles size={19} />
              </span>
              <div>
                <div className="text-[14px] font-semibold">AI 读整份资料</div>
                <div className="text-[10.5px] text-ink-faint">PDF / 照片 · 逐题核对</div>
              </div>
              <ArrowRight size={16} className="ml-auto text-ink-faint transition-transform group-hover:translate-x-0.5" />
            </div>
            <p className="mt-3 text-[11.5px] leading-relaxed text-ink-faint">
              把整份试卷/答案交给 DeepSeek：第一遍自动切题转录，第二遍拿答案册原页逐题核对；只有核对通过的题进核对界面（不自己解题，也不依赖本地模型）；
              识别结果进同一个核对界面，<b className="font-semibold text-ink-soft">仍然只读不写库</b>，你确认后才入库。
            </p>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {['100 页 PDF', '自动切题', '两遍核对', '人工确认'].map((x) => (
                <span key={x} className="b-chip">{x}</span>
              ))}
            </div>
            <div className="mt-4 flex items-center gap-1 text-[11.5px] font-medium text-[#6d28d9]">
              打开 AI 录题 <ArrowRight size={12} />
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
  )
}
