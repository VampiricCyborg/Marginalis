import { motion, useInView, useMotionValue, useSpring, useTransform } from 'motion/react'
import type { ReactNode } from 'react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { GapChart } from '../components/GapChart'
import { HeroCanvas } from '../components/HeroCanvas'
import { LoadWindow } from '../components/LoadWindow'
import { MethodScroll } from '../components/MethodScroll'
import { RegionList } from '../components/RegionList'
import { Callout, ErrorBox, Spinner, StatusBadge } from '../components/ui'
import type { BAStatus } from '../lib/api'
import { api, BA_LABEL, fmt } from '../lib/api'
import { Counter, EASE, Magnetic, Marquee, Parallax, Reveal, ScrubWords, SplitLines } from '../lib/motion'
import { useApi } from '../lib/useApi'

function WhenVisible({ children, minH = 200 }: { children: ReactNode; minH?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const seen = useInView(ref, { once: true, margin: '-15% 0px' })
  return <div ref={ref} style={{ minHeight: seen ? undefined : minH }}>{seen && children}</div>
}

function Hero() {
  return (
    <section className="relative flex min-h-[100svh] flex-col px-4 pb-8 pt-28 sm:px-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <motion.p className="eyebrow" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
          EIA-930 hourly · ERCOT / CAISO / MISO · 2019 → 2026
        </motion.p>
        <motion.p className="eyebrow hidden sm:block" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.7 }}>
          Pre-registered · hold-out tested
        </motion.p>
      </div>
      <h1 className="display relative z-10 mt-8 text-[17vw] sm:text-[12.5vw] lg:text-[10.5vw]">
        <SplitLines immediate delay={0.35} lines={[
          <>Green on <span className="text-average">average.</span></>,
          <>Dirty at the</>,
          <span className="flex items-center gap-[2vw]"><span className="text-marginal">margin?</span>
            <motion.span className="hidden h-[0.6em] w-[0.6em] shrink-0 rounded-full bg-ink sm:inline-block" animate={{ scale: [1, 0.85, 1] }} transition={{ duration: 2.4, repeat: Infinity }} />
          </span>,
        ]} />
      </h1>
      <motion.p className="relative z-10 mt-6 inline-flex w-fit flex-wrap items-center gap-2 rounded-full bg-page/80 px-3 py-1.5 text-sm backdrop-blur-sm"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.1 }}>
        <span className="font-medium text-good-text">✓ Confirmed out of sample in MISO.</span>
        <span className="text-ink-2">Not confirmed in ERCOT or CAISO.</span>
      </motion.p>
      <div className="pointer-events-auto absolute inset-x-0 bottom-0 h-[55%] opacity-90"><HeroCanvas /></div>
      <div className="relative z-10 mt-auto grid items-end gap-8 pt-10 md:grid-cols-[1fr_auto]">
        <motion.p className="max-w-md rounded-2xl bg-page/70 p-4 text-lg leading-snug backdrop-blur-sm sm:text-xl"
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1, duration: 1, ease: EASE }}>
          When you run flexible load matters. Most “run it when the grid is green” advice reads average intensity. We tested whether the marginal factor does better — and where it doesn't.
        </motion.p>
        <motion.div className="flex items-center gap-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.2 }}>
          <Magnetic><a href="#try" className="btn btn-solid" data-cursor="Try">Try the load window ↓</a></Magnetic>
          <div className="relative hidden h-24 w-24 sm:block" aria-hidden>
            <svg className="spin-slow absolute inset-0" viewBox="0 0 100 100">
              <defs><path id="sc" d="M50 50 m-38 0 a38 38 0 1 1 76 0 a38 38 0 1 1 -76 0" /></defs>
              <text fontSize="9" letterSpacing="3.4" fill="var(--ink)" fontFamily="var(--font-mono)"><textPath href="#sc">SCROLL · SCROLL · SCROLL · SCROLL · </textPath></text>
            </svg>
            <motion.span className="absolute inset-0 flex items-center justify-center text-xl" animate={{ y: [0, 6, 0] }} transition={{ duration: 1.6, repeat: Infinity }}>↓</motion.span>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

