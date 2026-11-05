import { useEffect, useState } from 'react'

/** 把一个值**延迟到用户停手之后**再放出去。
 *
 *  为什么要这个：搜索框和请求之间的连线上没有刹车。中文输入法打「断臂」，
 *  实际会连发 `d`→`duan`→`duanb`… 每次都是服务端一次**全库扫描**（2.8 万道），
 *  而且响应速度相近、直接乱序落地——之前那个「搜「断臂」却显示 8840 道」
 *  就是这条链上生出来的。
 *
 *  只延迟**真正参与请求的值**，输入框照旧即时回显：用户看到的是自己打的字，
 *  首屏到出结果之间只差一次停手（默认 160ms，比一次往返还短）。
 */
export function useDebounced<T>(value: T, ms = 160): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}
