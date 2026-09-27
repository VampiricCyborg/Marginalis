import { useState } from 'react'
import { Link } from 'react-router-dom'
import { GapChart } from '../components/GapChart'
import { Callout, Card, ErrorBox, EstimateLine, Spinner, StatusBadge } from '../components/ui'
import { api, BA_LABEL } from '../lib/api'
import { useApi } from '../lib/useApi'

export default function Overview() {
  const { data: bas, error } = useApi(api.bas, [])
  const [period, setPeriod] = useState<'2025' | '2026'>('2025')
  if (error) return <ErrorBox error={error} />
  if (!bas) return <Spinner />
  const ciso = bas.find((b) => b.ba_code === 'CISO')

  return (
    <div className="space-y-8">
      <header className="max-w-3xl space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">When you run flexible load matters. The obvious answer is often wrong.</h1>
        <p className="text-ink-2 leading-relaxed">
          Most “run it when the grid is green” advice uses <span className="font-medium text-average">average</span> CO₂
          intensity. The number that matters for a scheduling decision is the <span className="font-medium text-marginal">marginal</span>{' '}
          factor: how much CO₂ changes when one more MWh is added. We estimated both from EIA-930 data (2019–2024), then
          tested scheduling by each on held-out 2025 data, with the method pre-registered and frozen first.
        </p>
      </header>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Realised saving from marginal instead of average scheduling</h2>
            <p className="text-sm text-ink-2">kg CO₂ avoided per MWh of 4-hour flexible load shifted · point = estimate, bar = 95% CI · hold-out data only</p>
          </div>
          <div role="tablist" className="inline-flex rounded-lg bg-surface-2 p-1 text-sm">
            {(['2025', '2026'] as const).map((p) => (
              <button key={p} role="tab" aria-selected={period === p} onClick={() => setPeriod(p)}
                className={`rounded-md px-3 py-1 ${period === p ? 'bg-surface font-medium shadow-sm ring-1 ring-ring' : 'text-ink-2'}`}>
                {p === '2025' ? '2025 (decision)' : '2026 YTD (check)'}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4 overflow-x-auto"><div className="min-w-[560px]"><GapChart bas={bas} period={period} /></div></div>
        <p className="mt-2 text-xs text-ink-2">Decision rule (pre-registered): {bas[0].decision_rule}</p>
        {period === '2026' && ciso?.data_caveats?.map((c) => (
          <div className="mt-3" key={c}><Callout kind="warning" title="CAISO 2026 data caveat">{c}</Callout></div>
        ))}
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        {bas.map((b) => {
          const ok = b.scheduling_recommendation_validated
          return (
            <Link key={b.ba_code} to={`/ba/${b.ba_code}`}
              className={`group rounded-xl bg-surface p-5 ring-1 transition hover:shadow-md ${ok ? 'ring-good/50' : 'ring-ring border border-dashed border-neutral/50'}`}>
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">{BA_LABEL[b.ba_code]}</h3>
                <StatusBadge validated={ok} size="sm" />
              </div>
              <p className="mt-1 text-xs text-ink-2">{b.name}</p>
              <div className={`mt-4 ${ok ? '' : 'opacity-80'}`}>
                <div className="text-xs uppercase tracking-wide text-muted">Realised gap, 2025</div>
                <EstimateLine e={b.realised_gap_2025} />
              </div>
              <p className="mt-3 text-sm text-ink-2">
                {ok ? 'Scheduling recommendation validated.' : 'No validated scheduling recommendation: the effect was not distinguishable from zero.'}
              </p>
              <span className="mt-3 inline-block text-sm text-marginal group-hover:underline">Details →</span>
            </Link>
          )
        })}
      </div>

      <Card className="grid gap-4 md:grid-cols-2">
        <div>
          <h2 className="font-semibold">Plan a flexible load</h2>
          <p className="mt-1 text-sm text-ink-2">Compare the marginal-optimal and average-optimal window for a day. Only MISO carries a validated recommendation.</p>
          <Link to="/schedule" className="mt-3 inline-block rounded-md bg-marginal px-3 py-1.5 text-sm font-medium text-white">Open scheduler</Link>
        </div>
        <div>
          <h2 className="font-semibold">Ask the data</h2>
          <p className="mt-1 text-sm text-ink-2">A language-model interface that can only answer from these results. It carries its caveats, and it holds the line when pushed.</p>
          <Link to="/ask" className="mt-3 inline-block rounded-md bg-surface-2 px-3 py-1.5 text-sm font-medium ring-1 ring-ring">Try it</Link>
        </div>
      </Card>
    </div>
  )
}
