import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { MefRow } from '../lib/api'
import { fmt } from '../lib/api'

type Point = { hour: number; mef: number; ci: [number, number]; avg: number }

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="rounded-md bg-surface px-3 py-2 text-xs shadow-lg ring-1 ring-ring tabular">
      <div className="font-semibold text-ink">{String(p.hour).padStart(2, '0')}:00 local (typical, 2019–2024)</div>
      <div className="mt-1 flex items-center gap-2"><span className="h-0.5 w-3 bg-marginal" />
        Marginal {fmt(p.mef)} kg/MWh <span className="text-ink-2">(95% CI {fmt(p.ci[0])} to {fmt(p.ci[1])})</span></div>
      <div className="flex items-center gap-2"><span className="h-0.5 w-3 bg-average" />Average {fmt(p.avg)} kg/MWh</div>
    </div>
  )
}

/** Marginal factor (line + 95% CI band) vs average intensity, by local hour, one month. */
export function MefChart({ rows }: { rows: MefRow[] }) {
  const data: Point[] = rows.map((r) => ({
    hour: r.local_hour, mef: r.marginal.value, ci: [r.marginal.ci_low_95, r.marginal.ci_high_95],
    avg: r.average_intensity_kg_per_mwh,
  }))
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="hour" tickFormatter={(h) => `${String(h).padStart(2, '0')}`} ticks={[0, 3, 6, 9, 12, 15, 18, 21]}
          stroke="var(--axis)" tick={{ fill: 'var(--muted)', fontSize: 11 }} />
        <YAxis stroke="var(--axis)" tick={{ fill: 'var(--muted)', fontSize: 11 }} width={48}
          label={{ value: 'kg CO₂/MWh', angle: -90, position: 'insideLeft', fill: 'var(--muted)', fontSize: 11 }} />
        <ReferenceLine y={0} stroke="var(--axis)" />
        <Tooltip content={<Tip />} />
        <Legend wrapperStyle={{ fontSize: 12, color: 'var(--ink-2)' }} />
        <Area dataKey="ci" name="Marginal 95% CI" fill="var(--marginal-soft)" stroke="none" isAnimationActive={false} />
        <Line dataKey="mef" name="Marginal" stroke="var(--marginal)" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line dataKey="avg" name="Average" stroke="var(--average)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
