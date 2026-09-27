/* Motion primitives: smooth scroll, reveals, counters, magnetic, marquee.
   Everything respects prefers-reduced-motion. */
import Lenis from 'lenis'
import {
  animate, motion, useAnimationFrame, useInView, useMotionValue, useReducedMotion, useScroll, useSpring,
  useTransform, useVelocity,
} from 'motion/react'
import type { ReactNode } from 'react'
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

export const EASE = [0.19, 1, 0.22, 1] as const

/* ---------- Smooth scroll (Lenis) ---------- */
const LenisCtx = createContext<Lenis | null>(null)
export const useLenis = () => useContext(LenisCtx)

export function SmoothScroll({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion()
  const [lenis, setLenis] = useState<Lenis | null>(null)
  const { pathname } = useLocation()
  useEffect(() => {
    if (reduce) return
    const l = new Lenis({ lerp: 0.09, wheelMultiplier: 1 })
    let id = 0
    const raf = (t: number) => { l.raf(t); id = requestAnimationFrame(raf) }
    id = requestAnimationFrame(raf)
    setLenis(l)
    return () => { cancelAnimationFrame(id); l.destroy(); setLenis(null) }
  }, [reduce])
  useEffect(() => {
    if (lenis) lenis.scrollTo(0, { immediate: true })
    else window.scrollTo(0, 0)
  }, [pathname, lenis])
  return <LenisCtx.Provider value={lenis}>{children}</LenisCtx.Provider>
}

/* ---------- Reveal: fades + lifts a block when it enters the viewport ---------- */
export function Reveal({ children, delay = 0, y = 40, className = '', as = 'div' }:
  { children: ReactNode; delay?: number; y?: number; className?: string; as?: 'div' | 'section' | 'li' }) {
  const reduce = useReducedMotion()
  const M = motion[as]
  return (
    <M className={className} initial={reduce ? false : { opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-10% 0px' }} transition={{ duration: 1.1, ease: EASE, delay }}>
      {children}
    </M>
  )
}

/* ---------- SplitText: each line slides up from behind a mask ---------- */
export function SplitLines({ lines, className = '', delay = 0, stagger = 0.08, immediate = false }:
  { lines: ReactNode[]; className?: string; delay?: number; stagger?: number; immediate?: boolean }) {
  const reduce = useReducedMotion()
  // Observe the (unclipped) wrapper: the lines themselves start hidden behind their masks.
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -8% 0px' })
  const show = immediate || inView
  return (
    <span ref={ref} className={`block ${className}`}>
      {lines.map((l, i) => (
        <span key={i} className="line-mask">
          <motion.span className="block" initial={reduce ? false : { y: '110%', rotate: 2 }}
            animate={show ? { y: '0%', rotate: 0 } : undefined}
            transition={{ duration: 1.2, ease: EASE, delay: delay + i * stagger }}>
            {l}
          </motion.span>
        </span>
      ))}
    </span>
  )
}

/* Word-by-word opacity scrub tied to scroll — for the big statement paragraph */
export function ScrubWords({ text, className = '' }: { text: string; className?: string }) {
  const ref = useRef<HTMLParagraphElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 85%', 'end 45%'] })
  const words = text.split(' ')
  return (
    <p ref={ref} className={className}>
      {words.map((w, i) => <Word key={i} p={scrollYProgress} range={[i / words.length, (i + 1) / words.length]}>{w}</Word>)}
    </p>
  )
}
function Word({ children, p, range }: { children: string; p: ReturnType<typeof useScroll>['scrollYProgress']; range: [number, number] }) {
  const o = useTransform(p, range, [0.14, 1])
  const reduce = useReducedMotion()
  const hl = /marginal/i.test(children) ? 'text-marginal' : /average/i.test(children) ? 'text-average' : ''
  return <motion.span className={hl} style={{ opacity: reduce ? 1 : o }}>{children} </motion.span>
}

/* ---------- Counter: counts up to a value when in view ---------- */
export function Counter({ value, decimals = 0, className = '', prefix = '' }: { value: number; decimals?: number; className?: string; prefix?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-10% 0px' })
  const reduce = useReducedMotion()
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const f = (n: number) => prefix + n.toLocaleString('en-US', { maximumFractionDigits: decimals, minimumFractionDigits: decimals })
    if (reduce) { el.textContent = f(value); return }
    if (!inView) { el.textContent = f(0); return }
    const c = animate(0, value, { duration: 1.8, ease: EASE, onUpdate: (v) => { el.textContent = f(v) } })
    return () => c.stop()
  }, [inView, value, decimals, reduce, prefix])
  return <span ref={ref} className={`tabular ${className}`} />
}

/* ---------- Magnetic: element leans toward the pointer ---------- */
export function Magnetic({ children, strength = 0.35, className = '' }: { children: ReactNode; strength?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const x = useSpring(0, { stiffness: 200, damping: 15 }), y = useSpring(0, { stiffness: 200, damping: 15 })
  return (
    <motion.div ref={ref} className={`inline-block ${className}`} style={{ x, y }}
      onPointerMove={(e) => {
        if (e.pointerType !== 'mouse') return
        const r = ref.current!.getBoundingClientRect()
        x.set((e.clientX - r.left - r.width / 2) * strength); y.set((e.clientY - r.top - r.height / 2) * strength)
      }}
      onPointerLeave={() => { x.set(0); y.set(0) }}>
      {children}
    </motion.div>
  )
}

/* ---------- Marquee: infinite ticker; speeds up and flips with scroll velocity ---------- */
export function Marquee({ children, speed = 40, className = '' }: { children: ReactNode; speed?: number; className?: string }) {
  const reduce = useReducedMotion()
  const base = useMotionValue(0)
  const { scrollY } = useScroll()
  const vel = useSpring(useVelocity(scrollY), { damping: 50, stiffness: 400 })
  const factor = useTransform(vel, [-2000, 0, 2000], [-4, 1, 4], { clamp: false })
  const dir = useRef(1)
  const x = useTransform(base, (v) => `${((v % 50) + 50) % 50 - 50}%`)
  useAnimationFrame((_, dt) => {
    if (reduce) return
    const f = factor.get()
    if (f < 0) dir.current = -1; else if (f > 0) dir.current = 1
    base.set(base.get() + dir.current * speed * 0.0007 * (dt / 16) * (1 + Math.abs(f)))
  })
  return (
    <div className={`overflow-hidden whitespace-nowrap ${className}`} aria-hidden>
      <motion.div className="inline-flex" style={{ x }}>
        <span className="inline-flex shrink-0">{children}</span>
        <span className="inline-flex shrink-0">{children}</span>
      </motion.div>
    </div>
  )
}

/* ---------- Scroll progress bar at the top ---------- */
export function ScrollProgress() {
  const { scrollYProgress } = useScroll()
  const scaleX = useSpring(scrollYProgress, { stiffness: 120, damping: 30 })
  return <motion.div aria-hidden className="fixed inset-x-0 top-0 z-[70] h-[3px] origin-left bg-marginal" style={{ scaleX }} />
}

/* ---------- Parallax wrapper ---------- */
export function Parallax({ children, offset = 80, className = '' }: { children: ReactNode; offset?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] })
  const reduce = useReducedMotion()
  const y = useTransform(scrollYProgress, [0, 1], reduce ? [0, 0] : [offset, -offset])
  return <motion.div ref={ref} style={{ y }} className={className}>{children}</motion.div>
}
