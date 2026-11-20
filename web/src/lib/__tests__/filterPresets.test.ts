/** 筛选预设的 localStorage 读写：坏数据不能把筛选栏打挂，超过 30 条要截断。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FILTER_PRESETS_KEY, loadPresets, savePresets, type FilterPreset } from '@/lib/filterPresets'
import { EMPTY_FILTERS } from '@/lib/urlState'

function stubStorage(init: Record<string, string> = {}) {
  const map = new Map(Object.entries(init))
  const store = {
    getItem: (k: string) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k: string, v: string) => { map.set(k, v) },
    removeItem: (k: string) => { map.delete(k) },
    clear: () => map.clear(),
    key: (i: number) => Array.from(map.keys())[i] ?? null,
    get length() { return map.size },
    map,
  }
  vi.stubGlobal('localStorage', store)
  return store
}

const preset = (name: string, q = '三角'): FilterPreset => ({
  name, at: '2026-11-20T10:00:00.000Z', filters: { ...EMPTY_FILTERS, q }, sort: 'used',
})

afterEach(() => { vi.unstubAllGlobals() })

describe('loadPresets', () => {
  it('没有存过 → []', () => {
    stubStorage()
    expect(loadPresets()).toEqual([])
  })

  it('JSON 坏了 / 存的不是数组 → []，不抛错', () => {
    stubStorage({ [FILTER_PRESETS_KEY]: '{不是 json' })
    expect(loadPresets()).toEqual([])
    stubStorage({ [FILTER_PRESETS_KEY]: JSON.stringify({ name: 'x' }) })
    expect(loadPresets()).toEqual([])
  })

  it('丢掉 name 缺失/为空/非字符串、filters 缺失的条目，保留中文名', () => {
    stubStorage({
      [FILTER_PRESETS_KEY]: JSON.stringify([
        preset('2026 模拟·导数'),
        { name: '', filters: EMPTY_FILTERS },
        { name: 42, filters: EMPTY_FILTERS },
        { name: '没有 filters' },
        null,
        'not-an-object',
        { ...preset('缺答案'), filters: undefined },
      ]),
    })
    const out = loadPresets()
    expect(out.map((x) => x.name)).toEqual(['2026 模拟·导数'])
    expect(out[0].filters.q).toBe('三角')
    expect(out[0].at).toBe('2026-11-20T10:00:00.000Z')
  })

  it('超过 30 条只读前 30 条', () => {
    stubStorage({
      [FILTER_PRESETS_KEY]: JSON.stringify(Array.from({ length: 35 }, (_, i) => preset(`p${i}`))),
    })
    const out = loadPresets()
    expect(out).toHaveLength(30)
    expect(out[0].name).toBe('p0')
    expect(out.at(-1)?.name).toBe('p29')
  })
})

describe('savePresets', () => {
  it('写回 JSON，可被 loadPresets 原样读回', () => {
    const store = stubStorage()
    savePresets([preset('我的组合', '导数')])
    expect(JSON.parse(store.map.get(FILTER_PRESETS_KEY) as string)).toHaveLength(1)
    expect(loadPresets()[0]).toMatchObject({ name: '我的组合', sort: 'used' })
    expect(loadPresets()[0].filters.q).toBe('导数')
  })

  it('存之前截断到 30 条（别让 localStorage 被预设撑爆）', () => {
    stubStorage()
    savePresets(Array.from({ length: 40 }, (_, i) => preset(`p${i}`)))
    expect(loadPresets()).toHaveLength(30)
    expect(loadPresets().at(-1)?.name).toBe('p29')
  })

  it('localStorage 满/隐私模式抛错时不冒泡（存不下只是不记忆）', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => { throw new Error('QuotaExceededError') },
      removeItem: () => {}, clear: () => {}, key: () => null, length: 0,
    })
    expect(() => savePresets([preset('x')])).not.toThrow()
  })
})
