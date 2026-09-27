import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react'
import { useEffect, useRef, useState } from 'react'

const STEPS = [
  { k: 'Ingest', t: 'Hourly EIA-930 demand, generation by fuel and interchange for ERCOT, CAISO and MISO, plus weather for four load centres per region.', icon: 'ingest' },
  { k: 'Clean', t: 'Stored in UTC, local time derived in the database. Gaps, spikes and reporting breaks flagged in a data-quality report before any modelling.', icon: 'clean' },
  { k: 'Estimate', t: 'First-difference regression of ΔCO₂ on Δdemand within month × hour strata. Two emissions series checked against each other.', icon: 'estimate' },
  { k: 'Freeze', t: 'Train on 2019-07 → 2024-12. The method and the decision rule are pre-registered and frozen before any hold-out data is read.', icon: 'freeze' },
  { k: 'Test', t: 'Schedule a 4-hour load by marginal vs by average on held-out 2025 data, then again on 2026 YTD. Count what was actually avoided.', icon: 'test' },
  { k: 'Serve', t: 'A read-only API serves the frozen results. The Ask interface can only quote them, with their confidence intervals and caveats attached by code.', icon: 'serve' },
]

function Icon({ kind }: { kind: string }) {
  const reduce = useReducedMotion()
  const draw = reduce ? { initial: false as const, transition: {} } : { initial: { pathLength: 0 }, whileInView: { pathLength: 1 }, viewport: { once: false }, transition: { duration: 1.4, ease: 'easeInOut' as const } }
  const s = { fill: 'none', stroke: 'currentColor', strokeWidth: 3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  switch (kind) {
    case 'ingest': return <svg viewBox="0 0 80 80" className="h-20 w-20">{[16, 32, 48, 64].map((x, i) => <motion.path key={x} d={`M${x} 10 V70`} {...s} {...draw} transition={{ ...draw.transition, delay: i * 0.15 }} />)}<motion.path d="M8 70 H72" {...s} {...draw} /></svg>
    case 'clean': return <svg viewBox="0 0 80 80" className="h-20 w-20"><motion.path d="M8 50 L20 40 L28 62 L36 20 L44 46 L56 38 L72 42" {...s} opacity={0.3} {...draw} /><motion.path d="M8 48 L20 42 L32 44 L44 40 L56 38 L72 40" {...s} {...draw} transition={{ ...draw.transition, delay: 0.5 }} /></svg>
    case 'estimate': return <svg viewBox="0 0 80 80" className="h-20 w-20">{[[14, 60], [24, 50], [30, 54], [40, 40], [48, 36], [56, 30], [66, 20]].map(([x, y], i) => <motion.circle key={i} cx={x} cy={y} r="3.5" fill="currentColor" initial={{ scale: 0 }} whileInView={{ scale: 1 }} transition={{ delay: i * 0.08 }} />)}<motion.path d="M8 66 L72 14" {...s} {...draw} transition={{ ...draw.transition, delay: 0.6 }} /></svg>
    case 'freeze': return <svg viewBox="0 0 80 80" className="h-20 w-20"><motion.rect x="16" y="34" width="48" height="36" rx="6" {...s} {...draw} /><motion.path d="M26 34 V24 a14 14 0 0 1 28 0 V34" {...s} {...draw} transition={{ ...draw.transition, delay: 0.4 }} /></svg>
    case 'test': return <svg viewBox="0 0 80 80" className="h-20 w-20"><motion.path d="M12 40 H68" {...s} opacity={0.3} {...draw} /><motion.path d="M24 40 H56 M24 32 V48 M56 32 V48" {...s} {...draw} /><motion.circle cx="40" cy="40" r="6" fill="currentColor" initial={{ scale: 0 }} whileInView={{ scale: 1 }} transition={{ delay: 0.8 }} /></svg>
    default: return <svg viewBox="0 0 80 80" className="h-20 w-20"><motion.path d="M12 58 H68 M18 58 V30 L40 16 L62 30 V58" {...s} {...draw} /><motion.path d="M32 58 V40 H48 V58" {...s} {...draw} transition={{ ...draw.transition, delay: 0.5 }} /></svg>
  }
}

/* Pinned section that scrolls horizontally through the method */
export function MethodScroll() {
  const ref = useRef<HTMLDivElement>(null)
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] })
  const track = useRef<HTMLDivElement>(null)
  const [dist, setDist] = useState(0)
  useEffect(() => {
    const m = () => { const t = track.current; if (t) setDist(Math.max(0, t.scrollWidth - window.innerWidth + 32)) }
    m(); window.addEventListener('resize', m); return () => window.removeEventListener('resize', m)
  }, [reduce])
  const x = useTransform(scrollYProgress, [0.05, 0.95], [0, -dist])
  const bar = useTransform(scrollYProgress, [0, 1], [0, 1])

  if (reduce) {
    return (
      <div className="grid gap-4 px-4 sm:grid-cols-2 sm:px-8 lg:grid-cols-3">
        {STEPS.map((s, i) => <Card key={s.k} s={s} i={i} />)}
      </div>
    )
  }
  return (
    <div ref={ref} style={{ height: `${STEPS.length * 70}vh` }} className="relative">
      <div className="sticky top-0 flex h-screen flex-col justify-center overflow-hidden">
        <div className="mb-8 flex items-end justify-between px-4 sm:px-8">
          <h2 className="display text-5xl sm:text-7xl">How it's<br />made</h2>
          <div className="hidden w-64 sm:block">
            <p className="eyebrow mb-2">Scroll</p>
            <div className="h-[2px] w-full bg-ink/10"><motion.div className="h-full origin-left bg-ink" style={{ scaleX: bar }} /></div>
          </div>
        </div>
        <motion.div ref={track} style={{ x }} className="flex gap-4 pl-4 sm:gap-6 sm:pl-8">
          {STEPS.map((s, i) => <Card key={s.k} s={s} i={i} />)}
        </motion.div>
      </div>
    </div>
  )
}

function Card({ s, i }: { s: typeof STEPS[number]; i: number }) {
  const dark = i % 2 === 1
  return (
    <article className={`flex h-[58vh] min-h-[360px] w-[80vw] shrink-0 flex-col justify-between rounded-3xl p-6 sm:w-[46vw] sm:p-8 lg:w-[30vw] ${dark ? 'theme-dark' : 'bg-surface ring-1 ring-ring'}`}>
      <div className="flex items-start justify-between">
        <span className="font-mono text-sm text-muted">0{i + 1} / 0{STEPS.length}</span>
        <span className={i === 4 ? 'text-marginal' : 'text-ink'}><Icon kind={s.icon} /></span>
      </div>
      <div>
        <h3 className="display text-5xl sm:text-6xl">{s.k}</h3>
        <p className="mt-4 max-w-md leading-relaxed text-ink-2">{s.t}</p>
      </div>
    </article>
  )
}
