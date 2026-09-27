import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { MefChart } from '../components/MefChart'
import { Callout, ErrorBox, Spinner, StatusBadge } from '../components/ui'
import type { Estimate, OvernightCheck } from '../lib/api'
import { api, BA_LABEL, fmt } from '../lib/api'
import { Counter, EASE, Magnetic, Reveal, SplitLines } from '../lib/motion'
import { useApi } from '../lib/useApi'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const ORDER = ['MISO', 'ERCO', 'CISO']

function OvernightPanel({ o }: { o: OvernightCheck }) {
  // Deliberately styled unlike the saving: dashed marginal-coloured frame, its own label.
  return (
    <Reveal as="section" className="rounded-3xl border-2 border-dashed border-marginal/50 p-6 sm:p-8">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-semibold tracking-tight">Overnight factor check ({o.local_hours})</h2>
        <span className="rounded-full bg-surface-2 px-2.5 py-1 text-xs font-medium text-ink-2 ring-1 ring-ring">Factor comparison · not a scheduling saving</span>
      </div>
      <p className="mt-2 max-w-3xl text-sm text-ink-2">{o.what_this_is}</p>
      <div className="mt-6 grid gap-4 sm:grid-cols-2 tabular">
        {([['2025 hold-out', o.holdout_2025], ['Train 2019–2024', o.train]] as const).map(([label, v]) => {
          const max = Math.max(v.marginal.ci_high_95, v.average) * 1.1
          return (
            <div key={label} className="rounded-2xl bg-surface p-5 ring-1 ring-ring">
              <div className="eyebrow">{label}</div>
              {[['Marginal', v.marginal.value, 'bg-marginal', v.marginal], ['Average', v.average, 'bg-average', null]].map(([n, val, c, ci]) => (
                <div key={n as string} className="mt-4">
                  <div className="flex justify-between text-sm"><span className="font-medium">{n as string}</span><span className="font-semibold">{fmt(val as number)} <span className="font-normal text-ink-2">kg/MWh</span></span></div>
                  <div className="relative mt-1.5 h-2.5 rounded-full bg-surface-2">
                    <motion.div className={`h-full rounded-full ${c}`} initial={{ width: 0 }} whileInView={{ width: `${((val as number) / max) * 100}%` }} viewport={{ once: true }} transition={{ duration: 1.2, ease: EASE }} />
                    {ci && <div className="absolute top-[-3px] h-4 border-x-2 border-ink/60" style={{ left: `${((ci as Estimate).ci_low_95 / max) * 100}%`, width: `${(((ci as Estimate).ci_high_95 - (ci as Estimate).ci_low_95) / max) * 100}%` }} />}
                  </div>
                  {ci && <div className="mt-1 text-xs text-ink-2">95% CI {fmt((ci as Estimate).ci_low_95)} to {fmt((ci as Estimate).ci_high_95)}</div>}
                </div>
              ))}
            </div>
          )
        })}
      </div>
      <p className="mt-4 text-sm text-ink-2">
        Overnight hours look cleanest on average, but extra load then is met by higher-emitting generation. The gap held in 2025 but was smaller than in training.
      </p>
    </Reveal>
  )
}

function Stat({ label, e, sub, ok }: { label: string; e?: Estimate; sub?: string; ok: boolean }) {
  return (
    <div className={`border-t pt-4 ${ok ? 'border-ink' : 'border-dashed border-neutral'}`}>
      <div className="eyebrow">{label}</div>
      {e && <>
        <div className="display mt-3 text-6xl sm:text-7xl"><Counter value={e.value} /></div>
        <div className="mt-1 text-sm text-ink-2 tabular">95% CI {fmt(e.ci_low_95)} to {fmt(e.ci_high_95)}</div>
      </>}
      {sub && <div className="mt-1 text-sm text-ink-2">{sub}</div>}
    </div>
  )
}

