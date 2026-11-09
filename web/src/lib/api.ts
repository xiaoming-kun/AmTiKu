/** 后端 API 层：统一请求、错误上报。
 *
 *  从 App.tsx 抽出来（编辑器拆成独立模块后两边都要用）。
 */
/** 统一的请求入口。
 *
 *  以前每个方法都是裸 `fetch(...).then(r => r.json())`：**不查 `r.ok`**，
 *  后端报错时返回的 `{"detail": ...}` 会被当成正常数据往下传 ——
 *  表现成"这个考点没题""保存成功但其实没存"这类静默错误
 *  （代码审查报告 C-1）。现在错误在这里统一抛，调用方 try/catch 或 .catch()。
 */
export async function request<T = any>(url: string, init?: RequestInit): Promise<T> {
  let r: Response
  try {
    r = await fetch(url, init)
  } catch (e) {
    // **主动取消不是故障**：加了 `AbortController` 之后，切筛选/关页面都会
    // 取消在途请求。这里要是把它翻译成"连不上"，用户会看到红条报错。
    if ((e as { name?: string } | null)?.name === 'AbortError') throw e
    throw new Error('连不上题库服务，确认服务还在跑')
  }
  if (!r.ok) {
    let msg = `请求失败（HTTP ${r.status}）`
    try {
      const j = await r.json()
      if (j?.detail) msg = String(j.detail)
    } catch { /* 响应不是 JSON —— 用默认文案 */ }
    throw new Error(msg)
  }
  // 有些接口 204/空体，直接 .json() 会抛
  const ct = r.headers.get('content-type') || ''
  if (!ct.includes('json')) return null as T
  return r.json() as Promise<T>
}

