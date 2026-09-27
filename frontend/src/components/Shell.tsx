import { AnimatePresence, motion, useMotionValueEvent, useReducedMotion, useScroll } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { EASE, Magnetic, Marquee, useLenis } from '../lib/motion'

export const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/ba/MISO', label: 'MISO' },
  { to: '/ba/ERCO', label: 'ERCOT' },
  { to: '/ba/CISO', label: 'CAISO' },
  { to: '/schedule', label: 'Scheduler' },
  { to: '/ask', label: 'Ask' },
]

/* Animated logo mark: the favicon's curve, redrawn on a loop */
export function LogoMark({ size = 26 }: { size?: number }) {
  const reduce = useReducedMotion()
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--ink)" />
      <motion.path d="M6 22c4 0 5-12 10-12s6 8 10 8" fill="none" stroke="var(--marginal)" strokeWidth="2.8" strokeLinecap="round"
        initial={{ pathLength: reduce ? 1 : 0 }} animate={{ pathLength: 1 }}
        transition={reduce ? undefined : { duration: 2.4, ease: 'easeInOut', repeat: Infinity, repeatType: 'reverse', repeatDelay: 1.2 }} />
      <path d="M6 25.5h20" stroke="var(--average)" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}

function useClock(tz: string) {
  const fmt = () => new Date().toLocaleTimeString('en-GB', { timeZone: tz, hour: '2-digit', minute: '2-digit' })
  const [t, setT] = useState(fmt)
  useEffect(() => { const id = setInterval(() => setT(fmt()), 15000); return () => clearInterval(id) })
  return t
}

function Clocks({ className = '' }: { className?: string }) {
  const ct = useClock('America/Chicago'), pt = useClock('America/Los_Angeles')
  return (
    <div className={`font-mono text-[11px] uppercase tracking-wider ${className}`}>
      <span className="mr-4"><span className="pulse-dot mr-2 text-good align-middle" />MISO · ERCOT {ct} CT</span>
      <span>CAISO {pt} PT</span>
    </div>
  )
}

