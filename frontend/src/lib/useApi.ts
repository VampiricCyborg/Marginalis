import { useEffect, useState } from 'react'

export function useApi<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  useEffect(() => {
    let live = true
    setData(null)
    setError(null)
    fn().then((d) => live && setData(d)).catch((e) => live && setError(e))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return { data, error }
}
