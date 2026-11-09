import { createContext, useContext } from 'react'
import type { ReactNode } from 'react'
import type { IngestBag } from './useIngest'

const Ctx = createContext<IngestBag | null>(null)

export function IngestProvider({ value, children }: {
  value: IngestBag
  children: ReactNode
}) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useIngestCtx(): IngestBag {
  const v = useContext(Ctx)
  if (!v) throw new Error('useIngestCtx 必须在 IngestProvider 内使用')
  return v
}
