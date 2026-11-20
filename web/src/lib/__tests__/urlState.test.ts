/** 地址栏状态：刷新不丢、可分享的筛选。
 *
 *  这两个函数一个只读、一个只写，必须在「没写」和「写了空串」之间分得清
 *  （旧链接 `sort=` 是题库原序，缺省才是默认排序），所以测试全部走
 *  真实 URLSearchParams + 假 window，而不是把 URL 拼字符串猜。 */
import { afterEach, describe, expect, it, vi } from 'vitest'

type FakeWin = ReturnType<typeof installWindow>

function installWindow(search = '', pathname = '/bank', hash = '') {
  const location = { search, pathname, hash }
  const replaceCalls: string[] = []
  const win = {
    location,
    history: {
      // 模拟浏览器：replaceState 之后 location 就是新地址
      replaceState: (_state: unknown, _title: string, url: string) => {
        replaceCalls.push(url)
        const u = new URL(url, 'http://local')
        location.pathname = u.pathname
        location.search = u.search
        location.hash = u.hash
      },
    },
  }
  vi.stubGlobal('window', win)
  return { location, replaceCalls, win }
}

/** 每个用例都要重新加载模块：`INITIAL_URL` 是模块加载时读一次的。 */
async function load(search = '', pathname = '/bank', hash = ''): Promise<FakeWin & { mod: typeof import('@/lib/urlState') }> {
  const env = installWindow(search, pathname, hash)
  vi.resetModules()
  const mod = await import('@/lib/urlState')
  return { ...env, mod }
}

const nonDefaultFilters = {
  q: '三角 函数', type: 'multi_choice', kind: 'pic', point: 'p1,p2', pm: 'all',
  diff: '中档', year: '2024', source: '某卷', has: 'answer', missing: 'solution',
  inc: '1', scope: 'book', paper: '7', star: '4', quality: 'warn', psrc: 'a,b',
  asrc: 'c', reviewed: '1',
}

afterEach(() => { vi.unstubAllGlobals() })

describe('read（INITIAL_URL）', () => {
  it('没有 window（node/SSR）时给全默认值，写回也不抛错', async () => {
    vi.stubGlobal('window', undefined)
    vi.resetModules()
    const { INITIAL_URL, writeUrlState, EMPTY_FILTERS } = await import('@/lib/urlState')
    expect(INITIAL_URL).toEqual({
      filters: { ...EMPTY_FILTERS }, sort: null, page: 1, tab: '', view: '', stage: '', ingest: '',
    })
    expect(Object.keys(EMPTY_FILTERS)).toHaveLength(18)
    expect(Object.values(EMPTY_FILTERS).every((v) => v === '')).toBe(true)
    expect(() => writeUrlState(INITIAL_URL)).not.toThrow()
  })

  it('解析全部筛选字段（中文、逗号拼接、短名 rv）与页面/学段', async () => {
    const { mod } = await load(
      '?q=' + encodeURIComponent('三角 函数') + '&type=multi_choice&kind=pic&point=p1,p2&pm=all' +
      '&diff=%E4%B8%AD%E6%A1%A3&year=2024&source=%E6%9F%90%E5%8D%B7&has=answer&missing=solution' +
      '&inc=1&scope=book&paper=7&star=4&quality=warn&psrc=a,b&asrc=c&rv=1' +
      '&page=3&sort=raw&tab=legacy&view=bank&stage=primary&ingest=ai',
    )
    expect(mod.INITIAL_URL.filters).toEqual(nonDefaultFilters)
    expect(mod.INITIAL_URL.page).toBe(3)
    expect(mod.INITIAL_URL.sort).toBe('raw')
    expect(mod.INITIAL_URL.tab).toBe('legacy')
    expect(mod.INITIAL_URL.view).toBe('bank')
    expect(mod.INITIAL_URL.stage).toBe('primary')
    expect(mod.INITIAL_URL.ingest).toBe('ai')
  })

  it('页码归一到 >= 1 的整数（0 / 负数 / 非数字都回到第 1 页）', async () => {
    for (const bad of ['0', '-5', 'abc', '', '0.4']) {
      const { mod } = await load(`?page=${bad}`)
      expect(mod.INITIAL_URL.page, `page=${bad}`).toBe(1)
    }
    expect((await load('?page=12')).mod.INITIAL_URL.page).toBe(12)
  })

  it('区分「没写 sort」（null）和「写了空串」（旧链接的题库原序）', async () => {
    expect((await load('')).mod.INITIAL_URL.sort).toBeNull()
    expect((await load('?sort=')).mod.INITIAL_URL.sort).toBe('')
    expect((await load('?sort=raw')).mod.INITIAL_URL.sort).toBe('raw')
  })

  it('只认短名 rv，不认长名 reviewed（写出去的是短名，别指望旧长名生效）', async () => {
    expect((await load('?rv=1')).mod.INITIAL_URL.filters.reviewed).toBe('1')
    expect((await load('?reviewed=1')).mod.INITIAL_URL.filters.reviewed).toBe('')
  })
})

