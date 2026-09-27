import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Callout, Card, ErrorBox, Spinner, StatusBadge } from '../components/ui'
import type { ScheduleResponse, Window } from '../lib/api'
import { api, BA_LABEL, fmt } from '../lib/api'

const hourOf = (iso: string) => Number(iso.slice(11, 13))

function DayStrip({ r }: { r: ScheduleResponse }) {
  const ok = r.recommendation.validated
  const bar = (w: Window, color: string, label: string, row: number) => {
    const s = hourOf(w.start_local)
    const e = hourOf(w.end_local) || 24
    return (
      <g>
        <rect x={`${(s / 24) * 100}%`} y={22 + row * 30} width={`${((e - s) / 24) * 100}%`} height="20" rx="4"
          fill={color} fillOpacity={ok ? 0.9 : 0.35} stroke={color} strokeDasharray={ok ? undefined : '4 3'} strokeWidth="1.5" />
        <text x={`${(s / 24) * 100}%`} dx="6" y={36 + row * 30} fontSize="11" fontWeight="600" fill={ok ? '#fff' : 'var(--ink)'}>{label}</text>
      </g>
    )
  }
  return (
    <div>
      {!ok && (
        <div className="mb-1 flex justify-end">
          <span className="rounded-full border border-dashed border-neutral/60 bg-neutral-bg px-2 py-0.5 text-xs font-medium text-ink-2">
            Exploratory windows · not validated
          </span>
        </div>
      )}
      <svg width="100%" height="92" role="img" aria-label="24-hour day with the marginal-optimal and average-optimal windows">
        {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((h) => (
          <g key={h}>
            <line x1={`${(h / 24) * 100}%`} x2={`${(h / 24) * 100}%`} y1="16" y2="84" stroke="var(--grid)" />
            <text x={`${(h / 24) * 100}%`} y="11" fontSize="10" fill="var(--muted)" textAnchor={h === 24 ? 'end' : h === 0 ? 'start' : 'middle'}>
              {String(h).padStart(2, '0')}
            </text>
          </g>
        ))}
        {bar(r.marginal_optimal_window, 'var(--marginal)', 'Marginal-optimal', 0)}
        {bar(r.average_optimal_window, 'var(--average)', 'Average-optimal', 1)}
      </svg>
    </div>
  )
}

function WindowFacts({ w, kind }: { w: Window; kind: 'marginal' | 'average' }) {
  const [lo, hi] = w.window_marginal_mean.ci_bounds_conservative
  return (
    <div className="rounded-lg bg-surface-2 p-3 text-sm tabular">
      <div className={`font-semibold ${kind === 'marginal' ? 'text-marginal' : 'text-average'}`}>
        {kind === 'marginal' ? 'Marginal-optimal' : 'Average-optimal'} · {w.start_local.slice(11, 16)}–{w.end_local.slice(11, 16)}
      </div>
      <div className="mt-1 text-ink-2">Marginal {fmt(w.window_marginal_mean.value)} kg/MWh
        <span className="block text-xs">conservative CI bounds {fmt(lo)} to {fmt(hi)}</span></div>
      <div className="text-ink-2">Average {fmt(w.window_average_intensity_kg_per_mwh)} kg/MWh</div>
    </div>
  )
}

export default function Schedule() {
  const [params, setParams] = useSearchParams()
  const [form, setForm] = useState({
    ba: params.get('ba')?.toUpperCase() ?? 'MISO', date: params.get('date') ?? '2025-08-12',
    duration_h: params.get('duration_h') ?? '4', load_mwh: params.get('load_mwh') ?? '100',
    earliest_hour: params.get('earliest_hour') ?? '', latest_hour: params.get('latest_hour') ?? '',
  })
  const [res, setRes] = useState<ScheduleResponse | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })

  async function load(f: typeof form) {
    setBusy(true); setErr(null)
    const q = new URLSearchParams(Object.entries(f).filter(([, v]) => v !== ''))
    try { setRes(await api.schedule(q)) } catch (x) { setErr(x); setRes(null) } finally { setBusy(false) }
  }
  function submit(e: React.FormEvent) {
    e.preventDefault()
    setParams(new URLSearchParams(Object.entries(form).filter(([, v]) => v !== '')), { replace: true })
    load(form)
  }
  // A link with a date in it (shared result) runs immediately.
  useEffect(() => { if (params.get('date')) load(form) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const input = 'mt-1 w-full rounded-md bg-surface-2 px-2 py-1.5 ring-1 ring-ring'

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Plan a flexible load</h1>
        <p className="mt-1 text-ink-2">Windows come from the frozen 2019–2024 profiles. Only MISO’s recommendation is validated.</p>
      </header>
      <Card>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6 text-sm">
          <label>Region<select value={form.ba} onChange={set('ba')} className={input}>
            {Object.entries(BA_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label>Date<input type="date" min="2019-07-01" max="2026-08-31" value={form.date} onChange={set('date')} className={input} required /></label>
          <label>Duration (h)<input type="number" min="1" max="24" value={form.duration_h} onChange={set('duration_h')} className={input} /></label>
          <label>Load (MWh)<input type="number" min="1" value={form.load_mwh} onChange={set('load_mwh')} className={input} /></label>
          <label>Earliest hour<input type="number" min="0" max="23" placeholder="any" value={form.earliest_hour} onChange={set('earliest_hour')} className={input} /></label>
          <label>Latest hour<input type="number" min="1" max="24" placeholder="any" value={form.latest_hour} onChange={set('latest_hour')} className={input} /></label>
          <button disabled={busy} className="rounded-md bg-marginal px-3 py-2 font-medium text-white sm:col-span-3 lg:col-span-6 disabled:opacity-60">
            {busy ? 'Finding windows…' : 'Compare windows'}</button>
        </form>
      </Card>

      {err != null && <ErrorBox error={err} />}
      {busy && !res && <Spinner />}
      {res && (
        <Card className={res.recommendation.validated ? 'ring-good/50' : 'border border-dashed border-neutral/60'}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">{BA_LABEL[res.ba_code]} · {res.date} · {res.duration_h} h · {fmt(res.load_mwh)} MWh</h2>
            <StatusBadge validated={res.recommendation.validated} size="sm" />
          </div>
          <div className="mt-4"><DayStrip r={res} /></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <WindowFacts w={res.marginal_optimal_window} kind="marginal" />
            <WindowFacts w={res.average_optimal_window} kind="average" />
          </div>
          <div className="mt-4 space-y-3">
            {res.recommendation.validated ? (
              <Callout kind="good" title={`Hold-out-confirmed · ${res.recommendation.advice}`}>
                Realised saving in 2025 for this load:{' '}
                <strong className="tabular">{fmt(res.recommendation.realised_saving_for_this_load_kg.value)} kg CO₂</strong>{' '}
                (95% CI {fmt(res.recommendation.realised_saving_for_this_load_kg.ci_low_95)} to{' '}
                {fmt(res.recommendation.realised_saving_for_this_load_kg.ci_high_95)}).{' '}
                {res.recommendation.realised_saving_for_this_load_kg.basis}
              </Callout>
            ) : (
              <Callout kind="neutral" title="No validated recommendation">{res.recommendation.advice}</Callout>
            )}
            {res.caveats.map((c) => <Callout key={c} kind="warning">{c}</Callout>)}
            <Callout kind="info" title="Reading marginal factors">{res.usage.text}</Callout>
          </div>
        </Card>
      )}
      {busy && res && <Spinner label="Updating" />}
    </div>
  )
}