function TiltCard({ children, to, dark = false }: { children: ReactNode; to: string; dark?: boolean }) {
  const mx = useMotionValue(0.5), my = useMotionValue(0.5)
  const rx = useSpring(useTransform(my, [0, 1], [7, -7]), { stiffness: 200, damping: 20 })
  const ry = useSpring(useTransform(mx, [0, 1], [-9, 9]), { stiffness: 200, damping: 20 })
  const gx = useTransform(mx, (v) => `${v * 100}%`), gy = useTransform(my, (v) => `${v * 100}%`)
  const bg = useTransform([gx, gy], ([a, b]) => `radial-gradient(500px circle at ${a} ${b}, rgba(74,144,232,0.28), transparent 45%)`)
  return (
    <motion.div style={{ rotateX: rx, rotateY: ry, transformPerspective: 900 }} className="h-full"
      onPointerMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); mx.set((e.clientX - r.left) / r.width); my.set((e.clientY - r.top) / r.height) }}
      onPointerLeave={() => { mx.set(0.5); my.set(0.5) }}>
      <Link to={to} data-cursor="Open" className={`group relative flex h-full min-h-[340px] flex-col justify-between overflow-hidden rounded-3xl p-8 ${dark ? 'theme-dark' : 'bg-surface ring-1 ring-ring'}`}>
        <motion.span aria-hidden className="pointer-events-none absolute inset-0" style={{ background: bg }} />
        {children}
      </Link>
    </motion.div>
  )
}

function StatBlock({ b, i }: { b: BAStatus; i: number }) {
  const ok = b.scheduling_recommendation_validated
  const e = b.realised_gap_2025
  return (
    <Reveal delay={i * 0.1} className={`flex flex-col justify-between rounded-3xl p-6 ring-1 sm:p-8 ${ok ? 'ring-good/60' : 'ring-ring border border-dashed border-neutral/50'}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xl font-semibold">{BA_LABEL[b.ba_code]}</span>
        <StatusBadge validated={ok} size="sm" />
      </div>
      <div className={`mt-10 ${ok ? '' : 'opacity-80'}`}>
        <div className={`display ${ok ? 'text-7xl sm:text-8xl' : 'text-5xl text-ink-2 sm:text-6xl'}`}><Counter value={e.value} /></div>
        <p className="mt-2 text-sm text-ink-2">{ok ? 'kg CO₂ avoided per MWh shifted · 2025 hold-out'
          : 'estimated gap, kg CO₂/MWh shifted · 2025 hold-out · not distinguishable from zero'}</p>
        {/* CI strip: where the interval sits relative to 0 and the 50 threshold */}
        <CiStrip lo={e.ci_low_95} hi={e.ci_high_95} v={e.value} ok={ok} />
        <p className="mt-2 text-xs text-ink-2 tabular">95% CI {fmt(e.ci_low_95)} to {fmt(e.ci_high_95)}{e.ci_low_95 <= 0 && ' — includes zero'}</p>
      </div>
    </Reveal>
  )
}

function CiStrip({ lo, hi, v, ok }: { lo: number; hi: number; v: number; ok: boolean }) {
  const mn = -150, mx = 500
  const p = (n: number) => `${((n - mn) / (mx - mn)) * 100}%`
  return (
    <div className="relative mt-5 h-6" aria-hidden>
      <div className="absolute inset-x-0 top-1/2 h-px bg-grid" />
      <div className="absolute top-0 h-full w-px bg-ink-2" style={{ left: p(0) }} />
      <span className="absolute -top-4 -translate-x-1/2 font-mono text-[10px] text-muted" style={{ left: p(0) }}>0</span>
      <motion.div className={`absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full ${ok ? 'bg-good' : 'bg-neutral'}`}
        initial={{ left: p(v), right: `calc(100% - ${p(v)})` }} whileInView={{ left: p(lo), right: `calc(100% - ${p(hi)})` }}
        viewport={{ once: true }} transition={{ duration: 1.4, ease: EASE, delay: 0.3 }} />
      <motion.div className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 ${ok ? 'border-good bg-good' : 'border-neutral bg-page'}`}
        style={{ left: p(v) }} initial={{ scale: 0 }} whileInView={{ scale: 1 }} viewport={{ once: true }} />
    </div>
  )
}

