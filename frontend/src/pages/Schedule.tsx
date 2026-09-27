import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Callout, ErrorBox, Spinner, StatusBadge } from '../components/ui'
import { Counter, EASE, Magnetic, Reveal, SplitLines } from '../lib/motion'
import type { ScheduleResponse, Window } from '../lib/api'
import { api, BA_LABEL, fmt } from '../lib/api'

const hourOf = (iso: string) => Number(iso.slice(11, 13))

function DayStrip({ r }: { r: ScheduleResponse }) {
  const ok = r.recommendation.validated
  const bar = (w: Window, color: string, label: string, row: number) => {
    const s = hourOf(w.start_local)
    const e = hourOf(w.end_local) || 24
    return (
      <div className="relative h-9" key={label}>
        <motion.div className="absolute inset-y-0 flex items-center overflow-hidden whitespace-nowrap rounded-lg px-2.5 text-xs font-semibold"
          style={{ background: ok ? color : `color-mix(in srgb, ${color} 30%, transparent)`, border: `1.5px ${ok ? 'solid' : 'dashed'} ${color}`, color: ok ? '#fff' : 'var(--ink)' }}
          initial={{ left: '0%', width: '0%' }} animate={{ left: `${(s / 24) * 100}%`, width: `${((e - s) / 24) * 100}%` }}
          transition={{ duration: 1.1, ease: EASE, delay: row * 0.15 }}>
          {label} · {String(s).padStart(2, '0')}–{String(e).padStart(2, '0')}
        </motion.div>
      </div>
    )
  }
  return (
    <div role="img" aria-label={`24-hour day. Marginal-optimal window ${r.marginal_optimal_window.start_local.slice(11, 16)}–${r.marginal_optimal_window.end_local.slice(11, 16)}, average-optimal ${r.average_optimal_window.start_local.slice(11, 16)}–${r.average_optimal_window.end_local.slice(11, 16)}`}>
      {!ok && (
        <div className="mb-2 flex justify-end">
          <span className="rounded-full border border-dashed border-neutral/60 bg-neutral-bg px-2 py-0.5 text-xs font-medium text-ink-2">Exploratory windows · not validated</span>
        </div>
      )}
      <div className="relative">
        <div className="relative mb-2 h-4">
          {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((h) => (
            <span key={h} className="absolute font-mono text-[10px] text-muted" style={{ left: `${(h / 24) * 100}%`, transform: h === 24 ? 'translateX(-100%)' : h === 0 ? undefined : 'translateX(-50%)' }}>{String(h).padStart(2, '0')}</span>
          ))}
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 top-6">
          {Array.from({ length: 25 }, (_, h) => <span key={h} className={`absolute inset-y-0 w-px ${h % 3 ? 'bg-grid/60' : 'bg-grid'}`} style={{ left: `${(h / 24) * 100}%` }} />)}
        </div>
        <div className="relative space-y-2 py-1">
          {bar(r.marginal_optimal_window, 'var(--marginal)', 'Marginal-optimal', 0)}
          {bar(r.average_optimal_window, 'var(--average)', 'Average-optimal', 1)}
        </div>
      </div>
    </div>
  )
}

