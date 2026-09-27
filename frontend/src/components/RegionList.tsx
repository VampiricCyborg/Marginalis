import { AnimatePresence, motion, useMotionValue, useSpring } from 'motion/react'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import type { BAStatus, MefResponse } from '../lib/api'
import { api, BA_LABEL, fmt } from '../lib/api'
import { EASE } from '../lib/motion'
import { useApi } from '../lib/useApi'
import { StatusBadge } from './ui'

/* Tiny marginal-vs-average sparkline for the hover preview */
export function Spark({ data, w = 260, h = 110 }: { data: MefResponse | null; w?: number; h?: number }) {
  if (!data) return <div style={{ width: w, height: h }} className="flex items-center justify-center"><span className="pulse-dot text-marginal" /></div>
  const rows = [...data.rows].sort((a, b) => a.local_hour - b.local_hour)
  const vals = rows.flatMap((r) => [r.marginal.value, r.average_intensity_kg_per_mwh])
  const lo = Math.min(...vals) * 0.9, hi = Math.max(...vals) * 1.05
  const p = (k: 'm' | 'a') => rows.map((r, i) => `${i ? 'L' : 'M'}${(i / 23) * w},${h - ((k === 'm' ? r.marginal.value : r.average_intensity_kg_per_mwh) - lo) / (hi - lo) * h}`).join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <motion.path d={p('a')} fill="none" stroke="var(--average)" strokeWidth="2" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9, ease: EASE }} />
      <motion.path d={p('m')} fill="none" stroke="var(--marginal)" strokeWidth="2" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9, ease: EASE, delay: 0.1 }} />
    </svg>
  )
}

/* Locomotive-style "work list": big rows, a preview card chases the cursor on hover */
export function RegionList({ bas }: { bas: BAStatus[] }) {
  const [active, setActive] = useState<string | null>(null)
  const x = useMotionValue(0), y = useMotionValue(0)
  const sx = useSpring(x, { stiffness: 250, damping: 28 }), sy = useSpring(y, { stiffness: 250, damping: 28 })
  const miso = useApi(() => api.mef('MISO', 8), [])
  const erco = useApi(() => api.mef('ERCO', 8), [])
  const ciso = useApi(() => api.mef('CISO', 8), [])
  const spark: Record<string, MefResponse | null> = { MISO: miso.data, ERCO: erco.data, CISO: ciso.data }
  const order = ['MISO', 'ERCO', 'CISO']
  const sorted = order.map((c) => bas.find((b) => b.ba_code === c)!).filter(Boolean)

  return (
    <div className="relative" onPointerMove={(e) => { x.set(e.clientX); y.set(e.clientY) }} onPointerLeave={() => setActive(null)}>
      <ul className="border-t border-ink/15">
        {sorted.map((b, i) => {
          const ok = b.scheduling_recommendation_validated
          return (
            <li key={b.ba_code} className="border-b border-ink/15">
              <Link to={`/ba/${b.ba_code}`} onPointerEnter={(e) => {
                  if (!active) { sx.jump(e.clientX); sy.jump(e.clientY) }
                  x.set(e.clientX); y.set(e.clientY); setActive(b.ba_code)
                }}
                className="group relative grid grid-cols-[auto_1fr_auto] items-center gap-4 overflow-hidden py-6 sm:gap-8 sm:py-9">
                <span aria-hidden className="absolute inset-0 origin-bottom scale-y-0 bg-ink transition-transform duration-700 ease-[cubic-bezier(.19,1,.22,1)] group-hover:scale-y-100" />
                <span className="relative font-mono text-xs text-muted transition-colors duration-500 group-hover:text-page/60 sm:pl-4">0{i + 1}</span>
                <span className="relative min-w-0">
                  <span className="display block text-6xl transition-all duration-700 group-hover:translate-x-4 group-hover:text-page sm:text-8xl lg:text-9xl">{BA_LABEL[b.ba_code]}</span>
                  <span className="mt-1 block truncate text-sm text-ink-2 transition-colors duration-500 group-hover:translate-x-4 group-hover:text-page/60">{b.name}</span>
                </span>
                <span className="relative flex flex-col items-end gap-2 pr-1 text-right sm:pr-4">
                  <span className="rounded-full bg-page"><StatusBadge validated={ok} size="sm" /></span>
                  <span className="hidden text-sm text-ink-2 transition-colors duration-500 group-hover:text-page/70 sm:block tabular">
                    2025 gap {fmt(b.realised_gap_2025.value)} <span className="opacity-70">(CI {fmt(b.realised_gap_2025.ci_low_95)}–{fmt(b.realised_gap_2025.ci_high_95)})</span>
                  </span>
                </span>
              </Link>
            </li>
          )
        })}
      </ul>
      {createPortal(<AnimatePresence>
        {active && (
          <motion.div className="pointer-events-none fixed left-0 top-0 z-40 hidden w-[300px] rounded-2xl bg-surface p-4 shadow-2xl ring-1 ring-ring lg:block"
            style={{ x: sx, y: sy, translateX: '24px', translateY: '-50%' }}
            initial={{ opacity: 0, scale: 0.6, rotate: -6 }} animate={{ opacity: 1, scale: 1, rotate: 0 }} exit={{ opacity: 0, scale: 0.6, rotate: 6 }}
            transition={{ duration: 0.45, ease: EASE }}>
            <p className="eyebrow">{BA_LABEL[active]} · typical August day</p>
            <div className="mt-2"><Spark key={active} data={spark[active]} w={268} /></div>
            <div className="mt-2 flex gap-4 text-xs text-ink-2">
              <span className="flex items-center gap-1.5"><i className="h-0.5 w-3 bg-marginal" />Marginal</span>
              <span className="flex items-center gap-1.5"><i className="h-0.5 w-3 bg-average" />Average</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>, document.body)}
    </div>
  )
}