describe('writeUrlState', () => {
  it('默认状态不写任何参数（地址栏保持干净）', async () => {
    const { mod, replaceCalls } = await load('')
    mod.writeUrlState({
      filters: { ...mod.EMPTY_FILTERS }, sort: 'used', page: 1,
      tab: 'workbench', view: '', stage: 'senior', ingest: '',
    })
    expect(replaceCalls).toEqual([])
  })

  it('非默认值全部写进地址栏，筛选用短名（reviewed → rv）', async () => {
    const { mod, replaceCalls, location } = await load('')
    mod.writeUrlState({
      filters: { ...nonDefaultFilters }, sort: 'raw', page: 3,
      tab: 'health', view: 'bank', stage: 'primary', ingest: 'ai',
    })
    expect(replaceCalls).toHaveLength(1)
    const sp = new URLSearchParams(location.search)
    expect(sp.get('q')).toBe('三角 函数')
    expect(sp.get('type')).toBe('multi_choice')
    expect(sp.get('rv')).toBe('1')
    expect(sp.get('sort')).toBe('raw')
    expect(sp.get('page')).toBe('3')
    expect(sp.get('tab')).toBe('health')
    expect(sp.get('view')).toBe('bank')
    expect(sp.get('stage')).toBe('primary')
    expect(sp.get('ingest')).toBe('ai')
    expect(sp.has('reviewed')).toBe(false)
  })

  it('写出再读回：18 个筛选字段一个不丢（防止字段表与写回逻辑脱节）', async () => {
    const first = await load('')
    first.mod.writeUrlState({
      filters: { ...nonDefaultFilters }, sort: 'raw', page: 2,
      tab: '', view: 'bank', stage: 'junior', ingest: '',
    })
    vi.resetModules()
    const second = (await import('@/lib/urlState')).INITIAL_URL
    expect(second.filters).toEqual(nonDefaultFilters)
    expect(second).toMatchObject({ sort: 'raw', page: 2, view: 'bank', stage: 'junior' })
  })

  it('sort 传空串会写成 sort=（旧链接兼容），不是删掉', async () => {
    const { mod, location } = await load('')
    mod.writeUrlState({
      filters: { ...mod.EMPTY_FILTERS }, sort: '', page: 1,
      tab: 'workbench', view: '', stage: 'senior', ingest: '',
    })
    const sp = new URLSearchParams(location.search)
    expect(sp.has('sort')).toBe(true)
    expect(sp.get('sort')).toBe('')
  })

  it('目标地址与当前一致时不重复 replaceState（否则点一下筛就刷一条历史）', async () => {
    const { mod, replaceCalls } = await load('?q=a&page=2')
    mod.writeUrlState({
      filters: { ...mod.EMPTY_FILTERS, q: 'a' }, sort: null, page: 2,
      tab: 'workbench', view: '', stage: 'senior', ingest: '',
    })
    expect(replaceCalls).toEqual([])
  })

  it('保留 hash；replaceState 被浏览器拒绝（file://）时不冒泡', async () => {
    const { mod, location } = await load('', '/bank', '#sec-2')
    mod.writeUrlState({
      filters: { ...mod.EMPTY_FILTERS, q: 'b' }, sort: null, page: 1,
      tab: 'workbench', view: '', stage: 'senior', ingest: '',
    })
    expect(location.hash).toBe('#sec-2')

    const env = installWindow('')
    env.win.history.replaceState = () => { throw new Error('SecurityError') }
    vi.resetModules()
    const mod2 = await import('@/lib/urlState')
    expect(() => mod2.writeUrlState({
      filters: { ...mod2.EMPTY_FILTERS, q: 'c' }, sort: null, page: 1,
      tab: 'workbench', view: '', stage: 'senior', ingest: '',
    })).not.toThrow()
  })
})