function WindowFacts({ w, kind }: { w: Window; kind: 'marginal' | 'average' }) {
  const [lo, hi] = w.window_marginal_mean.ci_bounds_conservative
  return (
    <div className="rounded-2xl bg-surface-2 p-5 text-sm tabular">
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
  const input = 'field mt-1'
  function preset(p: Partial<typeof form>) {
    const f = { ...form, ...p }
    setForm(f)
    setParams(new URLSearchParams(Object.entries(f).filter(([, v]) => v !== '')), { replace: true })
    load(f)
  }
  const PRESETS = [
    { label: 'EV fleet charging', sub: '6 h · 40 MWh', p: { duration_h: '6', load_mwh: '40', earliest_hour: '', latest_hour: '' } },
    { label: 'Data-centre batch job', sub: '4 h · 100 MWh', p: { duration_h: '4', load_mwh: '100', earliest_hour: '', latest_hour: '' } },
    { label: 'Water pumping', sub: '8 h · 30 MWh', p: { duration_h: '8', load_mwh: '30', earliest_hour: '', latest_hour: '' } },
    { label: 'Office-hours only', sub: '3 h · 20 MWh · 08–18', p: { duration_h: '3', load_mwh: '20', earliest_hour: '8', latest_hour: '18' } },
  ]

  return (
    <div className="px-4 pb-24 pt-28 sm:px-8">
      <header className="grid gap-8 md:grid-cols-[1.5fr_1fr] md:items-end">
        <div>
          <p className="eyebrow mb-6">Tool · Scheduler</p>
          <h1 className="display text-[15vw] sm:text-[10vw] lg:text-[8.5vw]"><SplitLines immediate delay={0.3} lines={['Plan a', <span className="text-marginal">flexible load.</span>]} /></h1>
        </div>
        <Reveal className="text-lg text-ink-2">Windows come from the frozen 2019–2024 profiles. Only MISO's recommendation is validated — the others are shown as exploratory.</Reveal>
      </header>

      <Reveal className="mt-12">
        <p className="eyebrow mb-3">Quick start</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PRESETS.map((pr) => (
            <button key={pr.label} onClick={() => preset(pr.p)} disabled={busy}
              className="group relative overflow-hidden rounded-2xl p-5 text-left ring-1 ring-ring transition-shadow hover:shadow-xl">
              <span aria-hidden className="absolute inset-0 origin-left scale-x-0 bg-ink transition-transform duration-700 ease-[cubic-bezier(.19,1,.22,1)] group-hover:scale-x-100" />
              <span className="relative block text-lg font-semibold transition-colors duration-500 group-hover:text-page">{pr.label}</span>
              <span className="relative block text-sm text-ink-2 transition-colors duration-500 group-hover:text-page/70">{pr.sub}</span>
              <span className="relative mt-6 block text-2xl transition-all duration-500 group-hover:translate-x-2 group-hover:text-page">→</span>
            </button>
          ))}
        </div>
      </Reveal>

      <Reveal className="mt-6 rounded-3xl bg-surface p-6 ring-1 ring-ring sm:p-8">
        <form onSubmit={submit} className="grid gap-x-8 gap-y-6 text-sm sm:grid-cols-3 lg:grid-cols-6">
          <label className="eyebrow">Region<select value={form.ba} onChange={set('ba')} className={input}>
            {Object.entries(BA_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="eyebrow">Date<input type="date" min="2019-07-01" max="2026-08-31" value={form.date} onChange={set('date')} className={input} required /></label>
          <label className="eyebrow">Duration (h)<input type="number" min="1" max="24" value={form.duration_h} onChange={set('duration_h')} className={input} /></label>
          <label className="eyebrow">Load (MWh)<input type="number" min="1" value={form.load_mwh} onChange={set('load_mwh')} className={input} /></label>
          <label className="eyebrow">Earliest hour<input type="number" min="0" max="23" placeholder="any" value={form.earliest_hour} onChange={set('earliest_hour')} className={input} /></label>
          <label className="eyebrow">Latest hour<input type="number" min="1" max="24" placeholder="any" value={form.latest_hour} onChange={set('latest_hour')} className={input} /></label>
          <div className="sm:col-span-3 lg:col-span-6">
            <Magnetic><button disabled={busy} className="btn btn-solid text-base">{busy ? 'Finding windows…' : 'Compare windows →'}</button></Magnetic>
          </div>
        </form>
      </Reveal>

      <div className="mt-6">
        {err != null && <ErrorBox error={err} />}
        {busy && !res && <Spinner label="Finding windows" />}
        <AnimatePresence mode="wait">
          {res && (
            <motion.section key={`${res.ba_code}-${res.date}-${res.duration_h}-${res.load_mwh}`}
              initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} transition={{ duration: 0.8, ease: EASE }}
              className={`rounded-3xl p-6 sm:p-8 ${res.recommendation.validated ? 'bg-surface ring-2 ring-good/50' : 'border border-dashed border-neutral/60 bg-surface'}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-2xl font-semibold tracking-tight">{BA_LABEL[res.ba_code]} · {res.date} · {res.duration_h} h · {fmt(res.load_mwh)} MWh</h2>
                <StatusBadge validated={res.recommendation.validated} size="sm" />
              </div>
              {res.recommendation.validated && (
                <div className="mt-8">
                  <div className="eyebrow">Realised 2025 saving for this load</div>
                  <div className="display mt-2 text-7xl sm:text-9xl"><Counter value={res.recommendation.realised_saving_for_this_load_kg.value} /><span className="ml-3 text-3xl font-medium tracking-tight sm:text-4xl">kg CO₂</span></div>
                  <div className="mt-1 text-sm text-ink-2 tabular">95% CI {fmt(res.recommendation.realised_saving_for_this_load_kg.ci_low_95)} to {fmt(res.recommendation.realised_saving_for_this_load_kg.ci_high_95)}</div>
                </div>
              )}
              <div className="mt-8"><DayStrip r={res} /></div>
              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                <WindowFacts w={res.marginal_optimal_window} kind="marginal" />
                <WindowFacts w={res.average_optimal_window} kind="average" />
              </div>
              <div className="mt-6 space-y-3">
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
            </motion.section>
          )}
        </AnimatePresence>
        {busy && res && <Spinner label="Updating" />}
      </div>
    </div>
  )
}
