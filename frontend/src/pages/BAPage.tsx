import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { MefChart } from '../components/MefChart'
import { Callout, Card, ErrorBox, EstimateLine, Spinner, StatusBadge } from '../components/ui'
import type { OvernightCheck } from '../lib/api'
import { api, BA_LABEL, fmt } from '../lib/api'
import { useApi } from '../lib/useApi'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function OvernightPanel({ o }: { o: OvernightCheck }) {
  // Deliberately styled unlike the saving: dashed marginal-coloured frame, its own label.
  return (
    <section className="rounded-xl border-2 border-dashed border-marginal/50 bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">Overnight factor check ({o.local_hours})</h2>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-ink-2 ring-1 ring-ring">
          Factor comparison · not a scheduling saving
        </span>
      </div>
      <p className="mt-1 text-sm text-ink-2">{o.what_this_is}</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 tabular">
        {([['2025 hold-out', o.holdout_2025], ['Train 2019–2024', o.train]] as const).map(([label, v]) => (
          <div key={label} className="rounded-lg bg-surface-2 p-3">
            <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
            <div className="mt-1"><span className="font-semibold text-marginal">Marginal {fmt(v.marginal.value)}</span>{' '}
              <span className="text-sm text-ink-2">kg/MWh (95% CI {fmt(v.marginal.ci_low_95)} to {fmt(v.marginal.ci_high_95)})</span></div>
            <div><span className="font-semibold text-average">Average {fmt(v.average)}</span> <span className="text-sm text-ink-2">kg/MWh</span></div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-sm text-ink-2">
        Overnight hours look cleanest on average, but extra load then is met by higher-emitting generation. The gap
        held in 2025 but was smaller than in training.
      </p>
    </section>
  )
}

export default function BAPage() {
  const { code = 'MISO' } = useParams()
  const ba = code.toUpperCase()
  const [month, setMonth] = useState(7)
  const { data: f, error } = useApi(() => api.findings(ba), [ba])
  const { data: mef, error: mefErr } = useApi(() => api.mef(ba, month), [ba, month])
  if (error) return <ErrorBox error={error} />
  if (!f) return <Spinner />
  const v = f.validation
  const ok = v.scheduling_recommendation_validated

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">{BA_LABEL[ba]}</h1>
        <StatusBadge validated={ok} />
      </header>

      <Callout kind={ok ? 'good' : 'neutral'} title={ok ? 'Scheduling recommendation validated' : 'No validated scheduling recommendation'}>
        {v.summary}
      </Callout>

      <Card className={ok ? '' : 'border border-dashed border-neutral/60'}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Realised saving from marginal scheduling</h2>
          <StatusBadge validated={ok} size="sm" />
        </div>
        <p className="text-sm text-ink-2">kg CO₂ avoided per MWh shifted, measured on held-out data the method never saw</p>
        <div className={`mt-4 grid gap-4 sm:grid-cols-3 ${ok ? '' : 'opacity-85'}`}>
          <div><div className="text-xs uppercase tracking-wide text-muted">2025 (decision)</div><EstimateLine e={v.realised_gap_2025} /></div>
          <div>
            <div className="text-xs uppercase tracking-wide text-muted">2026 YTD (second check)</div>
            <EstimateLine e={v.realised_gap_2026_ytd} />
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-muted">EDA prediction (in-sample)</div>
            <span className="text-2xl font-semibold tabular">{fmt(v.eda_predicted_gap)}</span>
            <span className="block text-sm text-ink-2">predicted before the hold-out test</span>
          </div>
        </div>
        {!ok && <p className="mt-3 text-sm font-medium text-ink-2">The CI includes zero: these numbers are not a saving you can plan on.</p>}
        <div className="mt-4 space-y-3">
          {v.eda_estimate_not_confirmed && <Callout kind="neutral" title="EDA estimate not confirmed">{v.eda_estimate_not_confirmed}</Callout>}
          {v.data_caveats?.map((c) => <Callout key={c} kind="warning" title="2026 data caveat (applies to the 2026 YTD figure)">{c}</Callout>)}
        </div>
      </Card>

      {f.overnight_check && <OvernightPanel o={f.overnight_check} />}

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Marginal vs average intensity by hour</h2>
            <p className="text-sm text-ink-2">Typical {MONTHS[month - 1]} pattern, estimated on 2019–2024 (frozen). Band = 95% CI.</p>
          </div>
          <div className="flex items-center gap-2">
            {!ok && <span className="rounded-full border border-dashed border-neutral/60 bg-neutral-bg px-2 py-0.5 text-xs font-medium text-ink-2">
              Descriptive only · not a validated scheduling signal</span>}
            <label className="text-sm text-ink-2">Month{' '}
              <select value={month} onChange={(e) => setMonth(Number(e.target.value))}
                className="ml-1 rounded-md bg-surface-2 px-2 py-1 ring-1 ring-ring">
                {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </select>
            </label>
          </div>
        </div>
        <div className="mt-4">{mefErr ? <ErrorBox error={mefErr} /> : mef ? <MefChart rows={mef.rows} /> : <Spinner />}</div>
        <div className="mt-3"><Callout kind="info" title="Reading marginal factors">{f.usage.text}</Callout></div>
      </Card>

      <Link to={`/schedule?ba=${ba}`} className="inline-block text-sm text-marginal hover:underline">Plan a load in {BA_LABEL[ba]} →</Link>
    </div>
  )
}