export default function Overview() {
  const { data: bas, error } = useApi(api.bas, [])
  const [period, setPeriod] = useState<'2025' | '2026'>('2025')
  const ciso = bas?.find((b) => b.ba_code === 'CISO')
  const ordered = bas ? ['MISO', 'ERCO', 'CISO'].map((c) => bas.find((b) => b.ba_code === c)!).filter(Boolean) : []

  return (
    <div>
      <Hero />

      <Marquee speed={45} className="border-y border-ink/15 py-4">
        {['Marginal', 'Average', 'Marginal', 'Average'].map((t, i) => (
          <span key={i} className={`display mx-8 flex items-center gap-16 text-6xl sm:text-8xl ${t === 'Marginal' ? 'text-marginal' : 'text-transparent [-webkit-text-stroke:1.5px_var(--average)]'}`}>
            {t} <span className="text-ink">≠</span>
          </span>
        ))}
      </Marquee>

      <section className="px-4 py-28 sm:px-8 sm:py-40">
        <p className="eyebrow mb-8">The idea</p>
        <ScrubWords className="max-w-6xl text-3xl font-medium leading-[1.15] tracking-tight sm:text-5xl lg:text-6xl"
          text="Average intensity tells you how clean the grid already is. The marginal factor tells you what happens when you add one more MWh — which generation ramps up to serve it. For a scheduling decision, only the second one counts." />
      </section>

      <section id="try" className="scroll-mt-20 px-4 pb-28 sm:px-8">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-6">
          <h2 className="display text-6xl sm:text-8xl"><SplitLines lines={['Drag the load.', <span className="text-ink-2">Watch the carbon.</span>]} /></h2>
          <Reveal className="max-w-sm text-ink-2">Pick a region and month, then drag the dashed window across a typical day — or snap it to where each measure says to run.</Reveal>
        </div>
        {bas ? <LoadWindow bas={bas} /> : error ? <ErrorBox error={error} /> : <Spinner />}
      </section>

      <section className="theme-dark rounded-t-[2.5rem] px-4 py-24 sm:px-8 sm:py-32">
        <div className="mb-14 grid gap-6 md:grid-cols-2 md:items-end">
          <div>
            <p className="eyebrow mb-6">What held up out of sample</p>
            <h2 className="display text-6xl sm:text-8xl"><SplitLines lines={['One grid', 'passed.', <span className="text-ink-2">Two didn't.</span>]} /></h2>
          </div>
          <Reveal className="max-w-md text-lg text-ink-2 md:justify-self-end">
            We froze the method, then scheduled a 4-hour load by marginal instead of average on 2025 data the model never saw. Here's what that shift would have avoided, estimated from the held-out data.
          </Reveal>
        </div>
        {error != null && <ErrorBox error={error} />}
        {!bas && !error && <Spinner />}
        {bas && (
          <>
            <div className="grid gap-4 md:grid-cols-3">{ordered.map((b, i) => <StatBlock key={b.ba_code} b={b} i={i} />)}</div>
            <Reveal className="mt-6 rounded-3xl bg-surface p-5 ring-1 ring-ring sm:p-8">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-xl font-semibold">Realised saving, marginal vs average scheduling</h3>
                  <p className="text-sm text-ink-2">kg CO₂ avoided per MWh of 4-hour flexible load shifted · point = estimate, bar = 95% CI · hold-out data only</p>
                </div>
                <div role="tablist" className="relative inline-flex rounded-full bg-surface-2 p-1 text-sm">
                  {(['2025', '2026'] as const).map((p) => (
                    <button key={p} role="tab" aria-selected={period === p} onClick={() => setPeriod(p)}
                      className={`relative rounded-full px-4 py-1.5 ${period === p ? 'font-medium text-page' : 'text-ink-2 hover:text-ink'}`}>
                      {period === p && <motion.span layoutId="period-pill" className="absolute inset-0 rounded-full bg-ink" />}
                      <span className="relative">{p === '2025' ? '2025 (decision)' : '2026 YTD (check)'}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="mt-6 overflow-x-auto" data-lenis-prevent-horizontal><div className="min-w-[560px]"><WhenVisible minH={260}><GapChart bas={bas} period={period} /></WhenVisible></div></div>
              <p className="mt-2 text-xs text-ink-2">Decision rule (pre-registered): {bas[0].decision_rule}</p>
              {period === '2026' && ciso?.data_caveats?.map((c) => (
                <div className="mt-3" key={c}><Callout kind="warning" title="CAISO 2026 data caveat">{c}</Callout></div>
              ))}
            </Reveal>
          </>
        )}
      </section>

      <section className="px-4 py-24 sm:px-8 sm:py-32">
        <div className="mb-10 flex items-end justify-between">
          <h2 className="display text-6xl sm:text-8xl">Regions</h2>
          <p className="eyebrow">(03)</p>
        </div>
        {bas && <RegionList bas={bas} />}
      </section>

      <MethodScroll />

      <section className="grid gap-4 px-4 py-24 sm:px-8 md:grid-cols-2">
        <Parallax offset={30}>
          <TiltCard to="/schedule">
            <p className="eyebrow">01 · Tool</p>
            <div>
              <h3 className="display text-6xl sm:text-7xl">Plan a<br />flexible load</h3>
              <p className="mt-4 max-w-sm text-ink-2">Compare the marginal-optimal and average-optimal window for any day. Only MISO carries a validated recommendation.</p>
              <span className="btn mt-6">Open scheduler →</span>
            </div>
          </TiltCard>
        </Parallax>
        <Parallax offset={60}>
          <TiltCard to="/ask" dark>
            <p className="eyebrow">02 · Interface</p>
            <div>
              <h3 className="display text-6xl sm:text-7xl">Ask the<br /><span className="text-marginal">data</span></h3>
              <p className="mt-4 max-w-sm text-ink-2">A language model that can only answer from these results. It carries its caveats and holds the line when pushed.</p>
              <span className="btn mt-6">Try it →</span>
            </div>
          </TiltCard>
        </Parallax>
      </section>
    </div>
  )
}