export default function BAPage() {
  const { code = 'MISO' } = useParams()
  const ba = code.toUpperCase()
  const [month, setMonth] = useState(7)
  const [playing, setPlaying] = useState(false)
  const { data: f, error } = useApi(() => api.findings(ba), [ba])
  const { data: mef, error: mefErr } = useApi(() => api.mef(ba, month), [ba, month])
  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setMonth((m) => (m % 12) + 1), 1600)
    return () => clearInterval(id)
  }, [playing])
  const next = ORDER[(ORDER.indexOf(ba) + 1) % ORDER.length]

  if (error) return <div className="px-4 pt-32 sm:px-8"><ErrorBox error={error} /></div>
  if (!f) return <div className="px-4 pt-32 sm:px-8"><Spinner /></div>
  const v = f.validation
  const ok = v.scheduling_recommendation_validated

  return (
    <div>
      <section className="px-4 pb-16 pt-28 sm:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="eyebrow">Region {String(ORDER.indexOf(ba) + 1).padStart(2, '0')} / 03 · {v.ba_code}</p>
          <StatusBadge validated={ok} />
        </div>
        <h1 className="display mt-6 text-[30vw] leading-[0.8] sm:text-[24vw]">
          <SplitLines immediate delay={0.3} lines={[BA_LABEL[ba] ?? ba]} />
        </h1>
        <div className="mt-10 grid gap-10 md:grid-cols-[1fr_1.4fr]">
          <Reveal>
            <p className="text-2xl font-medium leading-snug tracking-tight sm:text-3xl">
              {ok ? 'Scheduling by the marginal factor beat scheduling by average — on data the method never saw.' : 'The marginal-vs-average saving could not be told apart from zero on held-out data.'}
            </p>
          </Reveal>
          <Reveal delay={0.1}><Callout kind={ok ? 'good' : 'neutral'} title={ok ? 'Scheduling recommendation validated' : 'No validated scheduling recommendation'}>{v.summary}</Callout></Reveal>
        </div>
      </section>

      <section className={`mx-4 rounded-3xl p-6 sm:mx-8 sm:p-10 ${ok ? 'theme-dark' : 'border border-dashed border-neutral/60 bg-surface'}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-2xl font-semibold tracking-tight">Realised saving from marginal scheduling</h2>
          <StatusBadge validated={ok} size="sm" />
        </div>
        <p className="text-sm text-ink-2">kg CO₂ avoided per MWh shifted, measured on held-out data the method never saw</p>
        <div className={`mt-10 grid gap-8 sm:grid-cols-3 ${ok ? '' : 'opacity-85'}`}>
          <Stat label="2025 (decision)" e={v.realised_gap_2025} ok={ok} />
          <Stat label="2026 YTD (second check)" e={v.realised_gap_2026_ytd} ok={ok} />
          <div className={`border-t pt-4 ${ok ? 'border-ink' : 'border-dashed border-neutral'}`}>
            <div className="eyebrow">EDA prediction (in-sample)</div>
            <div className="display mt-3 text-6xl sm:text-7xl"><Counter value={v.eda_predicted_gap} /></div>
            <div className="mt-1 text-sm text-ink-2">predicted before the hold-out test</div>
          </div>
        </div>
        {!ok && <p className="mt-6 text-sm font-medium text-ink-2">The CI includes zero: these numbers are not a saving you can plan on.</p>}
        <div className="mt-6 space-y-3">
          {v.eda_estimate_not_confirmed && <Callout kind="neutral" title="EDA estimate not confirmed">{v.eda_estimate_not_confirmed}</Callout>}
          {v.data_caveats?.map((c) => <Callout key={c} kind="warning" title="2026 data caveat (applies to the 2026 YTD figure)">{c}</Callout>)}
        </div>
      </section>

      {f.overnight_check && <div className="px-4 pt-6 sm:px-8"><OvernightPanel o={f.overnight_check} /></div>}

      <section className="px-4 py-24 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="eyebrow mb-4">Hour by hour</p>
            <h2 className="display text-5xl sm:text-7xl">Marginal vs<br />average, <AnimatePresence mode="wait">
              <motion.span key={month} className="inline-block text-marginal" initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -30, opacity: 0 }} transition={{ duration: 0.4, ease: EASE }}>
                {MONTHS[month - 1]}
              </motion.span>
            </AnimatePresence></h2>
          </div>
          {!ok && <span className="rounded-full border border-dashed border-neutral/60 bg-neutral-bg px-3 py-1 text-xs font-medium text-ink-2">Descriptive only · not a validated scheduling signal</span>}
        </div>
        <div className="mt-8 flex flex-wrap items-center gap-2" role="group" aria-label="Month">
          <Magnetic>
            <button onClick={() => setPlaying(!playing)} aria-pressed={playing} className={`btn py-2! text-sm ${playing ? 'btn-solid' : ''}`} data-cursor={playing ? 'Pause' : 'Play'}>
              {playing ? '❚❚ Pause' : '▶ Play the year'}
            </button>
          </Magnetic>
          {MONTHS.map((m, i) => (
            <button key={m} onClick={() => { setPlaying(false); setMonth(i + 1) }} aria-pressed={month === i + 1}
              className={`relative h-9 w-12 rounded-full text-sm transition-colors ${month === i + 1 ? 'text-page' : 'text-ink-2 ring-1 ring-ring hover:text-ink hover:ring-ink'}`}>
              {month === i + 1 && <motion.span layoutId="month-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ type: 'spring', stiffness: 400, damping: 32 }} />}
              <span className="relative">{m}</span>
            </button>
          ))}
        </div>
        {playing && <div className="mt-3 h-[2px] w-full max-w-md bg-ink/10"><motion.div key={month} className="h-full origin-left bg-marginal" initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 1.6, ease: 'linear' }} /></div>}
        <div className="mt-6 rounded-3xl bg-surface p-4 ring-1 ring-ring sm:p-8">
          <p className="mb-4 text-sm text-ink-2">Typical {MONTHS[month - 1]} pattern, estimated on 2019–2024 (frozen). Band = 95% CI.</p>
          {mefErr ? <ErrorBox error={mefErr} /> : mef ? <MefChart rows={mef.rows} /> : <Spinner />}
        </div>
        <div className="mt-4"><Callout kind="info" title="Reading marginal factors">{f.usage.text}</Callout></div>
        <div className="mt-8"><Link to={`/schedule?ba=${ba}`} className="btn">Plan a load in {BA_LABEL[ba]} →</Link></div>
      </section>

      <Link to={`/ba/${next}`} data-cursor="Next" className="group block border-t border-ink/15 px-4 py-16 sm:px-8">
        <p className="eyebrow">Next region</p>
        <div className="mt-4 flex items-center justify-between">
          <span className="display text-[18vw] transition-transform duration-700 group-hover:translate-x-6 sm:text-[12vw]">{BA_LABEL[next]}</span>
          <span className="text-6xl transition-transform duration-700 group-hover:-rotate-45 sm:text-8xl">→</span>
        </div>
      </Link>
    </div>
  )
}