export function Nav() {
  const [open, setOpen] = useState(false)
  const [hidden, setHidden] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const { scrollY } = useScroll()
  const { pathname } = useLocation()
  const lenis = useLenis()
  useMotionValueEvent(scrollY, 'change', (v) => {
    const prev = scrollY.getPrevious() ?? 0
    setHidden(v > prev && v > 200 && !open)
    setScrolled(v > 30)
  })
  useEffect(() => { setOpen(false) }, [pathname])
  useEffect(() => { if (open) lenis?.stop(); else lenis?.start() }, [open, lenis])
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [])

  return (
    <>
      <motion.header className="fixed inset-x-0 top-0 z-50" animate={{ y: hidden ? '-110%' : '0%' }} transition={{ duration: 0.6, ease: EASE }}>
        <div className={`mx-auto flex items-center justify-between gap-4 px-4 py-3 transition-colors duration-500 sm:px-8 ${scrolled && !open ? 'bg-page/80 backdrop-blur-md' : ''}`}>
          <Link to="/" className="flex items-center gap-2.5 text-lg font-semibold tracking-tight" data-cursor="Home">
            <LogoMark /> Marginalis
          </Link>
          <nav className="hidden items-center gap-6 text-[15px] lg:flex" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `link-draw ${isActive ? 'active' : 'text-ink-2 hover:text-ink'}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <Magnetic>
            <button onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="menu"
              className={`btn py-2.5! text-sm ${open ? 'border-white! text-white!' : ''}`}>
              <span className="relative block h-2.5 w-4">
                <motion.span className="absolute left-0 top-0 h-[1.5px] w-full bg-current" animate={open ? { rotate: 45, y: 4.5 } : { rotate: 0, y: 0 }} />
                <motion.span className="absolute bottom-0 left-0 h-[1.5px] w-full bg-current" animate={open ? { rotate: -45, y: -4.5 } : { rotate: 0, y: 0 }} />
              </span>
              {open ? 'Close' : 'Menu'}
            </button>
          </Magnetic>
        </div>
      </motion.header>

      <AnimatePresence>
        {open && (
          <motion.div id="menu" className="theme-dark fixed inset-0 z-40 flex flex-col overflow-hidden" data-lenis-prevent
            initial={{ clipPath: 'inset(0 0 100% 0)' }} animate={{ clipPath: 'inset(0 0 0% 0)' }} exit={{ clipPath: 'inset(100% 0 0 0)' }}
            transition={{ duration: 0.9, ease: EASE }}>
            <div className="flex flex-1 flex-col justify-center px-4 pt-20 sm:px-8">
              <ul className="group/menu">
                {NAV.map((n, i) => (
                  <li key={n.to} className="border-b border-white/10">
                    <NavLink to={n.to} end={n.end} data-cursor="Go"
                      className={({ isActive }) => `group flex items-baseline gap-4 py-2 transition-all duration-500 group-hover/menu:opacity-40 hover:!opacity-100 hover:pl-6 ${isActive ? 'text-marginal' : ''}`}>
                      <span className="font-mono text-xs text-muted">0{i + 1}</span>
                      <span className="line-mask">
                        <motion.span className="display block text-[13vw] sm:text-[8vw] lg:text-[6.4vw]"
                          initial={{ y: '110%' }} animate={{ y: '0%' }} transition={{ duration: 1, ease: EASE, delay: 0.25 + i * 0.06 }}>
                          {n.label}
                        </motion.span>
                      </span>
                      <span className="ml-auto hidden text-3xl opacity-0 transition-all duration-500 group-hover:translate-x-0 group-hover:opacity-100 sm:block -translate-x-6">→</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-6 text-ink-2 sm:px-8">
              <Clocks />
              <a href="https://github.com/VampiricCyborg/Marginalis" target="_blank" rel="noreferrer" className="link-draw font-mono text-[11px] uppercase tracking-wider">Source on GitHub ↗</a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

export function Footer() {
  const lenis = useLenis()
  const onAsk = useLocation().pathname === '/ask'
  return (
    <footer className="theme-dark relative overflow-hidden pt-24">
      <Marquee speed={30} className="border-y border-white/10 py-5">
        {['Marginal ≠ Average', 'Pre-registered', 'Hold-out tested', 'EIA-930 hourly', 'ERCOT · CAISO · MISO'].map((t) => (
          <span key={t} className="display mx-6 flex items-center gap-12 text-5xl sm:text-7xl">
            {t}<span className="inline-block h-4 w-4 rounded-full bg-average" />
          </span>
        ))}
      </Marquee>
      <div className="grid gap-12 px-4 py-20 sm:px-8 md:grid-cols-[1.4fr_1fr]">
        <div>
          <p className="eyebrow mb-6">Got a flexible load?</p>
          <h2 className="display text-6xl sm:text-8xl">{onAsk ? <>Plan a<br /><span className="text-marginal">load.</span></> : <>Ask the<br /><span className="text-marginal">data.</span></>}</h2>
          <div className="mt-10 flex flex-wrap items-center gap-6">
            <Magnetic strength={0.5}>
              <Link to={onAsk ? '/schedule' : '/ask'} data-cursor={onAsk ? 'Plan' : 'Ask'}
                className="group relative flex h-36 w-36 items-center justify-center rounded-full bg-marginal text-center text-lg font-medium text-white transition-transform duration-500 hover:scale-110">
                <svg className="spin-slow absolute inset-0" viewBox="0 0 144 144" aria-hidden>
                  <defs><path id="circ" d="M72 72 m-58 0 a58 58 0 1 1 116 0 a58 58 0 1 1 -116 0" /></defs>
                  <text fontSize="10" letterSpacing="3" fill="#fff" fontFamily="var(--font-mono)"><textPath href="#circ">ASK · THE · DATA · GROUNDED · ANSWERS · </textPath></text>
                </svg>
                <span className="text-3xl transition-transform duration-500 group-hover:rotate-[-45deg]">→</span>
              </Link>
            </Magnetic>
            <Link to={onAsk ? '/' : '/schedule'} className="btn border-white/40!">{onAsk ? 'Back to overview' : 'Open the scheduler'}</Link>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-8 text-sm">
          <div>
            <p className="eyebrow mb-4">Explore</p>
            <ul className="space-y-2">{NAV.map((n) => <li key={n.to}><Link to={n.to} className="link-draw text-ink-2 hover:text-ink">{n.label}</Link></li>)}</ul>
          </div>
          <div>
            <p className="eyebrow mb-4">Elsewhere</p>
            <ul className="space-y-2">
              <li><a className="link-draw text-ink-2 hover:text-ink" href="https://github.com/VampiricCyborg/Marginalis" target="_blank" rel="noreferrer">GitHub ↗</a></li>
              <li><a className="link-draw text-ink-2 hover:text-ink" href="https://github.com/VampiricCyborg/Marginalis/blob/main/docs/preregistration.md" target="_blank" rel="noreferrer">Pre-registration ↗</a></li>
              <li><a className="link-draw text-ink-2 hover:text-ink" href="https://www.eia.gov/electricity/gridmonitor/" target="_blank" rel="noreferrer">EIA Grid Monitor ↗</a></li>
            </ul>
            <button onClick={() => (lenis ? lenis.scrollTo(0, { duration: 2 }) : window.scrollTo({ top: 0, behavior: 'smooth' }))}
              className="btn mt-8 border-white/40! py-2! text-xs" data-cursor="Up">Back to top ↑</button>
          </div>
        </div>
      </div>
      <p className="px-4 pb-4 text-xs text-muted sm:px-8">
        EIA-930 hourly data, 2019-07 to 2026-08. Estimates are frozen and pre-registered; see the repository for methods and limitations.
      </p>
      <div aria-hidden className="display select-none px-2 text-center text-[21vw] leading-[0.78] text-white/[0.06]">Marginalis</div>
      <Clocks className="absolute bottom-4 right-4 hidden text-muted sm:block sm:right-8" />
    </footer>
  )
}

/* First-visit preloader: counter + wave, then a curtain lift */
export function Preloader() {
  const reduce = useReducedMotion()
  const [show, setShow] = useState(() => {
    if (reduce) return false
    try { return !sessionStorage.getItem('mg-loaded') } catch { return true }
  })
  const [n, setN] = useState(0)
  useEffect(() => {
    if (!show) return
    let v = 0
    const id = setInterval(() => {
      v = Math.min(100, v + Math.ceil(Math.random() * 9))
      setN(v)
      if (v >= 100) {
        clearInterval(id)
        setTimeout(() => { setShow(false); try { sessionStorage.setItem('mg-loaded', '1') } catch { /* private mode */ } }, 350)
      }
    }, 45)
    return () => clearInterval(id)
  }, [show])
  return (
    <AnimatePresence>
      {show && (
        <motion.div className="theme-dark fixed inset-0 z-[90] flex flex-col justify-between p-4 sm:p-8"
          exit={{ y: '-100%' }} transition={{ duration: 1.1, ease: EASE }}>
          <div className="flex items-center gap-3 text-lg font-semibold"><LogoMark /> Marginalis</div>
          <svg viewBox="0 0 600 120" className="mx-auto w-full max-w-3xl" aria-hidden>
            <motion.path d="M0 90 C 80 90, 110 20, 200 30 S 330 100, 400 70 S 520 10, 600 40" fill="none" stroke="var(--marginal)" strokeWidth="3"
              initial={{ pathLength: 0 }} animate={{ pathLength: n / 100 }} transition={{ ease: 'linear', duration: 0.1 }} />
            <motion.path d="M0 60 C 100 55, 200 70, 300 62 S 500 55, 600 60" fill="none" stroke="var(--average)" strokeWidth="3"
              initial={{ pathLength: 0 }} animate={{ pathLength: n / 100 }} transition={{ ease: 'linear', duration: 0.1 }} />
          </svg>
          <div className="flex items-end justify-between">
            <p className="max-w-xs text-sm text-ink-2">Loading marginal and average CO₂ profiles for three US grids…</p>
            <span className="display tabular text-[22vw] sm:text-[14vw]">{n}</span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/* Route transition: page content eases in; a black panel wipes across */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const reduce = useReducedMotion()
  if (reduce) return <>{children}</>
  return (
    <>
      <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
        transition={{ duration: 0.9, ease: EASE, delay: 0.25 }}>
        {children}
      </motion.div>
      <motion.div aria-hidden className="pointer-events-none fixed inset-0 z-[80] origin-top bg-ink"
        initial={{ scaleY: 1 }} animate={{ scaleY: 0 }} exit={{ scaleY: 0 }}
        transition={{ duration: 0.8, ease: EASE }} style={{ originY: 0 }} />
    </>
  )
}
