import { motion } from 'motion/react'
import type { BAStatus, Estimate } from '../lib/api'
import { BA_LABEL, fmt } from '../lib/api'

/** Realised hold-out gap per BA with 95% CI error bars. Validation state is drawn on the
 *  chart itself: confirmed = solid green interval + check; unconfirmed = dashed neutral
 *  interval, hollow point and an inline "Not validated" label. */
export function GapChart({ bas, period }: { bas: BAStatus[]; period: '2025' | '2026' }) {
  const pick = (b: BAStatus): Estimate => (period === '2025' ? b.realised_gap_2025 : b.realised_gap_2026_ytd)
  const threshold = 50
  const lo = Math.min(-150, ...bas.map((b) => pick(b).ci_low_95))
  const hi = Math.max(500, ...bas.map((b) => pick(b).ci_high_95))
  const W = 720, rowH = 64, top = 34, left = 76, right = 230
  const H = top + rowH * bas.length + 26
  const x = (v: number) => left + ((v - lo) / (hi - lo)) * (W - left - right)
  const ticks: number[] = []
  for (let t = Math.ceil(lo / 100) * 100; t <= hi; t += 100) ticks.push(t)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img"
      aria-label={`Realised hold-out gap by BA, ${period}, kg CO2 per MWh shifted, with 95% confidence intervals`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={top - 8} y2={H - 26} stroke="var(--grid)" />
          <text x={x(t)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--muted)" className="tabular">{fmt(t)}</text>
        </g>
      ))}
      <line x1={x(0)} x2={x(0)} y1={top - 12} y2={H - 26} stroke="var(--axis)" strokeWidth="1.5" />
      <text x={x(0)} y={top - 16} textAnchor="middle" fontSize="11" fill="var(--ink-2)">0 = no difference</text>
      <line x1={x(threshold)} x2={x(threshold)} y1={top - 4} y2={H - 26} stroke="var(--ink-2)" strokeDasharray="4 3" />
      <text x={x(threshold) + 4} y={top + 2} fontSize="10" fill="var(--ink-2)">threshold 50</text>
      {bas.map((b, i) => {
        const e = pick(b)
        const y = top + rowH * i + rowH / 2
        const ok = b.scheduling_recommendation_validated
        const color = ok ? 'var(--good)' : 'var(--muted)'
        const crossesZero = e.ci_low_95 <= 0
        return (
          <g key={b.ba_code}>
            <title>{`${BA_LABEL[b.ba_code]} ${period}: ${fmt(e.value)} kg CO2/MWh shifted (95% CI ${fmt(e.ci_low_95)} to ${fmt(e.ci_high_95)}) — ${ok ? 'validated' : 'not validated'}`}</title>
            <text x={left - 12} y={y + 4} textAnchor="end" fontSize="13" fontWeight="600" fill="var(--ink)">{BA_LABEL[b.ba_code]}</text>
            <rect x={left - 70} y={y - rowH / 2 + 4} width={W - left - right + 80} height={rowH - 8} rx="10" className="fill-transparent transition-colors hover:fill-[var(--surface-2)]" />
            <motion.line y1={y} y2={y} stroke={color} strokeWidth="2.5" strokeDasharray={ok ? undefined : '5 4'}
              initial={{ x1: x(e.value), x2: x(e.value) }} animate={{ x1: x(e.ci_low_95), x2: x(e.ci_high_95) }}
              transition={{ duration: 1.2, ease: [0.19, 1, 0.22, 1], delay: 0.2 + i * 0.12 }} />
            {[e.ci_low_95, e.ci_high_95].map((v, j) => (
              <motion.line key={j} y1={y - 7} y2={y + 7} stroke={color} strokeWidth="2"
                initial={{ x1: x(e.value), x2: x(e.value), opacity: 0 }} animate={{ x1: x(v), x2: x(v), opacity: 1 }}
                transition={{ duration: 1.2, ease: [0.19, 1, 0.22, 1], delay: 0.2 + i * 0.12 }} />
            ))}
            <motion.circle cy={y} r="6.5" fill={ok ? color : 'var(--surface)'} stroke={color} strokeWidth="2.5"
              initial={{ cx: x(0), scale: 0 }} animate={{ cx: x(e.value), scale: 1 }} transition={{ type: 'spring', stiffness: 120, damping: 16, delay: i * 0.12 }} />
            <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6, delay: 0.6 + i * 0.12 }}>
              <text x={x(e.value)} y={y - 12} textAnchor="middle" fontSize="11" fill="var(--ink)" className="tabular">{fmt(e.value)}</text>
            </motion.g>
            <g transform={`translate(${W - right + 16}, ${y - 11})`}>
              {ok ? (
                <>
                  <path d="M2 11l4 4 8-9" fill="none" stroke="var(--good-text)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                  <text x="20" y="14" fontSize="12.5" fontWeight="600" fill="var(--good-text)">Validated</text>
                  <text x="20" y="29" fontSize="11" fill="var(--ink-2)">CI above 0, gap ≥ 50</text>
                </>
              ) : (
                <>
                  <circle cx="8" cy="10" r="6" fill="none" stroke="var(--muted)" strokeWidth="1.6" strokeDasharray="2.5 2" />
                  <text x="20" y="14" fontSize="12.5" fontWeight="600" fill="var(--ink-2)">Not validated</text>
                  <text x="20" y="29" fontSize="11" fill="var(--ink-2)">{crossesZero ? 'CI includes 0' : 'below threshold'}</text>
                </>
              )}
            </g>
          </g>
        )
      })}
    </svg>
  )
}
