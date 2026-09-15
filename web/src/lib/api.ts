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
  } catch {
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
  list: (p: Record<string, string>) =>
    request(`/api/questions?${new URLSearchParams(p)}`),
  /** 改标签（考点/难度）。**只动标签，动不了正文**——后端会校验指纹。 */
  patch: (key: string, body: Record<string, unknown>) =>
    send('/api/questions/' + enc(key), 'PATCH', body),
  facets: () => request('/api/facets'),
  /** 单题完整记录。**带 `tex`**——卷面上真正会写出去的那段源码，
   *  由 `amti/render_tex.py` 生成，前端不再自己拼一遍。 */
  get: (key: string) => request('/api/questions/' + enc(key)),
  baseline: () => request('/api/baseline'),
  changes: () => request('/api/changes'),
  changeText: (name: string) => request('/api/changes/' + enc(name)),
  statsDetail: () => request('/api/stats/detail'),
  export: (body: any) => send('/api/export', 'POST', body),
  exportSlidev: (body: any) => send('/api/export/slidev', 'POST', body),
  exportBlocks: (body: any) => send('/api/export/slidev-blocks', 'POST', body),
  handouts: () => request('/api/handouts'),
  handout: (name: string) => request(`/api/handouts/${enc(name)}`),
  saveHandout: (body: any) => send('/api/handouts', 'POST', body),
  deleteHandout: (name: string) => send(`/api/handouts/${enc(name)}`, 'DELETE'),
  generate: (body: any) => send('/api/generate', 'POST', body),
  ingestPreview: (body: any) => send('/api/ingest/preview', 'POST', body),
  ingestCommit: (body: any) => send('/api/ingest/commit', 'POST', body),
  /* ── 回收站 ────────────────────────────────────────
     「删除」不是真删：移进回收站（存整道题），随时能恢复。 */
  trashReasons: () => request('/api/trash/reasons'),
  /** **批量**删题。理由：现在不考的题很多，一道道点太慢。 */
  trashBatch: (keys: string[], reason: string, password: string) =>
    send('/api/trash/delete', 'POST', { keys, reason, password }),
  /** 把当前状态存成**新基线**——有意改完数据后点一下，顶栏回到「存量未改动」。 */
  snapshot: () => send('/api/snapshot', 'POST'),
  trash: (key: string, reason: string, password: string) =>
    send(`/api/questions/${enc(key)}/trash`, 'POST', { reason, password }),
  trashList: () => request('/api/trash'),
  trashRestore: (keys: string[]) => send('/api/trash/restore', 'POST', { keys }),
  trashPurge: (keys: string[], password: string) =>
    send('/api/trash/purge', 'POST', { keys, password }),
  reveal: (path: string) => request('/api/reveal?path=' + enc(path)),
  /* ── 试卷存档 / 合集 ────────────────────────────
     存档里只存**题号**，所以任何时候都能原样还原那套卷。 */
  papers: () => request('/api/papers'),
  paperSave: (body: any) => send('/api/papers', 'POST', body),
  paperDelete: (name: string) => send(`/api/papers/${enc(name)}`, 'DELETE'),
}
