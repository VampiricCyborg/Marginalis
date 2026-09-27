import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { BAStatus, MefRow } from '../lib/api'
import { api, BA_LABEL, fmt } from '../lib/api'
import { EASE } from '../lib/motion'
import { useApi } from '../lib/useApi'
import { StatusBadge } from './ui'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const BAS = ['MISO', 'ERCO', 'CISO']

function windowMean(rows: MefRow[], start: number, dur: number) {
  const hrs = Array.from({ length: dur }, (_, i) => rows[(start + i) % 24])
  return {
    m: hrs.reduce((s, r) => s + r.marginal.value, 0) / dur,
    // Same method as the API's ci_bounds_conservative: mean of the hours' 95% CI bounds.
    mLo: hrs.reduce((s, r) => s + r.marginal.ci_low_95, 0) / dur,
    mHi: hrs.reduce((s, r) => s + r.marginal.ci_high_95, 0) / dur,
    a: hrs.reduce((s, r) => s + r.average_intensity_kg_per_mwh, 0) / dur,
  }
}
function best(rows: MefRow[], dur: number, key: 'm' | 'a') {
  let bi = 0, bv = Infinity
  for (let s = 0; s + dur <= 24; s++) { const v = windowMean(rows, s, dur)[key]; if (v < bv) { bv = v; bi = s } }
  return bi
}

/* Drag a flexible-load window across a typical day and watch both intensities respond.
   Descriptive only: the frozen 2019–2024 profile, not a hold-out result. */