/** 带 JSON body 的 POST/PATCH/DELETE 便捷写法 */
export const send = <T = any>(url: string, method: string, body?: unknown) =>
  request<T>(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

/** 模块级错误上报。
 *
 *  组件里不用层层传 prop —— 挂在 window 上的事件没人管的话，
 *  失败就是静默的（这是审查报告 C-1 指出的病根）。
 */
let _onGlobalErr: ((msg: string) => void) | null = null

export function reportErr(e: unknown) {
  const msg = e instanceof Error ? e.message : String(e)
  if (_onGlobalErr) _onGlobalErr(msg)
  else console.error('[AmTiKu]', msg)
}

export const enc = encodeURIComponent

/** App 启动时注册错误提示入口（顶栏那条警告带） */
export function setGlobalErrHandler(fn: ((msg: string) => void) | null) {
  _onGlobalErr = fn
}

export const api = {
  /** 列表。`signal` 用来**取消在途请求**——改筛选/翻页时旧请求已经没意义，
   *  它还会白白扫一遍全库（2.8 万道），回来晚了又会覆盖新结果。 */
  list: (p: Record<string, string>, signal?: AbortSignal) =>
    request(`/api/questions?${new URLSearchParams(p)}`, signal ? { signal } : undefined),
  /** 改标签（考点/难度）。**只动标签，动不了正文**——后端会校验指纹。 */
  patch: (key: string, body: Record<string, unknown>) =>
    send('/api/questions/' + enc(key), 'PATCH', body),
  /** 批量改标签（考点/难度/星级/年份/地区/书卷名）。**一次写盘**。
   *  正文改不了——后端只接受标签字段，且整批过 conform。 */
  batchPatch: (body: {
    keys: string[]
    points?: string[]
    /** 考点操作：默认 replace；add 追加；remove 移除 */
    point_mode?: 'replace' | 'add' | 'remove'
    difficulty?: string
    stars?: number
    year?: number | string
    region?: string
    book?: string
    label?: string
    reviewed?: boolean
  }) => send('/api/questions/batch', 'POST', body),
  /** 改源码。三种用法：`{}` = 取当前源码；`{tex}` = 只检查；
   *  再加 `dry_run: false` = 保存。不设口令；安全靠解析/规范审查/
   *  指纹校验/原子写盘。 */
  source: (key: string, body: {
    tex?: string; dry_run?: boolean; expect_hash?: string
  }) => send('/api/questions/' + enc(key) + '/source', 'POST', body),
  facets: (stage = '') =>
    request('/api/facets' + (stage ? `?stage=${encodeURIComponent(stage)}` : '')),
  /** 学段驾驶舱：图谱 / 讲义 / 题库 / 组卷四段流水线汇总。 */
  overview: (stage = 'senior') =>
    request(`/api/overview?stage=${encodeURIComponent(stage)}`),
  /** 小学/初中诊断题库（高中走 /api/questions）。 */
  diagnostics: (p: Record<string, string>) =>
    request(`/api/diagnostics?${new URLSearchParams(p)}`),
  diagnosticsExport: (body: {
    stage: string; q?: string; book?: string; chapter?: string; point?: string;
    level?: string; limit?: number; title?: string; answers?: boolean
  }) => send('/api/diagnostics/export', 'POST', body),
  /** 知识地图：学段 → 年级/册 → 章 → 知识点（按教材顺序）。只读。 */
  map: () => request('/api/map'),
  /** 考点专题：列表 / 详情（含讲义 PDF 地址与精选题）。 */
  topics: (stage = '') =>
    request('/api/topics' + (stage ? `?stage=${encodeURIComponent(stage)}` : '')),
  topic: (id: string) => request('/api/topics/' + enc(id)),
  /** 从高中考点新建一份讲义骨架（不覆盖已有讲义）。 */
  topicNew: (point: string, title = '') => send('/api/topics/new', 'POST', { point, title }),
  /** 网页版讲义（HTML 片段 + KaTeX 公式）。 */
  topicLecture: (id: string) => request('/api/topics/' + enc(id) + '/lecture'),
  topicHistory: (id: string) => request('/api/topics/' + enc(id) + '/history'),
  topicRestore: (id: string, name: string) => send('/api/topics/' + enc(id) + '/restore', 'POST', { name }),
  /** 单个知识点的诊断题（小学/初中）。 */
  mapQuestions: (id: string) => request('/api/map/questions/' + enc(id)),
  /** 单题完整记录。**带 `tex`**——卷面上真正会写出去的那段源码，
   *  由 `amti/render_tex.py` 生成，前端不再自己拼一遍。 */
  get: (key: string) => request('/api/questions/' + enc(key)),
  /** 列表「显示答案」：只取答案的块 IR，避免为一道题拉整份解析。 */
  answer: (key: string) => request('/api/questions/' + enc(key) + '/answer'),
  /** 相似题：同考点 / 同公式结构 / 同题型。 */
  similar: (key: string, limit = 8) =>
    request(`/api/questions/${enc(key)}/similar?limit=${limit}`),
  /** 重复题：同指纹 / duplicate_group / dup_of。只提示，不合并。 */
  duplicates: (key: string) =>
    request(`/api/questions/${enc(key)}/duplicates`),
  baseline: () => request('/api/baseline'),
  /** 只读设置（导出位置等）。 */
  settings: () => request('/api/settings'),
  changes: () => request('/api/changes'),
  changeText: (name: string) => request('/api/changes/' + enc(name)),
  statsDetail: () => request('/api/stats/detail'),
  /* ── 审阅工作台 ─────────────────────────────────────
     复核状态与“编辑过”分开；队列/抽样只读，决定通过下面一个写入口落盘。 */
  reviewStats: () => request('/api/review/stats'),
  reviewQueue: (p: Record<string, string>) =>
    request(`/api/review/queue?${new URLSearchParams(p)}`),
  reviewSample: (body: {
    n: number; seed?: number; book?: string; type?: string;
    year_from?: number; risk?: string
  }) => send('/api/review/sample', 'POST', body),
  reviewDecision: (body: {
    items: { key: string; status: string; note?: string }[]
    reviewer?: string
    batch_id?: string
  }) => send('/api/review/decision', 'POST', body),
  export: (body: any) => send('/api/export', 'POST', body),
  exportDocx: (body: any) => send('/api/export/docx', 'POST', body),
  ingestJobs: () => send('/api/ingest/jobs?limit=6', 'GET'),
  ingestJob: (id: string) => send(`/api/ingest/jobs/${encodeURIComponent(id)}`, 'GET'),
  ingestJobSaveOcr: (id: string, body: any) =>
    send(`/api/ingest/jobs/${encodeURIComponent(id)}/ocr`, 'POST', body),
  ingestJobsPrune: (keep = 50) =>
    send(`/api/ingest/jobs/prune?keep=${Math.round(keep)}`, 'POST'),
  ingestJobDelete: (id: string) =>
    send(`/api/ingest/jobs/${encodeURIComponent(id)}`, 'DELETE'),
  /** 源文件准备：DOCX 转 PDF、TEX/MD/TXT 读文本；只准备，不入库。 */
  ingestPrepare: async (file: File): Promise<any> => {
    const r = await fetch(`/api/ingest/prepare?name=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
    })
    if (!r.ok) {
      let msg = `HTTP ${r.status}`
      try { const j = await r.json(); msg = j.detail || msg } catch { /* ignore */ }
      throw new Error(msg)
    }
    return r.json()
  },
  /** 分享包：返回 zip Blob（用原生 fetch，不走 JSON 的 request 包装）。 */
  shareExport: async (keys: string[], name: string): Promise<Blob> => {
    const r = await fetch('/api/share/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys, name }),
    })
    if (!r.ok) {
      let msg = `HTTP ${r.status}`
      try { const j = await r.json(); msg = j.detail || msg } catch { /* ignore */ }
      throw new Error(msg)
    }
    return r.blob()
  },
  shareImport: async (file: File): Promise<any> => {
    const r = await fetch('/api/share/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/zip' },
      body: file,
    })
    if (!r.ok) {
      let msg = `HTTP ${r.status}`
      try { const j = await r.json(); msg = j.detail || msg } catch { /* ignore */ }
      throw new Error(msg)
    }
    return r.json()
  },
  generate: (body: any) => send('/api/generate', 'POST', body),
  /** 单题换题：同题型/同板块/同难度的候选（只读，不写库）。 */
  replaceCandidates: (body: any) => send('/api/generate/replace', 'POST', body),
  ingestPreview: (body: any) => send('/api/ingest/preview', 'POST', body),
  ingestCommit: (body: any) => send('/api/ingest/commit', 'POST', body),
  /** 多题录入：只认前几行的标题/年份，用来预填出处（轻量，不查重）。 */
  ingestSource: (text: string) => send('/api/ingest/source', 'POST', { text }),
  /** 多题录入：qwen3.5 预标考点/难度。只读，不写库。 */
  ingestTag: (body: any) => send('/api/ingest/tag', 'POST', body),
  /* ── 大模型读图 ────────────────────────────────────
     图片/PDF → LaTeX 文本。**只识别，不写库**：结果填进录入框，
     再走上面的 preview → 人工审阅 → commit。
     模型按需启动——不点这个，LM Studio 不会被拉起来。 */
  vlmStatus: () => request('/api/vlm/status'),
  /* 标注/27B 模型状态与卸载（只释放内存，不碰题库） */
  llmStatus: () => request('/api/llm/status'),
  llmUnload: (model: string) => send('/api/llm/unload', 'POST', { model }),
  vlmExtract: (data: string, name: string, dpi = 200) =>
    send('/api/vlm/extract', 'POST', { data, name, dpi }),
  /* ── AI 录题（DeepSeek 读整份资料）──────────────────
     和读图不同：这个能吃 100 页 PDF，跑几分钟，所以是"开任务 + 轮询进度"。
     **仍然只读不写库**：产物是一段源材料文本，填进录入框后面走同一条管线。 */
  aiStatus: () => request('/api/ai/status'),
  /** 保存配置。`api_key` 传 undefined = 不动；传 "" = 清空。 */
  aiConfig: (body: {
    api_key?: string; base_url?: string; model?: string
    pages_per_call?: number; workers?: number
  }) => send('/api/ai/config', 'POST', body),
  aiTest: () => send('/api/ai/test', 'POST'),
  /** 开一个读资料任务。`answer*` 是**另一份文件**（答案/解析），没有就传空。 */
  aiRun: (data: string, name: string, answerData = '', answerName = '') =>
    send('/api/ai/run', 'POST', {
      data, name, answer_data: answerData, answer_name: answerName,
    }),
  aiJob: (id: string) => request('/api/ai/job/' + encodeURIComponent(id)),
  /** 取消：不再发新请求；已读到的批次保留，已经在飞的请求仍会计费。 */
  aiCancel: (id: string) =>
    send('/api/ai/job/' + encodeURIComponent(id) + '/cancel', 'POST'),
  /* ── 回收站 ────────────────────────────────────────
     「删除」不是真删：移进回收站（存整道题），随时能恢复。 */
  trashReasons: () => request('/api/trash/reasons'),
  /** **批量**删题。理由：现在不考的题很多，一道道点太慢。
   *  **不要口令**（删除可恢复）；清空回收站才要口令。 */
  trashBatch: (keys: string[], reason: string) =>
    send('/api/trash/delete', 'POST', { keys, reason }),
  /** 把当前状态存成**新基线**——有意改完数据后点一下，顶栏回到「存量未改动」。 */
  snapshot: () => send('/api/snapshot', 'POST'),
  trash: (key: string, reason: string) =>
    send(`/api/questions/${enc(key)}/trash`, 'POST', { reason }),
  trashList: () => request('/api/trash'),
  trashRestore: (keys: string[]) => send('/api/trash/restore', 'POST', { keys }),
  trashPurge: (keys: string[], password: string) =>
    send('/api/trash/purge', 'POST', { keys, password }),
  reveal: (path: string) => request('/api/reveal?path=' + enc(path)),
  /* ── 试卷存档 / 合集 ────────────────────────────
     存档里只存**题号**，所以任何时候都能原样还原那套卷。 */
  papers: () => request('/api/papers'),
  paper: (name: string) => request('/api/papers/' + enc(name)),
  paperSave: (body: any) => send('/api/papers', 'POST', body),
  paperDelete: (name: string) => send(`/api/papers/${enc(name)}`, 'DELETE'),
}