export function LoadWindow({ bas }: { bas: BAStatus[] }) {
  const [ba, setBa] = useState('MISO')
  const [month, setMonth] = useState(8)
  const [dur, setDur] = useState(4)
  const [start, setStart] = useState(18)
  const [hover, setHover] = useState<number | null>(null)
  const { data, error } = useApi(() => api.mef(ba, month), [ba, month])
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<{ dx: number } | null>(null)
  const status = bas.find((b) => b.ba_code === ba)
  const rows = useMemo(() => (data ? [...data.rows].sort((a, b) => a.local_hour - b.local_hour) : null), [data])

  const boxRef = useRef<HTMLDivElement>(null)
  const [W, setW] = useState(960)
  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))))
    ro.observe(el); return () => ro.disconnect()
  }, [])
  const H = W < 600 ? 300 : 340, L = 40, R = 8, T = 20, B = 30
  const hourTicks = W < 600 ? [0, 6, 12, 18] : [0, 3, 6, 9, 12, 15, 18, 21]
  const cw = (W - L - R) / 24
  const s = Math.min(start, 24 - dur)
  const [lo, hi] = useMemo(() => {
    if (!rows) return [0, 1000]
    const vals = rows.flatMap((r) => [r.marginal.ci_low_95, r.marginal.ci_high_95, r.average_intensity_kg_per_mwh])
    const mn = Math.min(0, ...vals), mx = Math.max(...vals)
    return [Math.floor(mn / 100) * 100, Math.ceil(mx / 100) * 100]
  }, [rows])
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B)
  const xc = (h: number) => L + cw * (h + 0.5)

  const hourFromEvent = (clientX: number) => {
    const r = svgRef.current!.getBoundingClientRect()
    return ((clientX - r.left) / r.width * W - L) / cw
  }

  const cur = rows ? windowMean(rows, s, dur) : null
  const validated = !!status?.scheduling_recommendation_validated
  const mBest = rows ? best(rows, dur, 'm') : 0
  const aBest = rows ? best(rows, dur, 'a') : 0
  const hv = hover != null && rows ? rows[hover] : null

  const line = (key: 'm' | 'a') => rows!.map((r, i) => `${i ? 'L' : 'M'}${xc(r.local_hour)},${y(key === 'm' ? r.marginal.value : r.average_intensity_kg_per_mwh)}`).join(' ')
  const band = rows ? rows.map((r, i) => `${i ? 'L' : 'M'}${xc(r.local_hour)},${y(r.marginal.ci_high_95)}`).join(' ') + ' ' +
    [...rows].reverse().map((r) => `L${xc(r.local_hour)},${y(r.marginal.ci_low_95)}`).join(' ') + ' Z' : ''

  return (
    <div>
      {/* Controls in one row above the chart */}
      <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
        <div className="flex gap-1 rounded-full bg-surface-2 p-1" role="tablist" aria-label="Region">
          {BAS.map((b) => (
            <button key={b} role="tab" aria-selected={ba === b} onClick={() => setBa(b)}
              className={`relative rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${ba === b ? 'text-page' : 'text-ink-2 hover:text-ink'}`}>
              {ba === b && <motion.span layoutId="ba-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ type: 'spring', stiffness: 400, damping: 35 }} />}
              <span className="relative">{BA_LABEL[b]}</span>
            </button>
          ))}
        </div>
        <label className="flex items-center gap-3 text-sm text-ink-2">
          <span className="eyebrow">Month</span>
          <input type="range" min={1} max={12} value={month} onChange={(e) => setMonth(+e.target.value)} className="w-32 accent-[var(--ink)]" aria-valuetext={MONTHS[month - 1]} />
          <span className="w-8 font-medium text-ink">{MONTHS[month - 1]}</span>
        </label>
        <div className="flex items-center gap-2 text-sm">
          <span className="eyebrow">Duration</span>
          {[2, 4, 6, 8].map((d) => (
            <button key={d} onClick={() => setDur(d)} aria-pressed={dur === d}
              className={`h-8 w-10 rounded-full text-sm ring-1 transition ${dur === d ? 'bg-ink text-page ring-ink' : 'ring-ring hover:ring-ink'}`}>{d}h</button>
          ))}
        </div>
        {status && <div className="ml-auto"><StatusBadge validated={status.scheduling_recommendation_validated} size="sm" /></div>}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="relative rounded-2xl bg-surface p-3 ring-1 ring-ring sm:p-5">
          <div ref={boxRef} className="w-full" />
          {error ? <p className="p-8 text-sm text-ink-2">Could not load the profile: {String((error as Error).message)}</p> : !rows ? (
            <div className="flex h-[260px] items-center justify-center"><span className="pulse-dot text-marginal" /></div>
          ) : (
            <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full touch-none select-none" role="img"
              aria-label={`${BA_LABEL[ba]} typical ${MONTHS[month - 1]} day: marginal and average CO2 intensity by hour. Selected window ${s}:00 to ${s + dur}:00.`}
              onPointerMove={(e) => {
                const h = hourFromEvent(e.clientX)
                setHover(h >= 0 && h < 24 ? Math.floor(h) : null)
                if (drag.current) setStart(Math.max(0, Math.min(24 - dur, Math.round(h - drag.current.dx))))
              }}
              onPointerLeave={() => setHover(null)}
              onPointerUp={() => { drag.current = null }}
              onPointerDown={(e) => {
                const h = hourFromEvent(e.clientX)
                if (h < s || h > s + dur) setStart(Math.max(0, Math.min(24 - dur, Math.round(h - dur / 2))))
                drag.current = { dx: dur / 2 }
                ;(e.target as Element).setPointerCapture?.(e.pointerId)
              }}>
              {/* grid */}
              {Array.from({ length: Math.round((hi - lo) / 100) + 1 }, (_, i) => lo + i * 100).map((v) => (
                <g key={v}>
                  <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
                  <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--muted)" className="tabular">{v}</text>
                </g>
              ))}
              {hourTicks.map((hh) => (
                <text key={hh} x={L + cw * hh} y={H - 8} fontSize="11" fill="var(--muted)" className="tabular">{String(hh).padStart(2, '0')}:00</text>
              ))}
              {/* optimal markers */}
              {([['m', mBest], ['a', aBest]] as const).map(([k, b], i) => (
                <g key={k}>
                  <rect x={L + cw * b} y={T - 14 + i * 7} width={cw * dur} height="4" rx="2" fill={k === 'm' ? 'var(--marginal)' : 'var(--average)'} opacity="0.85" />
                </g>
              ))}
              {/* selected window */}
              <motion.g animate={{ x: cw * s }} transition={{ type: 'spring', stiffness: 380, damping: 36 }} data-cursor="Drag"
                role="slider" tabIndex={0} aria-label="Load window start hour" aria-valuemin={0} aria-valuemax={24 - dur} aria-valuenow={s}
                aria-valuetext={`${s}:00 to ${s + dur}:00`} className="cursor-grab outline-none focus-visible:[&>rect]:stroke-[3]"
                onKeyDown={(e) => {
                  if (e.key === 'ArrowLeft') { e.preventDefault(); setStart(Math.max(0, s - 1)) }
                  if (e.key === 'ArrowRight') { e.preventDefault(); setStart(Math.min(24 - dur, s + 1)) }
                }}>
                <rect x={L} y={T} width={cw * dur} height={H - T - B} rx="10" fill="var(--ink)" fillOpacity="0.06" stroke="var(--ink)" strokeWidth="1.5" strokeDasharray="6 4" />
                <rect x={L + cw * dur / 2 - 14} y={T + (H - T - B) / 2 - 5} width="28" height="10" rx="5" fill="var(--ink)" />
              </motion.g>
              {/* data */}
              <path d={band} fill="var(--marginal-soft)" />
              <path d={line('a')} fill="none" stroke="var(--average)" strokeWidth="2" strokeLinejoin="round" />
              <path d={line('m')} fill="none" stroke="var(--marginal)" strokeWidth="2" strokeLinejoin="round" />
              {/* direct labels at the right end */}
              <text x={xc(23) - 4} y={y(rows[23].marginal.value) - 10} textAnchor="end" fontSize="12" fontWeight="600" fill="var(--ink)">Marginal</text>
              <text x={xc(23) - 4} y={y(rows[23].average_intensity_kg_per_mwh) + 18} textAnchor="end" fontSize="12" fontWeight="600" fill="var(--ink)">Average</text>
              {/* hover crosshair */}
              {hv && (
                <g pointerEvents="none">
                  <line x1={xc(hv.local_hour)} x2={xc(hv.local_hour)} y1={T} y2={H - B} stroke="var(--ink-2)" strokeWidth="1" />
                  <circle cx={xc(hv.local_hour)} cy={y(hv.marginal.value)} r="5" fill="var(--marginal)" stroke="var(--surface)" strokeWidth="2" />
                  <circle cx={xc(hv.local_hour)} cy={y(hv.average_intensity_kg_per_mwh)} r="5" fill="var(--average)" stroke="var(--surface)" strokeWidth="2" />
                </g>
              )}
            </svg>
          )}
          <AnimatePresence>
            {hv && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="pointer-events-none absolute inset-x-3 top-3 mx-auto w-fit max-w-[calc(100%-1.5rem)] rounded-lg bg-ink px-3 py-2 text-xs text-page shadow-xl tabular">
                <b>{String(hv.local_hour).padStart(2, '0')}:00</b> · marginal {fmt(hv.marginal.value)} ({fmt(hv.marginal.ci_low_95)}–{fmt(hv.marginal.ci_high_95)}) · average {fmt(hv.average_intensity_kg_per_mwh)} kg/MWh
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Readout */}
        <div className="flex flex-col gap-4">
          <div className={`rounded-2xl p-5 ${validated ? 'bg-ink text-page' : 'border-2 border-dashed border-neutral/70 bg-surface text-ink'}`}>
            <div className="flex items-center justify-between gap-2">
              <p className="font-mono text-[11px] uppercase tracking-wider opacity-60">Your window</p>
              {!validated && <span className="rounded-full bg-neutral-bg px-2 py-0.5 text-[10px] font-medium text-ink-2">Descriptive · not validated</span>}
            </div>
            <p className="display mt-1 text-5xl tabular">{String(s).padStart(2, '0')}–{String(s + dur).padStart(2, '0')}<span className="text-2xl">h</span></p>
            {cur && (
              <dl className="mt-4 space-y-2 text-sm tabular">
                <div className="flex items-start justify-between gap-3">
                  <dt className="flex items-center gap-2 pt-1"><i className={`h-0.5 w-4 ${validated ? 'bg-[#4a90e8]' : 'bg-marginal'}`} />Marginal</dt>
                  <dd className="text-right"><span className="text-lg font-semibold">{fmt(cur.m)}</span>
                    <span className="block text-xs opacity-70">CI bounds {fmt(cur.mLo)} to {fmt(cur.mHi)}</span></dd>
                </div>
                <div className="flex items-center justify-between"><dt className="flex items-center gap-2"><i className={`h-0.5 w-4 ${validated ? 'bg-[#e0622d]' : 'bg-average'}`} />Average</dt><dd className="text-lg font-semibold">{fmt(cur.a)}</dd></div>
                <p className="text-xs opacity-60">kg CO₂/MWh, mean over window. Marginal CI bounds are the mean of the hours' 95% CI bounds (wider than the true window CI).</p>
              </dl>
            )}
          </div>
          <button onClick={() => setStart(mBest)} className="group flex items-center justify-between rounded-2xl p-4 text-left ring-1 ring-ring transition hover:ring-marginal">
            <span><span className="block text-xs text-muted">Snap to lowest marginal</span><span className="font-semibold">{String(mBest).padStart(2, '0')}:00–{String(mBest + dur).padStart(2, '0')}:00</span></span>
            <span className="h-2 w-8 rounded-full bg-marginal transition-all group-hover:w-12" />
          </button>
          <button onClick={() => setStart(aBest)} className="group flex items-center justify-between rounded-2xl p-4 text-left ring-1 ring-ring transition hover:ring-average">
            <span><span className="block text-xs text-muted">Snap to lowest average</span><span className="font-semibold">{String(aBest).padStart(2, '0')}:00–{String(aBest + dur).padStart(2, '0')}:00</span></span>
            <span className="h-2 w-8 rounded-full bg-average transition-all group-hover:w-12" />
          </button>
          <AnimatePresence mode="wait">
            <motion.p key={`${mBest}-${aBest}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ ease: EASE, duration: 0.6 }}
              className="text-sm leading-relaxed text-ink-2">
              {mBest === aBest ? 'In this month both measures pick the same window.' :
                <>The two measures pick different windows: average says <b className="text-ink">{String(aBest).padStart(2, '0')}:00</b>, marginal says <b className="text-ink">{String(mBest).padStart(2, '0')}:00</b>.
                  {validated ? <> In {BA_LABEL[ba]}, scheduling by marginal instead of average was confirmed on held-out 2025 data.</>
                    : <> In {BA_LABEL[ba]}, the saving from following marginal was <b className="text-ink">not distinguishable from zero</b> on held-out data — don't plan on it.</>}</>}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>
      <p className="mt-4 text-xs text-ink-2">
        Typical-day profile estimated on 2019–2024 (frozen); band = marginal 95% CI. Descriptive — only use it to rank windows.
        {status && !status.scheduling_recommendation_validated && <> {BA_LABEL[ba]}'s scheduling recommendation did <b>not</b> validate on held-out data.</>}
      </p>
    </div>
  )
}
